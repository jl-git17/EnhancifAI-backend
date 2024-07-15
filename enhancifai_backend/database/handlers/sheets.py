import pickle
from google.oauth2.credentials import Credentials
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

class SheetsDbCore:

    @classmethod
    def update_user_google_credentials(cls, user_id, creds: Credentials):
        """
        Update Google credentials for a user.

        Parameters:
        user_id (str): The ID of the user.
        creds (google.oauth2.credentials.Credentials): The Google credentials.

        Returns:
        None
        """
        creds_bytes = pickle.dumps(creds)
        sql = schemafy("""
            INSERT INTO enhancifai.google_sheets_credentials (user_id, credentials) 
            VALUES (%s, %s) 
            ON CONFLICT (user_id) DO UPDATE 
            SET credentials = EXCLUDED.credentials, 
            updated_at = now();
        """)
        write_db.do('execute', sql=sql, data=(user_id, creds_bytes))
    
    @classmethod
    def get_user_google_credentials(cls, user_id) -> Credentials:
        """
        Retrieve Google credentials for a user.

        Parameters:
        user_id (str): The ID of the user.

        Returns:
        google.oauth2.credentials.Credentials: The Google credentials.
        """
        sql = schemafy("SELECT credentials FROM enhancifai.google_sheets_credentials WHERE user_id = %s;")
        result = read_db.do('select_one', sql=sql, data=(user_id,))
        if result:
            creds_bytes = result['credentials']
            return pickle.loads(creds_bytes)
        return None
    
    @classmethod
    def store_oauth_state(cls, user_id, state):
        """
        Store the OAuth state for a user.

        Parameters:
        user_id (str): The ID of the user.
        state (str): The OAuth state.

        Returns:
        None
        """
        sql = schemafy("""
            INSERT INTO enhancifai.google_oauth_state (user_id, state)
            VALUES (%s, %s)
            ON CONFLICT (user_id, state) DO NOTHING;
        """)
        write_db.do('execute', sql=sql, data=(user_id, state,))

    @classmethod
    def get_oauth_state(cls, state):
        """
        Retrieve the user ID associated with an OAuth state.

        Parameters:
        state (str): The OAuth state.

        Returns:
        int: The user ID.
        """
        sql = schemafy("SELECT user_id FROM enhancifai.google_oauth_state WHERE state = %s;")
        result = read_db.do('select_one', sql=sql, data=(state,))
        return result['user_id'] if result else None

    @classmethod
    def delete_oauth_state(cls, state):
        """
        Delete the OAuth state after use.

        Parameters:
        state (str): The OAuth state.

        Returns:
        None
        """
        sql = schemafy("DELETE FROM enhancifai.google_oauth_state WHERE state = %s;")
        write_db.do('execute', sql=sql, data=(state,))
