from enhancifai_backend.database.handlers.utils import schemafy
from enhancifai_backend.database.access import read_db, write_db


class PromptsDbCore:
    """
    A class to handle database operations related to prompts.
    """

    @classmethod
    def get_latest_prompt_by_user(cls, user_id):
        """
        Retrieve the latest prompt for a user.
        
        Parameters:
        user_id (int): The ID of the user.
        
        Returns:
        dict: The latest prompt and its metadata.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.prompts
            WHERE user_id = %s
            ORDER BY version DESC
            LIMIT 1;
        """)
        return read_db.do('select_one', sql=sql, data=(user_id,))

    @classmethod
    def get_prompt_versions_by_user(cls, user_id):
        """
        Retrieve all prompt versions for a user.
        
        Parameters:
        user_id (int): The ID of the user.
        
        Returns:
        list: A list of all prompt versions and metadata for the user.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.prompts
            WHERE user_id = %s
            ORDER BY version DESC;
        """)
        return read_db.do('select', sql=sql, data=(user_id,))

    @classmethod
    def save_new_prompt(cls, user_id, prompt, ai_engine):
        """
        Save a new prompt with versioning. It will increment the version number.
        
        Parameters:
        user_id (int): The ID of the user.
        prompt (str): The prompt text.
        ai_engine (str): The AI engine used.
        
        Returns:
        None
        """
        # Get the latest version number
        latest_prompt = cls.get_latest_prompt_by_user(user_id)
        new_version = (latest_prompt['version'] + 1) if latest_prompt else 1

        sql = schemafy("""
            INSERT INTO enhancifai.prompts (user_id, prompt, ai_engine, version)
            VALUES (%s, %s, %s, %s);
        """)
        write_db.do('execute', sql=sql, data=(user_id, prompt, ai_engine, new_version,))

    @classmethod
    def get_prompt_by_version(cls, user_id, version):
        """
        Retrieve a specific prompt version for a user.
        
        Parameters:
        user_id (int): The ID of the user.
        version (int): The version number of the prompt.
        
        Returns:
        dict: The prompt and its metadata.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.prompts
            WHERE user_id = %s AND version = %s;
        """)
        return read_db.do('select_one', sql=sql, data=(user_id, version,))

class ModelPricesDbCore:
    @classmethod
    def get_all_model_prices(cls):
        sql = schemafy("""
            SELECT DISTINCT ON (model_name)
                model_name, price_per_token, effective_date
            FROM enhancifai.model_price_history
            ORDER BY model_name, effective_date DESC;
        """)
        return read_db.do('select', sql=sql)

    @classmethod
    def update_model_price(cls, model_name, price_per_token, effective_date):
        """
        Update model price and insert into history.
        """
        # Insert new price into model_price_history
        sql = schemafy("""
            INSERT INTO enhancifai.model_price_history (model_name, price_per_token, effective_date)
            VALUES (%s, %s, %s)
            ON CONFLICT (model_name, effective_date) DO UPDATE
            SET price_per_token = EXCLUDED.price_per_token;
        """)
        data = (model_name, price_per_token, effective_date)
        write_db.do('execute', sql=sql, data=data)
