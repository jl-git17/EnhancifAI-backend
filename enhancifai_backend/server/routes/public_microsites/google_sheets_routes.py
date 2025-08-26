import json
import logging
import secrets
import ast
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from google_auth_oauthlib.flow import Flow

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.microsites import MicrositesRunsDbCore
from enhancifai_backend.engine.public_microsites.import_google_sheets_public_microsites import GoogleSheetsHandler
from enhancifai_backend.server.models.execution import ExportSheetsRequest
from enhancifai_backend.server.utils import get_microsite_session_id, verify_secret_key
from enhancifai_backend.engine.public_microsites.export_google_sheets_public_microsites import export_to_google_sheets_public_microsites
from enhancifai_backend.engine.public_microsites.sheets_creds_mem import sheets_creds_memory

router = APIRouter()

# Load client secrets from environment variable
client_secrets_json = settings.google_token_info_auth
if client_secrets_json is None:
    raise ValueError("GOOGLE_TOKEN_INFO_AUTH environment variable not set")

client_secrets = json.loads(client_secrets_json)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
REDIRECT_URI = str(settings.google_sheets_redirect_uri).replace('/callback/google/sheets', '/microsites/callback/google/sheets')
if REDIRECT_URI is None:
    raise ValueError("GOOGLE_SHEETS_REDIRECT_URI environment variable not set")


def get_flow(state=None):
    return Flow.from_client_config(
        client_secrets,
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI
    )

@router.get("/microsites/sheets/login", tags=["Microsites - Google Sheets"], operation_id="login_sheets_operation")
async def login_sheets(session_id: str):
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
    already_logged_in = sheets_creds_memory.has_creds(session_id)
    if already_logged_in:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail="User has already logged in for Google Sheets usage."
        )

    # Create a stateless state value that embeds the session_id so callback
    # requests can determine the originating session without relying on
    # in-memory process-local storage (avoids load-balancer instance issues).
    random_token = secrets.token_urlsafe(24)
    state_value = f"{session_id}|{random_token}"

    # Pass our generated state into the flow so the same value is round-tripped
    flow = get_flow(state=state_value)
    authorization_url, returned_state = flow.authorization_url(
        access_type='offline', include_granted_scopes='true'
    )

    # Sanity check: ensure returned_state matches what we set
    if returned_state != state_value:
        logging.warning("OAuth returned state does not match generated state")


    return JSONResponse(status_code=200, content={"status": "success", "url": authorization_url})


