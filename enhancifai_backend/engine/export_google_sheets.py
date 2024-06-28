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
    print(f"Starting export_to_google_sheets with user_id: {user_id} and file_path: {file_path}")
    
    # Authenticate Google Sheets
    print("Authenticating Google Sheets")
    creds = authenticate_google_sheets(user_id)
    client = gspread.authorize(creds)
    print("Google Sheets authentication successful")
    
    # Determine file path type and read the file
    file_path = Path(file_path)
    print(f"File path resolved to: {file_path}")
    
    if file_path.suffix == '.csv':
        print("File is a CSV, reading CSV")
        df = pd.read_csv(file_path)
    elif file_path.suffix in ['.xls', '.xlsx']:
        print("File is an Excel file, reading Excel")
        df = pd.read_excel(file_path)
    else:
        print("Unsupported file type")
        return HTTPException(status_code=400, detail="Unsupported file type")

    # Convert DataFrame to list
    print("Converting DataFrame to list")
    data = df.values.tolist()
    data.insert(0, df.columns.tolist())
    print(f"Data to be exported: {data[:5]}...")  # Only printing the first 5 rows for brevity

    # Create a unique title for the Google Sheet
    current_time = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    title = f'EnhancifAI - {current_time}'
    print(f"Generated title for the sheet: {title}")

    try:
        # Create the Google Sheet
        print("Creating Google Sheet")
        spreadsheet = client.create(title)
        sheet_id = spreadsheet.id
        print(f"Created Google Sheet with ID: {sheet_id}")

        # Open the sheet and update it with the data
        print("Opening the created sheet")
        sheet = client.open_by_key(sheet_id).sheet1
        print("Updating the sheet with data")
        sheet.update([data])
        print("Sheet update successful")
    except Exception as e:
        error_message = f"Failed to create or update the Google Sheet: {str(e)}"
        print(error_message)
        return HTTPException(status_code=500, detail=error_message)

    print(f"Export successful, spreadsheetId: {sheet_id}")
    return {'spreadsheetId': sheet_id}

