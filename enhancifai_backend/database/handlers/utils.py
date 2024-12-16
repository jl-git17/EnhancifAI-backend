import os
import re

def schemafy(data: str) -> str:
    schema = os.getenv('DB_SCHEMA')
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