from enhancifai_backend.database.access import read_db

class SysDbCore:
    """
    A class to handle system-level database operations.
    """

    @classmethod
    def keep_db_alive(cls):
        """
        Run a simple query to keep the database connection alive.

        Returns:
        None
        """
        # Run a simple query to keep the connection alive
        sql = "SELECT 1;"
        read_db.do('select_one', sql=sql)
