from datetime import datetime, date
import json
import os
from typing import Optional
import logging
import stripe
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

# Initialize logging
logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


class StripeDbCore:
    """
    Handles Stripe-related database operations including:
    - Retrieving Stripe customer IDs.
    - Creating and sending invoices.
    - Updating invoice statuses.
    - Checking invoice existence within a billing period.
    """

    @classmethod
    def get_stripe_customer_id(cls, user_id: int) -> Optional[str]:
        """
        Retrieve the Stripe Customer ID for the specified user.

        Parameters:
            user_id (int): The unique identifier of the user.

        Returns:
            Optional[str]: The Stripe Customer ID if found; otherwise, None.
        """
        sql = schemafy("SELECT stripe_customer_id FROM enhancifai.users WHERE user_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result['stripe_customer_id'] if result and 'stripe_customer_id' in result else None

    @classmethod
    def update_invoice_status(cls, invoice_id: str, status: str) -> None:
        """
        Update the status of a specified Stripe invoice in the database.

        Parameters:
            invoice_id (str): The unique identifier of the invoice.
            status (str): The new status to be applied.
        """
        sql = schemafy("UPDATE enhancifai.stripe_invoices SET status = %s WHERE invoice_id = %s;")
        write_db.do('execute', sql=sql, data=(status, invoice_id,))
        logger.debug("Updated Invoice Status: %s to %s", invoice_id, status)

    @classmethod
    def update_subscription_status(cls, subscription_id: str, status: str) -> None:
        """
        Update the status of a specified Stripe subscription in the database.

        Parameters:
            subscription_id (str): The unique identifier of the subscription.
            status (str): The new status to be applied.
        """
        sql = schemafy("UPDATE enhancifai.stripe_subscriptions SET status = %s WHERE subscription_id = %s;")
        write_db.do('execute', sql=sql, data=(status, subscription_id,))
        logger.debug("Updated Subscription Status: %s to %s", subscription_id, status)

    @classmethod
    def create_invoice(
        cls,
        user_id: int,
        amount: int,
        description: str,
        billing_period_start: date,
        billing_period_end: date
    ) -> dict:
        """
        Create and send a new invoice for a user with a one-time fee.

        Parameters:
            user_id (int): The unique identifier of the user.
            amount (int): The charge amount in cents.
            description (str): A description for the invoice.
            billing_period_start (date): The start date of the billing period.
            billing_period_end (date): The end date of the billing period.

        Returns:
            dict: Details of the created invoice.
        """
        try:
            # Check if an invoice for the billing period already exists
            if cls.invoice_exists(user_id, billing_period_start, billing_period_end):
                raise Exception("An invoice for this billing period already exists.")

            # Retrieve the Stripe Customer ID associated with the user
            customer_id = cls.get_stripe_customer_id(user_id)
            if not customer_id:
                raise ValueError(f"No Stripe customer found for user_id {user_id}")

            # Create an invoice item (e.g., a one-time fee)
            invoice_item = stripe.InvoiceItem.create(
                customer=customer_id,
                amount=amount,
                currency='usd',  # Adjust currency as needed
                description=description,
            )
            logger.debug("Created InvoiceItem: %s", invoice_item.id)

            # Create the invoice with collection_method 'send_invoice' and expand 'lines'
            invoice = stripe.Invoice.create(
                customer=customer_id,
                collection_method='send_invoice',
                days_until_due=30,  # Adjust as per your billing terms
                description=description,
                metadata={
                    'billing_period_start': billing_period_start.isoformat(),
                    'billing_period_end': billing_period_end.isoformat(),
                },
                expand=['lines']
            )
            logger.debug("Created Invoice: %s", invoice.id)

            # Verify the invoice includes the invoice item
            if not any(
                line.description == description and line.amount == amount
                for line in invoice.lines.data
            ):
                raise Exception("Invoice item not found in the created invoice.")

            # Send the invoice
            invoice.send_invoice()
            logger.debug("Sent Invoice: %s", invoice.id)

            # Record the invoice in your local database
            cls.save_stripe_invoice(invoice, user_id)

            return invoice.to_dict()

        except stripe.error.StripeError as e:
            # Handle Stripe-specific errors
            logger.error("Stripe error: %s", e.user_message)
            raise Exception(f"Stripe error: {e.user_message}") from e
        except Exception as e:
            # Handle general errors
            logger.error("Failed to create invoice: %s", str(e))
            raise Exception(f"Failed to create invoice: {str(e)}") from e

    @classmethod
    def invoice_exists(cls, user_id: int, billing_period_start: date, billing_period_end: date) -> bool:
        """
        Check if an invoice already exists for the user during the specified billing period.

        Parameters:
            user_id (int): The unique identifier of the user.
            billing_period_start (date): Start date of the billing period.
            billing_period_end (date): End date of the billing period.

        Returns:
            bool: True if an invoice exists, otherwise False.
        """
        sql = schemafy("""
            SELECT 1 
            FROM enhancifai.stripe_invoices 
            WHERE user_id = %s 
              AND billing_period_start = %s 
              AND billing_period_end = %s
            LIMIT 1;
        """)
        result: Optional[dict] = read_db.do(
            'select_one', 
            sql=sql,
            data=(user_id, billing_period_start, billing_period_end)
        )
        logger.debug(
            "Invoice Exists Check for User %s, Period %s to %s: %s", 
            user_id,
            billing_period_start,
            billing_period_end,
            bool(result)
        )
        return bool(result)

    @classmethod
    def save_stripe_invoice(cls, invoice: stripe.Invoice, user_id: int) -> None:
        """
        Save the provided Stripe invoice to the local database.

        Parameters:
            invoice (stripe.Invoice): The invoice object from Stripe.
            user_id (int): The unique identifier of the user associated with the invoice.

        Raises:
            Exception: When saving to the database fails.
        """
        try:
            # Serialize metadata to JSON
            metadata_json = json.dumps(invoice.metadata) if hasattr(invoice, 'metadata') and invoice.metadata else None

            # Extract billing_period_start and billing_period_end from metadata
            billing_period_start = invoice.metadata.get('billing_period_start')
            billing_period_end = invoice.metadata.get('billing_period_end')

            # Convert billing periods from ISO format to date
            billing_period_start_dt = (
                datetime.fromisoformat(billing_period_start).date()
                if billing_period_start else None
            )
            billing_period_end_dt = (
                datetime.fromisoformat(billing_period_end).date()
                if billing_period_end else None
            )

            # Insert the main invoice record
            sql = schemafy("""
                INSERT INTO enhancifai.stripe_invoices 
                (invoice_id, user_id, amount, currency, status, created_at, billing_period_start, billing_period_end, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, billing_period_start, billing_period_end) 
                DO NOTHING;
            """)
            data = (
                invoice.id,
                user_id,
                invoice.amount_due,    # Amount in cents
                invoice.currency,      # Currency, e.g., 'usd'
                invoice.status,        # e.g., 'draft', 'open', 'paid', etc.
                datetime.fromtimestamp(invoice.created),
                billing_period_start_dt,
                billing_period_end_dt,
                metadata_json
            )
            write_db.do('execute', sql=sql, data=data)
            logger.debug("Saved Invoice: %s", invoice.id)
        except Exception as e:
            logger.error("Failed to save invoice %s to DB: %s", invoice.id, str(e))
            raise Exception(f"Failed to save invoice to DB: {str(e)}") from e

    @classmethod
    def is_user_subscribed(cls, user_id: int) -> bool:
        """
        Check if a user is currently subscribed.

        Parameters:
            user_id (int): The unique identifier of the user.

        Returns:
            bool: True if the user is subscribed, otherwise False.
        """
        sql = schemafy("SELECT 1 FROM enhancifai.stripe_subscriptions WHERE user_id = %s AND status = 'active' LIMIT 1;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return bool(result)

    @classmethod
    def get_subscription(cls, subscription_id: str) -> Optional[dict]:
        """
        Retrieve a subscription record from the database.
        """
        sql = schemafy("SELECT * FROM enhancifai.stripe_subscriptions WHERE subscription_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(subscription_id,))
        return result

    @classmethod
    def create_subscription(cls, subscription_id: str, user_id: int, status: str) -> None:
        """
        Create a new subscription record in the database.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.stripe_subscriptions 
            (subscription_id, user_id, status, created_at) 
            VALUES (%s, %s, %s, now())
            ON CONFLICT (subscription_id) DO NOTHING;
        """)
        write_db.do('execute', sql=sql, data=(subscription_id, user_id, status))
        logger.debug("Created Subscription: %s for User: %s with status: %s", subscription_id, user_id, status)

    @staticmethod
    def store_invoice_record(user_id, invoice_id, amount, status):
        """
        Store a newly created Stripe invoice record in the database.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.stripe_invoices 
            (user_id, invoice_id, amount, status, created_at) 
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (invoice_id) DO NOTHING;
        """)
        write_db.do('execute', sql=sql, data=(user_id, invoice_id, amount, status))
        logger.debug("Stored Invoice Record: %s for User: %s with status: %s", invoice_id, user_id, status)
