import time
from datetime import datetime

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
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s;")
        return read_db.do('select_one', sql=sql, data=(email,))

    @classmethod
    def get_user_by_id(cls, user_id):
        """
        Retrieve user details by user_id.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE user_id = %s;")
        return read_db.do('select_one', sql=sql, data=(user_id,))

    @classmethod
    def create_user_by_email(cls, email, name, password_hash):
        """
        Create a new user with the given email, name, and password hash.
        """
        sql = schemafy("INSERT INTO enhancifai.users (email, name, password_hash) VALUES (%s, %s, %s) RETURNING user_id;")
        return write_db.do('execute', sql=sql, data=(email, name, password_hash,))

    @classmethod
    def set_user_password(cls, user_id, new_password_hash):
        """
        Update the user's password hash.
        """
        sql = schemafy("UPDATE enhancifai.users SET password_hash = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(new_password_hash, user_id,))

    @classmethod
    def check_user_password(cls, email, password_hash):
        """
        Check if the provided password hash matches the user's password.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s AND password_hash = %s")
        return read_db.do('select_exists', sql=sql, data=(email, password_hash,))

    @classmethod
    def check_user_verified_email(cls, email):
        """
        Check if the user's email is verified.
        """
        sql = schemafy("SELECT email_verified FROM enhancifai.users WHERE email = %s;")
        result = read_db.do('select_one', sql=sql, data=(email,))
        return result['email_verified'] if result else False

    @classmethod
    def verify_email(cls, email):
        """
        Set the user's email as verified.
        """
        sql = schemafy("UPDATE enhancifai.users SET email_verified = TRUE WHERE email = %s;")
        write_db.do('execute', sql=sql, data=(email,))

    @classmethod
    def check_ai_consent(cls, user_id):
        """
        Check if the user has consented to AI usage.
        """
        sql = schemafy("SELECT ai_consent FROM enhancifai.users WHERE user_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result['ai_consent'].isoformat() if result else False

    @classmethod
    def update_ai_consent(cls, user_id):
        """
        Update the user's AI consent status to True.
        """
        sql = schemafy("UPDATE enhancifai.users SET ai_consent = TRUE WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(user_id,))

    @classmethod
    def update_user_profile(cls, user_id, name):
        """
        Update the user's profile information.
        """
        sql = schemafy("UPDATE enhancifai.users SET name = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(name, user_id,))

    @classmethod
    def get_session_expiration_by_user_id(cls, user_id):
        """
        Get the session expiration timestamp for a user by their ID.
        """
        sql = schemafy("SELECT expires_at FROM enhancifai.users_sessions WHERE user_id = %s ORDER BY created_at DESC LIMIT 1;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        return result['expires_at'] if result else None

    @classmethod
    def get_user_token_usage(cls, user_id: int, start_date: datetime, end_date: datetime) -> int:
        """
        Calculate the total tokens used by the user within a specific date range.
        
        Args:
            user_id (int): The ID of the user.
            start_date (datetime): The start datetime of the range.
            end_date (datetime): The end datetime of the range.
        
        Returns:
            int: Total tokens used within the specified range.
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
        Add token usage for the user.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.users_token_usage (user_id, run_id, model, tokens)
            VALUES (%s, %s, %s, %s);
        """)
        write_db.do('execute', sql=sql, data=(user_id, run_id, model, tokens,))

    @classmethod
    def create_session(cls, user_id, token, expires_at):
        """
        Create a new session for the user.
        """
        sql = schemafy("INSERT INTO enhancifai.users_sessions (user_id, token, expires_at) VALUES (%s, %s, %s);")
        write_db.do('execute', sql=sql, data=(user_id, token, expires_at,))

    @classmethod
    def get_user_invoices(cls, user_id):
        """
        Retrieve all invoices for the user.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.stripe_invoices 
            WHERE user_id = %s 
            ORDER BY created_at DESC;
        """)
        return read_db.do('select', sql=sql, data=(user_id,)) or []

    @classmethod
    def get_user_by_email_unverified(cls, email):
        """
        Retrieve user details by email without verifying email status.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s;")
        return read_db.do('select_one', sql=sql, data=(email,))

    @classmethod
    def cleanup_timed_out_jobs(cls):
        """
        Clean up any timed-out jobs or sessions if necessary.
        Implement as per your requirements.
        """
        # Example: Remove expired sessions
        sql = schemafy("DELETE FROM enhancifai.users_sessions WHERE expires_at < NOW();")
        write_db.do('execute', sql=sql)


class UsersDbRegisterTokens:
    """
    A class to handle database operations related to user registration tokens.
    """

    @classmethod
    def check_user_register_token(cls, email, token):
        """
        Check if a user registration token exists and is not redeemed.

        Parameters:
        email (str): The email of the user.
        token (str): The registration token.

        Returns:
        bool: True if the token exists and is not redeemed, False otherwise.
        """
        sql = schemafy("SELECT * FROM enhancifai.user_register_tokens WHERE email = %s AND token = %s AND redeemed = FALSE")
        return read_db.do('select_exists', sql=sql, data=(email, token,))
    
    @classmethod
    def create_user_register_token(cls, email, token):
        """
        Create a new user registration token.

        Parameters:
        email (str): The email of the user.
        token (str): The registration token.

        Returns:
        None
        """
        sql = schemafy("INSERT INTO enhancifai.user_register_tokens (email, token) VALUES (%s, %s)")
        write_db.do('execute', sql=sql, data=(email, token,))
    
    @classmethod
    def redeem_user_register_token(cls, email, token):
        """
        Redeem a user registration token.

        Parameters:
        email (str): The email of the user.
        token (str): The registration token.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.user_register_tokens SET redeemed = TRUE WHERE email = %s AND token = %s;")
        write_db.do('execute', sql=sql, data=(email, token,))

class UsersDbLoginTokens:
    """
    A class to handle database operations related to user login tokens.
    """

    @classmethod
    def check_user_login_token(cls, email, token):
        """
        Check if a user login token exists and is not redeemed.

        Parameters:
        email (str): The email of the user.
        token (str): The login token.

        Returns:
        bool: True if the token exists and is not redeemed, False otherwise.
        """
        sql = schemafy("SELECT * FROM enhancifai.user_login_tokens WHERE email = %s AND token = %s AND redeemed = FALSE")
        return read_db.do('select_exists', sql=sql, data=(email, token,))
    
    @classmethod
    def create_user_login_token(cls, email, token):
        """
        Create a new user login token.

        Parameters:
        email (str): The email of the user.
        token (str): The login token.

        Returns:
        None
        """
        sql = schemafy("INSERT INTO enhancifai.user_login_tokens (email, token) VALUES (%s, %s)")
        write_db.do('execute', sql=sql, data=(email, token,))
    
    @classmethod
    def redeem_user_login_token(cls, email, token):
        """
        Redeem a user login token.

        Parameters:
        email (str): The email of the user.
        token (str): The login token.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.user_login_tokens SET redeemed = TRUE WHERE email = %s AND token = %s;")
        write_db.do('execute', sql=sql, data=(email, token,))

class UsersDbPswdResetTokens:
    """
    A class to handle database operations related to user password reset tokens.
    """

    @classmethod
    def check_user_password_reset_token(cls, email, token):
        """
        Check if a user password reset token exists and is not redeemed.

        Parameters:
        email (str): The email of the user.
        token (str): The password reset token.

        Returns:
        bool: True if the token exists and is not redeemed, False otherwise.
        """
        sql = schemafy("SELECT * FROM enhancifai.user_password_reset_tokens WHERE email = %s AND token = %s AND redeemed = FALSE")
        return read_db.do('select_exists', sql=sql, data=(email, token,))
    
    @classmethod
    def get_email_from_password_reset_token(cls, token):
        """
        Retrieve the email associated with a password reset token.

        Parameters:
        token (str): The password reset token.

        Returns:
        Any: The email associated with the token.
        """
        sql = schemafy("SELECT email FROM enhancifai.user_password_reset_tokens WHERE token = %s AND redeemed = FALSE")
        return read_db.do('select_one', sql=sql, data=(token,))
    
    @classmethod
    def create_user_password_reset_token(cls, email, token):
        """
        Create a new user password reset token.

        Parameters:
        email (str): The email of the user.
        token (str): The password reset token.

        Returns:
        None
        """
        sql = schemafy("INSERT INTO enhancifai.user_password_reset_tokens (email, token) VALUES (%s, %s)")
        write_db.do('execute', sql=sql, data=(email, token,))
    
    @classmethod
    def redeem_user_password_reset_token(cls, email, token):
        """
        Redeem a user password reset token.

        Parameters:
        email (str): The email of the user.
        token (str): The password reset token.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.user_password_reset_tokens SET redeemed = TRUE WHERE email = %s AND token = %s;")
        write_db.do('execute', sql=sql, data=(email, token,))
