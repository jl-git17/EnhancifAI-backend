from datetime import datetime
from typing import Dict, List, Optional

from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

class UsersDbCore:
    """
    A class to handle database operations related to users.
    """

    @classmethod
    def get_user_by_email(cls, email):
        """
        Retrieve user details by email.

        Args:
            email (str): The user's email address.
        
        Returns:
            dict or None: User record if found, else None.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s;")
        return read_db.do('select_one', sql=sql, data=(email,))

    @classmethod
    def get_user_by_id(cls, user_id):
        """
        Retrieve user details by user_id.

        Args:
            user_id (int): The user's unique identifier.
        
        Returns:
            dict or None: User record if found, else None.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE user_id = %s;")
        return read_db.do('select_one', sql=sql, data=(user_id,))

    @classmethod
    def create_user_by_email(cls, email, name, password_hash):
        """
        Create a new user with the specified email, name, and password hash.

        Args:
            email (str): The user's email.
            name (str): The user's full name.
            password_hash (str): The hashed password.
        
        Returns:
            int: The newly created user's ID.
        """
        sql = schemafy("INSERT INTO enhancifai.users (email, name, password_hash) VALUES (%s, %s, %s) RETURNING user_id;")
        return write_db.do('execute', sql=sql, data=(email, name, password_hash,))

    @classmethod
    def set_user_password(cls, user_id, new_password_hash):
        """
        Update the password hash for the given user.

        Args:
            user_id (int): The user's ID.
            new_password_hash (str): The new password hash.
        """
        sql = schemafy("UPDATE enhancifai.users SET password_hash = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(new_password_hash, user_id,))

    @classmethod
    def check_user_password(cls, email, password_hash):
        """
        Verify if the provided password hash matches the stored hash for the given email.

        Args:
            email (str): The user's email.
            password_hash (str): The password hash to verify.
        
        Returns:
            bool: True if the password matches, otherwise False.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s AND password_hash = %s")
        return read_db.do('select_exists', sql=sql, data=(email, password_hash,))

    @classmethod
    def check_user_verified_email(cls, email):
        """
        Check if the user's email address has been verified.

        Args:
            email (str): The user's email.
        
        Returns:
            bool: True if verified, otherwise False.
        """
        sql = schemafy("SELECT email_verified FROM enhancifai.users WHERE email = %s;")
        result = read_db.do('select_one', sql=sql, data=(email,))
        return result['email_verified'] if result else False

    @classmethod
    def verify_email(cls, email):
        """
        Mark the user's email as verified.

        Args:
            email (str): The user's email.
        """
        sql = schemafy("UPDATE enhancifai.users SET email_verified = TRUE WHERE email = %s;")
        write_db.do('execute', sql=sql, data=(email,))

    @classmethod
    def check_ai_consent(cls, user_id):
        """
        Check if the user has given AI consent.

        Args:
            user_id (int): The user's ID.
        
        Returns:
            str or bool: ISO formatted timestamp if consent exists, otherwise False.
        """
        sql = schemafy("SELECT ai_consent FROM enhancifai.users WHERE user_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result['ai_consent'].isoformat() if result else False

    @classmethod
    def update_ai_consent(cls, user_id):
        """
        Update the user's record with the current timestamp for AI consent.

        Args:
            user_id (int): The user's ID.
        """
        sql = schemafy("UPDATE enhancifai.users SET ai_consent = NOW() WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(user_id,))

    @classmethod
    def update_user_profile(cls, user_id, name):
        """
        Update the user's profile information.

        Args:
            user_id (int): The user's ID.
            name (str): The new name.
        """
        sql = schemafy("UPDATE enhancifai.users SET name = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(name, user_id,))

    @classmethod
    def get_session_expiration_by_user_id(cls, user_id):
        """
        Retrieve the expiration timestamp of the user's most recent session.

        Args:
            user_id (int): The user's ID.
        
        Returns:
            datetime or None: Session expiration time if exists, else None.
        """
        sql = schemafy(
            "SELECT expires_at FROM enhancifai.users_sessions WHERE "
            "user_id = %s ORDER BY created_at DESC LIMIT 1;"
        )
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result['expires_at'] if result else None

    @classmethod
    def get_user_token_usage(cls, user_id: int, start_date: datetime, end_date: datetime) -> int:
        """
        Calculate total tokens used by the user within a given date range.

        Args:
            user_id (int): The user's ID.
            start_date (datetime): Range start.
            end_date (datetime): Range end.
        
        Returns:
            int: Total number of tokens used.
        """
        sql = schemafy("""
            SELECT COALESCE(SUM(tokens), 0) AS tokens_used 
            FROM enhancifai.users_token_usage 
            WHERE user_id = %s 
              AND created_at >= %s 
              AND created_at < %s;
        """)
        result = read_db.do('select_one', sql=sql, data=(user_id, start_date, end_date))
        return result['tokens_used'] if result else 0

    @classmethod
    def add_user_token_usage(cls, user_id, run_id, model, tokens):
        """
        Log token usage for a user.

        Args:
            user_id (int): The user's ID.
            run_id (str): The run identifier.
            model (str): The model name.
            tokens (int): Number of tokens used.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.users_token_usage (user_id, run_id, model, tokens)
            VALUES (%s, %s, %s, %s);
        """)
        write_db.do('execute', sql=sql, data=(user_id, run_id, model, tokens,))

    @classmethod
    def add_user_token_usage_pi(cls, user_id, model, tokens):
        """
        Log Prompt Improver token usage for a user.

        Args:
            user_id (int): The user's ID.
            model (str): The model name.
            tokens (int): Number of tokens used.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.users_token_usage_pi (user_id, model, tokens)
            VALUES (%s, %s, %s);
        """)
        write_db.do('execute', sql=sql, data=(user_id, model, tokens,))

    @classmethod
    def create_session(cls, user_id, token, expires_at):
        """
        Create a new session for the user.

        Args:
            user_id (int): The user's ID.
            token (str): The session token.
            expires_at (datetime): When the session expires.
        """
        sql = schemafy("INSERT INTO enhancifai.users_sessions (user_id, token, expires_at) VALUES (%s, %s, %s);")
        write_db.do('execute', sql=sql, data=(user_id, token, expires_at,))

    @classmethod
    def get_user_invoices(cls, user_id):
        """
        Retrieve all invoices for the specified user.

        Args:
            user_id (int): The user's ID.
        
        Returns:
            list: A list of invoice records.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.internal_invoices 
            WHERE user_id = %s 
            ORDER BY created_at DESC;
        """)
        return read_db.do('select', sql=sql, data=(user_id,)) or []

    @classmethod
    def get_user_by_email_unverified(cls, email):
        """
        Retrieve user details by email without verifying email status.

        Args:
            email (str): The user's email.
        
        Returns:
            dict or None: User record if exists, else None.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s;")
        return read_db.do('select_one', sql=sql, data=(email,))

    @classmethod
    def cleanup_timed_out_jobs(cls):
        """
        Cleanup any expired sessions or jobs.

        Note:
            Implementation can be extended as needed.
        """
        # Example: Remove expired sessions
        sql = schemafy("DELETE FROM enhancifai.users_sessions WHERE expires_at < NOW();")
        write_db.do('execute', sql=sql)

    @classmethod
    def get_date_joined(cls, user_id: int) -> Optional[datetime]:
        """
        Retrieve the date when the user joined.

        Args:
            user_id (int): The user's ID.
        
        Returns:
            Optional[datetime]: The join date if found, otherwise None.
        """
        try:
            sql = schemafy("""
                SELECT created_at
                FROM enhancifai.users
                WHERE user_id = %s;
            """)
            data = (user_id,)
            result = read_db.do('select_one', sql=sql, data=data)
            return result['created_at'] if result else None
        except Exception as e:
            print(f"Error fetching date of joining for user {user_id}: {str(e)}",)
            return None

    @classmethod
    def get_user_token_usage_per_model(cls, user_id: int, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Retrieve token usage totals per model over a specified date range.

        Args:
            user_id (int): The user's ID.
            start_date (datetime): Range start.
            end_date (datetime): Range end.
        
        Returns:
            List[Dict]: List of records with model and total tokens.
        """
        sql = schemafy("""
            SELECT model, SUM(tokens) AS total_tokens
            FROM (
                SELECT model, tokens
                FROM enhancifai.users_token_usage
                WHERE user_id = %s
                AND created_at >= %s
                AND created_at < %s
                UNION ALL
                SELECT model, tokens
                FROM enhancifai.users_token_usage_pi
                WHERE user_id = %s
                AND created_at >= %s
                AND created_at < %s
            ) AS combined_usage
            GROUP BY model;
        """)
        data = (user_id, start_date, end_date, user_id, start_date, end_date)
        result = read_db.do('select', sql=sql, data=data)
        return result if result else []

    @classmethod
    def get_user_token_usage_per_model_per_day(cls, user_id: int, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Retrieve daily token usage totals per model over a specified date range.

        Args:
            user_id (int): The user's ID.
            start_date (datetime): Range start.
            end_date (datetime): Range end.
        
        Returns:
            List[Dict]: Records with usage_date, model, and total tokens.
        """
        sql = schemafy("""
            SELECT
                date_trunc('day', created_at) AS usage_date,
                model,
                SUM(tokens) AS total_tokens
            FROM (
                SELECT created_at, model, tokens
                FROM enhancifai.users_token_usage
                WHERE user_id = %s
                AND created_at >= %s
                AND created_at < %s
                UNION ALL
                SELECT created_at, model, tokens
                FROM enhancifai.users_token_usage_pi
                WHERE user_id = %s
                AND created_at >= %s
                AND created_at < %s
            ) AS combined_usage
            GROUP BY usage_date, model
            ORDER BY usage_date, model;
        """)
        data = (user_id, start_date, end_date, user_id, start_date, end_date)
        result = read_db.do('select', sql=sql, data=data)
        return result if result else []

    @classmethod
    def get_user_normal_token_usage_per_model_per_day(
        cls, user_id: int, start_date: datetime, end_date: datetime
    ) -> List[Dict]:
        """
        Retrieve daily normal token usage per model within a specified date range.

        Args:
            user_id (int): The user's ID.
            start_date (datetime): Range start.
            end_date (datetime): Range end.
        
        Returns:
            List[Dict]: Records with usage_date, model, and total tokens.
        """
        sql = schemafy("""
            SELECT
                date_trunc('day', created_at) AS usage_date,
                model,
                SUM(tokens) AS total_tokens
            FROM enhancifai.users_token_usage
            WHERE user_id = %s
            AND created_at >= %s
            AND created_at < %s
            GROUP BY usage_date, model
            ORDER BY usage_date, model;
        """)
        data = (user_id, start_date, end_date)
        result = read_db.do('select', sql=sql, data=data)
        return result if result else []

    @classmethod
    def get_user_pi_token_usage_per_model_per_day(cls, user_id: int, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Retrieve daily Prompt Improver token usage per model within a specified date range.

        Args:
            user_id (int): The user's ID.
            start_date (datetime): Range start.
            end_date (datetime): Range end.
        
        Returns:
            List[Dict]: Records with usage_date, model, and total tokens.
        """
        sql = schemafy("""
            SELECT
                date_trunc('day', created_at) AS usage_date,
                model,
                SUM(tokens) AS total_tokens
            FROM enhancifai.users_token_usage_pi
            WHERE user_id = %s
            AND created_at >= %s
            AND created_at < %s
            GROUP BY usage_date, model
            ORDER BY usage_date, model;
        """)
        data = (user_id, start_date, end_date)
        result = read_db.do('select', sql=sql, data=data)
        return result if result else []

    @classmethod
    def get_user_by_stripe_customer_id(cls, stripe_customer_id):
        """
        Retrieve user details by stripe customer id.

        Args:
            stripe_customer_id (str): The user's Stripe customer id.
        
        Returns:
            dict or None: User record if found, else None.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE stripe_customer_id = %s;")
        return read_db.do('select_one', sql=sql, data=(stripe_customer_id,))

    @classmethod
    def get_all_user_ids(cls):
        """
        Retrieve all user IDs.

        Returns:
            List[int]: List of all user IDs.
        """
        sql = schemafy("SELECT user_id FROM enhancifai.users;")
        result = read_db.do('select', sql=sql)
        return [row['user_id'] for row in result] if result else []

class UsersDbRegisterTokens:
    """
    A class to handle operations related to user registration tokens.
    """

    @classmethod
    def check_user_register_token(cls, email, token):
        """
        Verify the existence of an unredeemed registration token for the given email.

        Args:
            email (str): The user's email.
            token (str): The registration token.
        
        Returns:
            bool: True if token exists and is unredeemed, otherwise False.
        """
        sql = schemafy("SELECT * FROM enhancifai.user_register_tokens WHERE email = %s AND token = %s AND redeemed = FALSE")
        return read_db.do('select_exists', sql=sql, data=(email, token,))

    @classmethod
    def create_user_register_token(cls, email, token):
        """
        Create a new registration token for a user.

        Args:
            email (str): The user's email.
            token (str): The registration token.
        """
        sql = schemafy("INSERT INTO enhancifai.user_register_tokens (email, token) VALUES (%s, %s)")
        write_db.do('execute', sql=sql, data=(email, token,))

    @classmethod
    def redeem_user_register_token(cls, email, token):
        """
        Mark a registration token as redeemed for a user.

        Args:
            email (str): The user's email.
            token (str): The registration token.
        """
        sql = schemafy("UPDATE enhancifai.user_register_tokens SET redeemed = TRUE WHERE email = %s AND token = %s;")
        write_db.do('execute', sql=sql, data=(email, token,))

class UsersDbLoginTokens:
    """
    A class to handle operations related to user login tokens.
    """

    @classmethod
    def check_user_login_token(cls, email, token):
        """
        Verify the existence of an unredeemed login token for the given email.

        Args:
            email (str): The user's email.
            token (str): The login token.
        
        Returns:
            bool: True if token exists and is unredeemed, otherwise False.
        """
        sql = schemafy("SELECT * FROM enhancifai.user_login_tokens WHERE email = %s AND token = %s AND redeemed = FALSE")
        return read_db.do('select_exists', sql=sql, data=(email, token,))

    @classmethod
    def create_user_login_token(cls, email, token):
        """
        Create a new login token for a user.

        Args:
            email (str): The user's email.
            token (str): The login token.
        """
        sql = schemafy("INSERT INTO enhancifai.user_login_tokens (email, token) VALUES (%s, %s)")
        write_db.do('execute', sql=sql, data=(email, token,))

    @classmethod
    def redeem_user_login_token(cls, email, token):
        """
        Mark a login token as redeemed for a user.

        Args:
            email (str): The user's email.
            token (str): The login token.
        """
        sql = schemafy("UPDATE enhancifai.user_login_tokens SET redeemed = TRUE WHERE email = %s AND token = %s;")
        write_db.do('execute', sql=sql, data=(email, token,))

class UsersDbPswdResetTokens:
    """
    A class to handle operations related to user password reset tokens.
    """

    @classmethod
    def check_user_password_reset_token(cls, email, token):
        """
        Verify the existence of an unredeemed password reset token for the given email.

        Args:
            email (str): The user's email.
            token (str): The password reset token.
        
        Returns:
            bool: True if token exists and is unredeemed, otherwise False.
        """
        sql = schemafy(
            "SELECT * FROM enhancifai.user_password_reset_tokens WHERE "
            "email = %s AND token = %s AND redeemed = FALSE"
        )
        return read_db.do('select_exists', sql=sql, data=(email, token,))

    @classmethod
    def get_email_from_password_reset_token(cls, token):
        """
        Retrieve the email address associated with an unredeemed password reset token.

        Args:
            token (str): The password reset token.
        
        Returns:
            str or None: The associated email if found, else None.
        """
        sql = schemafy("SELECT email FROM enhancifai.user_password_reset_tokens WHERE token = %s AND redeemed = FALSE")
        return read_db.do('select_one', sql=sql, data=(token,))

    @classmethod
    def create_user_password_reset_token(cls, email, token):
        """
        Create a new password reset token for a user.

        Args:
            email (str): The user's email.
            token (str): The password reset token.
        """
        sql = schemafy("INSERT INTO enhancifai.user_password_reset_tokens (email, token) VALUES (%s, %s)")
        write_db.do('execute', sql=sql, data=(email, token,))

    @classmethod
    def redeem_user_password_reset_token(cls, email, token):
        """
        Mark a password reset token as redeemed.

        Args:
            email (str): The user's email.
            token (str): The password reset token.
        """
        sql = schemafy("UPDATE enhancifai.user_password_reset_tokens SET redeemed = TRUE WHERE email = %s AND token = %s;")
        write_db.do('execute', sql=sql, data=(email, token,))
