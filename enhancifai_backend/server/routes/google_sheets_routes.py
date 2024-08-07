import os
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from google_auth_oauthlib.flow import Flow
from starlette.middleware.cors import CORSMiddleware

from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.database.handlers.sheets import SheetsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.engine.import_google_sheets import GoogleSheetsHandler
from enhancifai_backend.server.models.execution import ExportSheetsRequest
from enhancifai_backend.server.utils import get_current_user_id, verify_secret_key
from enhancifai_backend.engine.export_google_sheets import export_to_google_sheets

router = APIRouter()

# Load client secrets from environment variable
client_secrets_json = os.getenv("GOOGLE_TOKEN_INFO_AUTH")
if client_secrets_json is None:
    raise ValueError("GOOGLE_TOKEN_INFO_AUTH environment variable not set")

client_secrets = json.loads(client_secrets_json)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
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

@router.get("/sheets/login", tags=["Google Sheets"], operation_id="login_sheets_operation")
async def login_sheets(user_id: int = Depends(get_current_user_id)):
    """
    Initiate Google Sheets login and authorization process.

    This endpoint initiates the OAuth2 flow for Google Sheets API. It generates an authorization URL that the user
    needs to visit to grant access to their Google Sheets account.

    - **user_id**: The ID of the authenticated user. This is fetched automatically by dependency injection (`token`).

    Returns a JSON response containing the status of the operation and the authorization URL.

    - **200**: Successfully generated authorization URL.
      - **content**: `{"status": "success", "url": "<Google Sheets Authorization URL>"}`
    - **401**: User not authenticated.
      - **detail**: `{"detail": "User not authenticated"}`
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    flow = get_flow()
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    
    # Store state in the database
    SheetsDbCore.store_oauth_state(user_id, state)
    
    return JSONResponse(status_code=200, content={"status": "success", "url": authorization_url})


@router.get("/callback/google/sheets", tags=["Google Sheets"], operation_id="oauth2callback_google_sheets_operation")
async def oauth2callback(request: Request):
    state = request.query_params.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")
    
    user_id = SheetsDbCore.get_oauth_state(state)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    _url = str(request.url).replace("http://", "https://")
    flow = get_flow(state)
    try:
        flow.fetch_token(authorization_response=_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token fetch failed: {str(e)}")

    creds = flow.credentials
    
    SheetsDbCore.update_user_google_credentials(user_id, creds)
    SheetsDbCore.delete_oauth_state(state)
    
    #return RedirectResponse(url="/")
    return "Authentication successful. You can close this window."

@router.post("/sheets/export", tags=["Google Sheets"], operation_id="export_to_sheets_operation")
async def export_to_sheets(req_sheets: ExportSheetsRequest, user_id: int = Depends(get_current_user_id), _: str = Depends(verify_secret_key)):
    
    """
    Export run data to a Google Sheets document.

    This endpoint exports the run data specified by `run_id` in the request body to a Google Sheets document.
    
    - **req_sheets**: The request body containing the `run_id` of the data to be exported.
    - **user_id**: The ID of the authenticated user. This is fetched automatically by dependency injection (`token`).

    Returns a JSON response containing the status of the export operation and the URL of the created Google Sheets document if successful.

    - **200**: Successfully processed request.
      - **content**: `{"status": "success", "url": "<Google Sheets URL>"}`
      - **content**: `{"status": "failed", "status_code": 400, "error": "Unsupported file type"}`
      - **content**: `{"status": "failed", "status_code": 403, "error": "User is not authenticated with Google"}`
      - **content**: `{"status": "failed", "status_code": 403, "error": "Invalid Google credentials or access revoked"}`
      - **content**: `{"status": "failed", "status_code": 500, "error": "Failed to create or update the Google Sheet"}`
    - **401**: User not authenticated.
      - **detail**: `{"detail": "User not authenticated"}`
    - **404**: Run not found or file path not available.
      - **detail**: `{"detail": "Run not found or file path not available"}`
    - **500**: Internal server error.
      - **detail**: Error message detailing what went wrong.
    """
    
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    file_path = RunsDbCore.get_run_file_url(req_sheets.run_id)
    source_filename = RunsDbCore.get_source_filename(req_sheets.run_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Run not found or file path not available")

    try:
        result = await export_to_google_sheets(user_id, file_path, source_filename)
        if isinstance(result, dict):
            sheet_url = f"https://docs.google.com/spreadsheets/d/{result['spreadsheetId']}"
            return JSONResponse(status_code=200, content={"status": "success", "url": sheet_url})
        elif isinstance(result, HTTPException):
            return JSONResponse(status_code=200, content={"status": "failed", "status_code": result.status_code, "error": result.detail})
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get("/sheets/list", tags=["Google Sheets"], operation_id="list_sheets_operation")
async def list_sheets(search_name: Optional[str] = "", page: Optional[int] = 1, user_id: int = Depends(get_current_user_id), _: str = Depends(verify_secret_key)):
    """
    List and search Google Sheets for the authenticated user with pagination.

    This endpoint lists Google Sheets for the authenticated user, optionally filtering by a search name, with pagination.

    - **search_name**: The name or partial name of the sheet to search for. If empty, all sheets are returned.
    - **page**: The page number to retrieve (default is 1).
    - **page_size**: The number of sheets per page (default is 20).
    - **user_id**: The ID of the authenticated user. This is fetched automatically by dependency injection (`token`).

    Returns a JSON response containing the list of sheets with their names, IDs, and nextPageToken.

    - **200**: Successfully retrieved list of sheets.
      - **content**: `{"sheets": [{"spreadsheet_id": "<ID>", "sheet_name": "<Name>", "worksheets": ["<worksheet1>", "<worksheet2>"]}], "nextPageToken": "<Token>"}`
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    handler = GoogleSheetsHandler(user_id)
    page_token = None if page == 1 else page
    result = handler.find_sheet(search_name, page_token)
    return JSONResponse(status_code=200, content=result)

@router.get("/sheets/data", tags=["Google Sheets"], operation_id="get_data_sheets_operation")
async def get_sheet_data(sheet_id: str, worksheet_name: str = None, user_id: int = Depends(get_current_user_id), _: str = Depends(verify_secret_key)):
    """
    Retrieve the data contained in the specified Google Sheet for the authenticated user.

    This endpoint returns an array of records contained in the specified `sheet_id`.

    - **sheet_id**: The unique ID of the Google Sheet, as retrieved from the `/sheets/list` endpoint.
    - **worksheet_name**: The name of the worksheet within the Google Sheet. If not specified, the first sheet is used.

    Returns a JSON response containing the list of records.

    - **200**: Successfully retrieved the Google Sheet's data.
      - **content**: ``
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    handler = GoogleSheetsHandler(user_id)
    try:
        result = handler.get_sheet_as_dataframe(sheet_id, worksheet_name)
        records = result.to_dict(orient='records')
        return JSONResponse(status_code=200, content={
                "message": "Google Sheet data processed successfully.",
                "records": json.dumps(records)
            })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred")