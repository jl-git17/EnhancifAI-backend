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
