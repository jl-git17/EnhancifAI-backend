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
        # Insert new price into model_price_history with effective_date set to first of the month
        sql = schemafy("""
            INSERT INTO enhancifai.model_price_history (model_name, price_per_token, effective_date)
            VALUES (%s, %s, DATE_TRUNC('month', %s)::date)
            ON CONFLICT (model_name, effective_date) DO UPDATE
            SET price_per_token = EXCLUDED.price_per_token;
        """)
        data = (model_name, price_per_token, effective_date)
        write_db.do('execute', sql=sql, data=data)

    @classmethod
    def get_earliest_effective_month(cls):
        """
        Return the earliest month (YYYY-MM-01) in the model_price_history.
        If none, return None.
        """
        sql = schemafy("""
            SELECT MIN(effective_date) as earliest_date
            FROM enhancifai.model_price_history;
        """)
        result = read_db.do('select_one', sql=sql)
        return result['earliest_date'] if result and result['earliest_date'] else None

    @classmethod
    def get_model_prices_for_month(cls, year, month):
        """
        Get all model prices that were in effect for a specific year-month.
        
        We define 'in effect' as any record whose effective_date is in that month
        (i.e., [YYYY-MM-01, YYYY-MM-31]).
        
        You may choose to show exactly the entries from that month or 
        the price that was effective as of that month by querying the 
        latest price <= year-month.
        For simplicity, let's just fetch the rows with matching year-month.
        """
        start_of_month = f"{year}-{month:02d}-01"
        # Postgres trick to add 1 month and subtract 1 day:
        # or use date_trunc + interval
        sql = schemafy(f"""
            SELECT model_name, price_per_token, effective_date
            FROM enhancifai.model_price_history
            WHERE effective_date = DATE_TRUNC('month', DATE '{start_of_month}')
            ORDER BY model_name;
        """)
        return read_db.do('select', sql=sql)