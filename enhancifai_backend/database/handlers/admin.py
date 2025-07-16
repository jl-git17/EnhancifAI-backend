from enhancifai_backend.database.handlers.utils import schemafy
from enhancifai_backend.database.access import read_db, write_db


class PromptsDbCore:
    """
    Provides operations for managing user prompts with version control.
    """

    @classmethod
    def get_latest_prompt_by_user(cls, user_id):
        """
        Retrieve the most recent prompt for the specified user.
        
        Parameters:
            user_id (int): Unique identifier of the user.
        
        Returns:
            dict or None: The latest prompt details with metadata, or None if not found.
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
        Retrieve all prompt versions for the specified user, ordered from newest to oldest.
        
        Parameters:
            user_id (int): Unique identifier of the user.
        
        Returns:
            list: A list of dictionaries with prompt details and metadata.
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
        Save a new prompt for the user with an incremented version number.
        
        Parameters:
            user_id (int): Unique identifier of the user.
            prompt (str): The text content of the prompt.
            ai_engine (str): The AI engine used for the prompt.
        
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
        Retrieve a specific version of the user's prompt.
        
        Parameters:
            user_id (int): Unique identifier of the user.
            version (int): The version number of the prompt.
        
        Returns:
            dict or None: The prompt details if found, otherwise None.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.prompts
            WHERE user_id = %s AND version = %s;
        """)
        return read_db.do('select_one', sql=sql, data=(user_id, version,))

class ModelPricesDbCore:
    @classmethod
    def get_all_model_prices(cls):
        """
        Fetch all model pricing records ordered by model name, year, and month.
        
        Returns:
            list: A list of dictionaries containing model pricing data.
        """
        sql = schemafy("""
            SELECT model_name, month, year, price
            FROM enhancifai.model_pricing
            ORDER BY model_name, year, month;
        """)
        return read_db.do('select', sql=sql)

    @classmethod
    def update_model_price(cls, model_name, year, month, price):
        """
        Update or insert the pricing record for a model for a specific year and month.
        
        Parameters:
            model_name (str): The name of the model.
            year (int): The year of the pricing record.
            month (int): The month of the pricing record.
            price (float): The new price value.
        
        Returns:
            None
        """
        sql = schemafy("""
            INSERT INTO enhancifai.model_pricing (model_name, year, month, price)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (model_name, year, month)
            DO UPDATE SET price = EXCLUDED.price;
        """)
        write_db.do('execute', sql=sql, data=(model_name, year, month, price))

    @classmethod
    def get_earliest_effective_month(cls):
        """
        Determine the earliest month for which model pricing data is available.
        
        Returns:
            str or None: The earliest effective month in 'YYYY-MM-01' format, or None if data is absent.
        """
        sql = schemafy("""
            SELECT MIN(year) AS min_year, MIN(month) AS min_month
            FROM enhancifai.model_pricing;
        """)
        result = read_db.do('select_one', sql=sql)
        if result and result['min_year'] and result['min_month']:
            return f"{result['min_year']}-{result['min_month']:02d}-01"
        return None

    @classmethod
    def get_model_prices_for_month(cls, year, month):
        """
        Retrieve model pricing details for the specified year and month.
        
        Parameters:
            year (int): The year to filter records.
            month (int): The month to filter records.
        
        Returns:
            list: A list of dictionaries with model names and their corresponding prices.
        """
        sql = schemafy("""
            SELECT model_name, price
            FROM enhancifai.model_pricing
            WHERE year = %s AND month = %s
            ORDER BY model_name;
        """)
        return read_db.do('select', sql=sql, data=(year, month,))

class AISettingsDbCore:
    @classmethod
    def get_ai_settings(cls):
        """
        Fetch the AI settings from the database.
        
        Returns:
            dict: A dictionary containing the AI settings.
        """
        sql = schemafy("""
            SELECT openai_temperature, openai_temperature_batched FROM enhancifai.global_settings
            LIMIT 1;
        """)
        return read_db.do('select_one', sql=sql)

    @classmethod
    def update_ai_settings(cls, openai_temperature, openai_temperature_batched):
        """
        Update the AI settings in the database.
        
        Parameters:
            openai_temperature (float): The new temperature setting for OpenAI.
            openai_temperature_batched (float): The new batched temperature setting for OpenAI.
        
        Returns:
            None
        """
        sql = schemafy("""
            UPDATE enhancifai.global_settings
            SET openai_temperature = %s, openai_temperature_batched = %s
            WHERE id = 1;
        """)
        write_db.do('execute', sql=sql, data=(openai_temperature, openai_temperature_batched))