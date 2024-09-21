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
    
    @classmethod
    def get_subscription_status(cls, user_id):
        """
        Retrieve the subscription status of a given user.

        Parameters:
        user_id (int): The ID of the user.

        Returns:
        str: The current subscription status ('active', 'canceled', 'past_due', etc.).
        """
        sql = schemafy("SELECT subscription_status FROM enhancifai.users WHERE user_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result.get('subscription_status') if result else None
    
    @classmethod
    def update_subscription_status(cls, subscription_id, status):
        """
        Update the subscription status and adjust the user's tier based on the subscription plan.

        Parameters:
        subscription_id (str): The ID of the subscription.
        status (str): The new status of the subscription.

        Returns:
        None
        """
        # Update the subscription status in the users table
        sql = schemafy("UPDATE enhancifai.users SET subscription_status = %s WHERE stripe_subscription_id = %s;")
        write_db.do('execute', sql=sql, data=(status, subscription_id))

        # Fetch the user's current subscription and determine the correct tier
        subscription = stripe.Subscription.retrieve(subscription_id)
        user_id = cls.get_user_id_by_subscription(subscription_id)  # Fetch user ID based on subscription

        if subscription.status == 'active':
            plan_id = subscription['items']['data'][0]['plan']['id']  # Assuming the plan ID corresponds to the tier

            # Determine the correct tier based on the plan ID
            tier_id = cls.get_tier_id_by_plan_id(plan_id)
            if tier_id:
                cls.update_user_tier(user_id, tier_id)

    @classmethod
    def get_user_id_by_subscription(cls, subscription_id):
        """
        Retrieve the user ID associated with a given Stripe subscription ID.

        Parameters:
        subscription_id (str): The Stripe subscription ID.

        Returns:
        int: The user ID or None if not found.
        """
        sql = schemafy("SELECT user_id FROM enhancifai.users WHERE stripe_subscription_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(subscription_id,))
        return result.get('user_id') if result else None

    @classmethod
    def get_tier_id_by_plan_id(cls, plan_id):
        """
        Retrieve the corresponding account tier ID based on the Stripe plan ID.

        Parameters:
        plan_id (str): The Stripe plan ID.

        Returns:
        int: The corresponding tier ID or None if not found.
        """
        # Assuming your account_tiers table has a column linking the tier to the Stripe plan ID
        sql = schemafy("SELECT tier_id FROM enhancifai.account_tiers WHERE stripe_plan_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(plan_id,))
        return result.get('tier_id') if result else None

    @classmethod
    def update_user_tier(cls, user_id, tier_id):
        """
        Update the user's current tier to the new tier based on subscription.

        Parameters:
        user_id (int): The user ID.
        tier_id (int): The new tier ID.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.users SET current_tier_id = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(tier_id, user_id))