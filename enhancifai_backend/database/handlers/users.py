import time
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

from psycopg2.extras import Json

class UsersDbCore:
    """
    A class to handle database operations related to users.
    """

    @classmethod
    def get_user_by_id(cls, user_id):
        """
        Retrieve a user by their ID.

        Parameters:
        user_id (str): The ID of the user.

        Returns:
        Any: The user data.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE user_id = %s;")
        return read_db.do('select_one', sql=sql, data=(user_id,))
    
    @classmethod
    def get_user_name_by_id(cls, user_id):
        """
        Retrieve a user's name by their ID.

        Parameters:
        user_id (str): The ID of the user.

        Returns:
        Any: The user's name.
        """
        sql = schemafy("SELECT name FROM enhancifai.users WHERE user_id = %s;")
        return read_db.do('select_one', sql=sql, data=(user_id,))
    
    @classmethod
    def get_user_by_email(cls, email):
        """
        Retrieve a user by their email if the email is verified.

        Parameters:
        email (str): The email of the user.

        Returns:
        Any: The user data.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s AND email_verified = true;")
        return read_db.do('select_one', sql=sql, data=(email,))
    
    @classmethod
    def get_user_id_by_email(cls, email):
        """
        Retrieve a user's ID by their email.

        Parameters:
        email (str): The email of the user.

        Returns:
        Any: The user ID.
        """
        sql = schemafy("SELECT user_id FROM enhancifai.users WHERE email = %s;")
        return read_db.do('select_one', sql=sql, data=(email,))
    
    @classmethod
    def get_user_by_email_unverified(cls, email):
        """
        Retrieve a user by their email if the email is verified.

        Parameters:
        email (str): The email of the user.

        Returns:
        Any: The user data.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s;")
        return read_db.do('select_one', sql=sql, data=(email,))
    
    @classmethod
    def check_user_exists_email(cls, email):
        """
        Check if a user exists by their email.

        Parameters:
        email (str): The email of the user.

        Returns:
        bool: True if the user exists, False otherwise.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s")
        return read_db.do('select_exists', sql=sql, data=(email,))
    
    @classmethod
    def check_user_verified_email(cls, email) -> bool:
        """
        Check if a user account has verified their email address.

        Parameters:
        email (str): The email of the user.

        Returns:
        bool: True if the user has verified their email address, False otherwise.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email_verified = true AND email = %s")
        return read_db.do('select_exists', sql=sql, data=(email,))
    
    @classmethod
    def check_user_password(cls, email, password_hash) -> bool:
        """
        Check if the provided password hash matches the stored password hash for the user.

        Parameters:
        email (str): The email of the user.
        password_hash (str): The password hash to check.

        Returns:
        bool: True if the password matches, False otherwise.
        """
        sql = schemafy("SELECT * FROM enhancifai.users WHERE email = %s AND (password_hash IS NULL OR password_hash = %s)")
        return read_db.do('select_exists', sql=sql, data=(email, password_hash,))

    @classmethod
    def set_user_password(cls, user_id, password_hash):
        """
        Set a new password hash for the user.

        Parameters:
        user_id (str): The ID of the user.
        password_hash (str): The new password hash.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.users SET password_hash = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(password_hash, user_id, ))
    
    @classmethod
    def create_user_by_email(cls, email, name, password_hash=None):
        """
        Create a new user with email and optional password hash.

        Parameters:
        email (str): The email of the user.
        name (str): The name of the user.
        password_hash (str, optional): The password hash. Defaults to None.

        Returns:
        None
        """
        sql = schemafy("INSERT INTO enhancifai.users (email, name, password_hash) VALUES (%s,%s,%s);")
        write_db.do('execute', sql=sql, data=(email, name, password_hash,))
    
    @classmethod
    def create_user_by_apple(cls, email):
        """
        Create a new user using Apple login.

        Parameters:
        email (str): The email of the user.

        Returns:
        None
        """
        sql = schemafy("INSERT INTO enhancifai.users (email) VALUES (%s);")
        write_db.do('execute', sql=sql, data=(email,))
    
    @classmethod
    def create_user_by_google(cls, email, google_oauth_token):
        """
        Create a new user using Google login.

        Parameters:
        email (str): The email of the user.
        google_oauth_token (str): The Google OAuth token.

        Returns:
        None
        """
        sql = schemafy("INSERT INTO enhancifai.users (email, google_oauth_token) VALUES (%s, %s);")
        write_db.do('execute', sql=sql, data=(email, google_oauth_token,))
    
    @classmethod
    def update_google_login(cls, user_id, google_oauth_token):
        """
        Update Google OAuth token for a user.

        Parameters:
        user_id (str): The ID of the user.
        google_oauth_token (str): The new Google OAuth token.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.users SET google_oauth_token = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(google_oauth_token, user_id,))
    
    @classmethod
    def verify_email(cls, email):
        """
        Verify a user's email.

        Parameters:
        email (str): The email of the user.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.users SET email_verified = true WHERE email = %s;")
        write_db.do('execute', sql=sql, data=(email,))
    
    @classmethod
    def update_user_profile(cls, user_id, name):
        """
        Update a user's profile information.

        Parameters:
        user_id (str): The ID of the user.
        name (str): The new name of the user.

        Returns:
        None
        """
        sql = schemafy(
            "UPDATE enhancifai.users SET name = %s WHERE user_id = %s;"
        )
        write_db.do('execute', sql=sql, data=(name, user_id,))

    @classmethod
    def get_user_pending_jobs(cls, user_id):
        """
        Get the count of pending jobs for a user.

        Parameters:
        user_id (str): The ID of the user.

        Returns:
        int: The count of pending jobs.
        """
        sql = schemafy(
            "SELECT COUNT(*) FROM enhancifai.runs "
            "WHERE user_id = %s AND run_details->>'status' NOT IN ('completed', 'timed out', 'cancelled');"
        )
        return read_db.do('select_one', sql=sql, data=(user_id,))['count']
    
    @classmethod
    def cleanup_timed_out_jobs(cls):
        """
        Clean up jobs that have timed out.

        Returns:
        None
        """
        # Time-based timeout
        sql_time_based = schemafy("""
            UPDATE enhancifai.runs 
            SET run_details = jsonb_set(run_details, '{status}', '"timed out"')
            WHERE run_details->>'status' = 'pending'
            AND created_at < current_timestamp - interval '1 hour'
            AND cancelled IS NOT TRUE;
        """)
        write_db.do('execute', sql=sql_time_based)

        # Jobs in status 'new' but older than 1 minute (created_at)
        sql_new_jobs_timeout = schemafy("""
            UPDATE enhancifai.runs 
            SET run_details = jsonb_set(run_details, '{status}', '"timed out"')
            WHERE run_details->>'status' = 'new'
            AND created_at < current_timestamp - interval '1 minute'
            AND cancelled IS NOT TRUE;
        """)
        write_db.do('execute', sql=sql_new_jobs_timeout)

        # Check-in based timeout
        current_time = time.time()
        timeout_threshold = current_time - 30
        sql_check_in_based = schemafy("""
            UPDATE enhancifai.runs 
            SET run_details = jsonb_set(run_details, '{status}', '"timed out"')
            WHERE run_details->>'status' = 'pending'
            AND check_in IS NOT NULL 
            AND check_in < %s
            AND cancelled IS NOT TRUE;
        """)
        write_db.do('execute', sql=sql_check_in_based, data=(timeout_threshold,))
    
    @classmethod
    def add_token_usage(cls, user_id, model, tokens):
        """
        Add a token usage entry for a user.

        Parameters:
        user_id (int): The ID of the user.
        model (str): The model used.
        tokens (int): The number of tokens used.

        Returns:
        None
        """
        sql = schemafy("INSERT INTO enhancifai.users_token_usage (user_id, model, tokens) VALUES (%s, %s, %s);")
        write_db.do('execute', sql=sql, data=(user_id, model, tokens))
    
    @classmethod
    def assign_tier_to_user(cls, user_id, tier_id):
        """
        Assign a tier to a user.

        Parameters:
        user_id (int): The ID of the user.
        tier_id (int): The ID of the tier.

        Returns:
        None
        """
        sql = schemafy("INSERT INTO enhancifai.user_account_tiers (user_id, tier_id, assigned_at) VALUES (%s, %s, now()) ON CONFLICT (user_id) DO UPDATE SET tier_id = EXCLUDED.tier_id, assigned_at = now();")
        write_db.do('execute', sql=sql, data=(user_id, tier_id))
        cls.update_user_current_tier(user_id, tier_id)
    
    @classmethod
    def get_user_tier(cls, user_id):
        """
        Get the tier of a user.

        Parameters:
        user_id (int): The ID of the user.

        Returns:
        Any: The tier data.
        """
        sql = schemafy("SELECT t.* FROM enhancifai.account_tiers t JOIN enhancifai.user_account_tiers uat ON t.tier_id = uat.tier_id WHERE uat.user_id = %s;")
        return read_db.do('select_one', sql=sql, data=(user_id,))
    
    @classmethod
    def get_all_tiers(cls):
        """
        Get all available tiers.

        Returns:
        Any: The list of all tiers.
        """
        sql = schemafy("SELECT * FROM enhancifai.account_tiers;")
        return read_db.do('select_all', sql=sql)
    
    @classmethod
    def update_user_current_tier(cls, user_id, tier_id):
        """
        Update the user's current tier in the users table.

        Parameters:
        user_id (int): The ID of the user.
        tier_id (int): The ID of the tier.

        Returns:
        None
        """
        sql = schemafy("UPDATE enhancifai.users SET current_tier_id = %s WHERE user_id = %s;")
        write_db.do('execute', sql=sql, data=(tier_id, user_id))
    
    @classmethod
    def is_user_admin(cls, user_id) -> bool:
        sql = schemafy("SELECT * FROM enhancifai.users WHERE is_admin IS TRUE AND user_id = %s")
        return write_db.do('select_exists', sql=sql, data=(user_id,))
    
    @classmethod
    def check_ai_consent(cls, user_id) -> bool:
        sql = schemafy("SELECT * FROM enhancifai.users WHERE ai_consent IS NOT NULL AND user_id = %s")
        return write_db.do('select_exists', sql=sql, data=(user_id,))
    
    @classmethod
    def update_ai_consent(cls, user_id) -> bool:
        sql = schemafy("UPDATE enhancifai.users SET ai_consent = NOW() WHERE user_id = %s;")
        return write_db.do('execute', sql=sql, data=(user_id,))
    
    @classmethod
    def create_session(cls, user_id, token, expires_at):
        """
        Create a new session for a user.

        Parameters:
        user_id (int): The ID of the user.
        token (str): The session token (JWT).
        expires_at (str): The expiration timestamp of the session.

        Returns:
        None
        """
        sql = schemafy("INSERT INTO enhancifai.users_sessions (user_id, token, expires_at) VALUES (%s, %s, %s);")
        write_db.do('execute', sql=sql, data=(user_id, token, expires_at,))

    @classmethod
    def is_token_expired(cls, token):
        """
        Check if the provided token is expired.

        Parameters:
        token (str): The session token (JWT).

        Returns:
        bool: True if the token is expired, False otherwise.
        """
        sql = schemafy("SELECT expires_at < now() FROM enhancifai.users_sessions WHERE token = %s;")
        return read_db.do('select_one', sql=sql, data=(token,))

    @classmethod
    def get_session_expiration_by_user_id(cls, user_id):
        """
        Get the session expiration timestamp for a user by their ID.

        Parameters:
        user_id (int): The ID of the user.

        Returns:
        str: The expiration timestamp of the session.
        """
        sql = schemafy("SELECT expires_at FROM enhancifai.users_sessions WHERE user_id = %s ORDER BY created_at DESC LIMIT 1;")
        return read_db.do('select_one', sql=sql, data=(user_id,))

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
