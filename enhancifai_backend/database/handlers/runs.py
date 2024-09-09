import time
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

class RunsDbCore:
    """
    A class to handle database operations related to runs.
    """

    @classmethod
    def new_run(cls, user_id, source_type, source_filename):
        """
        Create a new run entry in the database.

        Parameters:
        user_id (str): The ID of the user.
        source_type (str): The type of the source.

        Returns:
        Any: Result of the write_db operation.
        """
        sql = schemafy("INSERT INTO enhancifai.runs (user_id, source_type, source_filename) VALUES (%s,%s,%s) RETURNING id;")
        return write_db.do('execute', sql=sql, data=(user_id, source_type, source_filename))

    @classmethod
    def new_run_call(cls, run_id, prompt, tokens_used):
        """
        Create a new run call entry in the database.

        Parameters:
        run_id (str): The ID of the run.
        prompt (str): The prompt used in the run call.
        tokens_used (int): The number of tokens used in the run call.

        Returns:
        Any: Result of the write_db operation.
        """
        sql = schemafy("INSERT INTO enhancifai.runs_calls (run_id, prompt, tokens_used) VALUES (%s,%s,%s);")
        return write_db.do('execute', sql=sql, data=(run_id, prompt, tokens_used))

    @classmethod
    def insert_run_details(cls, run_id, run_details):
        """
        Insert or update run details in the database.

        Parameters:
        run_id (str): The ID of the run.
        run_details (str): The details of the run.

        Returns:
        Any: Result of the write_db operation.
        """
        sql = schemafy("UPDATE enhancifai.runs SET run_details = %s WHERE id = %s;")
        return write_db.do('execute', sql=sql, data=(run_details, run_id))

    @classmethod
    def get_run_details(cls, run_id):
        """
        Retrieve the details of a specific run.

        Parameters:
        run_id (str): The ID of the run.

        Returns:
        Any: The details of the run.
        """
        sql = schemafy("SELECT run_details FROM enhancifai.runs WHERE id = %s;")
        return read_db.do('select_one', sql=sql, data=(run_id,))

    @classmethod
    def set_run_checkin(cls, run_id):
        """
        Set the check-in time for a run.

        Parameters:
        run_id (str): The ID of the run.

        Returns:
        Any: Result of the write_db operation.
        """
        current_time = time.time()
        sql = schemafy("UPDATE enhancifai.runs SET check_in = %s WHERE id = %s AND cancelled IS NOT TRUE;")
        return write_db.do('execute', sql=sql, data=(current_time, run_id))

    @classmethod
    def cancel_run(cls, run_id):
        """
        Cancel a run and update its status.

        Parameters:
        run_id (str): The ID of the run.

        Returns:
        Any: Result of the write_db operation.
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
        Get the status of a specific run.

        Parameters:
        run_id (str): The ID of the run.

        Returns:
        str: The status of the run.
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
        Check if a run has been cancelled.

        Parameters:
        run_id (str): The ID of the run.

        Returns:
        bool: True if the run is cancelled, False otherwise.
        """
        sql = schemafy("SELECT COALESCE(cancelled, FALSE) AS cancelled FROM enhancifai.runs WHERE id = %s;")
        result = read_db.do('select_one', sql=sql, data=(run_id,))
        return result['cancelled'] if result else False

    @classmethod
    def check_run_ownership(cls, user_id, run_id) -> bool:
        """
        Check if a user owns a specific run.

        Parameters:
        user_id (str): The ID of the user.
        run_id (str): The ID of the run.

        Returns:
        bool: True if the user owns the run, False otherwise.
        """
        sql = schemafy("SELECT * FROM enhancifai.runs WHERE user_id = %s AND id = %s")
        return read_db.do('select_exists', sql=sql, data=(user_id, run_id))

    @classmethod
    def get_user_id(cls, run_id):
        """
        Get the user_id associated with a specific run_id.

        Parameters:
        run_id (str): The ID of the run.

        Returns:
        int: The ID of the user.
        """
        sql = schemafy("SELECT user_id FROM enhancifai.runs WHERE id = %s;")
        result = read_db.do('select_one', sql=sql, data=(run_id,))
        return result['user_id'] if result else None

    @classmethod
    def get_run_file_url(cls, run_id):
        """
        Retrieve the file URL for a given run ID from the run_details JSONB column.
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
        Retrieve the source filename for a given run ID.

        Parameters:
        run_id (str): The ID of the run.

        Returns:
        str: The source filename.
        """
        sql = schemafy("SELECT source_filename FROM enhancifai.runs WHERE id = %s;")
        result = read_db.do('select_one', sql=sql, data=(run_id,))
        return result['source_filename'] if result else None
