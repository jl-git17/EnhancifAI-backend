from datetime import datetime, timezone
import json
import mimetypes
import asyncio
import csv
import logging
from enum import Enum
import os
from tempfile import NamedTemporaryFile
from threading import Thread
import time
import uuid
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
import openpyxl
import pandas as pd

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.engine.prompts import PromptsProcessor
from enhancifai_backend.engine.runs_progress import runs_progress
from enhancifai_backend.server.hooks import handle_csv_file, handle_excel_file, pi_ai_connection
from enhancifai_backend.server.models.execution import (
    PromptImproveRequest, PromptObject, RunCancelsRequest, RunProgressRequest, RunDataRequest)
from enhancifai_backend.database.handlers.run_logs import PromptImproverRunLogsDbCore
from enhancifai_backend.server.routes.files_routes import save_to_cache
from enhancifai_backend.server.utils import (
    STATIC_FILES_DIRECTORY, get_current_user_id, verify_secret_key)

MAX_RECORDS = 10
GLOBAL_MAX_ROWS = settings.global_max_rows
GLOBAL_MAX_PROMPTS = settings.global_max_prompts
EXCEL_MIME_TYPES = ['application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']

class EngineType(str, Enum):
    gpt_4_o = "gpt-4o"
    gpt_4_o_mini = "gpt-4o-mini"
    gpt_3_5_turbo = "gpt-3.5-turbo"

router = APIRouter()

def read_prompt_file(prompt_file_path: str):
    """
    Reads and validates prompts from a CSV file.
    """
    valid_prompts = []
    errors = []
    with open(prompt_file_path, newline='', encoding='utf-8') as csvfile:
        i = 1
        reader = csv.DictReader(csvfile)
        for row in reader:
            try:
                prompt_number = row['Line Number']
                columns = row['Columns being Referenced']
                prompt = row['The Prompt']
                output_heading = row['Output Heading']

                if not prompt_number.isdigit():
                    errors.append(f"Row {i} >> Invalid prompt number: {prompt_number}")
                    continue

                columns = columns.replace(" ", "").upper()
                if (columns != '*' and not all(c.isalpha() and
                            len(c) == 1 for c in columns.split('+'))):
                    if '+' not in columns:
                        errors.append(
                            "'Columns being Referenced' must be separated "
                            "by a '+' (plus) character."
                            f"\nSubmitted columns: ({columns})")
                    else:
                        errors.append(f"Invalid 'Columns being Referenced' format: ({columns})")
                    continue

                if not prompt:
                    errors.append("Missing prompt text")
                    continue

                valid_prompts.append(
                    {
                        'prompt_number': prompt_number,
                        'columns': columns,
                        'prompt': prompt,
                        'output_heading': output_heading
                    }
                )
                i += 1
            except KeyError as e:
                print(e)
                print("CSV file format is incorrect.")
                errors.append(f"CSV is missing a column: {e}")
                break
    errors = list(set(errors))
    if len(errors) > 0:
        _errors = '\n\n'.join(errors).strip()
        raise HTTPException(status_code=400, detail=_errors)

    return valid_prompts

def extract_columns_from_file(file_path):
    # Read the file based on its extension
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    elif file_path.endswith(('.xls', '.xlsx')):
        df = pd.read_excel(file_path)
    else:
        raise ValueError("Unsupported file format")

    # Extract columns and format them as JSON objects
    columns = {chr(65 + i): col for i, col in enumerate(df.columns)}
    extracted_columns = [columns]
    return extracted_columns

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
            performance_optimization=performance_optimization
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
            performance_optimization=performance_optimization
        )
    else:
        # Handle unsupported file types or add more conditions for other types
        results = f"Unsupported file type: {mime_type}"

    # Assuming runs_progress is defined elsewhere to track the progress of runs
    runs_progress.update_details(run_id=run_id, details=results)

def cleanup_temp_files(prompt_file_path, data_file_path):
    if prompt_file_path and os.path.exists(prompt_file_path):
        os.remove(prompt_file_path)
    if data_file_path and os.path.exists(data_file_path):
        os.remove(data_file_path)

