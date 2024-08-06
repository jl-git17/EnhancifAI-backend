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

    def list_google_sheets(self, page_size=20, page_token=None):
        service = build('drive', 'v3', credentials=self.creds)
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            orderBy="modifiedTime desc",
            fields="nextPageToken, files(id, name, modifiedTime)",
            pageSize=page_size,
            pageToken=page_token
        ).execute()
        sheets = results.get('files', [])
        next_page_token = results.get('nextPageToken')
        return sheets, next_page_token


    def search_google_sheet(self, sheets, search_name):
        if not search_name:
            return sheets
        filtered_sheets = [sheet for sheet in sheets if search_name.lower() in sheet['name'].lower()]
        return filtered_sheets

    def get_spreadsheet_details(self, sheet):
        spreadsheet_id = sheet['id']
        sheet_name = sheet['name']
        return spreadsheet_id, sheet_name

    def get_worksheet_names(self, spreadsheet_id):
        try:
            gc = gspread.authorize(self.creds)
            sh = gc.open_by_key(spreadsheet_id)
            worksheets = sh.worksheets()
            worksheet_names = [ws.title for ws in worksheets]
            return worksheet_names
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An error occurred while fetching worksheets: {str(e)}")

    def find_sheet(self, search_name, page_size=20, page_token=None):
        sheets, next_page_token = self.list_google_sheets(page_size=page_size, page_token=page_token)
        if not sheets:
            return {"sheets": [], "nextPageToken": None}

        matching_sheets = self.search_google_sheet(sheets, search_name)
        if not matching_sheets:
            return {"sheets": [], "nextPageToken": next_page_token}

        sheet_details = []
        for sheet in matching_sheets:
            spreadsheet_id, sheet_name = self.get_spreadsheet_details(sheet)
            worksheet_names = self.get_worksheet_names(spreadsheet_id)
            sheet_details.append({
                "spreadsheet_id": spreadsheet_id,
                "sheet_name": sheet_name,
                "worksheets": worksheet_names
            })

        return {"sheets": sheet_details, "nextPageToken": next_page_token}

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
