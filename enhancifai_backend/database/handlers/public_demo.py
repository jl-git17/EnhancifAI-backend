from enhancifai_backend.database.handlers.utils import schemafy
from enhancifai_backend.database.access import read_db, write_db

class PublicDemoDbCore:
    """
    Provides operations for managing free use cases, demo usage logs, demo settings, demo runs, and demo run calls.
    """

    # --- use_cases_free methods ---

    @classmethod
    def get_all_use_cases(cls):
        """
        Retrieve all free use cases.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.use_cases_free
            ORDER BY created_at DESC;
        """)
        return read_db.do('select', sql=sql)

    @classmethod
    def get_use_case_by_id(cls, use_case_id):
        """
        Retrieve a single use case by its id.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.use_cases_free
            WHERE id = %s;
        """)
        return read_db.do('select_one', sql=sql, data=(use_case_id,))

    @classmethod
    def create_use_case(cls, title, description=None, thumbnail=None,
                       sample_input_file_csv=None, sample_input_file_excel=None, prompt_config_file=None):
        """
        Create a new free use case.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.use_cases_free
                (title, description, thumbnail, sample_input_file_csv, sample_input_file_excel, prompt_config_file)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """)
        return write_db.do('execute', sql=sql, data=(title, description, thumbnail, sample_input_file_csv, sample_input_file_excel, prompt_config_file))

    @classmethod
    def update_use_case(cls, use_case_id, **kwargs):
        """
        Update fields of a use case by id. Only provided fields will be updated.
        """
        allowed_fields = ['title', 'description', 'thumbnail', 'sample_input_file_csv', 'sample_input_file_excel', 'prompt_config_file', 'updated_at']
        set_clauses = []
        values = []
        for field in allowed_fields:
            if field in kwargs:
                set_clauses.append(f"{field} = %s")
                values.append(kwargs[field])
        if not set_clauses:
            return None
        # Always update updated_at
        set_clauses.append("updated_at = now()")
        sql = schemafy(f"""
            UPDATE enhancifai.use_cases_free
            SET {', '.join(set_clauses)}
            WHERE id = %s;
        """)
        values.append(use_case_id)
        return write_db.do('execute', sql=sql, data=tuple(values))

    @classmethod
    def delete_use_case(cls, use_case_id):
        """
        Delete a use case by id.
        """
        sql = schemafy("""
            DELETE FROM enhancifai.use_cases_free
            WHERE id = %s;
        """)
        return write_db.do('execute', sql=sql, data=(use_case_id,))

    # --- demo_usage_logs methods ---

    @classmethod
    def log_demo_usage(cls, ip_address, use_case_id, model_name, tokens_used, status):
        """
        Log a demo usage event.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.demo_usage_logs
                (ip_address, use_case_id, model_name, tokens_used, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """)
        return write_db.do('execute', sql=sql, data=(ip_address, use_case_id, model_name, tokens_used, status))

    @classmethod
    def get_demo_usage_logs(cls, use_case_id=None, ip_address=None, limit=100):
        """
        Retrieve demo usage logs, optionally filtered by use_case_id or ip_address.
        """
        filters = []
        values = []
        if use_case_id:
            filters.append("use_case_id = %s")
            values.append(use_case_id)
        if ip_address:
            filters.append("ip_address = %s")
            values.append(ip_address)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        sql = schemafy(f"""
            SELECT * FROM enhancifai.demo_usage_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s;
        """)
        values.append(limit)
        return read_db.do('select', sql=sql, data=tuple(values))

class PublicDemoSettingsDbCore:
    """
    Provides operations for managing demo settings such as model defaults and fallbacks.
    """

    @classmethod
    def get_demo_settings(cls):
        """
        Retrieve the demo settings (model_default, model_fallback).
        """
        sql = schemafy("""
            SELECT model_default, model_fallback FROM enhancifai.demo_settings LIMIT 1;
        """)
        return read_db.do('select_one', sql=sql)

    @classmethod
    def update_demo_settings(cls, model_default=None, model_fallback=None):
        """
        Update the demo settings (model_default, model_fallback).
        """
        set_clauses = []
        values = []
        if model_default is not None:
            set_clauses.append("model_default = %s")
            values.append(model_default)
        if model_fallback is not None:
            set_clauses.append("model_fallback = %s")
            values.append(model_fallback)
        if not set_clauses:
            return None
        set_clauses.append("updated_at = now()")
        sql = schemafy(f"""
            UPDATE enhancifai.demo_settings
            SET {', '.join(set_clauses)}
            WHERE id = (SELECT id FROM enhancifai.demo_settings LIMIT 1);
        """)
        return write_db.do('execute', sql=sql, data=tuple(values))