def json_to_excel(json_data, output_path):
    df = pd.DataFrame(json_data)
    df.to_excel(output_path, index=False)

@router.post("/execution/progress", tags=["Execution"])
async def check_run_progress(req_run: RunProgressRequest, _: str = Depends(verify_secret_key),
                             user_id: int = Depends(get_current_user_id)):
    """Check the progress of a given Run ID."""
    ai_consent = UsersDbCore.check_ai_consent(user_id)
    if ai_consent is False:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail="User has not consented for AI usage."
        )
    retries = 3  # Number of retries
    for attempt in range(retries):
        try:
            _status = runs_progress.check_status(req_run.run_id)
            if _status:
                # Modify payload if status is 'new'
                if _status.get("status") == "new":
                    _status = {
                        "status": "pending",
                        "progress": "1",
                        "remark": "1% completed."
                    }
                # Ensure progress is not below 1% for 'pending'
                elif _status.get("status") == "pending" and int(_status.get("progress", "0").replace("%", "")) < 1:
                    _status["progress"] = "1"
                    _status["remark"] = "1% completed."
                elif _status.get("status") == "completed":
                    logging.info("Status: %s", _status)
                    attempts = 0
                    while 'results' not in _status and attempts < 3:
                        time.sleep(1)
                        attempts += 1
                    input_tokens = _status.get("results", {}).get("input_tokens_sum", 0)
                    output_tokens = _status.get("results", {}).get("output_tokens_sum", 0)
                    total_tokens_sum = input_tokens + output_tokens
                    _status['results']['total_tokens_sum'] = total_tokens_sum
                return JSONResponse(status_code=status.HTTP_200_OK, content=_status)
            else:
                raise HTTPException(status_code=400, detail=f"Run ID '{req_run.run_id}' not found.")
        except HTTPException as e:
            if attempt < retries - 1:
                await asyncio.sleep(0.5)  # wait for 2 seconds before retrying
                continue
            else:
                print(e)
                return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        except Exception as e:
            # Catch-all for unexpected errors
            print(e)
            return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    # If we get here, it means all retries have failed
    return JSONResponse(
        status_code=400,
        content={
            "detail": f"Run ID '{req_run.run_id}' not found after {retries} attempts."
        }
    )

