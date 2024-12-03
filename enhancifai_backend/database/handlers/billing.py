# enhancifai_backend/database/handlers/billing.py

from datetime import datetime
import json
import logging
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
                mp.price_per_token AS cost_per_token,
                (rl.num_tokens * mp.price_per_token) AS total_cost  -- Since price is per single token
            FROM enhancifai.run_logs rl
            JOIN enhancifai.runs r ON rl.run_id = r.id
            LEFT JOIN enhancifai.model_prices mp ON rl.engine_model = mp.model_name
            WHERE r.user_id = %s
            ORDER BY rl.log_timestamp DESC;
        """)
        data = (user_id,)
        raw_records = read_db.do('select', sql=sql, data=data)

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
                SUM(rl.num_tokens * mp.price_per_token) AS total_monthly_cost
            FROM enhancifai.run_logs rl
            JOIN enhancifai.runs r ON rl.run_id = r.id
            LEFT JOIN enhancifai.model_prices mp ON rl.engine_model = mp.model_name
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
    def get_usage_by_model(cls, user_id):
        """
        Aggregate data by AI model, including tokens used, price per token, and total monthly cost for each model.
        Returns amounts in dollars as floats rounded to two decimal places.
        """
        sql = schemafy("""
            SELECT 
                rl.engine_model AS ai_model_name,
                SUM(rl.num_tokens) AS tokens_used,
                (mp.price_per_token * 1000) AS price_per_token,
                SUM(rl.num_tokens * mp.price_per_token) AS total_cost
            FROM enhancifai.run_logs rl
            JOIN enhancifai.runs r ON rl.run_id = r.id
            LEFT JOIN enhancifai.model_prices mp ON rl.engine_model = mp.model_name
            WHERE r.user_id = %s AND DATE_TRUNC('month', rl.log_timestamp) = DATE_TRUNC('month', NOW())
            GROUP BY ai_model_name, mp.price_per_token;
        """)
        data = (user_id,)
        raw_records = read_db.do('select', sql=sql, data=data)

        # Convert total_cost to dollars, rounded to two decimal places
        usage_by_model = []
        for record in raw_records:
            record['price_per_token'] = float(Decimal(record['price_per_token']).quantize(Decimal('0.0001')))
            record['total_cost'] = float((Decimal(record['total_cost'])).quantize(Decimal('0.01')))
            usage_by_model.append(record)

        return usage_by_model

    @classmethod
    def create_invoice(cls, user_id, amount_cents, description, billing_period_start, billing_period_end):
        """
        Create an invoice and save it in the database.

        Args:
            user_id (int): The user's ID.
            amount_cents (int): The total amount in cents.
            description (str): Description of the invoice.
            billing_period_start (date): Start of the billing period.
            billing_period_end (date): End of the billing period.

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

            sql = schemafy("""
                INSERT INTO enhancifai.stripe_invoices (
                    user_id, amount, status, created_at,
                    billing_period_start, billing_period_end, metadata
                ) VALUES (%s, %s, 'open', NOW(), %s, %s, %s)
                RETURNING invoice_id, amount, status, created_at, billing_period_start, billing_period_end;
            """)
            data = (user_id, amount_cents, billing_period_start, billing_period_end, json.dumps({'description': description}))
            result = write_db.do('execute', sql=sql, data=data)
            pass
            return {
                'id': result['invoice_id'],
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
                si.invoice_id AS invoice_number,
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
                    price_per_token,
                    TO_CHAR(effective_date, 'YYYY-MM-DD') AS effective_date
                FROM enhancifai.model_price_history
                WHERE EXTRACT(MONTH FROM effective_date) = %s
                AND EXTRACT(YEAR FROM effective_date) = %s
                ORDER BY model_name;
            """)
            data = (month, year)
        else:
            # Retrieve current rates (latest effective_date for each model)
            sql = schemafy("""
                SELECT DISTINCT ON (model_name)
                    model_name,
                    price_per_token,
                    TO_CHAR(effective_date, 'YYYY-MM-DD') AS effective_date
                FROM enhancifai.model_price_history
                ORDER BY model_name, effective_date DESC;
            """)
            data = ()

        return read_db.do('select', sql=sql, data=data)


    @classmethod
    def get_invoice_by_id(cls, user_id, invoice_id):
        """
        Retrieve a specific invoice for a user.
        Returns amount in dollars as float rounded to two decimal places.
        """
        sql = schemafy("""
            SELECT 
                TO_CHAR(si.created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS date,
                si.invoice_id AS invoice_number,
                si.amount AS invoice_amount,
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
            amount_in_cents = Decimal(record['invoice_amount'])
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
    def get_price_per_token(cls, model_name: str, effective_date: datetime) -> Optional[Decimal]:
        """
        Retrieve the price per token for a specific model effective on a given date.

        Args:
            model_name (str): The name of the AI model (e.g., 'standard', 'pi').
            effective_date (datetime): The date for which to fetch the rate.

        Returns:
            Optional[Decimal]: The price per token if found, else None.
        """
        sql = schemafy("""
            SELECT price_per_token
            FROM enhancifai.model_price_history
            WHERE model_name = %s
            AND effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """)
        data = (model_name, effective_date)
        result = read_db.do('select_one', sql=sql, data=data)

        # Return None if no price is found for the given date and model
        return Decimal(result['price_per_token']) if result and result['price_per_token'] else None


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
    