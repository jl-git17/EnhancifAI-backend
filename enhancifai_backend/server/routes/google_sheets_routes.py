import os
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from google_auth_oauthlib.flow import Flow

from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.database.handlers.sheets import SheetsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.server.utils import get_current_user_id
from enhancifai_backend.engine.export_google_sheets import export_to_google_sheets

router = APIRouter()

# Load client secrets from environment variable
client_secrets_json = os.getenv("GOOGLE_TOKEN_INFO_AUTH")
if client_secrets_json is None:
    raise ValueError("GOOGLE_TOKEN_INFO_AUTH environment variable not set")

client_secrets = json.loads(client_secrets_json)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']
REDIRECT_URI = os.getenv("GOOGLE_SHEETS_REDIRECT_URI")
if REDIRECT_URI is None:
    raise ValueError("GOOGLE_SHEETS_REDIRECT_URI environment variable not set")

def get_flow(state=None):
    return Flow.from_client_config(
        client_secrets,
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI
    )

@router.get("/sheets/login", tags=["Sheets"])
async def login(user_id: Optional[int] = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    flow = get_flow()
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    
    # Store state in the database
    SheetsDbCore.store_oauth_state(user_id, state)
    
    return RedirectResponse(authorization_url)

@router.get("/callback/google/sheets", tags=["Sheets"])
async def oauth2callback(request: Request):
    state = request.query_params.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")
    
    user_id = SheetsDbCore.get_oauth_state(state)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    flow = get_flow(state)
    flow.fetch_token(authorization_response=str(request.url))
    creds = flow.credentials
    
    UsersDbCore.update_user_google_credentials(user_id, creds_to_dict(creds))
    SheetsDbCore.delete_oauth_state(state)
    
    return RedirectResponse(url="/")

def creds_to_dict(creds):
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

@router.post("/sheets/export", tags=["Sheets"])
async def export_to_sheets(run_id: int, user_id: Optional[int] = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Assuming you have a method to get the file path from the run_id
    file_path = RunsDbCore.get_run_details(run_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Run not found or file path not available")

    try:
        result = await export_to_google_sheets(user_id, file_path)
        sheet_url = f"https://docs.google.com/spreadsheets/d/{result['spreadsheetId']}"
        return JSONResponse(status_code=200, content={"url": sheet_url})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
