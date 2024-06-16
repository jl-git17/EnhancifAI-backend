import os


def schemafy(data:str):
    _data = data.replace('enhancifai.', f"{os.getenv('DB_SCHEMA')}.").replace("table_schema = 'enhancifai'", f"table_schema = '{os.getenv('DB_SCHEMA')}'")
    return _data