@router.post("/execution/upload", tags=["Execution"])
async def upload_files(data_file: UploadFile = File(None), prompt_file: UploadFile = File(...),
                       json_data: str = Body(None), max_records: bool = Form(False),
                       _: str = Depends(verify_secret_key), user_id: int = Depends(get_current_user_id)):
    """
    Upload a CSV/Excel file or provide JSON data, and a prompt file (CSV or Excel).
    """
    ai_consent = UsersDbCore.check_ai_consent(user_id)
    if ai_consent is False:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail="User has not consented for AI usage."
        )

    temp_data_file_path = None
    temp_prompt_file_path = None
    data_file_suffix = None
    file_name = None
    sheet_name = None

    if data_file and json_data:
        raise HTTPException(status_code=400, detail="Cannot upload both a file and JSON data. Provide either one.")

    if json_data:
        try:
            _json_data = json.loads(json_data)
            sheet_name = _json_data['sheet_name']
            data_json = _json_data['data']
            with NamedTemporaryFile(delete=False, dir='/tmp', suffix='.xlsx') as temp_data_file:
                temp_data_file_path = temp_data_file.name
                json_to_excel(data_json, temp_data_file_path)
            file_name = f"{sheet_name}.xlsx"
            data_file_suffix = '.xlsx'
        except Exception as err:
            print(err)
            raise HTTPException(status_code=400, detail="Invalid JSON data.") from err
    elif data_file:
        file_suffix_map = {
            'text/csv': '.csv',
            'application/vnd.ms-excel': '.xls',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
        }
        data_file_suffix = file_suffix_map.get(data_file.content_type, None)
        prompt_file_suffix = file_suffix_map.get(prompt_file.content_type, None)
        file_name = data_file.filename

        if not data_file_suffix:
            raise HTTPException(status_code=400, detail="Invalid data file type")

        if not prompt_file_suffix:
            raise HTTPException(status_code=400, detail="Invalid prompt file type")

        # Handling Data File
        with NamedTemporaryFile(delete=False, dir='/tmp', suffix=data_file_suffix) as temp_data_file:
            temp_data_file_path = temp_data_file.name
            data_contents = await data_file.read()

            temp_data_file.write(data_contents)
            temp_data_file.flush()

            # Debugging: Verify the temporary file creation
            if not os.path.exists(temp_data_file_path):
                print(f"Failed to create temp file at {temp_data_file_path}")
    else:
        raise HTTPException(status_code=400, detail="Either data file or JSON data must be provided.")

    # Handle Prompt File
    with NamedTemporaryFile(delete=False, dir='/tmp', suffix=prompt_file_suffix) as temp_prompt_file:
        temp_prompt_file_path = temp_prompt_file.name
        prompt_contents = await prompt_file.read()
        temp_prompt_file.write(prompt_contents)
        temp_prompt_file.flush()
        prompt_format = 'csv' if prompt_file_suffix == '.csv' else 'excel'
        prompts = PromptsProcessor.read_prompt_file(temp_prompt_file_path, file_format=prompt_format)

    # Proceed with existing logic after preparing the data file and prompt file
    # TODO: lift limits for subscribers
    max_recs = MAX_RECORDS if max_records else GLOBAL_MAX_ROWS

    # Extract columns from data file
    extracted_columns = extract_columns_from_file(temp_data_file_path)

    run_type = 'csv' if data_file_suffix == '.csv' else 'excel'
    if sheet_name:
        source_filename = sheet_name
    else:
        source_filename = str(file_name).replace(data_file_suffix, '')
    run_id = RunsDbCore.new_run(user_id, run_type, source_filename)
    runs_progress.add_run(run_id, None)

    save_to_cache(temp_data_file_path, user_id, file_name)
    save_to_cache(temp_prompt_file_path, user_id, prompt_file.filename)

    # Threading issues might arise if files are cleaned up too early,
    # consider alternatives or move cleanup to a more appropriate place
    try:
        Thread(
            target=start_async_run,
            args=(
                run_id, temp_data_file_path, prompts,
                max_recs, user_id, file_name
            )
        ).start()
    except Exception as e:
        print(f"Error starting async run: {str(e)}")
        time.sleep(1)
        cleanup_temp_files(temp_prompt_file_path, temp_data_file_path)
        raise HTTPException(status_code=500, detail="Failed to start the asynchronous process.") from e

    # Ensure files are cleaned up at the right time to avoid premature deletion
    #cleanup_temp_files(temp_prompt_file_path, None)

    return JSONResponse(status_code=200, content={'run_id': run_id, "data_columns": extracted_columns})

@router.post("/execution/cancel", tags=["Execution"])
async def cancel_run(req_run: RunCancelsRequest, _: str = Depends(verify_secret_key),
                             user_id: int = Depends(get_current_user_id)):
    """Cancel a job, given Run ID."""
    try:
        ai_consent = UsersDbCore.check_ai_consent(user_id)
        if ai_consent is False:
            raise HTTPException(
                status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
                detail="User has not consented for AI usage."
            )
        if RunsDbCore.check_run_ownership(user_id=user_id, run_id=req_run.run_id) is False:
            raise HTTPException(status_code=400, detail="User not owner of provided run_id.")
        RunsDbCore.cancel_run(req_run.run_id)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    return JSONResponse(status_code=200, content={"message": "Job cancelled successfully"})


