import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from fastapi import HTTPException
from typing import Union
from pathlib import Path
from datetime import datetime

from enhancifai_backend.database.handlers.sheets import SheetsDbCore

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

def authenticate_google_sheets(user_id):
    creds = SheetsDbCore.get_user_google_credentials(user_id)
    if not creds:
        return HTTPException(status_code=403, detail="User is not authenticated with Google")
    
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            return HTTPException(status_code=403, detail="Google credentials are invalid or expired")
    
    return creds

async def export_to_google_sheets(user_id: int, file_path: Union[str, Path]):
    creds = authenticate_google_sheets(user_id)
    client = gspread.authorize(creds)
    
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
        spreadsheet = client.create(title)
        sheet_id = spreadsheet.id
        print(f"Sheet ID: {sheet_id}")

        sheet = client.open_by_key(sheet_id).sheet1
        sheet.update([data])
    except Exception as e:
        return HTTPException(status_code=500, detail=f"Failed to create or update the Google Sheet: {str(e)}")

    return {'spreadsheetId': sheet_id}
