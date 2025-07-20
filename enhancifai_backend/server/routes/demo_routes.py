import asyncio
import json
import logging
import mimetypes
import os
from tempfile import NamedTemporaryFile
from threading import Thread
from fastapi import APIRouter, Body, Depends, File, Form, UploadFile, Request
from fastapi.responses import JSONResponse
import base64
from fastapi import HTTPException
import pandas as pd
import uuid
from fastapi.security import HTTPBasic

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.public_demo import PublicDemoDbCore, PublicDemoRunsDbCore
from enhancifai_backend.server.hooks import handle_csv_file, handle_excel_file
from enhancifai_backend.engine.prompts import PromptsProcessor
from enhancifai_backend.engine.runs_progress_free import runs_progress_free
from enhancifai_backend.server.utils import (
    CACHE_DIRECTORY_FREE, extract_columns_from_file,
    verify_secret_key, EXCEL_MIME_TYPES)

from enhancifai_backend.server.models.execution import PromptObject
from enhancifai_backend.server.routes.files_routes import save_to_cache


USERNAME = settings.admin_username
PASSWORD = settings.admin_password

security = HTTPBasic()

# TODO: harden security of admin accessed endpoints

GLOBAL_MAX_PROMPTS = settings.global_max_prompts
GLOBAL_MAX_ROWS = settings.global_max_rows

router = APIRouter()

def start_async_run(
        run_id, data_file, prompts, max_recs, user_id,
        file_name, batched_processing=False, performance_optimization=False
):
    coro = process_run(
        run_id,
        data_file,
        prompts,
        max_recs,
        user_id,
        file_name,
        batched_processing=batched_processing,
        performance_optimization=performance_optimization
    )
    asyncio.run(coro)

async def process_run(run_id, data_file, prompts, max_recs, user_id, file_name,
                        batched_processing=False, performance_optimization=False):

    # Guess the MIME type based on the file extension
    mime_type, _ = mimetypes.guess_type(data_file)

    if mime_type == 'text/csv':
        results = await handle_csv_file(
            run_id=run_id,
            csv_file=data_file,
            prompts=prompts,
            max_recs=max_recs,
            user_id=user_id,
            filename=file_name,
            batched_processing=batched_processing,
            performance_optimization=performance_optimization,
            free_mode=True
        )
    elif mime_type in EXCEL_MIME_TYPES:
        results = await handle_excel_file(
            run_id=run_id,
            excel_file=data_file,
            prompts=prompts,
            max_recs=max_recs,
            user_id=user_id,
            filename=file_name,
            batched_processing=batched_processing,
            performance_optimization=performance_optimization,
            free_mode=True
        )
    else:
        # Handle unsupported file types or add more conditions for other types
        results = f"Unsupported file type: {mime_type}"

    # Assuming runs_progress is defined elsewhere to track the progress of runs
    runs_progress_free.update_details(run_id=run_id, details=results)

def cleanup_temp_files(prompt_file_path, data_file_path):
    if prompt_file_path and os.path.exists(prompt_file_path):
        os.remove(prompt_file_path)
    if data_file_path and os.path.exists(data_file_path):
        os.remove(data_file_path)

def _detect_mime(file_bytes):
    return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if file_bytes[:2] == b'PK' else 'text/csv'

@router.get("/demo/use-cases", tags=["Demo"])
async def get_use_cases(_: str = Depends(verify_secret_key)):
    """
    Returns array of { id, title, description, thumbnail }
    """
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

@router.get("/demo/use-cases/{use_case_id}", tags=["Demo"])
async def get_use_case(use_case_id: int, _: str = Depends(verify_secret_key)):
    """
    Returns a single use case by its ID, including sample input files and prompt config if present.
    """
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

