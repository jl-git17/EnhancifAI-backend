# enhancifai_backend/database/handlers/stripe.py

from datetime import datetime
import os
from typing import Optional
import stripe
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.utils import schemafy

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class StripeDbCore:
    """
    A class to handle database operations related to Stripe functionalities.
    This includes managing Stripe customers and handling invoices based on token usage.
    """

    @classmethod
    def get_stripe_customer_id(cls, user_id: int) -> Optional[str]:
        """
        Retrieve the Stripe Customer ID for a given user.
        
        Args:
            user_id (int): The ID of the user.
        
        Returns:
            Optional[str]: Stripe Customer ID or None if not found.
        """
        sql = schemafy("SELECT stripe_customer_id FROM enhancifai.users WHERE user_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result['stripe_customer_id'] if result and 'stripe_customer_id' in result else None


    @classmethod
    def save_stripe_customer_id(cls, user_id: int, customer_id: str) -> None:
        """
        Save the Stripe customer ID for a given user.

        Args:
            user_id (int): The ID of the user.
            customer_id (str): The Stripe customer ID to be saved.
        """
        sql = schemafy("UPDATE enhancifai.users SET stripe_customer_id = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(customer_id, user_id,))

    @classmethod
    def save_stripe_invoice(cls, invoice_id: str, user_id: int, amount: int, status: str) -> None:
        """
        Save a new Stripe invoice record in the database.

        Args:
            invoice_id (str): The Stripe invoice ID.
            user_id (int): The ID of the user associated with the invoice.
            amount (int): The amount due in cents.
            status (str): The status of the invoice (e.g., 'paid', 'open').
        """
        sql = schemafy("""
            INSERT INTO enhancifai.stripe_invoices (invoice_id, user_id, amount, status, created_at)
            VALUES (%s, %s, %s, %s, NOW());
        """)
        write_db.do('execute', sql=sql, data=(invoice_id, user_id, amount, status))

    @classmethod
    def update_invoice_status(cls, invoice_id: str, status: str) -> None:
        """
        Update the status of an existing Stripe invoice.

        Args:
            invoice_id (str): The Stripe invoice ID.
            status (str): The new status of the invoice.
        """
        sql = schemafy("UPDATE enhancifai.stripe_invoices SET status = %s WHERE invoice_id = %s;")
        write_db.do('execute', sql=sql, data=(status, invoice_id,))

    @classmethod
    def get_user_invoices(cls, user_id: int) -> list:
        """
        Retrieve all invoices associated with a specific user.

        Args:
            user_id (int): The ID of the user.

        Returns:
            list: A list of dictionaries containing invoice details.
        """
        sql = schemafy("""
            SELECT invoice_id, amount, status, created_at 
            FROM enhancifai.stripe_invoices 
            WHERE user_id = %s 
            ORDER BY created_at DESC;
        """)
        return read_db.do('select', sql=sql, data=(user_id,)) or []

    @classmethod
    def create_invoice(cls, user_id: int, amount: int, description: str, billing_period_start: datetime, billing_period_end: datetime) -> dict:
        """
        Create a new invoice for the user with collection_method set to 'send_invoice'.
        
        Args:
            user_id (int): The ID of the user.
            amount (int): The amount in cents.
            description (str): Description of the invoice.
            billing_period_start (datetime): Start of the billing period.
            billing_period_end (datetime): End of the billing period.
        
        Returns:
            dict: Created invoice details.
        """
        try:
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

            # Create the invoice with collection_method 'send_invoice'
            invoice = stripe.Invoice.create(
                customer=customer_id,
                collection_method='send_invoice',
                days_until_due=30,  # Adjust as per your billing terms
                description=description,
                metadata={
                    'user_id': user_id,
                    'billing_period_start': billing_period_start.isoformat(),
                    'billing_period_end': billing_period_end.isoformat(),
                },
            )
            
            invoice.send_invoice()

            # Record the invoice in your local database
            cls.record_invoice(invoice, user_id)

            return invoice

        except stripe.error.StripeError as e:
            # Handle Stripe-specific errors
            raise Exception(f"Stripe error: {e.user_message}") from e
        except Exception as e:
            # Handle general errors
            raise Exception(f"Failed to create invoice: {str(e)}") from e


    @classmethod
    def cancel_stripe_subscription(cls, invoice_id: str) -> None:
        """
        (Optional) If you plan to handle subscription-like features in the future,
        this method can be used to cancel a subscription based on the invoice ID.
        Currently retained for potential future use.

        Args:
            invoice_id (str): The Stripe invoice ID.
        """
        # Placeholder for future subscription cancellation logic
        pass

    @classmethod
    def update_subscription_status(cls, subscription_id: str, status: str) -> None:
        """
        (Optional) Update the status of a subscription.
        Currently retained for potential future use.

        Args:
            subscription_id (str): The Stripe subscription ID.
            status (str): The new status of the subscription.
        """
        # Placeholder for future subscription status updates
        pass

    @classmethod
    def invoice_exists(cls, user_id: int, start_date: datetime, end_date: datetime) -> bool:
        """
        Check if an invoice already exists for the user within the specified billing period.
        
        Args:
            user_id (int): The ID of the user.
            start_date (datetime): Start of the billing period.
            end_date (datetime): End of the billing period.
        
        Returns:
            bool: True if an invoice exists, False otherwise.
        """
        sql = schemafy("""
            SELECT 1 
            FROM enhancifai.stripe_invoices 
            WHERE user_id = %s 
              AND created_at >= %s 
              AND created_at < %s
            LIMIT 1;
        """)
        result: Optional[dict] = read_db.do('select_one', sql=sql, data=(user_id, start_date, end_date))
        return bool(result)
    
    @classmethod
    def record_invoice(cls, invoice: stripe.Invoice, user_id: int):
        """
        Record the created invoice in the local database.
        
        Args:
            invoice (stripe.Invoice): The created Stripe invoice object.
            user_id (int): The ID of the user.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.stripe_invoices (invoice_id, user_id, amount, status, created_at)
            VALUES (%s, %s, %s, %s, %s);
        """)
        data = (
            invoice.id,
            user_id,
            invoice.amount_due,  # Amount in cents
            invoice.status,      # e.g., 'draft', 'open', 'paid', etc.
            datetime.fromtimestamp(invoice.created),
        )
        write_db.do('insert', sql=sql, data=data)