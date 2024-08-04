from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from fastapi import HTTPException
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe

from enhancifai_backend.database.handlers.sheets import SheetsDbCore

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

class GoogleSheetsHandler:
    def __init__(self, user_id):
        self.user_id = user_id
        self.creds = self.authenticate_google_sheets()

    def authenticate_google_sheets(self):
        creds = SheetsDbCore.get_user_google_credentials(self.user_id)
        if not creds:
            raise HTTPException(status_code=403, detail="User is not authenticated with Google")
        
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Update the refreshed credentials in the database
                    SheetsDbCore.update_user_google_credentials(self.user_id, creds)
                except RefreshError:
                    SheetsDbCore.delete_user_google_credentials(self.user_id)
                    raise HTTPException(status_code=403, detail="Google credentials are invalid or expired, re-authentication required.")
            else:
                raise HTTPException(status_code=403, detail="Google credentials are invalid or expired")
        print(f"Found creds: {creds}")
        return creds

    def list_google_sheets(self):
        service = build('drive', 'v3', credentials=self.creds)
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            orderBy="modifiedTime desc",
            fields="files(id, name, modifiedTime)"
        ).execute()
        sheets = results.get('files', [])
        return sheets

    def search_google_sheet(self, sheets, search_name):
        if not search_name:
            return sheets
        filtered_sheets = [sheet for sheet in sheets if search_name.lower() in sheet['name'].lower()]
        return filtered_sheets

    def get_spreadsheet_details(self, sheet):
        spreadsheet_id = sheet['id']
        sheet_name = sheet['name']
        return spreadsheet_id, sheet_name

    def find_sheet(self, search_name):
        sheets = self.list_google_sheets()
        if not sheets:
            return "No Google Sheets found."

        matching_sheets = self.search_google_sheet(sheets, search_name)
        if not matching_sheets:
            return f"No sheet found with the name containing '{search_name}'."

        sheet_details = [{"spreadsheet_id": self.get_spreadsheet_details(sheet)[0],
                          "sheet_name": self.get_spreadsheet_details(sheet)[1]} for sheet in matching_sheets]
        return sheet_details

    def get_sheet_as_dataframe(self, spreadsheet_id, worksheet_name=None):
        try:
            gc = gspread.authorize(self.creds)
            sh = gc.open_by_key(spreadsheet_id)
            
            if worksheet_name:
                worksheet = sh.worksheet(worksheet_name)
            else:
                worksheet = sh.sheet1
            
            df = get_as_dataframe(worksheet, evaluate_formulas=True)
            return df
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
