


import asyncio
import csv
import json
import mimetypes
import os
from threading import Thread
from typing import Any, Dict
from fastapi.responses import JSONResponse
import pandas as pd
from enum import Enum
import logging
from tempfile import NamedTemporaryFile
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.microsites import MicrositesRunsDbCore
from enhancifai_backend.engine.public_microsites.runs_progress import runs_progress
from enhancifai_backend.server.models.execution import PromptObject, RunProgressRequest
from enhancifai_backend.server.public_microsites.hooks import handle_csv_file, handle_excel_file
from enhancifai_backend.server.routes.files_routes import save_to_cache
from enhancifai_backend.server.utils import verify_secret_key

TEST_MAX_RECORDS = 10
GLOBAL_MAX_ROWS = settings.global_max_rows
GLOBAL_MAX_PROMPTS = settings.global_max_prompts
EXCEL_MIME_TYPES = ['application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']

class EngineType(str, Enum):
    gpt_4_1_nano = "gpt-4.1-nano"
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
                logging.error(e)
                logging.error("CSV file format is incorrect.")
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
        run_id, data_file, prompts, max_recs,
        file_name, batched_processing=False, performance_optimization=False
):
    coro = process_run(
        run_id,
        data_file,
        prompts,
        max_recs,
        file_name,
        batched_processing=batched_processing,
        performance_optimization=performance_optimization
    )
    asyncio.run(coro)

async def process_run(run_id, data_file, prompts, max_recs, file_name,
                        batched_processing=False, performance_optimization=False):

    # Guess the MIME type based on the file extension
    mime_type, _ = mimetypes.guess_type(data_file)

    if mime_type == 'text/csv':
        results = await handle_csv_file(
            run_id=run_id,
            csv_file=data_file,
            prompts=prompts,
            max_recs=max_recs,
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



@router.post("/microsites/execution/progress", tags=["Microsites - Execution"])
async def check_run_progress(req_run: RunProgressRequest, _: str = Depends(verify_secret_key)):
    """Check the progress of a given Run ID."""
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
                    # Only return completed if results are present
                    if "results" not in _status or not _status["results"]:
                        # If results are not yet available, keep status as pending
                        return JSONResponse(status_code=status.HTTP_200_OK, content={
                            "status": "pending",
                            "progress": "100",
                            "remark": "Finalizing results..."
                        })
                    logging.info("Status: %s", _status)
                    input_tokens = _status.get("results", {}).get("input_tokens_sum", 0)
                    output_tokens = _status.get("results", {}).get("output_tokens_sum", 0)
                    total_tokens_sum = input_tokens + output_tokens
                    _status['results']['total_tokens_sum'] = total_tokens_sum
                return JSONResponse(status_code=status.HTTP_200_OK, content=_status)
            else:
                raise HTTPException(status_code=400, detail=f"Run ID '{req_run.run_id}' not found.")
        except HTTPException as e:
            logging.error(e)
            if attempt < retries - 1:
                await asyncio.sleep(0.5)  # wait for 0.5 seconds before retrying
                continue
            else:
                return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        except Exception as e:
            # Catch-all for unexpected errors
            logging.error(e)
            return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    # If we get here, it means all retries have failed
    return JSONResponse(
        status_code=400,
        content={
            "detail": f"Run ID '{req_run.run_id}' not found after {retries} attempts."
        }
    )


@router.post("/microsites/execution/direct", tags=["Microsites - Execution"])
async def upload_direct_prompt(
    req: Request,
    function_name: str = Form(...),
    function_params: str = Form('{}'),
    data_file: UploadFile = File(None),
    _: str = Depends(verify_secret_key),
):
    """
    Upload a CSV/Excel file or provide JSON data, with prompts payload.

    This endpoint processes the uploaded file, extracts columns, and starts an asynchronous run.

    Params:
    - `function_name`: Name of the function to execute.
    - `function_params`: JSON string containing parameters for the function. For example. `{"include_descriptions": true}`
    - `data_file`: The file to be processed (CSV or Excel).
    """
    logging.debug("Entered upload_direct_prompt endpoint")
    logging.debug("Data file provided: %s", "Yes" if data_file else "No")

    try:
        function_params_dict: Dict[str, Any] = json.loads(function_params)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON for function_params: {e}")

    ip_address = req.client.host

    max_recs = 0

    temp_data_file_path = None
    data_file_suffix = None
    file_name = None
    sheet_name = None

    if not data_file:
        logging.error("No data file provided")
        raise HTTPException(status_code=400, detail="Data file is required.")

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

    # Handling Data File with empty content check
    try:
        with NamedTemporaryFile(delete=False, dir='/tmp', suffix=data_file_suffix) as temp_data_file:
            temp_data_file_path = temp_data_file.name
            logging.debug("Created temporary data file at %s", temp_data_file_path)
            data_contents = await data_file.read()
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

    # Check if data file exceeds max_recs when max_recs > 0
    if max_recs > 0:
        if data_file_suffix == '.csv':
            df = pd.read_csv(temp_data_file_path)
        else:
            df = pd.read_excel(temp_data_file_path)
        if df.shape[0] > max_recs:
            raise HTTPException(status_code=400, detail="Trial User maximum exceeded - Maximum 20 rows per file allowed")

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

    
    max_prompts = GLOBAL_MAX_PROMPTS

    if function_name == 'fix-product-titles':
        read_prompts = [
            {
                'prompt_number': '1',
                'columns': '*',
                'prompt': "Rewrite the product title to be clean, descriptive, and shopper-friendly. Fix grammar, add missing context if necessary, and keep it under 60 characters. Remove filler words and ensure it's ready for eCommerce listing.",
                'output_heading': 'New Title'
            }
        ]
        if 'include_descriptions' in function_params_dict:
            if function_params_dict['include_descriptions'] is True:
                read_prompts.append(
                    {
                        'prompt_number': '2',
                        'columns': '*',
                        'prompt': "Write a short, compelling product description based on the title. Highlight key features and use cases in 1 to 2 sentences. Use clear, professional language suitable for an online store.",
                        'output_heading': 'New Description'
                    }
                )
    else:
        # unsupported function_name
        logging.error("Unsupported function_name: %s", function_name)
        raise HTTPException(status_code=400, detail=f"Unsupported function_name: {function_name}")

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
        run_id = MicrositesRunsDbCore.new_run(ip_address=ip_address, source_type=run_type)
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
        save_to_cache(temp_data_file_path, "public", file_name)
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
                file_name
            ),
            kwargs={
                "batched_processing": True,
                "performance_optimization": True,
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