@router.post("/execution/direct", tags=["Execution"])
async def upload_direct_prompt(
    prompts: str = Form(...),
    data_file: UploadFile = File(None),
    json_data: str = Body(None),
    max_records: bool = Form(...),
    batched_processing: bool = Form(False),
    performance_optimization: bool = Form(False),
    _: str = Depends(verify_secret_key),
    user_id: int = Depends(get_current_user_id)
):
    """
    Upload a CSV/Excel file or provide JSON data, with prompts payload.
    """
    logging.debug("Entered upload_direct_prompt endpoint")
    logging.debug("User ID: %s", user_id)
    logging.debug("Prompts: %s", prompts)
    logging.debug("Data file provided: %s", "Yes" if data_file else "No")
    logging.debug("JSON data provided: %s", "Yes" if json_data else "No")
    logging.debug("Max records flag: %s", max_records)

    ai_consent = UsersDbCore.check_ai_consent(user_id)
    logging.debug("AI consent for user %s: %s", user_id, ai_consent)
    if not ai_consent:
        logging.warning("User %s has not consented for AI usage.", user_id)
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail="User has not consented for AI usage."
        )

    temp_data_file_path = None
    data_file_suffix = None
    file_name = None
    sheet_name = None

    if data_file and json_data:
        logging.error("Both data_file and json_data provided. This is not allowed.")
        raise HTTPException(
            status_code=400,
            detail="Cannot upload both a file and JSON data. Provide either one."
        )

    if json_data:
        logging.info("Processing JSON data")
        try:
            logging.debug("JSON data received: %s", json_data)
            _json_data = json.loads(json_data)
            logging.debug("Parsed JSON data: %s", _json_data)
            sheet_name = _json_data['sheet_name']
            logging.debug("Sheet name extracted: %s", sheet_name)
            data_json = _json_data['data']
            with NamedTemporaryFile(delete=False, dir='/tmp', suffix='.xlsx') as temp_data_file:
                temp_data_file_path = temp_data_file.name
                logging.debug("Created temporary data file at %s", temp_data_file_path)
                json_to_excel(data_json, temp_data_file_path)
            file_name = f"{sheet_name}.xlsx"
            data_file_suffix = '.xlsx'
            logging.info("JSON data converted to Excel: %s", file_name)
        except KeyError as e:
            logging.exception("Missing key in JSON data")
            raise HTTPException(status_code=400, detail="Invalid JSON data.") from e
        except Exception as err:
            logging.exception("Error processing JSON data")
            raise HTTPException(status_code=400, detail="Invalid JSON data.") from err
    elif data_file:
        logging.info("Processing uploaded data file")
        file_suffix_map = {
            'text/csv': '.csv',
            'application/vnd.ms-excel': '.xls',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
        }
        data_file_suffix = file_suffix_map.get(data_file.content_type, None)
        file_name = data_file.filename

        logging.debug("Received data file '%s' with content type: %s", file_name, data_file.content_type)

        if not data_file_suffix:
            logging.error("Invalid data file type: %s", data_file.content_type)
            raise HTTPException(status_code=400, detail="Invalid data file type")

        prompt_file_suffix = file_suffix_map.get(data_file.content_type, None)  # Assuming prompt_file has similar types
        if not prompt_file_suffix:
            logging.error("Invalid prompt file type for content type: %s", data_file.content_type)
            raise HTTPException(status_code=400, detail="Invalid prompt file type")

        # Handling Data File
        try:
            with NamedTemporaryFile(delete=False, dir='/tmp', suffix=data_file_suffix) as temp_data_file:
                temp_data_file_path = temp_data_file.name
                logging.debug("Created temporary data file at %s", temp_data_file_path)
                data_contents = await data_file.read()
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
    else:
        logging.error("Neither data_file nor json_data provided")
        raise HTTPException(status_code=400, detail="Either data file or JSON data must be provided.")

    # Handle Prompts
    try:
        if data_file:
            logging.info("Processing uploaded prompt file")
            #prompt_file = data_file  # Adjust if prompt_file is different
            # Implement prompt file handling if necessary
            # For now, assuming prompt_file_suffix and temp_prompt_file_path are handled elsewhere
    except Exception as e:
        logging.exception("Error processing prompt file")
        raise HTTPException(status_code=500, detail="Failed to process prompt file.") from e

    # Handle Prompts from 'prompts' Form Field
    try:
        logging.debug("Parsing prompts payload: %s", prompts)
        prompt_list = json.loads(prompts)
        logging.debug("Parsed prompts list: %s", prompt_list)
    except json.JSONDecodeError as e:
        logging.exception("Invalid JSON in prompts payload")
        raise HTTPException(status_code=400, detail="Invalid prompts payload.") from e

    try:
        read_prompts = PromptsProcessor.read_prompt_objects(
            [PromptObject(**prompt) for prompt in prompt_list]
        )
        logging.info("Read %s prompts successfully", len(read_prompts))
    except Exception as e:
        logging.exception("Error reading prompt objects")
        raise HTTPException(status_code=400, detail="Invalid prompts format.") from e

    max_recs = MAX_RECORDS if max_records else GLOBAL_MAX_ROWS
    logging.debug("Max records set to: %s", max_recs)

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
    source_filename = sheet_name if sheet_name else os.path.splitext(file_name)[0]
    logging.debug("Run type: %s, Source filename: %s", run_type, source_filename)

    try:
        run_id = RunsDbCore.new_run(user_id, run_type, source_filename)
        if not run_id:
            raise HTTPException(status_code=500, detail="Failed to created new run.")
        logging.info("Created new run with ID: %s", run_id)
        runs_progress.add_run(run_id, None)
        logging.debug("Added run %s to runs_progress", run_id)
    except Exception as e:
        logging.exception("Error creating new run")
        cleanup_temp_files(None, temp_data_file_path)
        raise HTTPException(status_code=500, detail="Failed to create new run.") from e

    try:
        save_to_cache(temp_data_file_path, user_id, file_name)
        logging.debug("Saved data file to cache for run %s", run_id)
    except Exception as e:
        logging.exception("Error saving data file to cache")
        cleanup_temp_files(None, temp_data_file_path)
        raise HTTPException(status_code=500, detail="Failed to save data file to cache.") from e

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
                user_id,
                file_name
            ),
            kwargs={
                "batched_processing": batched_processing,
                "performance_optimization": performance_optimization,
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


@router.post("/execution/upload/prompts", tags=["Execution"])
async def upload_prompts(prompt_file: UploadFile = File(...), _: str = Depends(verify_secret_key),
                           user_id: int = Depends(get_current_user_id)):
    """
    Upload a prompts file, process it and return the prompts.
    """
    try:
        # Check AI consent
        ai_consent = UsersDbCore.check_ai_consent(user_id)
        if ai_consent is False:
            raise HTTPException(
                status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
                detail="User has not consented for AI usage."
            )
        # Determine the suffix for the file based on its content type
        file_suffix_map = {
            'text/csv': '.csv',
            'application/vnd.ms-excel': '.xls',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
        }
        prompt_file_suffix = file_suffix_map.get(prompt_file.content_type, None)

        if not prompt_file_suffix:
            raise HTTPException(status_code=400, detail="Invalid prompt file type")

        # Handle Prompt File
        with NamedTemporaryFile(delete=False, dir='/tmp', suffix=prompt_file_suffix) as temp_prompt_file:
            temp_prompt_file_path = temp_prompt_file.name
            prompt_contents = await prompt_file.read()
            temp_prompt_file.write(prompt_contents)
            temp_prompt_file.flush()
            prompt_format = 'csv' if prompt_file_suffix == '.csv' else 'excel'
            prompts = PromptsProcessor.read_prompt_file(temp_prompt_file_path, file_format=prompt_format)

        # Process the prompts to the required format
        processed_prompts = [
            {
                "prompt": prompt['prompt'],
                "output_heading": prompt['output_heading'],
                "columns": prompt['columns']
            }
            for prompt in prompts
        ]

        # Cleanup prompt file after processing
        cleanup_temp_files(temp_prompt_file_path, None)

        return JSONResponse(status_code=200, content={
            "message": "Prompts file processed successfully.",
            "prompts": processed_prompts
        })

    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})

