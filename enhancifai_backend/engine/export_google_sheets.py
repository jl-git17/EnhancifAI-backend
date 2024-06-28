
import pandas as pd
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from fastapi import HTTPException
from typing import Union
from pathlib import Path
from datetime import datetime

from enhancifai_backend.database.handlers.sheets import SheetsDbCore

async def export_to_google_sheets(user_id: int, file_path: Union[str, Path]):
    creds = SheetsDbCore.get_user_google_credentials(user_id)
    if not creds:
        return HTTPException(status_code=403, detail="User is not authenticated with Google")
    
    try:
        service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        sheet = service.spreadsheets()  # pylint: disable=no-member
    except Exception as e:
        return HTTPException(status_code=403, detail=f"Invalid Google credentials or access revoked: {str(e)}")

    file_path = Path(file_path)
    if file_path.suffix == '.csv':
        df = pd.read_csv(file_path)
    elif file_path.suffix in ['.xls', '.xlsx']:
        df = pd.read_excel(file_path)
    else:
        return HTTPException(status_code=400, detail="Unsupported file type")

    data = df.values.tolist()
    data.insert(0, df.columns.tolist())

    current_time = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    title = f'EnhancifAI - {current_time}'

    try:
        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        print("Creating sheet")
        spreadsheet = sheet.create(body=spreadsheet, fields='spreadsheetId').execute()
        sheet_id = spreadsheet.get('spreadsheetId')
        print(f"Sheet ID: {sheet_id}")

        body = {
            'values': data
        }

        sheet.values().update(
            spreadsheetId=sheet_id,
            range='Sheet1!A1',
            valueInputOption='RAW',
            body=body
        ).execute()
    except Exception as e:
        return HTTPException(status_code=500, detail=f"Failed to create or update the Google Sheet: {str(e)}")

    return {'spreadsheetId': sheet_id}
