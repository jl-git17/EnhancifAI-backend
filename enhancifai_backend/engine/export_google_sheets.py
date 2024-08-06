import os
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


def authenticate_google_sheets(user_id):
    creds = SheetsDbCore.get_user_google_credentials(user_id)
    if not creds:
        return HTTPException(status_code=403, detail="User is not authenticated with Google")
    
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            return HTTPException(status_code=403, detail="Google credentials are invalid or expired")
    print(f"Found creds: {creds}")
    return creds

async def export_to_google_sheets(user_id: int, file_url: str, source_filename: str):
    print(f"Starting export_to_google_sheets with user_id: {user_id} and file_url: {file_url}")
    
    if source_filename is None:
        source_filename = "Your File"
    # Authenticate Google Sheets
    print("Authenticating Google Sheets")
    creds = authenticate_google_sheets(user_id)

    if isinstance(creds, HTTPException):
        return creds

    client = gspread.authorize(creds)
    print("Google Sheets authentication successful")
    
    # Extract filename from URL and construct the file path in /tmp directory
    filename = file_url.split('/')[-1]
    file_path = os.path.join('/tmp', filename)
    print(f"Resolved file path: {file_path}")

    try:
        if filename.endswith('.csv'):
            print("File is a CSV, reading CSV")
            df = pd.read_csv(file_path)
        elif filename.endswith('.xls') or filename.endswith('.xlsx'):
            print("File is an Excel file, reading Excel")
            df = pd.read_excel(file_path)
        else:
            print("Unsupported file type")
            return HTTPException(status_code=400, detail="Unsupported file type")
        
        print(f"DataFrame read successfully: {df.shape} rows and columns")
    except Exception as e:
        error_message = f"Error reading file: {str(e)}"
        print(error_message)
        return HTTPException(status_code=400, detail=error_message)
    
    # Handle NaN and infinite values
    df = df.fillna('').replace([float('inf'), float('-inf')], '')

    # Convert Timestamp columns to string to ensure JSON serialization compatibility
    for col in df.select_dtypes(include=['datetime64[ns]', 'datetime64[ns, UTC]', 'timedelta64[ns]']).columns:
        df[col] = df[col].astype(str)

    # Convert DataFrame to list
    print("Converting DataFrame to list")
    data = [df.columns.tolist()] + df.values.tolist()
    print(f"Data to be exported: {data[:5]}...")  # Only printing the first 5 rows for brevity

    # Create a title for the Google Sheet
    current_time = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    title = f'EnhancifAI - {source_filename} - {current_time}'
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
        sheet.update('A1', data)
        print("Sheet update successful")
    except Exception as e:
        error_message = f"Failed to create or update the Google Sheet: {str(e)}"
        print(error_message)
        return HTTPException(status_code=500, detail=error_message)

    print(f"Export successful, spreadsheetId: {sheet_id}")
    return {'spreadsheetId': sheet_id}
