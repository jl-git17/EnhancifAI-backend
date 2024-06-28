import pandas as pd
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from fastapi import HTTPException
from typing import Union
from pathlib import Path
from datetime import datetime

from enhancifai_backend.database.handlers.sheets import SheetsDbCore

async def export_to_google_sheets(user_id: int, file_path: Union[str, Path]):
    creds_dict = SheetsDbCore.get_user_google_credentials(user_id)
    if not creds_dict:
        return HTTPException(status_code=403, detail="User is not authenticated with Google")
    
    try:
        creds = Credentials.from_service_account_info(creds_dict)  # Use from_service_account_info
        service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        sheet = service.spreadsheets()  # pylint: disable=no-member
    except Exception as e:
        return HTTPException(status_code=403, detail=f"Invalid Google credentials or access revoked: {str(e)}")

    # Read data from the file
    file_path = Path(file_path)
    if file_path.suffix == '.csv':
        df = pd.read_csv(file_path)
    elif file_path.suffix in ['.xls', '.xlsx']:
        df = pd.read_excel(file_path)
    else:
        return HTTPException(status_code=400, detail="Unsupported file type")

    data = df.values.tolist()
    data.insert(0, df.columns.tolist())  # Add the header row

    # Get the current date and time in the specified format
    current_time = datetime.now().strftime('%Y-%m-%d-%H%M%S')

    # Create the title using the current date and time
    title = f'EnhancifAI - {current_time}'

    try:
        # Create a new sheet with the generated title
        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        print("Creating sheet")
        spreadsheet = sheet.create(body=spreadsheet, fields='spreadsheetId').execute()
        sheet_id = spreadsheet.get('spreadsheetId')
        print(f"Sheet ID: {sheet_id}")

        # Prepare data for insertion
        body = {
            'values': data
        }

        # Insert data into the sheet
        sheet.values().update(
            spreadsheetId=sheet_id,
            range='Sheet1!A1',
            valueInputOption='RAW',
            body=body
        ).execute()
    except Exception as e:
        return HTTPException(status_code=500, detail=f"Failed to create or update the Google Sheet: {str(e)}")

    return {'spreadsheetId': sheet_id}
