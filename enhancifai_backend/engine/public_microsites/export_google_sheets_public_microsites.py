import logging
import os
from datetime import datetime

from google.auth.transport.requests import Request
from fastapi import HTTPException
import gspread
import pandas as pd

from enhancifai_backend.database.handlers.sheets import SheetsDbCore
from enhancifai_backend.database.handlers.microsites import m


def authenticate_google_sheets_public_microsites(session_id):
    creds = SheetsDbCore.get_user_google_credentials(session_id)
    if not creds:
        logging.error("User %s does not have Google credentials", session_id)
        return HTTPException(status_code=403, detail="User is not authenticated with Google")

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            logging.error("Google credentials for user %s are invalid or expired", session_id)
            return HTTPException(status_code=403, detail="Google credentials are invalid or expired")
    return creds

async def export_to_google_sheets(session_id: str, file_url: str, source_filename: str):
    logging.debug("Starting export_to_google_sheets with session_id: %s and file_url: %s", session_id, file_url)

    if source_filename is None:
        source_filename = "Your File"
    # Authenticate Google Sheets
    logging.debug("Authenticating Google Sheets")
    creds = authenticate_google_sheets_public_microsites(session_id)

    if isinstance(creds, HTTPException):
        return creds

    client = gspread.authorize(creds)
    logging.debug("Google Sheets authentication successful")

    # Extract filename from URL and construct the file path in /tmp directory
    filename = file_url.split('/')[-1]
    file_path = os.path.join('/tmp', filename)
    logging.debug("Resolved file path: %s", file_path)

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif filename.endswith('.xls') or filename.endswith('.xlsx'):
            df = pd.read_excel(file_path)
        else:
            logging.error("Unsupported file type")
            return HTTPException(status_code=400, detail="Unsupported file type")

    except Exception as e:
        error_message = f"Error reading file: {str(e)}"
        logging.error(error_message)
        return HTTPException(status_code=400, detail=error_message)

    # Handle NaN and infinite values
    df = df.fillna('').replace([float('inf'), float('-inf')], '')

    # Convert Timestamp columns to string to ensure JSON serialization compatibility
    for col in df.select_dtypes(include=['datetime64[ns]', 'datetime64[ns, UTC]', 'timedelta64[ns]']).columns:
        df[col] = df[col].astype(str)

    # Convert DataFrame to list
    data = [df.columns.tolist()] + df.values.tolist()

    # Create a title for the Google Sheet
    current_time = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    title = f'EnhancifAI - {source_filename} - {current_time}'

    try:
        # Create the Google Sheet
        spreadsheet = client.create(title)
        sheet_id = spreadsheet.id

        # Open the sheet and update it with the data
        sheet = client.open_by_key(sheet_id).sheet1
        sheet.update('A1', data)
    except Exception as e:
        error_message = f"Failed to create or update the Google Sheet: {str(e)}"
        logging.error(error_message)
        return HTTPException(status_code=500, detail=error_message)

    return {'spreadsheetId': sheet_id}

async def export_to_google_sheets_public_microsites(session_id: str, file_url: str, source_filename: str):
    logging.debug("Starting export_to_google_sheets with session_id: %s and file_url: %s", session_id, file_url)

    if source_filename is None:
        source_filename = "Your File"
    # Authenticate Google Sheets
    logging.debug("Authenticating Google Sheets")
    creds = authenticate_google_sheets_public_microsites(session_id)

    if isinstance(creds, HTTPException):
        return creds

    client = gspread.authorize(creds)
    logging.debug("Google Sheets authentication successful")

    # Extract filename from URL and construct the file path in /tmp directory
    filename = file_url.split('/')[-1]
    file_path = os.path.join('/tmp', filename)
    logging.debug("Resolved file path: %s", file_path)

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif filename.endswith('.xls') or filename.endswith('.xlsx'):
            df = pd.read_excel(file_path)
        else:
            logging.error("Unsupported file type")
            return HTTPException(status_code=400, detail="Unsupported file type")

    except Exception as e:
        error_message = f"Error reading file: {str(e)}"
        logging.error(error_message)
        return HTTPException(status_code=400, detail=error_message)

    # Handle NaN and infinite values
    df = df.fillna('').replace([float('inf'), float('-inf')], '')

    # Convert Timestamp columns to string to ensure JSON serialization compatibility
    for col in df.select_dtypes(include=['datetime64[ns]', 'datetime64[ns, UTC]', 'timedelta64[ns]']).columns:
        df[col] = df[col].astype(str)

    # Convert DataFrame to list
    data = [df.columns.tolist()] + df.values.tolist()

    # Create a title for the Google Sheet
    current_time = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    title = f'EnhancifAI - {source_filename} - {current_time}'

    try:
        # Create the Google Sheet
        spreadsheet = client.create(title)
        sheet_id = spreadsheet.id

        # Open the sheet and update it with the data
        sheet = client.open_by_key(sheet_id).sheet1
        sheet.update('A1', data)
    except Exception as e:
        error_message = f"Failed to create or update the Google Sheet: {str(e)}"
        logging.error(error_message)
        return HTTPException(status_code=500, detail=error_message)

    return {'spreadsheetId': sheet_id}
