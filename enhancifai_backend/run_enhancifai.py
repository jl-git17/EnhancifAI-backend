
import os
import sys
import logging
import signal
from typing import NoReturn

from enhancifai_backend.config import settings
from enhancifai_backend.database.core import DbSession
from enhancifai_backend.database.handlers.utils import schemafy
from enhancifai_backend.server.serve import run_server


# Configure logging to stdout with a specific format
production = settings.production
print("Logging initialized: production =", production)
logging.basicConfig(
    level=logging.ERROR if production else logging.DEBUG,
    handlers=[logging.StreamHandler(sys.stdout)]  # Ensure logs go to stdout
)

SOURCE_DIR = os.path.join(os.path.dirname(__file__), "database", "sql")

def process_sql_file(db: DbSession, filename: str) -> None:
    """Reads an SQL file, schemafies it, and executes it on the database."""
    filepath = os.path.join(SOURCE_DIR, filename)
    try:
        with open(filepath, 'r', encoding='UTF-8') as file:
            sql = schemafy(file.read())
            db.do('execute', sql)
    except IOError as e:
        logging.error(f"Error reading file {filename}: {e}")
        sys.exit(1)

def prepare_database(db: DbSession) -> None:
    """Prepares the database by creating a schema and processing SQL files."""
    schema_name = settings.db_schema
    if not schema_name:
        logging.error("Environment variable 'DB_SCHEMA' not set.")
        sys.exit(1)

    db.do('execute', f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
    db.do('execute', f"CREATE SCHEMA IF NOT EXISTS {schema_name};")
    for sql_file in ['schema.sql', 'migration.sql']:
        try:
            process_sql_file(db, sql_file)
        except Exception as e:
            logging.error("Error processing %s: %s", sql_file, e)

    db.do('commit')

def run() -> NoReturn:
    """Main entrypoint that sets up the database and runs the server."""
    db = DbSession('setup')

    def handle_sigterm(signum, frame):
        logging.info("Received SIGTERM, shutting down gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        prepare_database(db)
        run_server()
    except KeyboardInterrupt:
        logging.info("EnhancifAI Backend interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logging.error("Unexpected error: %s", e)
        sys.exit(2)

if __name__ == "__main__":
    run()
