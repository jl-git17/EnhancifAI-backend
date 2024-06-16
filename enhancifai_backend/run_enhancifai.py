
import os
import sys
import logging
from typing import NoReturn
from enhancifai_backend.database.core import DbSession
from enhancifai_backend.database.handlers.utils import schemafy

from enhancifai_backend.server.serve import run_server

# Configure logging
logging.basicConfig(level=logging.INFO)

SOURCE_DIR = os.path.join(os.path.dirname(__file__), "database", "sql")

def process_sql_file(db: DbSession, filename: str) -> None:
    """Reads an SQL file, schemafies it, and executes it on the database."""
    filepath = os.path.join(SOURCE_DIR, filename)
    try:
        with open(filepath, 'r', encoding='UTF-8') as file:
            sql = schemafy(file.read())
            db.do('execute', sql)
    except IOError as e:
        print(f"Error reading file {filename}: {e}")
        sys.exit(1)

def prepare_database(db: DbSession) -> None:
    """Prepares the database by creating a schema and processing SQL files."""
    schema_name = os.getenv('DB_SCHEMA')
    if not schema_name:
        print("Environment variable 'DB_SCHEMA' not set.")
        sys.exit(1)

    db.do('execute', f"CREATE SCHEMA IF NOT EXISTS {schema_name};")
    for sql_file in ['schema.sql', 'migration.sql']:
        process_sql_file(db, sql_file)
    db.do('commit')

def run() -> NoReturn:
    """Main entrypoint that sets up the database and runs the server."""
    db = DbSession('setup')
    try:
        prepare_database(db)
        run_server()
    except KeyboardInterrupt:
        logging.info("EnhancifAI Backend interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(2)

if __name__ == "__main__":
    run()
