from enhancifai_backend.database.handlers.utils import schemafy
from enhancifai_backend.database.access import read_db, write_db

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
        try:
            result = read_db.do('select_one', sql=sql)
            if result:
                return result
        except Exception as e:
            print(f"Error fetching AI settings: {e}")
        return {"openai_temperature": 0.5, "openai_temperature_batched": 0.5}

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
            SET openai_temperature = %s, openai_temperature_batched = %s;
        """)
        write_db.do('execute', sql=sql, data=(openai_temperature, openai_temperature_batched))