@router.post("/execution/download/prompts", tags=["Execution"])
async def download_prompts(prompts: str = Form(...), _: str = Depends(verify_secret_key),
                           user_id: int = Depends(get_current_user_id)):
    """
    Helper endpoint to get a Prompts file from Prompts payload.
    """
    try:
        # Check AI consent
        ai_consent = UsersDbCore.check_ai_consent(user_id)
        if ai_consent is False:
            raise HTTPException(
                status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
                detail="User has not consented for AI usage."
            )
        file_path = os.path.join(STATIC_FILES_DIRECTORY, "prompts_template.xlsx")
        unique_filename = f"prompts_{uuid.uuid4()}_{int(time.time()*1000)}.xlsx"
        processed_excel_path = os.path.join('/tmp', unique_filename)

        try:
            prompt_list = json.loads(prompts)
            wb = openpyxl.load_workbook(file_path)
            sheet = wb.active

            for idx, prompt in enumerate(prompt_list, start=1):
                sheet[f'A{idx + 1}'] = idx
                sheet[f'B{idx + 1}'] = prompt['columns']
                sheet[f'C{idx + 1}'] = prompt['prompt']
                sheet[f'D{idx + 1}'] = prompt['output_heading']

            wb.save(processed_excel_path)
            return FileResponse(
                processed_excel_path,
                media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                filename="prompts.xlsx"
            )

        except Exception as err:
            raise HTTPException(status_code=400, detail="Invalid prompts payload.") from err

    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})

