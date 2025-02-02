from datetime import datetime
import json
import logging
import re
from titlecase import titlecase
from typing import Optional
from decimal import Decimal
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

class BillingDbCore:
    """
    Database handler for billing-related operations.
    """

    @classmethod
    def get_usage_history(cls, user_id):
        """
        Retrieve the history of Enhancifai executions and token consumption for a user.
        Returns amounts in dollars as floats rounded to two decimal places.
        """
        sql = schemafy("""
            SELECT 
                TO_CHAR(rl.log_timestamp, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS execution_time,
                rl.filename AS uploaded_file_name,
                r.source_type AS type,
                rl.num_rows_processed AS number_of_rows,
                rl.num_tokens AS total_tokens,
                mp.price AS cost_per_token,
                (rl.num_tokens * mp.price) AS total_cost
            FROM enhancifai.run_logs rl
            JOIN enhancifai.runs r ON rl.run_id = r.id
            JOIN enhancifai.model_pricing mp
                ON mp.model_name = rl.engine_model
                AND mp.year = EXTRACT(YEAR FROM rl.log_timestamp)
                AND mp.month = EXTRACT(MONTH FROM rl.log_timestamp)
            WHERE r.user_id = %s
            ORDER BY rl.log_timestamp DESC;
        """)
        data = (user_id,)
        raw_records = read_db.do('select', sql=sql, data=data) or []

        # Convert total_cost to dollars, rounded to two decimal places
        usage_history = []
        for record in raw_records:
            record['cost_per_token'] = float(Decimal(record['cost_per_token']).quantize(Decimal('0.0001')))
            record['total_cost'] = float((Decimal(record['total_cost'])).quantize(Decimal('0.01')))
            usage_history.append(record)

        return usage_history

    @classmethod
    def get_monthly_balance(cls, user_id):
        """
        Provide the current monthly balance for the user, including the total cost for the current month.
        Returns amounts in dollars as floats rounded to two decimal places.
        """
        sql = schemafy("""
            SELECT 
                TO_CHAR(DATE_TRUNC('month', NOW()), 'YYYY-MM') AS billing_month,
                SUM(rl.num_tokens * mp.price) AS total_monthly_cost
            FROM enhancifai.run_logs rl
            JOIN enhancifai.runs r ON rl.run_id = r.id
            JOIN enhancifai.model_pricing mp
                ON mp.model_name = rl.engine_model
                AND mp.year = EXTRACT(YEAR FROM rl.log_timestamp)
                AND mp.month = EXTRACT(MONTH FROM rl.log_timestamp)
            WHERE r.user_id = %s AND DATE_TRUNC('month', rl.log_timestamp) = DATE_TRUNC('month', NOW())
            GROUP BY billing_month;
        """)
        data = (user_id,)
        result = read_db.do('select_one', sql=sql, data=data)
        if result is None:
            return {
                "billing_month": datetime.now().strftime("%Y-%m"),
                "total_monthly_cost": 0.0
            }
        return {
            "billing_month": result['billing_month'],
            "total_monthly_cost": float(Decimal(result['total_monthly_cost']).quantize(Decimal('0.01')))
        }

    @classmethod
    def get_usage_by_model(cls, user_id, month=None, year=None):
        """
        Aggregate data by AI model, including tokens used from both Normal and Prompt Improver usages,
        price per token, and total cost for each model.
        """
        if month is not None and year is not None:
            if not (1 <= month <= 12):
                raise ValueError("Invalid month. Must be between 1 and 12.")
            current_year = datetime.now().year
            if not (2000 <= year <= current_year):
                raise ValueError("Invalid year.")
            date_filter = "AND (EXTRACT(MONTH FROM created_at) = %s AND EXTRACT(YEAR FROM created_at) = %s)"
            date_filter_rl = date_filter
            date_filter_pil = date_filter
        else:
            date_filter_rl = ""
            date_filter_pil = ""

        sql = schemafy(f"""
            WITH combined_logs AS (
                SELECT 
                    model AS engine_model, 
                    tokens, 
                    created_at AS log_timestamp
                FROM enhancifai.users_token_usage
                WHERE user_id = %s {date_filter_rl}

                UNION ALL

                SELECT 
                    model AS engine_model, 
                    tokens, 
                    created_at AS log_timestamp
                FROM enhancifai.users_token_usage_pi
                WHERE user_id = %s {date_filter_pil}
            )
            SELECT 
                cl.engine_model AS ai_model_name,
                SUM(cl.tokens) AS tokens_used,
                mp.price AS price_per_token, 
                SUM(cl.tokens * mp.price) AS total_cost
            FROM combined_logs cl
            JOIN enhancifai.model_pricing mp
                ON cl.engine_model = mp.model_name
                AND mp.year = EXTRACT(YEAR FROM cl.log_timestamp)
                AND mp.month = EXTRACT(MONTH FROM cl.log_timestamp)
            GROUP BY ai_model_name, mp.price;
        """)

        if month is not None and year is not None:
            data = (user_id, month, year, user_id, month, year)
        else:
            data = (user_id, user_id)

        num_placeholders = len(re.findall(r'%s', sql))
        if num_placeholders != len(data):
            raise ValueError(f"Number of placeholders ({num_placeholders}) does not match number of data elements ({len(data)}).")

        raw_records = read_db.do('select', sql=sql, data=data) or []

        usage_by_model = []
        for record in raw_records:
            record['price_per_token'] = float((Decimal(record['price_per_token']) * 1000).quantize(Decimal('0.000001')))
            record['total_cost'] = float(Decimal(record['total_cost']).quantize(Decimal('0.01')))
            usage_by_model.append(record)

        return usage_by_model

    @classmethod
    def _get_placeholder(cls, user_id):
        # Helper method to return the correct placeholder for user_id
        return '%s'


    @classmethod
    def create_invoice(cls, user_id, amount_cents, description, billing_period_start, billing_period_end, metadata=None):
        """
        Create an invoice and save it in the database.

        Args:
            user_id (int): The user's ID.
            amount_cents (int): The total amount in cents.
            description (str): Description of the invoice.
            billing_period_start (date): Start of the billing period.
            billing_period_end (date): End of the billing period.
            metadata (dict): Additional metadata including line items.

        Returns:
            dict: A dictionary containing the created invoice details or None if skipped.
        """
        try:
            # Validate amount
            if amount_cents <= 0:
                logging.info(f"Skipping invoice for user {user_id}: amount is zero or negative.")
                return None

            # Check if an invoice already exists for the period
            if cls.invoice_exists(user_id, billing_period_start, billing_period_end):
                logging.info(f"Skipping invoice for user {user_id}: invoice already exists for this period.")
                return None

            if metadata is None:
                metadata = {'description': description}
            else:
                # Ensure description is included if not already
                if 'description' not in metadata:
                    metadata['description'] = description

            sql = schemafy("""
                INSERT INTO enhancifai.stripe_invoices (
                    user_id, amount, status, created_at,
                    billing_period_start, billing_period_end, metadata
                ) VALUES (%s, %s, 'unpaid', NOW(), %s, %s, %s)
                RETURNING invoice_id, amount, status, created_at, billing_period_start, billing_period_end;
            """)
            data = (user_id, amount_cents, billing_period_start, billing_period_end, json.dumps(metadata))
            result = write_db.do('execute', sql=sql, data=data)
            return {
                'invoice_id': result['invoice_id'],
                'amount': Decimal(result['amount']).quantize(Decimal('0.01')),
                'status': result['status'],
                'created_at': result['created_at'],
                'billing_period_start': result['billing_period_start'],
                'billing_period_end': result['billing_period_end'],
            }

        except Exception as e:
            raise RuntimeError(f"Failed to create invoice for user {user_id}: {str(e)}")


    @classmethod
    def invoice_exists(cls, user_id, billing_period_start, billing_period_end):
        """
        Check if an invoice exists for a user and billing period.

        Args:
            user_id (int): The user's ID.
            billing_period_start (date): Start of the billing period.
            billing_period_end (date): End of the billing period.

        Returns:
            bool: True if an invoice exists, False otherwise.
        """
        try:
            sql = schemafy("""
                SELECT 1
                FROM enhancifai.stripe_invoices
                WHERE user_id = %s
                AND billing_period_start = %s
                AND billing_period_end = %s;
            """)
            data = (user_id, billing_period_start, billing_period_end)
            result = read_db.do('select_one', sql=sql, data=data)

            return result is not None  # If result is not None, invoice exists

        except Exception as e:
            raise RuntimeError(f"Error checking if invoice exists for user {user_id}: {str(e)}")

    @classmethod
    def get_invoice_history(cls, user_id):
        """
        Retrieve invoice data, including date, invoice number, invoice amount, payment date, status,
        billing period start and end, and metadata.
        Returns amounts in dollars as floats rounded to two decimal places.
        """
        sql = schemafy("""
            SELECT 
                TO_CHAR(si.created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS date,
                si.invoice_id,
                si.amount AS invoice_amount,
                TO_CHAR(si.paid_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS payment_date,
                si.status AS payment_status,
                TO_CHAR(si.billing_period_start, 'YYYY-MM-DD') AS billing_period_start,
                TO_CHAR(si.billing_period_end, 'YYYY-MM-DD') AS billing_period_end,
                si.metadata
            FROM enhancifai.stripe_invoices si
            WHERE si.user_id = %s
            ORDER BY si.created_at DESC;
        """)
        data = (user_id,)
        raw_records = read_db.do('select', sql=sql, data=data) or []
        invoice_history = []
        for record in raw_records:
            # Convert amount from cents to dollars
            amount_in_cents = Decimal(record['invoice_amount'])
            amount_in_dollars = (amount_in_cents / Decimal('100')).quantize(Decimal('0.01'))
            record['invoice_amount'] = float(amount_in_dollars)
            
            # Handle possible None for payment_date
            record['payment_date'] = record['payment_date'] if record['payment_date'] else None
            
            # Process metadata (convert from JSON string to dict if necessary)
            if record['metadata'] and isinstance(record['metadata'], str):
                record['metadata'] = json.loads(record['metadata'])
            elif record['metadata'] is None:
                record['metadata'] = {}

            record['payment_status'] = titlecase(record['payment_status'])

            
            invoice_history.append(record)

        return invoice_history

    @classmethod
    def get_stripe_customer_id(cls, user_id):
        """
        Get the Stripe customer ID for the user.
        """
        sql = schemafy("SELECT stripe_customer_id FROM enhancifai.users WHERE user_id = %s;")
        data = (user_id,)
        result = read_db.do('select_one', sql=sql, data=data)
        return result['stripe_customer_id'] if result else None

    @classmethod
    def update_stripe_customer_id(cls, user_id, customer_id):
        """
        Update the Stripe customer ID for the user.
        """
        sql = schemafy("UPDATE enhancifai.users SET stripe_customer_id = %s WHERE user_id = %s;")
        data = (customer_id, user_id)
        write_db.do('execute', sql=sql, data=data)

    @classmethod
    def get_user_details(cls, user_id):
        """
        Get user details for Stripe customer creation.
        """
        sql = schemafy("SELECT email, name FROM enhancifai.users WHERE user_id = %s;")
        data = (user_id,)
        return read_db.do('select_one', sql=sql, data=data)

    @classmethod
    def update_invoice_status(cls, invoice_id, status):
        """
        Update the status of an invoice.
        """
        if status == 'paid':
            sql = schemafy("UPDATE enhancifai.stripe_invoices SET status = %s, paid_at = NOW() WHERE invoice_id = %s;")
            data = (status, invoice_id)
            write_db.do('execute', sql=sql, data=data)
        elif status == 'failed':
            sql = schemafy("UPDATE enhancifai.stripe_invoices SET status = %s WHERE invoice_id = %s;")
            data = (status, invoice_id)
            write_db.do('execute', sql=sql, data=data)

    @classmethod
    def get_rate_card(cls, month: Optional[int], year: Optional[int]):
        """
        Retrieve the cost per token for each AI model, supporting historical rates.

        Args:
            month (Optional[int]): The month for which rates are required (historical).
            year (Optional[int]): The year for which rates are required (historical).

        Returns:
            list: A list of model names and their prices per token.
        """
        if month and year:
            # Retrieve rates for the specified month and year
            sql = schemafy("""
                SELECT
                    model_name,
                    price
                FROM enhancifai.model_pricing
                WHERE month = %s
                AND year = %s
                ORDER BY model_name;
            """)
            data = (month, year)
        else:
            # Retrieve current rates (latest effective_date for each model)
            sql = schemafy("""
                SELECT DISTINCT ON (model_name)
                    model_name,
                    price,
                    year,
                    month
                FROM enhancifai.model_pricing
                ORDER BY model_name, (year * 100 + month) DESC;
            """)
            data = ()

        return read_db.do('select', sql=sql, data=data)

    @classmethod
    def get_rate_card_history(cls):
        """
        Retrieve the historical rate card data, showing rates per month for each AI model.
        Returns a list of dictionaries containing year_month, model_name, and price_per_token.
        """
        try:
            sql = schemafy("""
                SELECT
                    (year || '-' || LPAD(month::text, 2, '0')) AS year_month,
                    model_name,
                    price AS price_per_token
                FROM enhancifai.model_pricing
                ORDER BY year ASC, month ASC, model_name DESC;
            """)
            rate_history = read_db.do('select', sql=sql, data=[])
            
            # Optionally, format the effective_date if needed
            # For example, ensure year_month is in 'YYYY-MM' format as a string
            # This is already handled in the SQL query using TO_CHAR

            return rate_history
        except Exception as e:
            logging.error(f"Error retrieving rate card history: {str(e)}")
            raise

    @classmethod
    def get_invoice_by_id(cls, user_id, invoice_id):
        """
        Retrieve a specific invoice for a user.
        Returns amount in dollars as float rounded to two decimal places.
        """
        sql = schemafy("""
            SELECT 
                TO_CHAR(si.created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS date,
                si.invoice_id,
                si.amount AS invoice_amount_cents,
                TO_CHAR(si.paid_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS payment_date,
                si.status AS payment_status,
                TO_CHAR(si.billing_period_start, 'YYYY-MM-DD') AS billing_period_start,
                TO_CHAR(si.billing_period_end, 'YYYY-MM-DD') AS billing_period_end,
                si.metadata
            FROM enhancifai.stripe_invoices si
            WHERE si.user_id = %s AND si.invoice_id = %s;
        """)
        data = (user_id, invoice_id)
        record = read_db.do('select_one', sql=sql, data=data)
        if record:
            # Convert amount from cents to dollars
            amount_in_cents = Decimal(record['invoice_amount_cents'])
            amount_in_dollars = (amount_in_cents / Decimal('100')).quantize(Decimal('0.01'))
            record['invoice_amount'] = float(amount_in_dollars)
            
            # Handle possible None for payment_date
            record['payment_date'] = record['payment_date'] if record['payment_date'] else None
            
            # Process metadata
            if record['metadata'] and isinstance(record['metadata'], str):
                record['metadata'] = json.loads(record['metadata'])
            elif record['metadata'] is None:
                record['metadata'] = {}
        
        return record

    @classmethod
    def get_price_per_token(cls, model_name: str, year: int, month: int) -> Optional[Decimal]:
        """
        Retrieve the price per token for a specific model for a given month and year.

        Args:
            model_name (str): The name of the AI model (e.g., 'standard', 'pi').
            year (int): The year for which to fetch the rate.
            month (int): The month for which to fetch the rate.

        Returns:
            Optional[Decimal]: The price per token if found, else None.
        """
        sql = schemafy("""
            SELECT price
            FROM enhancifai.model_pricing
            WHERE model_name = %s
              AND year = %s
              AND month = %s
            LIMIT 1;
        """)
        data = (model_name, year, month)
        result = read_db.do('select_one', sql=sql, data=data)
        return Decimal(result['price']) if result and result['price'] else None

    @classmethod
    def has_any_invoice(cls, user_id):
        """
        Check if a user has any invoices.

        Args:
            user_id (int): The user's ID.

        Returns:
            bool: True if the user has any invoices, False otherwise.
        """
        try:
            sql = schemafy("""
                SELECT 1
                FROM enhancifai.stripe_invoices
                WHERE user_id = %s
                LIMIT 1;
            """)
            data = (user_id,)
            result = read_db.do('select_one', sql=sql, data=data)

            return result is not None  # If result is not None, user has at least one invoice

        except Exception as e:
            print(f"Error checking if user {user_id} has any invoices: {str(e)}")
            raise RuntimeError(f"Error checking if user {user_id} has any invoices: {str(e)}")
    
    @classmethod
    def get_last_invoice_end_date(cls, user_id):
        """
        Get the end date of the last invoice for a user.
        """
        sql = schemafy("""
            SELECT billing_period_end
            FROM enhancifai.stripe_invoices
            WHERE user_id = %s
            ORDER BY billing_period_end DESC
            LIMIT 1;
        """)
        data = (user_id,)
        result = read_db.do('select_one', sql=sql, data=data)
        if result:
            return result['billing_period_end']
        else:
            return None
    
    @classmethod
    def update_last_invoice_run(cls, user_id: int, run_timestamp: datetime):
        """
        Update the last_invoice_run_at timestamp for a user.

        Args:
            user_id (int): The user's ID.
            run_timestamp (datetime): The timestamp of the invoice run (timezone-aware).
        """
        try:
            sql = schemafy("""
                UPDATE enhancifai.users
                SET last_invoice_run_at = %s
                WHERE user_id = %s;
            """)
            data = (run_timestamp, user_id)
            write_db.do('execute', sql=sql, data=data)
            logging.info("Updated last_invoice_run_at for user %s to %s", user_id, run_timestamp.isoformat())
        except Exception as e:
            logging.error("Failed to update last_invoice_run_at for user %s: %s", user_id, str(e))
            raise

    @classmethod
    def get_last_invoice_run(cls, user_id: int) -> Optional[datetime]:
        """
        Retrieve the last_invoice_run_at timestamp for a user.

        Args:
            user_id (int): The user's ID.

        Returns:
            Optional[datetime]: The timestamp of the last invoice run, or None if not available.
        """
        try:
            sql = schemafy("""
                SELECT last_invoice_run_at
                FROM enhancifai.users
                WHERE user_id = %s;
            """)
            data = (user_id,)
            result = read_db.do('select_one', sql=sql, data=data)
            if result and result['last_invoice_run_at']:
                return result['last_invoice_run_at']
            return None
        except Exception as e:
            logging.error("Failed to retrieve last_invoice_run_at for user %s: %s", user_id, str(e))
            raise
