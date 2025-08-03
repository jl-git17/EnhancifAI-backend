import time
from enhancifai_backend.database.handlers.utils import schemafy
from enhancifai_backend.database.access import read_db, write_db


class MicrositeFunctionsDbCore:
    """
    Provides operations for managing microsite functions and their prompt pairs.
    """

    @classmethod
    def get_all_functions(cls):
        """
        Retrieve all microsite functions.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.microsite_functions
            ORDER BY id;
        """)
        return read_db.do('select', sql=sql)

    @classmethod
    def get_function_by_id(cls, function_id):
        """
        Retrieve a microsite function by its id.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.microsite_functions
            WHERE id = %s;
        """)
        return read_db.do('select_one', sql=sql, data=(function_id,))

    @classmethod
    def get_function_by_name(cls, function_name):
        """
        Retrieve a microsite function by its name.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.microsite_functions
            WHERE function_name = %s;
        """)
        return read_db.do('select_one', sql=sql, data=(function_name,))

    @classmethod
    def create_function(cls, function_name, prompt):
        """
        Create a new microsite function.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.microsite_functions (function_name, prompt)
            VALUES (%s, %s)
            RETURNING id;
        """)
        return write_db.do('execute', sql=sql, data=(function_name, prompt))

    @classmethod
    def update_function(cls, function_id, function_name=None, prompt=None):
        """
        Update fields of a microsite function by id.
        """
        # Ensure at least one field to update
        if function_name is None and prompt is None:
            raise ValueError("No fields provided for update.")
        # Prevent duplicate function names
        if function_name is not None:
            existing = cls.get_function_by_name(function_name)
            if existing and existing.get('id') != function_id:
                raise ValueError(f"Function name '{function_name}' already exists.")
        set_clauses = []
        values = []
        if function_name is not None:
            set_clauses.append("function_name = %s")
            values.append(function_name)
        if prompt is not None:
            set_clauses.append("prompt = %s")
            values.append(prompt)
        if not set_clauses:
            # Should not happen due to initial check
            raise ValueError("No valid fields to update.")
        sql = schemafy(f"""
            UPDATE enhancifai.microsite_functions
            SET {', '.join(set_clauses)}
            WHERE id = %s;
        """)
        values.append(function_id)
        # Execute update and return the updated record
        write_db.do('execute', sql=sql, data=tuple(values))
        return cls.get_function_by_id(function_id)

    @classmethod
    def delete_function(cls, function_id):
        """
        Delete a microsite function by id.
        """
        sql = schemafy("""
            DELETE FROM enhancifai.microsite_functions
            WHERE id = %s;
        """)
        return write_db.do('execute', sql=sql, data=(function_id,))


class MicrositesRunsDbCore:
    """
    Handles database operations related to runs.
    """

    @classmethod
    def new_run(cls, ip_address, source_type):
        """
        Insert a new run into the database.
        
        Parameters:
            ip_address (str): The IP address of the user.
            source_type (str): The type/category of the source.
            source_filename (str): Filename of the source.
        
        Returns:
            The newly created run's id if successful, otherwise None.
        """
        sql = schemafy("INSERT INTO enhancifai.microsite_function_runs (ip_address, source_type) VALUES (%s,%s) RETURNING id;")
        result = write_db.do('execute', sql=sql, data=(ip_address, source_type))
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
        sql = schemafy("INSERT INTO enhancifai.microsite_function_runs_calls (run_id, prompt, tokens_used) VALUES (%s,%s,%s);")
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
        sql = schemafy("UPDATE enhancifai.microsite_function_runs SET run_details = %s WHERE id = %s;")
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
        sql = schemafy("SELECT run_details FROM enhancifai.microsite_function_runs WHERE id = %s;")
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
        sql = schemafy("UPDATE enhancifai.microsite_function_runs SET check_in = %s WHERE id = %s AND cancelled IS NOT TRUE;")
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
            UPDATE enhancifai.microsite_function_runs
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
            FROM enhancifai.microsite_function_runs
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
        sql = schemafy("SELECT COALESCE(cancelled, FALSE) AS cancelled FROM enhancifai.microsite_function_runs WHERE id = %s;")
        result = read_db.do('select_one', sql=sql, data=(run_id,))
        return result['cancelled'] if result else False

    @classmethod
    def get_run_file_url(cls, run_id):
        """
        Extract the file URL from the run details JSONB field.
        
        Parameters:
            run_id (str): The run's identifier.
        
        Returns:
            The file URL if present, otherwise None.
        """
        sql = schemafy("SELECT run_details FROM enhancifai.microsite_function_runs WHERE id = %s;")
        result = read_db.do('select_one', sql=sql, data=(run_id,))

        if result and 'run_details' in result:
            run_details = result['run_details']
            file_url = run_details.get('details', {}).get('file_url')
            return file_url

        return None

