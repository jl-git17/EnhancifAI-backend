from fastapi import APIRouter, FastAPI, Depends, HTTPException, Cookie
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import os
from typing import List, Optional

from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.server.utils import get_current_user_id

router = APIRouter()

# Ensure you replace the below path with the actual path to your OAuth 2.0 Client IDs JSON file
CLIENT_SECRETS_FILE = "path/to/client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly', 'https://www.googleapis.com/auth/drive.metadata.readonly']
REDIRECT_URI = "http://localhost:8000/auth"

#flow = Flow.from_client_config(os.getenv('GOOGLE_TOKEN_INFO_AUTH'), SCOPES, redirect_uri=os.getenv('GOOGLE_REDIRECT_URL'))
flow = None
@router.get("/sheets/login", tags=["Sheets"])
async def login(user_id: Optional[int] = Depends(get_current_user_id)):
    authorization_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    return RedirectResponse(authorization_url)

@router.get("/sheets/auth", tags=["Sheets"])
async def auth(code: str, user_id: Optional[int] = Depends(get_current_user_id)):
    flow.fetch_token(code=code)
    credentials = flow.credentials

    # Save credentials to DB - adjust with your logic
    UsersDbCore.update_user_google_credentials(user_id, credentials)

    response = RedirectResponse(url="/sheets/success")
    
    response.set_cookie(key="access_token", value=credentials.token, httponly=True)
    return response

def get_credentials(access_token: Optional[str] = Cookie(None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return access_token



@router.get("/sheets/sheets", tags=["Sheets"])
async def list_sheets(access_token: str = Depends(get_credentials), user_id: Optional[int] = Depends(get_current_user_id)):
    credentials = flow.credentials
    service = build('drive', 'v3', credentials=credentials)
    results = service.files().list(q="mimeType='application/vnd.google-apps.spreadsheet'", fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])
    if not items:
        return {'message': 'No sheets found.'}
    sheets = [{'id': item['id'], 'name': item['name']} for item in items]
    return sheets

@router.get("/sheets/search-sheet/", tags=["Sheets"])
async def search_sheet(name: str, access_token: str = Depends(get_credentials)):
    credentials = flow.credentials
    service = build('drive', 'v3', credentials=credentials)
    query = f"mimeType='application/vnd.google-apps.spreadsheet' and name contains '{name}'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    if not items:
        return {'message': 'No matching sheets found.'}
    sheets = [{'id': item['id'], 'name': item['name']} for item in items]
    return sheets

@router.post("/sheets/process-sheet/", tags=["Sheets"])
async def process_sheet(sheet_id: str):
    # Placeholder for accepting a sheet ID for further processing
    return {"sheet_id": sheet_id, "status": "Ready for processing"}
