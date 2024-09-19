from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

class StripeDbCore:
    """
    A class to handle database operations related to Stripe.
    """
    @classmethod
    def get_stripe_customer_id(cls, user_id):
        """
        Retrieve the Stripe customer ID for a given user.

        Parameters:
        user_id (int): The ID of the user.

        Returns:
        str: The Stripe customer ID or None if not found.
        """
        sql = schemafy("SELECT stripe_customer_id FROM enhancifai.users WHERE user_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result.get('stripe_customer_id') if result else None

    @classmethod
    def save_stripe_customer_id(cls, user_id, customer_id):
        """
        Save the Stripe customer ID for a given user.

        Parameters:
        user_id (int): The ID of the user.
        customer_id (str): The Stripe customer ID.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.users SET stripe_customer_id = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(customer_id, user_id))

    @classmethod
    def get_stripe_subscription(cls, user_id):
        """
        Retrieve the Stripe subscription ID for a given user.

        Parameters:
        user_id (int): The ID of the user.

        Returns:
        str: The Stripe subscription ID or None if not found.
        """
        sql = schemafy("SELECT stripe_subscription_id FROM enhancifai.users WHERE user_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result.get('stripe_subscription_id') if result else None

    @classmethod
    def save_stripe_subscription(cls, user_id, subscription_id):
        """
        Save the Stripe subscription ID for a given user.

        Parameters:
        user_id (int): The ID of the user.
        subscription_id (str): The Stripe subscription ID.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.users SET stripe_subscription_id = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(subscription_id, user_id))
    
    @classmethod
    def cancel_stripe_subscription(cls, user_id):
        """
        Cancel the Stripe subscription for a given user.

        Parameters:
        user_id (int): The ID of the user.

        Returns:
        bool: True if the subscription was successfully canceled, False otherwise.
        """
        # Remove the subscription ID from the database
        sql = schemafy("UPDATE enhancifai.users SET stripe_subscription_id = NULL WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(user_id,))

    @classmethod
    def update_subscription_status(cls, subscription_id, status):
        """
        Update the subscription status for a given subscription ID.

        Parameters:
        subscription_id (str): The ID of the subscription.
        status (str): The new status of the subscription.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.users SET subscription_status = %s WHERE stripe_subscription_id = %s;")
        write_db.do('execute', sql=sql, data=(status, subscription_id))