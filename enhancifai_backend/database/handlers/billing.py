# enhancifai_backend/database/handlers/billing.py

from datetime import datetime
from typing import Optional
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
        """
        sql = schemafy("""
            SELECT 
                TO_CHAR(rl.log_timestamp, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS execution_time,
                rl.filename AS uploaded_file_name,
                r.source_type AS type,
                rl.num_rows_processed AS number_of_rows,
                rl.num_tokens AS total_tokens,
                mp.price_per_token AS cost_per_token,
                (rl.num_tokens * mp.price_per_token) AS total_cost
            FROM enhancifai.run_logs rl
            JOIN enhancifai.runs r ON rl.run_id = r.id
            LEFT JOIN enhancifai.model_prices mp ON rl.engine_model = mp.model_name
            WHERE r.user_id = %s
            ORDER BY rl.log_timestamp DESC;
        """)
        data = (user_id,)
        return read_db.do('select', sql=sql, data=data)

    @classmethod
    def get_monthly_balance(cls, user_id):
        """
        Provide the current monthly balance for the user, including the breakdown of tokens used per AI model.
        """
        sql = schemafy("""
            SELECT 
                TO_CHAR(NOW(), 'YYYY-MM') AS billing_month,
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
        return result

    @classmethod
    def get_usage_by_model(cls, user_id):
        """
        Aggregate data by AI model, including tokens used, price per token, and total monthly cost for each model.
        """
        sql = schemafy("""
            SELECT 
                rl.engine_model AS ai_model_name,
                SUM(rl.num_tokens) AS tokens_used,
                mp.price_per_token,
                SUM(rl.num_tokens * mp.price_per_token) AS total_cost
            FROM enhancifai.run_logs rl
            JOIN enhancifai.runs r ON rl.run_id = r.id
            LEFT JOIN enhancifai.model_prices mp ON rl.engine_model = mp.model_name
            WHERE r.user_id = %s AND DATE_TRUNC('month', rl.log_timestamp) = DATE_TRUNC('month', NOW())
            GROUP BY ai_model_name, mp.price_per_token;
        """)
        data = (user_id,)
        return read_db.do('select', sql=sql, data=data)

    @classmethod
    def get_invoice_history(cls, user_id):
        """
        Retrieve invoice data, including date, invoice number, invoice amount, payment date, and status.
        """
        sql = schemafy("""
            SELECT 
                TO_CHAR(si.created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS date,
                si.invoice_id AS invoice_number,
                si.amount AS invoice_amount,
                TO_CHAR(si.paid_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS payment_date,
                si.status AS payment_status
            FROM enhancifai.stripe_invoices si
            WHERE si.user_id = %s
            ORDER BY si.created_at DESC;
        """)
        data = (user_id,)
        return read_db.do('select', sql=sql, data=data)

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
        Retrieve the cost per 1000 tokens for each AI model, supporting historical rates.
        """
        if month and year:
            # Retrieve rates for the specified month and year
            sql = schemafy("""
                SELECT
                    model_name,
                    price_per_token,
                    effective_date
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
                    effective_date
                FROM enhancifai.model_price_history
                ORDER BY model_name, effective_date DESC;
            """)
            data = ()
        return read_db.do('select', sql=sql, data=data)
    
    @classmethod
    def get_invoice_by_id(cls, user_id, invoice_id):
        """
        Retrieve a specific invoice for a user.
        """
        sql = schemafy("""
            SELECT 
                TO_CHAR(si.created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS date,
                si.invoice_id AS invoice_number,
                si.amount AS invoice_amount,
                TO_CHAR(si.paid_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS payment_date,
                si.status AS payment_status
            FROM enhancifai.stripe_invoices si
            WHERE si.user_id = %s AND si.invoice_id = %s;
        """)
        data = (user_id, invoice_id)
        return read_db.do('select_one', sql=sql, data=data)
