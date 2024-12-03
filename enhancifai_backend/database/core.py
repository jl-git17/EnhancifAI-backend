import os
import psycopg2
from psycopg2.extras import DictCursor
import re
import time

RETURNING_REGEX = re.compile(r"RETURNING (\w+);")
RETRY_LIMIT = 3
RETRY_DELAY = 1  # in seconds

class DbSession:

    def __init__(self, pref):
        self.pref = pref
        self.load_config()
        self.new_conn()

    def load_config(self):
        self.config = {}
        self.config['db_host'] = os.getenv('DB_HOST')
        self.config['db_name'] = os.getenv('DB_NAME')
        self.config['db_username'] = os.getenv('DB_USERNAME')
        self.config['db_password'] = os.getenv('DB_PASSWORD')
        self.config['schema'] = os.getenv('DB_SCHEMA')

    def new_conn(self):
        try:
            self.conn = psycopg2.connect(
                host=self.config['db_host'],
                database=self.config['db_name'],
                user=self.config['db_username'],
                password=self.config['db_password'],
                application_name=self.config['schema'] + '-' + self.pref,
                connect_timeout=60,
                keepalives=2
            )
            self.conn.autocommit = True
            
        except psycopg2.OperationalError as e:
            if self.config['db_name'] in e.args[0] and "does not exist" in e.args[0]:
                print(f"No database found. Please create a '{self.config['db_name']}' database in PostgreSQL.")
                os._exit(1)
            else:
                print(e)
                os._exit(1)
    
    def _process(self, query_type, sql='', data=None):
        if query_type == 'select':
            return self._select(sql, data)
        elif query_type == 'select_one':
            return self._select_one(sql, data)
        elif query_type == 'select_exists':
            return self._select_exists(sql, data)
        elif query_type == 'execute':
            res = self._execute(sql, data)
            self._commit()
            return res
        elif query_type == 'commit':
            self._commit()
        else:
            raise Exception(f"Invalid query type passed: {query_type}")

    def do(self, query_type, sql='', data=None):
        attempt = 0
        while attempt < RETRY_LIMIT:
            try:
                return self._process(query_type=query_type, sql=sql, data=data)
            except psycopg2.InterfaceError as err:
                if "connection" in err.args[0]:
                    attempt += 1
                    print(f"Connection lost. Attempting to reconnect... (Attempt {attempt}/{RETRY_LIMIT})")
                    time.sleep(RETRY_DELAY)  # Delay before retrying
                    self.new_conn()
                else:
                    print(f"An unexpected database error occurred: {err}")
                    raise
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                raise
        print("Reached the maximum number of retries for reconnection. Exiting.")
        os._exit(1)

    def _select(self, sql, data):
        assert "SELECT" in sql, "Only SELECT queries are allowed."
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, data)
            res = cur.fetchall()
        _res = []
        for r in res:
            _res.append(dict(r))
        if res:
            return _res
        else:
            return None

    def _select_one(self, sql, data):
        assert "SELECT" in sql, "Only SELECT queries are allowed."
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(sql, data)
            res = cur.fetchone()
        if res:
            return dict(res)
        else:
            return None
    
    def _select_exists(self, sql, data) -> bool:
        assert "SELECT" in sql, "Only SELECT queries are allowed."
        res = self._select_one(f"SELECT EXISTS ({sql});", data)
        return res['exists']

    def _execute(self, sql, data=None):
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            if data:
                cur.execute(sql, data)
            else:
                cur.execute(sql)
            
            # If the SQL contains RETURNING, fetch the returned row
            if "RETURNING" in sql:
                returned_row = cur.fetchone()
                return dict(returned_row) if returned_row else None


    def _commit(self):
        self.conn.commit()
