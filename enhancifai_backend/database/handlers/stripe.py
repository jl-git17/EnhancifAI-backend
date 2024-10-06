# enhancifai_backend/database/handlers/stripe.py

import os
import stripe
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class StripeDbCore:
    """
    A class to handle database operations related to Stripe functionalities.
    This includes managing Stripe customers and handling invoices based on token usage.
    """

    @classmethod
    def get_stripe_customer_id(cls, user_id: int) -> str:
        """
        Retrieve the Stripe customer ID associated with a given user.

        Args:
            user_id (int): The ID of the user.

        Returns:
            str: The Stripe customer ID if exists, else None.
        """
        sql = schemafy("SELECT stripe_customer_id FROM enhancifai.users WHERE user_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result['stripe_customer_id'] if result else None

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
    def create_invoice(cls, user_id: int, amount: int, description: str) -> dict:
        """
        Create a Stripe invoice for the user based on token usage.

        Args:
            user_id (int): The ID of the user.
            amount (int): The amount due in cents.
            description (str): Description of the charge.

        Returns:
            dict: The created invoice object.
        """
        customer_id = cls.get_stripe_customer_id(user_id)
        if not customer_id:
            raise ValueError("Stripe customer not found for user.")

        try:
            # Create an InvoiceItem for the user
            invoice_item = stripe.InvoiceItem.create(
                customer=customer_id,
                amount=amount,
                currency='usd',
                description=description,
            )

            # Create the Invoice
            invoice = stripe.Invoice.create(
                customer=customer_id,
                auto_advance=True,  # Auto-finalize the invoice
            )

            # Optionally, you can send the invoice to the customer
            stripe.Invoice.send_invoice(invoice.id)

            # Save the invoice details in the database
            cls.save_stripe_invoice(invoice.id, user_id, amount, invoice.status)

            return invoice

        except stripe.error.StripeError as e:
            # Handle Stripe-specific errors
            raise e
        except Exception as e:
            # Handle generic errors
            raise e

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
