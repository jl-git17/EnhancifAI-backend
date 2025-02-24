import re

from enhancifai_backend.config import settings

def schemafy(data: str) -> str:
    """
    Replace schema placeholders in a SQL query with the actual schema name.

    Args:
        data (str): A SQL query string containing the placeholder schema 'enhancifai'.

    Returns:
        str: A new SQL query with the environment variable DB_SCHEMA replacing 'enhancifai'.

    Raises:
        ValueError: If the environment variable 'DB_SCHEMA' is not set.
    """
    schema = settings.db_schema
    if not schema:
        raise ValueError("Environment variable 'DB_SCHEMA' is not set.")

    # Replace schema-qualified table names
    data = data.replace('enhancifai.', f"{schema}.")

    # Replace specific string literals related to table schema
    data = data.replace("table_schema = 'enhancifai'", f"table_schema = '{schema}'")

    # Replace schema name within pg_namespace references
    # Using regex to ensure only exact matches are replaced
    pattern = re.compile(r"n\.nspname\s*=\s*'enhancifai'")
    data = pattern.sub(f"n.nspname = '{schema}'", data)

    return data
