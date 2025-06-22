from enhancifai_backend.database.handlers.utils import schemafy
from enhancifai_backend.database.access import read_db, write_db

class PublicDemoDbCore:
    """
    Provides operations for managing free use cases and demo usage logs.
    """

    # --- use_cases_free methods ---

    @classmethod
    def get_all_use_cases(cls, user_id=None):
        """
        Retrieve all free use cases, optionally filtered by user_id.
        """
        if user_id:
            sql = schemafy("""
                SELECT * FROM enhancifai.use_cases_free
                WHERE user_id = %s
                ORDER BY created_at DESC;
            """)
            return read_db.do('select', sql=sql, data=(user_id,))
        else:
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
    def create_use_case(cls, user_id, title, description=None, thumbnail=None,
                       sample_input_file_csv=None, sample_input_file_excel=None, prompt_config_file=None):
        """
        Create a new free use case.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.use_cases_free
                (user_id, title, description, thumbnail, sample_input_file_csv, sample_input_file_excel, prompt_config_file)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """)
        return write_db.do('execute', sql=sql, data=(user_id, title, description, thumbnail, sample_input_file_csv, sample_input_file_excel, prompt_config_file))

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
    def log_demo_usage(cls, ip_address, session_id, use_case_id, model_name, tokens_used, status):
        """
        Log a demo usage event.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.demo_usage_logs
                (ip_address, session_id, use_case_id, model_name, tokens_used, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """)
        return write_db.do('execute', sql=sql, data=(ip_address, session_id, use_case_id, model_name, tokens_used, status))

    @classmethod
    def get_demo_usage_logs(cls, use_case_id=None, session_id=None, ip_address=None, limit=100):
        """
        Retrieve demo usage logs, optionally filtered by use_case_id, session_id, or ip_address.
        """
        filters = []
        values = []
        if use_case_id:
            filters.append("use_case_id = %s")
            values.append(use_case_id)
        if session_id:
            filters.append("session_id = %s")
            values.append(session_id)
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