class PublicDemoRunsDbCore:
    """
    Provides operations for managing demo runs and their associated calls.
    This class handles the creation, retrieval, updating, and cancellation of demo runs.
    """
    @classmethod
    def create_demo_run(cls, use_case_id, session_id, ip_address, source_type, source_filename):
        """
        Create a new demo run.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.demo_runs
                (use_case_id, session_id, ip_address, source_type, source_filename)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """)
        return write_db.do('execute', sql=sql, data=(use_case_id, session_id, ip_address, source_type, source_filename))

    @classmethod
    def get_demo_run_by_id(cls, demo_run_id):
        """
        Retrieve a demo run by its id.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.demo_runs
            WHERE id = %s;
        """)
        return read_db.do('select_one', sql=sql, data=(demo_run_id,))

    @classmethod
    def update_demo_run_details(cls, demo_run_id, run_details):
        """
        Update the run_details JSONB field for a demo run.
        """
        sql = schemafy("""
            UPDATE enhancifai.demo_runs
            SET run_details = %s
            WHERE id = %s;
        """)
        return write_db.do('execute', sql=sql, data=(run_details, demo_run_id))

    @classmethod
    def set_demo_run_checkin(cls, demo_run_id, check_in_time):
        """
        Update the check_in timestamp for a demo run.
        """
        sql = schemafy("""
            UPDATE enhancifai.demo_runs
            SET check_in = %s
            WHERE id = %s AND cancelled IS NOT TRUE;
        """)
        return write_db.do('execute', sql=sql, data=(check_in_time, demo_run_id))

    @classmethod
    def cancel_demo_run(cls, demo_run_id):
        """
        Mark a demo run as cancelled and update its status in run_details.
        """
        sql = schemafy("""
            UPDATE enhancifai.demo_runs
            SET cancelled = TRUE,
                run_details = jsonb_set(run_details, '{status}', '"cancelled"')
            WHERE id = %s;
        """)
        return write_db.do('execute', sql=sql, data=(demo_run_id,))

    @classmethod
    def get_demo_run_status(cls, demo_run_id):
        """
        Fetch the current status of a demo run.
        """
        sql = schemafy("""
            SELECT run_details->>'status' AS status
            FROM enhancifai.demo_runs
            WHERE id = %s;
        """)
        result = read_db.do('select_one', sql=sql, data=(demo_run_id,))
        return result['status'] if result else None

    @classmethod
    def is_demo_run_cancelled(cls, demo_run_id):
        """
        Determine if a demo run has been cancelled.
        """
        sql = schemafy("""
            SELECT COALESCE(cancelled, FALSE) AS cancelled
            FROM enhancifai.demo_runs
            WHERE id = %s;
        """)
        result = read_db.do('select_one', sql=sql, data=(demo_run_id,))
        return result['cancelled'] if result else False


class PublicDemoRunCallsDbCore:
    """
    Provides operations for managing demo run calls.
    """

    @classmethod
    def create_demo_run_call(cls, demo_run_id, prompt, tokens_used):
        """
        Create a new prompt call for a demo run.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.demo_run_calls
                (demo_run_id, prompt, tokens_used)
            VALUES (%s, %s, %s)
            RETURNING id;
        """)
        return write_db.do('execute', sql=sql, data=(demo_run_id, prompt, tokens_used))

    @classmethod
    def get_demo_run_calls(cls, demo_run_id):
        """
        Retrieve all prompt calls for a given demo run.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.demo_run_calls
            WHERE demo_run_id = %s
            ORDER BY id ASC;
        """)
        return read_db.do('select', sql=sql, data=(demo_run_id,))

    @classmethod
    def get_demo_run_call_by_id(cls, call_id):
        """
        Retrieve a single demo run call by its id.
        """
        sql = schemafy("""
            SELECT * FROM enhancifai.demo_run_calls
            WHERE id = %s;
        """)
        return read_db.do('select_one', sql=sql, data=(call_id,))