@router.post("/demo/run-demo", tags=["Demo (WIP)"])
async def do_demo_run(
    request: Request,
    use_case_id: int,
    prompt_config: str = Form(..., description="JSON string of prompt configuration"),
    sample_input_file: UploadFile = File(None, description="Sample input file (CSV/Excel)"),
    _: str = Depends(verify_secret_key)
):
    """
    Upload a CSV/Excel file or provide JSON data, with prompts payload.
    """
    logging.debug("Entered do_demo_run endpoint")
    logging.debug("Prompt Config: %s", prompt_config)
    logging.debug("Sample Input File provided: %s", "Yes" if sample_input_file else "No")

    try:
        logging.debug("Parsing prompts payload: %s", prompt_config)
        prompt_list = json.loads(prompt_config)
        logging.debug("Parsed prompts list: %s", prompt_list)
    except json.JSONDecodeError as e:
        logging.exception("Invalid JSON in prompts payload")
        raise HTTPException(status_code=400, detail="Invalid prompts payload.") from e

    read_prompts = PromptsProcessor.read_prompt_objects(
        [PromptObject(**prompt) for prompt in prompt_list],
        GLOBAL_MAX_PROMPTS
    )
    logging.info("Read %s prompts successfully", len(read_prompts))


    logging.info("Processing uploaded data file")
    file_suffix_map = {
        'text/csv': '.csv',
        'application/vnd.ms-excel': '.xls',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
    }
    data_file_suffix = file_suffix_map.get(sample_input_file.content_type, None)
    file_name = sample_input_file.filename

    logging.debug("Received data file '%s' with content type: %s", file_name, sample_input_file.content_type)

    if not data_file_suffix:
        logging.error("Invalid data file type: %s", sample_input_file.content_type)
        raise HTTPException(status_code=400, detail="Invalid data file type")

    # Handling Data File with empty content check
    try:
        with NamedTemporaryFile(delete=False, dir=CACHE_DIRECTORY_FREE, suffix=data_file_suffix) as temp_data_file:
            temp_data_file_path = temp_data_file.name
            logging.debug("Created temporary data file at %s", temp_data_file_path)
            data_contents = await sample_input_file.read()
            if not data_contents:
                raise HTTPException(status_code=400, detail="Data file is empty.")
            logging.debug("Read %s bytes from data file", len(data_contents))
            temp_data_file.write(data_contents)
            temp_data_file.flush()
            logging.debug("Data file written to temporary storage")

        if os.path.exists(temp_data_file_path):
            logging.info("Temporary data file exists at %s", temp_data_file_path)
        else:
            logging.error("Temporary data file not found at %s", temp_data_file_path)
            raise HTTPException(status_code=500, detail="Failed to create temporary data file.")
    except Exception as e:
        logging.exception("Error handling uploaded data file")
        raise HTTPException(status_code=500, detail="Failed to process uploaded data file.") from e

    if data_file_suffix == '.csv':
        df = pd.read_csv(temp_data_file_path)
    else:
        df = pd.read_excel(temp_data_file_path)
    if df.shape[0] > GLOBAL_MAX_ROWS:
        raise HTTPException(status_code=400, detail="Trial User maximum exceeded - Maximum 20 rows per file allowed")


    # Extract columns from data file
    try:
        logging.info("Extracting columns from data file at %s", temp_data_file_path)
        extracted_columns = extract_columns_from_file(temp_data_file_path)
        logging.debug("Extracted columns: %s", extracted_columns)
    except Exception as e:
        logging.exception("Error extracting columns from data file")
        cleanup_temp_files(None, temp_data_file_path)
        raise HTTPException(status_code=500, detail="Failed to extract columns from data file.") from e

    run_type = 'csv' if data_file_suffix == '.csv' else 'excel'
    source_filename = os.path.splitext(file_name)[0]
    logging.debug("Run type: %s, Source filename: %s", run_type, source_filename)

    # Get client IP address
    ip_address = request.client.host if request.client else ""

    # Generate a session_id
    session_id = str(uuid.uuid4())

    try:
        run_id = PublicDemoRunsDbCore.create_demo_run(
            use_case_id=use_case_id,
            session_id=session_id,
            ip_address=ip_address,
            source_type=run_type,
            source_filename=source_filename
        )
        if not run_id:
            raise HTTPException(status_code=500, detail="Failed to create new demo run.")
        logging.info("Created new demo run with ID: %s", run_id)
        runs_progress_free.add_run(run_id, None)
        logging.debug("Added run %s to runs_progress_free", run_id)
    except Exception as e:
        logging.exception("Error creating new run")
        cleanup_temp_files(None, temp_data_file_path)
        raise HTTPException(status_code=500, detail="Failed to create new run.") from e

    try:
        save_to_cache(temp_data_file_path, ip_address, file_name, free=True)
        logging.debug("Saved data file to cache for run %s", run_id)
    except Exception as e:
        logging.exception("Error saving data file to cache")
        cleanup_temp_files(None, temp_data_file_path)
        raise HTTPException(status_code=500, detail="Failed to save data file to cache.") from e

    max_recs = GLOBAL_MAX_ROWS

    # Start asynchronous run in a separate thread, passing batched_processing
    try:
        logging.info("Starting asynchronous run for run ID: %s", run_id)
        Thread(
            target=start_async_run,
            args=(
                run_id,
                temp_data_file_path,
                read_prompts,
                max_recs,
                ip_address,
                file_name
            ),
            kwargs={
                "batched_processing": False,
                "performance_optimization": False
            },
        ).start()
        logging.debug("Asynchronous run thread started successfully")
    except Exception as e:
        logging.exception("Error starting asynchronous run")
        cleanup_temp_files(None, temp_data_file_path)
        raise HTTPException(status_code=500, detail="Failed to start the asynchronous process.") from e

    logging.info("upload_direct_prompt completed successfully for run ID: %s", run_id)
    return JSONResponse(
        status_code=200,
        content={'run_id': run_id, "data_columns": extracted_columns}
    )
