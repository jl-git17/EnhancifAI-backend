import time
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

class RunsDbCore:
    """
    Handles database operations related to runs.
    """

    @classmethod
    def new_run(cls, user_id, source_type, source_filename):
        """
        Insert a new run into the database.
        
        Parameters:
            user_id (str): The identifier for the user.
            source_type (str): The type/category of the source.
            source_filename (str): Filename of the source.
        
        Returns:
            The newly created run's id if successful, otherwise None.
        """
        sql = schemafy("INSERT INTO enhancifai.runs (user_id, source_type, source_filename) VALUES (%s,%s,%s) RETURNING id;")
        result = write_db.do('execute', sql=sql, data=(user_id, source_type, source_filename))
        if result:
            return result['id']
        return None

    @classmethod
    def new_run_call(cls, run_id, prompt, tokens_used):
        """
        Record a new run call in the database.
        
        Parameters:
            run_id (str): The run's identifier.
            prompt (str): The prompt text used.
            tokens_used (int): The number of tokens consumed.
        
        Returns:
            The result from the database operation.
        """
        sql = schemafy("INSERT INTO enhancifai.runs_calls (run_id, prompt, tokens_used) VALUES (%s,%s,%s);")
        return write_db.do('execute', sql=sql, data=(run_id, prompt, tokens_used))

    @classmethod
    def insert_run_details(cls, run_id, run_details):
        """
        Update run details in the database.
        
        Parameters:
            run_id (str): The run's identifier.
            run_details (str): The details to update.
        
        Returns:
            The result from the database operation.
        """
        sql = schemafy("UPDATE enhancifai.runs SET run_details = %s WHERE id = %s;")
        return write_db.do('execute', sql=sql, data=(run_details, run_id))

    @classmethod
    def get_run_details(cls, run_id):
        """
        Retrieve details for a given run.
        
        Parameters:
            run_id (str): The run's identifier.
        
        Returns:
            The run details if found, otherwise None.
        """
        sql = schemafy("SELECT run_details FROM enhancifai.runs WHERE id = %s;")
        return read_db.do('select_one', sql=sql, data=(run_id,))

    @classmethod
    def set_run_checkin(cls, run_id):
        """
        Update the check-in timestamp for a run.
        
        Parameters:
            run_id (str): The run's identifier.
        
        Returns:
            The result from the database operation.
        """
        current_time = time.time()
        sql = schemafy("UPDATE enhancifai.runs SET check_in = %s WHERE id = %s AND cancelled IS NOT TRUE;")
        return write_db.do('execute', sql=sql, data=(current_time, run_id))

    @classmethod
    def cancel_run(cls, run_id):
        """
        Mark a run as cancelled and update its status.
        
        Parameters:
            run_id (str): The run's identifier.
        
        Returns:
            The result from the database operation.
        """
        sql = schemafy("""
            UPDATE enhancifai.runs 
            SET cancelled = TRUE, 
                run_details = jsonb_set(run_details, '{status}', '"cancelled"')
            WHERE id = %s;
        """)
        return write_db.do('execute', sql=sql, data=(run_id,))

    @classmethod
    def get_run_status(cls, run_id):
        """
        Fetch the current status of a run.
        
        Parameters:
            run_id (str): The run's identifier.
        
        Returns:
            A string indicating the run's status or None if not found.
        """
        sql = schemafy("""
            SELECT run_details->>'status' AS status 
            FROM enhancifai.runs 
            WHERE id = %s;
        """)
        result = read_db.do('select_one', sql=sql, data=(run_id,))
        return result['status'] if result else None

    @classmethod
    def is_run_cancelled(cls, run_id):
        """
        Determine if a run has been cancelled.
        
        Parameters:
            run_id (str): The run's identifier.
        
        Returns:
            True if the run is cancelled, otherwise False.
        """
        sql = schemafy("SELECT COALESCE(cancelled, FALSE) AS cancelled FROM enhancifai.runs WHERE id = %s;")
        result = read_db.do('select_one', sql=sql, data=(run_id,))
        return result['cancelled'] if result else False

    @classmethod
    def check_run_ownership(cls, user_id, run_id) -> bool:
        """
        Verify if a user owns the specified run.
        
        Parameters:
            user_id (str): The user's identifier.
            run_id (str): The run's identifier.
        
        Returns:
            True if the user is the owner, otherwise False.
        """
        sql = schemafy("SELECT * FROM enhancifai.runs WHERE user_id = %s AND id = %s")
        return read_db.do('select_exists', sql=sql, data=(user_id, run_id))

    @classmethod
    def get_user_id(cls, run_id):
        """
        Retrieve the user ID associated with a run.
        
        Parameters:
            run_id (str): The run's identifier.
        
        Returns:
            The user ID if found, otherwise None.
        """
        sql = schemafy("SELECT user_id FROM enhancifai.runs WHERE id = %s;")
        result = read_db.do('select_one', sql=sql, data=(run_id,))
        return result['user_id'] if result else None

    @classmethod
    def get_run_file_url(cls, run_id):
        """
        Extract the file URL from the run details JSONB field.
        
        Parameters:
            run_id (str): The run's identifier.
        
        Returns:
            The file URL if present, otherwise None.
        """
        sql = schemafy("SELECT run_details FROM enhancifai.runs WHERE id = %s;")
        result = read_db.do('select_one', sql=sql, data=(run_id,))

        if result and 'run_details' in result:
            run_details = result['run_details']
            file_url = run_details.get('details', {}).get('file_url')
            return file_url

        return None

    @classmethod
    def get_source_filename(cls, run_id):
        """
        Retrieve the source filename for the specified run.
        
        Parameters:
            run_id (str): The run's identifier.
        
        Returns:
            The source filename if found, otherwise None.
        """
        sql = schemafy("SELECT source_filename FROM enhancifai.runs WHERE id = %s;")
        result = read_db.do('select_one', sql=sql, data=(run_id,))
        return result['source_filename'] if result else None
