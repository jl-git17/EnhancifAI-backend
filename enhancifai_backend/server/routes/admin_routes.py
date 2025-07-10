import csv
from datetime import datetime
import io
import os
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from enhancifai_backend.config import settings
from enhancifai_backend.ai.openai_api import PI_DEFAULT_AI_ENGINE, PI_DEFAULT_PROMPT
from enhancifai_backend.database.handlers.admin import PromptsDbCore, ModelPricesDbCore
from enhancifai_backend.database.handlers.run_logs import PromptImproverRunLogsDbCore, RunLogsDbCore
from enhancifai_backend.server.models.admin import AdminAISettings, RunLogsRequest
from enhancifai_backend.server.utils import STATIC_PAGES_DIRECTORY, get_current_user_id, verify_secret_key, AdminSettings


USERNAME = settings.admin_username
PASSWORD = settings.admin_password


router = APIRouter()
security = HTTPBasic()

def seconds_to_hms(seconds):
    """Converts seconds to a formatted string 'hh:mm:ss'."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{int(hours):02}:{int(minutes):02}:{seconds:06.3f}"


async def is_user_admin(_):
    #return UsersDbCore.is_user_admin(user_id)
    return True

def check_admin_credentials(credentials: HTTPBasicCredentials):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        return True
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Basic"},
    )

@router.get("/admin/dashboard", tags=["Admin"])
async def admin_dashboard(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "admin_dashboard.html"))

@router.get("/admin/dashboard/billing", tags=["Admin"])
async def admin_billing(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "admin_billing.html"))

@router.post("/admin/ai-settings", tags=["Admin"])
async def set_admin_settings_ai(settings_admin_ai:AdminAISettings, _: str = Depends(verify_secret_key),
                                __: int = Depends(get_current_user_id)):
    """Set the Admin settings for AI."""
    # TODO: check if user is an admin
    AdminSettings.set_ai_settings(engine=settings_admin_ai.ai_engine.value, api_key=settings_admin_ai.api_key)
    return JSONResponse(status_code=200, content={"message": "Success."})

@router.get("/admin/prompt-improver", tags=["Admin"])
async def admin_prompt_improver(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "pi_admin.html"))

@router.get("/admin/prompt-improver/settings", tags=["Admin"])
async def get_settings(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    user_id = settings.admin_user_id
    latest_prompt = PromptsDbCore.get_latest_prompt_by_user(user_id)
    if not latest_prompt:
        return {
            "prompt": PI_DEFAULT_PROMPT,
            "ai_engine": PI_DEFAULT_AI_ENGINE
        }
    return {
        "prompt": latest_prompt['prompt'],
        "ai_engine": latest_prompt['ai_engine']
    }

@router.get("/admin/prompt-improver/prompts", tags=["Admin"])
async def get_prompt_versions(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    user_id = settings.admin_user_id
    prompts = PromptsDbCore.get_prompt_versions_by_user(user_id)
    return {"prompts": prompts}

@router.get("/admin/prompt-improver/prompts/{version}", tags=["Admin"])
async def get_prompt_by_version(version: int, credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    user_id = settings.admin_user_id
    prompt = PromptsDbCore.get_prompt_by_version(user_id, version)
    if prompt:
        return prompt
    else:
        raise HTTPException(status_code=404, detail="Prompt not found.")

@router.post("/admin/prompt-improver/settings", tags=["Admin"])
async def update_settings(
    data: dict = Body(...),
    credentials: HTTPBasicCredentials = Depends(security)
):
    check_admin_credentials(credentials)
    prompt = data.get('prompt')
    ai_engine = data.get('ai_engine')
    if not prompt or not ai_engine:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt and AI Engine are required."
        )
    user_id = settings.admin_user_id
    PromptsDbCore.save_new_prompt(user_id, prompt, ai_engine)
    return {"message": "Settings updated successfully"}

@router.get("/admin/logs", tags=["Admin"])
async def admin_logs(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "download_logs.html"))

@router.post("/admin/logs/runs", tags=["Admin"])
async def get_logs_runs(logs_request: RunLogsRequest, _: str = Depends(verify_secret_key),
                        user_id: Optional[int] = Depends(get_current_user_id)):
    """Get run logs for a particular date/time range all times in UTC."""
    if not user_id or not await is_user_admin(user_id):  # Assuming is_user_admin is implemented
        raise HTTPException(status_code=403, detail="Unauthorized Access")

    # Assuming the retrieve_logs_by_date_range expects datetime in UTC
    logs = RunLogsDbCore.retrieve_logs_by_date_range(
        logs_request.start_date, logs_request.end_date)
    return logs

@router.get("/admin/logs/runs/csv", tags=["Admin"])
async def get_logs_runs_csv(
    start_date: datetime,
    end_date: datetime,
    credentials: HTTPBasicCredentials = Depends(security)
):
    check_admin_credentials(credentials)
    logs = RunLogsDbCore.retrieve_logs_by_date_range(
        start_date, end_date
    )
    output = io.StringIO()
    writer = csv.writer(output)
    if logs:
        writer.writerow(logs[0].keys())
        for log in logs:
            log['log_timestamp'] = log['log_timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')
            log['time_elapsed'] = seconds_to_hms(float(log['time_elapsed']))
            if log['errors'] == []:
                log['errors'] = ""
            writer.writerow(log.values())
    output.seek(0)
    response = StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=run_logs.csv"
    return response

@router.get("/admin/logs/pi_runs/csv", tags=["Admin"])
async def get_prompt_improver_logs_runs_csv(
    start_date: datetime,
    end_date: datetime,
    credentials: HTTPBasicCredentials = Depends(security)
):
    check_admin_credentials(credentials)
    logs = PromptImproverRunLogsDbCore.retrieve_logs_by_date_range(
        start_date, end_date
    )
    output = io.StringIO()
    writer = csv.writer(output)
    if logs:
        writer.writerow(logs[0].keys())
        for log in logs:
            log['log_timestamp'] = log['log_timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')
            log['time_elapsed'] = seconds_to_hms(float(log['time_elapsed']))
            if not log.get('errors'):
                log['errors'] = ""
            writer.writerow(log.values())
    output.seek(0)
    response = StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=prompt_improver_run_logs.csv"
    return response

@router.get("/admin/billing/model-prices", tags=["Admin"])
async def get_model_prices(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    prices = ModelPricesDbCore.get_all_model_prices()
    return JSONResponse(status_code=200, content={"model_prices": prices})

@router.post("/admin/billing/model-prices", tags=["Admin"])
async def upsert_model_prices(payload: dict = Body(...), credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    year = payload.get("year")
    month = payload.get("month")
    prices = payload.get("prices", [])
    if not (year and month and prices):
        raise HTTPException(status_code=400, detail="Invalid request data.")
    for item in prices:
        final_price = float(item["price_per_token"])
        ModelPricesDbCore.update_model_price(
            model_name=item["model_name"],
            year=year,
            month=month,
            price=final_price
        )
    return {"message": "Prices updated successfully"}

@router.get("/admin/billing/model-prices/earliest", tags=["Admin"])
async def get_earliest_effective_month(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    earliest_month = ModelPricesDbCore.get_earliest_effective_month()
    return JSONResponse(status_code=200, content={"earliest_month": earliest_month})

@router.get("/admin/billing/model-prices/{year}/{month}", tags=["Admin"])
async def get_model_prices_for_month(
    year: int,
    month: int,
    credentials: HTTPBasicCredentials = Depends(security)
):
    check_admin_credentials(credentials)
    prices = ModelPricesDbCore.get_model_prices_for_month(year, month)
    return JSONResponse(status_code=200, content={"model_prices": prices})

@router.get("/admin/public-demo", tags=["Admin"])
async def admin_public_demo():
    # Serve the page without HTTP Basic Auth
    return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "admin_public_demo.html"))
    
@router.get("/admin/logs/pi_runs/csv", tags=["Admin"])
async def get_prompt_improver_logs_runs_csv(
    start_date: datetime,
    end_date: datetime
):
    """
    Download prompt improver run logs as CSV for a specified date/time range.
    All times are in UTC, with default values for the start and end dates.
    
    Parameters:
    - start_date (datetime): The start of the date range.
    - end_date (datetime): The end of the date range.
    
    Returns:
    - StreamingResponse: A CSV file containing the prompt improver run logs.
    """

    # Retrieve logs from the database
    logs = PromptImproverRunLogsDbCore.retrieve_logs_by_date_range(
        start_date, end_date
    )

    # Initialize a StringIO buffer and CSV writer
    output = io.StringIO()
    writer = csv.writer(output)

    if logs:
        # Write CSV header using the keys of the first log entry
        writer.writerow(logs[0].keys())

        for log in logs:
            # Format datetime fields as strings
            log['log_timestamp'] = log['log_timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')
            # Convert time_elapsed from seconds to HH:MM:SS format
            log['time_elapsed'] = seconds_to_hms(float(log['time_elapsed']))
            # Handle empty errors field
            if not log.get('errors'):
                log['errors'] = ""
            # Write the log values as a CSV row
            writer.writerow(log.values())

    # Reset the buffer's position to the beginning
    output.seek(0)

    # Create a StreamingResponse with the CSV data
    response = StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv"
    )
    # Set the Content-Disposition header to prompt file download
    response.headers["Content-Disposition"] = "attachment; filename=prompt_improver_run_logs.csv"

    return response

@router.get("/admin/billing/model-prices", tags=["Admin"])
async def get_model_prices(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        prices = ModelPricesDbCore.get_all_model_prices()
        return JSONResponse(status_code=200, content={"model_prices": prices})
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.post("/admin/billing/model-prices", tags=["Admin"])
async def upsert_model_prices(payload: dict = Body(...), _: HTTPBasicCredentials = Depends(security)):
    year = payload.get("year")
    month = payload.get("month")
    prices = payload.get("prices", [])
    if not (year and month and prices):
        raise HTTPException(status_code=400, detail="Invalid request data.")
    for item in prices:
        final_price = float(item["price_per_token"])
        ModelPricesDbCore.update_model_price(
            model_name=item["model_name"],
            year=year,
            month=month,
            price=final_price
        )
    return {"message": "Prices updated successfully"}

@router.get("/admin/billing/model-prices/earliest", tags=["Admin"])
async def get_earliest_effective_month(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        earliest_month = ModelPricesDbCore.get_earliest_effective_month()
        return JSONResponse(status_code=200, content={"earliest_month": earliest_month})
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.get("/admin/billing/model-prices/{year}/{month}", tags=["Admin"])
async def get_model_prices_for_month(
    year: int,
    month: int,
    credentials: HTTPBasicCredentials = Depends(security)
):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        prices = ModelPricesDbCore.get_model_prices_for_month(year, month)
        return JSONResponse(status_code=200, content={"model_prices": prices})
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.get("/admin/public-demo", tags=["Admin"])
async def admin_public_demo():
    # Removed credentials: HTTPBasicCredentials = Depends(security)
    # Serve the page without HTTP Basic Auth
    return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "admin_public_demo.html"))
        #raise HTTPException(
            #status_code=status.HTTP_401_UNAUTHORIZED,
            #detail="Incorrect username or password",
            #headers={"WWW-Authenticate": "Basic"},
        #)
