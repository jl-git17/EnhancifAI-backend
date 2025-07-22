import csv
from datetime import datetime
import io
import os
from typing import Optional
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import base64

from enhancifai_backend.config import settings
from enhancifai_backend.ai.openai_api import PI_DEFAULT_AI_ENGINE, PI_DEFAULT_PROMPT
from enhancifai_backend.database.handlers.admin import AISettingsDbCore, PromptsDbCore, ModelPricesDbCore
from enhancifai_backend.database.handlers.run_logs import PromptImproverRunLogsDbCore, RunLogsDbCore
from enhancifai_backend.database.handlers.public_demo import PublicDemoDbCore, PublicDemoSettingsDbCore
from enhancifai_backend.server.models.admin import AdminAISettings, RunLogsRequest
from enhancifai_backend.server.utils import STATIC_PAGES_DIRECTORY, get_current_user_id, verify_secret_key, AdminSettings


USERNAME = settings.admin_username
PASSWORD = settings.admin_password


router = APIRouter()
security = HTTPBasic()

def _detect_mime(file_bytes):
    return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if file_bytes[:2] == b'PK' else 'text/csv'

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

# New: Retrieve current AI settings
@router.get("/admin/ai/settings", tags=["Admin"])
async def get_admin_ai_settings(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    ai_settings = AISettingsDbCore.get_ai_settings()
    return JSONResponse(status_code=200, content=ai_settings)

# New: Update AI settings
@router.post("/admin/ai/settings", tags=["Admin"])
async def set_admin_ai_settings(
    payload: dict = Body(...),
    credentials: HTTPBasicCredentials = Depends(security)
):
    """
    Set the Admin AI settings (stub - implement functionality yourself)
    """
    check_admin_credentials(credentials)
    # payload may contain e.g. {"temperature": "0.7"} etc.
    AISettingsDbCore.update_ai_settings(**payload)
    return JSONResponse(status_code=200, content={"message": "AI settings updated successfully"})

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
async def admin_public_demo(credentials: HTTPBasicCredentials = Depends(security)):
    check_admin_credentials(credentials)
    return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "admin_public_demo.html"))

# DEMO USE CASES

