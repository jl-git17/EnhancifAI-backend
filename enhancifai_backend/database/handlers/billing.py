from datetime import datetime
import json
import logging
import re
from typing import Optional
from decimal import Decimal

from titlecase import titlecase
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

class BillingDbCore:
    """
    Updated Database handler for billing-related operations.
    Handles invoicing, usage tracking, and rate card operations for Enhancifai.
    """

    @classmethod
    def get_usage_history(cls, user_id):
        """
        Retrieve the execution and token usage history for a given user.
        
        Args:
            user_id (int): Unique identifier for the user.
            
        Returns:
            list: A list of dictionaries with keys:
                - execution_time (str)
                - uploaded_file_name (str)
                - type (str)
                - number_of_rows (int)
                - total_tokens (int)
                - cost_per_token (float)
                - total_cost (float)
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
        Retrieve the current monthly billing balance for a user.
        
        Args:
            user_id (int): Unique identifier for the user.
            
        Returns:
            dict: Dictionary with:
                - billing_month (str)
                - total_monthly_cost (float)
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
        Aggregate token usage and cost by AI model.
        
        Args:
            user_id (int): Unique identifier for the user.
            month (Optional[int]): Month filter (1-12) if provided.
            year (Optional[int]): Year filter if provided.
            
        Returns:
            list: A list of dictionaries containing:
                - ai_model_name (str)
                - tokens_used (int)
                - price_per_token (float, per 1K tokens)
                - total_cost (float)
        """
        if month is not None and year is not None:
            if not 1 <= month <= 12:
                raise ValueError("Invalid month. Must be between 1 and 12.")
            current_year = datetime.now().year
            if not 2000 <= year <= current_year:
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
                COALESCE(mp.price, 0) AS price_per_token, 
                SUM(cl.tokens * COALESCE(mp.price, 0)) AS total_cost
            FROM combined_logs cl
            LEFT JOIN enhancifai.model_pricing mp
                ON cl.engine_model = mp.model_name
                AND mp.year = EXTRACT(YEAR FROM cl.log_timestamp)::INT
                AND mp.month = EXTRACT(MONTH FROM cl.log_timestamp)::INT
            GROUP BY cl.engine_model, mp.price;
        """)

        # Set parameters in the proper order.
        if month is not None and year is not None:
            # First usage query: user_id, month, year; second query: user_id, month, year.
            data = (user_id, month, year, user_id, month, year)
        else:
            data = (user_id, user_id)

        num_placeholders = len(re.findall(r'%s', sql))
        if num_placeholders != len(data):
            raise ValueError(
                f"Number of placeholders ({num_placeholders}) does not match "
                "number of data elements ({len(data)})."
            )

        raw_records = read_db.do('select', sql=sql, data=data) or []

        usage_by_model = []
        for record in raw_records:
            # Multiply the per-token price by 1000 if you want to show price per 1K tokens.
            record['price_per_token'] = float((Decimal(record['price_per_token']) * 1000).quantize(Decimal('0.000001')))
            record['total_cost'] = float(Decimal(record['total_cost']).quantize(Decimal('0.01')))
            usage_by_model.append(record)

        return usage_by_model


    @classmethod
    def create_invoice(cls, user_id, amount_cents, description, billing_period_start, billing_period_end, metadata=None):
        """
        Create an invoice record for a user with a specified billing period and amount.
        
        Args:
            user_id (int): Unique identifier for the user.
            amount_cents (int): Total amount in cents.
            description (str): Invoice description.
            billing_period_start (date): Billing period start date.
            billing_period_end (date): Billing period end date.
            metadata (dict, optional): Additional metadata including line items.
            
        Returns:
            dict or None: Invoice details if created; otherwise, None (e.g., if skipped).
        """
        try:
            # Validate amount
            if amount_cents <= 0:
                logging.info("Skipping invoice for user %s: amount is zero or negative.", user_id)
                return None

            # Check if an invoice already exists for the period
            if cls.invoice_exists(user_id, billing_period_start, billing_period_end):
                logging.info("Skipping invoice for user %s: invoice already exists for this period.", user_id)
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
        Check if an invoice already exists for a user in a given billing period.
        
        Args:
            user_id (int): Unique identifier for the user.
            billing_period_start (date): Start date of the billing period.
            billing_period_end (date): End date of the billing period.
            
        Returns:
            bool: True if an invoice exists; otherwise, False.
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
        Retrieve the invoice history for a user.
        
        Args:
            user_id (int): Unique identifier for the user.
            
        Returns:
            list: A list of dictionaries containing:
                - date (str)
                - invoice_id (int)
                - invoice_amount (float)
                - payment_date (str or None)
                - payment_status (str)
                - billing_period_start (str)
                - billing_period_end (str)
                - metadata (dict)
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
        Retrieve the Stripe customer ID for a user.
        
        Args:
            user_id (int): Unique identifier for the user.
        
        Returns:
            str or None: Stripe customer ID if available; otherwise, None.
        """
        sql = schemafy("SELECT stripe_customer_id FROM enhancifai.users WHERE user_id = %s;")
        data = (user_id,)
        result = read_db.do('select_one', sql=sql, data=data)
        return result['stripe_customer_id'] if result else None

    @classmethod
    def update_stripe_customer_id(cls, user_id, customer_id):
        """
        Update the Stripe customer ID for a given user.
        
        Args:
            user_id (int): Unique identifier for the user.
            customer_id (str): New Stripe customer ID.
        """
        sql = schemafy("UPDATE enhancifai.users SET stripe_customer_id = %s WHERE user_id = %s;")
        data = (customer_id, user_id)
        write_db.do('execute', sql=sql, data=data)

    @classmethod
    def get_user_details(cls, user_id):
        """
        Retrieve user details required for Stripe customer creation.
        
        Args:
            user_id (int): Unique identifier for the user.
            
        Returns:
            dict: Contains keys such as email and name.
        """
        sql = schemafy("SELECT email, name FROM enhancifai.users WHERE user_id = %s;")
        data = (user_id,)
        return read_db.do('select_one', sql=sql, data=data)

    @classmethod
    def update_invoice_status(cls, invoice_id, status):
        """
        Update the payment status of an invoice.
        
        Args:
            invoice_id (int): Unique identifier for the invoice.
            status (str): New status ('paid' or 'failed').
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
        Retrieve the cost per token for each AI model, optionally filtering by month and year.
        
        Args:
            month (Optional[int]): Month for historical rates.
            year (Optional[int]): Year for historical rates.
            
        Returns:
            list: A list of dictionaries with model_name and price.
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
        Retrieve historical rate card data for all AI models.
        
        Returns:
            list: A sorted list of dictionaries containing:
                - year_month (str)
                - model_name (str)
                - price_per_token (float)
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
            logging.error("Error retrieving rate card history: %s", str(e))
            raise

    @classmethod
    def get_invoice_by_id(cls, user_id, invoice_id):
        """
        Retrieve detailed invoice information for a specific invoice.
        
        Args:
            user_id (int): Unique identifier for the user.
            invoice_id (int): Unique identifier for the invoice.
            
        Returns:
            dict: Invoice details including amount (converted to dollars) and metadata.
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
        Retrieve the price per token for a specific model and time period.
        
        Args:
            model_name (str): Name of the AI model.
            year (int): Year to fetch the rate.
            month (int): Month to fetch the rate.
            
        Returns:
            Optional[Decimal]: Price per token if found; otherwise, None.
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
        Determine if the user has any invoices.
        
        Args:
            user_id (int): Unique identifier for the user.
            
        Returns:
            bool: True if any invoice exists; otherwise, False.
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
        Retrieve the end date of the most recent invoice of a user.
        
        Args:
            user_id (int): Unique identifier for the user.
            
        Returns:
            date or None: The billing period end date of the latest invoice if available; otherwise, None.
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
        Update the timestamp for the last invoice generation run for a user.
        
        Args:
            user_id (int): Unique identifier for the user.
            run_timestamp (datetime): The timestamp of the current invoice run.
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
        Retrieve the timestamp of the last invoice generation run for a user.
        
        Args:
            user_id (int): Unique identifier for the user.
            
        Returns:
            Optional[datetime]: The last invoice run timestamp if available; otherwise, None.
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
