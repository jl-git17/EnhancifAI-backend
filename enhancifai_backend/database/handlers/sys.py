from enhancifai_backend.database.access import read_db

class SysDbCore:
    """
    A class to manage system-level database operations,
    ensuring the database connection remains active.
    """

    @classmethod
    def keep_db_alive(cls):
        """
        Executes a simple query to maintain an active database connection.
        """
        # Run a simple query to keep the connection alive
        sql = "SELECT 1;"
        read_db.do('select_one', sql=sql)