@router.get("/admin/demo/use-cases", tags=["Admin"])
async def get_use_cases(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Returns array of { id, title, description, thumbnail }
    """
    check_admin_credentials(credentials)
    use_cases = PublicDemoDbCore.get_all_use_cases() or []
    result = []
    for uc in use_cases:
        item = {
            "id": uc.get("id"),
            "title": uc.get("title"),
            "description": uc.get("description"),
            "thumbnail": uc.get("thumbnail") and {
                "data": base64.b64encode(uc["thumbnail"]).decode()
            }
        }
        # sample CSV
        if uc.get("sample_input_file_csv"):
            b = uc["sample_input_file_csv"]
            item["sample_input_file_csv"] = {"data": base64.b64encode(b).decode(), "mime": "text/csv"}
        # sample Excel
        if uc.get("sample_input_file_excel"):
            b = uc["sample_input_file_excel"]
            item["sample_input_file_excel"] = {"data": base64.b64encode(b).decode(), "mime": _detect_mime(b)}
        # prompt config (CSV or Excel)
        if uc.get("prompt_config_file"):
            b = uc["prompt_config_file"]
            item["prompt_config_file"] = {"data": base64.b64encode(b).decode(), "mime": _detect_mime(b)}
        result.append(item)
    return JSONResponse(content=result)

@router.get("/admin/demo/use-cases/{use_case_id}", tags=["Admin"])
async def get_use_case(use_case_id: int, credentials: HTTPBasicCredentials = Depends(security)):
    """
    Returns a single use case by its ID, including sample input files and prompt config if present.
    """
    check_admin_credentials(credentials)
    use_case = PublicDemoDbCore.get_use_case_by_id(use_case_id)
    if not use_case:
        return JSONResponse(status_code=404, content={"detail": "Use case not found"})
    cfg = {}
    # thumbnail
    if use_case.get("thumbnail"):
        cfg["thumbnail"] = {"data": base64.b64encode(use_case["thumbnail"]).decode()}
    # sample CSV
    if use_case.get("sample_input_file_csv"):
        b = use_case["sample_input_file_csv"]
        cfg["sample_input_file_csv"] = {"data": base64.b64encode(b).decode(), "mime": "text/csv"}
    # sample Excel
    if use_case.get("sample_input_file_excel"):
        b = use_case["sample_input_file_excel"]
        cfg["sample_input_file_excel"] = {"data": base64.b64encode(b).decode(), "mime": _detect_mime(b)}
    # prompt config
    if use_case.get("prompt_config_file"):
        b = use_case["prompt_config_file"]
        cfg["prompt_config_file"] = {"data": base64.b64encode(b).decode(), "mime": _detect_mime(b)}
    resp = {
        "id": use_case.get("id"),
        "title": use_case.get("title"),
        "description": use_case.get("description"),
        **cfg,
        "created_at": str(use_case.get("created_at")) if use_case.get("created_at") else None,
        "updated_at": str(use_case.get("updated_at")) if use_case.get("updated_at") else None
    }
    return JSONResponse(content=resp)


@router.put("/admin/demo/use-cases/{use_case_id}", tags=["Admin"])
async def update_use_case(
    use_case_id: int,
    title: str = Form(...),
    description: str = Form(None),
    thumbnail: UploadFile = File(None),
    sample_input_file_csv: UploadFile = File(None),
    sample_input_file_excel: UploadFile = File(None),
    prompt_config_file: UploadFile = File(None),
    credentials: HTTPBasicCredentials = Depends(security)
):
    check_admin_credentials(credentials)
    update_fields = {"title": title, "description": description}
    if thumbnail:
        update_fields["thumbnail"] = await thumbnail.read()
    if sample_input_file_csv:
        update_fields["sample_input_file_csv"] = await sample_input_file_csv.read()
    if sample_input_file_excel:
        update_fields["sample_input_file_excel"] = await sample_input_file_excel.read()
    if prompt_config_file:
        update_fields["prompt_config_file"] = await prompt_config_file.read()
    updated = PublicDemoDbCore.update_use_case(use_case_id, **{k: v for k, v in update_fields.items() if v is not None})
    if not updated:
        raise HTTPException(status_code=404, detail="Use case not found or nothing to update.")
    return {"detail": "Use case updated successfully."}

@router.delete("/admin/demo/use-cases/{use_case_id}", tags=["Admin"])
async def delete_use_case(
    use_case_id: int,
    credentials: HTTPBasicCredentials = Depends(security)
):
    check_admin_credentials(credentials)
    deleted = PublicDemoDbCore.delete_use_case(use_case_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Use case not found.")
    return {"detail": "Use case deleted successfully."}


@router.get("/admin/demo/settings", tags=["Admin"])
async def get_demo_settings(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Get demo settings (model_default, model_fallback).
    """
    check_admin_credentials(credentials)
    _settings = PublicDemoSettingsDbCore.get_demo_settings()
    if not _settings:
        return JSONResponse(status_code=404, content={"detail": "Settings not found"})
    return JSONResponse(content=_settings)


@router.put("/admin/demo/settings", tags=["Admin"])
async def update_demo_settings(
    model_default: str = Form(None),
    model_fallback: str = Form(None),
    credentials: HTTPBasicCredentials = Depends(security)
):
    check_admin_credentials(credentials)
    updated = PublicDemoSettingsDbCore.update_demo_settings(model_default=model_default, model_fallback=model_fallback)
    if not updated:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    return {"detail": "Settings updated successfully."}

@router.post("/admin/demo/use-cases", tags=["Admin"])
async def create_use_case(
    _: Request,
    title: str = Form(...),
    description: str = Form(None),
    thumbnail: UploadFile = File(None),
    sample_input_file_csv: UploadFile = File(None),
    sample_input_file_excel: UploadFile = File(None),
    prompt_config_file: UploadFile = File(None),
    credentials: HTTPBasicCredentials = Depends(security)
):
    check_admin_credentials(credentials)
    # user_id is no longer used
    thumbnail_bytes = await thumbnail.read() if thumbnail else None
    csv_bytes = await sample_input_file_csv.read() if sample_input_file_csv else None
    excel_bytes = await sample_input_file_excel.read() if sample_input_file_excel else None
    prompt_config_bytes = await prompt_config_file.read() if prompt_config_file else None
    new_id = PublicDemoDbCore.create_use_case(
        title=title,
        description=description,
        thumbnail=thumbnail_bytes,
        sample_input_file_csv=csv_bytes,
        sample_input_file_excel=excel_bytes,
        prompt_config_file=prompt_config_bytes
    )
    if not new_id:
        raise HTTPException(status_code=500, detail="Failed to create use case.")
    return {"id": new_id}