@router.post("/execution/get-data", tags=["Execution"])
async def get_data(
    req_data: RunDataRequest,
    _: str = Depends(verify_secret_key),
    user_id: int = Depends(get_current_user_id)
):
    """
    Retrieve CSV or Excel data for a given run_id and return it in JSON format.
    """
    try:
        # Check AI consent
        ai_consent = UsersDbCore.check_ai_consent(user_id)
        if ai_consent is False:
            raise HTTPException(
                status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
                detail="User has not consented for AI usage."
            )
        # Get the file URL using the run_id
        file_url = RunsDbCore.get_run_file_url(req_data.run_id)
        if not file_url:
            raise HTTPException(status_code=404, detail="File not found for the given run_id")

        # Determine the file type based on the file extension
        file_extension = os.path.splitext(file_url)[-1].lower()
        if file_extension not in ['.csv', '.xlsx', '.xls']:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        # Read the file content and convert it to JSON
        if file_extension == '.csv':
            data = pd.read_csv(file_url)
        else:  # Excel file
            data = pd.read_excel(file_url)

        # Convert DataFrame to JSON
        data_json = data.to_json()

        return JSONResponse(status_code=200, content={
                "message": "Data file retrieved successfully.",
                "prompts": data_json
        })

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred", "error": str(e)}
        )

@router.post("/execution/tools/ai-prompt-improver", tags=["Execution"])
async def ai_prompt_improver(
    prompt_data: PromptImproveRequest,
    _: str = Depends(verify_secret_key),
    user_id: int = Depends(get_current_user_id)
):
    """
    Enhance the provided prompt data using AI tools.

    This endpoint takes in a list of prompts and processes them using an AI-driven prompt improver. 
    The AI model aims to refine and optimize the prompts for better clarity, focus, or effectiveness.
    
    Args:
        prompt_data (PromptImproveRequest): The request body containing a list of prompt strings.
        _ (str): Secret key for verification (handled by FastAPI's dependency injection).
        user_id (int): The ID of the current user (handled by FastAPI's dependency injection).

    Returns:
        JSONResponse: A JSON response containing a message and the improved prompts.

    Note:
        The user_id is used to log for usage tracking in future updates.
    """
    try:
        start_time = time.time()
        new_prompt = pi_ai_connection.improve_prompt(prompt_data.prompt, user_id)
        if not new_prompt or not isinstance(new_prompt,dict):
            raise HTTPException(status_code=404, detail="Error in processing request.")
        # save to log file
        end_time = time.time()
        logging.info("new_prompt: %s", new_prompt)
        PromptImproverRunLogsDbCore.insert_log(
            user_id=user_id,
            engine_model="gpt-4o-mini",
            log_timestamp=datetime.now(tz=timezone.utc),
            time_elapsed=end_time - start_time,
            num_prompts=1,
            input_tokens=new_prompt['input_tokens'],
            output_tokens=new_prompt['output_tokens'],
        )
        return JSONResponse(status_code=200, content={
                "message": "Prompts improved successfully.",
                "new_prompt": new_prompt['content']
        })
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
