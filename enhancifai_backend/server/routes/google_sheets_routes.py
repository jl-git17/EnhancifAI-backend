import os
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from enhancifai_backend.database.handlers.sheets import SheetsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.server.utils import get_current_user_id

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