@router.get("/microsites/callback/google/sheets", tags=["Microsites - Google Sheets"], operation_id="oauth2callback_google_sheets_operation")
async def oauth2callback(request: Request):
    state = request.query_params.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")

    # Expect the state to be in the format: "<session_id>|<random_token>"
    try:
        session_id_parsed, _token = state.split("|", 1)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    session_id = session_id_parsed

    _url = str(request.url).replace("http://", "https://")
    # Recreate the flow with the same state value so token exchange validates
    flow = get_flow(state)
    try:
        flow.fetch_token(authorization_response=_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token fetch failed: {str(e)}")

    creds = flow.credentials

    sheets_creds_memory.set_creds(session_id, creds)

    return "Authentication successful. You can close this window."

@router.post("/microsites/sheets/export", tags=["Microsites - Google Sheets"], operation_id="export_to_sheets_operation")
async def export_to_sheets(
    req_sheets: ExportSheetsRequest,
    session_id: str = Depends(get_microsite_session_id),
    _: str = Depends(verify_secret_key)
):
    """
    Export run data to a Google Sheets document.

    This endpoint exports the run data specified by `run_id` in the request body to a Google Sheets document.
    
    - **req_sheets**: The request body containing the `run_id` of the data to be exported.
    - **user_id**: The ID of the authenticated user. This is fetched automatically by dependency injection (`token`).

    Returns a JSON response containing the status of the export operation
        and the URL of the created Google Sheets document if successful.

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

    file_path = MicrositesRunsDbCore.get_run_file_url(req_sheets.run_id)
    source_filename = MicrositesRunsDbCore.get_source_filename(req_sheets.run_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Run not found or file path not available")

    try:
        result = await export_to_google_sheets_public_microsites(session_id, file_path, source_filename)
        if isinstance(result, dict):
            sheet_url = f"https://docs.google.com/spreadsheets/d/{result['spreadsheetId']}"
            return JSONResponse(status_code=200, content={"status": "success", "url": sheet_url})
        elif isinstance(result, HTTPException):
            return JSONResponse(
                status_code=200,
                content={
                    "status": "failed",
                    "status_code": result.status_code,
                    "error": result.detail
                }
            )
    except Exception as e:
        logging.error("Error exporting to Google Sheets: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get("/microsites/sheets/list", tags=["Microsites - Google Sheets"], operation_id="list_sheets_operation")
async def list_sheets(
    search_name: Optional[str] = "",
    page: int = 1,
    session_id: str = Depends(get_microsite_session_id),
    _: str = Depends(verify_secret_key)
):
    """
    List and search Google Sheets for the authenticated user with pagination.

    This endpoint lists Google Sheets for the authenticated user, optionally filtering by a search name, with pagination.

    - **search_name**: The name or partial name of the sheet to search for. If empty, all sheets are returned.
    - **page**: The page number to retrieve (default is 1).
    - **page_size**: The number of sheets per page (default is 20).
    - **user_id**: The ID of the authenticated user. This is fetched automatically by dependency injection (`token`).

    Returns a JSON response containing the list of sheets with their names, IDs, and nextPageToken.

    - **200**: Successfully retrieved list of sheets.
      - **content**:
        ```
            {
                "sheets": [{"spreadsheet_id": "<ID>",
                "sheet_name": "<Name>",
                "worksheets": ["<worksheet1>", "<worksheet2>"]}],
                "nextPageToken": "<Token>"
            }
        ```
    """

    handler = GoogleSheetsHandler(session_id)
    # keep the behavior that page==1 => no page token, otherwise pass page through
    page_token = None if page == 1 else page

    # find_sheet is a blocking (I/O) operation; run it in a threadpool so the
    # FastAPI event loop isn't blocked. This improves throughput for concurrent
    # callers and reduces latency under load.
    result = await run_in_threadpool(handler.find_sheet, search_name, page_token)
    return JSONResponse(status_code=200, content=result)

@router.get("/microsites/sheets/data", tags=["Microsites - Google Sheets"], operation_id="get_data_sheets_operation")
async def get_sheet_data(
    sheet_id: str, worksheet_name: str = None,
    session_id: str = Depends(get_microsite_session_id),
    _: str = Depends(verify_secret_key)
):
    """
    Retrieve the data contained in the specified Google Sheet for the authenticated user.

    This endpoint returns an array of records contained in the specified `sheet_id`.

    - **sheet_id**: The unique ID of the Google Sheet, as retrieved from the `/sheets/list` endpoint.
    - **worksheet_name**: The name of the worksheet within the Google Sheet. If not specified, the first sheet is used.

    Returns a JSON response containing the list of records.

    - **200**: Successfully retrieved the Google Sheet's data.
      - **content**: ``
    """

    handler = GoogleSheetsHandler(session_id)
    try:
        result = handler.get_sheet_as_dataframe(sheet_id, worksheet_name)

        records = []
        # If result is a pandas DataFrame, convert directly to list of dicts
        try:
            import pandas as _pd
            if isinstance(result, _pd.DataFrame):
                records = result.astype(str).to_dict(orient='records')
            else:
                # Handle list/dict responses coming from older handlers
                if isinstance(result, list):
                    for item in result:
                        # Case: item has "data" which is a stringified dict (single quotes) or a dict
                        if isinstance(item, dict) and 'data' in item:
                            data = item['data']
                            parsed = None
                            if isinstance(data, str):
                                # Try JSON first (double quotes), then ast.literal_eval for single-quoted dicts
                                try:
                                    parsed = json.loads(data)
                                except Exception:
                                    try:
                                        parsed = ast.literal_eval(data)
                                    except Exception:
                                        parsed = {'data': data}
                            elif isinstance(data, dict):
                                parsed = data
                            else:
                                parsed = {'data': data}
                            records.append(parsed)
                        elif isinstance(item, dict):
                            # Already a dict mapping columns -> values
                            records.append(item)
                        else:
                            records.append({'value': item})
                elif isinstance(result, dict):
                    records = [result]
                else:
                    records = [{'value': str(result)}]
        except Exception:
            logging.exception("Error while normalizing sheet data")
            raise HTTPException(status_code=500, detail="Failed to normalize sheet data")

        # Return the normalized list of row-dictionaries directly
        return JSONResponse(status_code=200, content=records)
    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error("Error retrieving Google Sheet data: %s", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
