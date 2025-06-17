import os
import time
import uuid

from fastapi import HTTPException

from enhancifai_backend.config import settings
from enhancifai_backend.ai.openai_api import OpenAIConnector
from enhancifai_backend.ai.gemini import GeminiConnector
from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.engine.csv_handler import CSVHandler
from enhancifai_backend.engine.excel_handler import ExcelHandler
from enhancifai_backend.server.utils import AdminSettings

pi_ai_connection = OpenAIConnector()

def get_ai_connection(free_mode: bool, gemini: bool = False):
    if gemini:
        return GeminiConnector()
    else:
        return OpenAIConnector(free_mode)

async def handle_csv_file(csv_file, prompts, max_recs, run_id, user_id, filename,
                          free_mode:bool, batched_processing=False,
                          performance_optimization=False):
    """
    Handle CSV file processing, including new 'batched_processing' and
    'performance_optimization' parameters.
    """
    temp_csv_file_path = csv_file

    unique_filename = f"processed_{uuid.uuid4()}_{int(time.time()*1000)}.csv"
    processed_csv_path = os.path.join('/tmp', unique_filename)

    if performance_optimization:
        engine = AdminSettings.get_ai_engine_performance_optimization() # TODO: verify usefulness
    else:
        engine = AdminSettings.get_ai_engine()

    csv_handler = CSVHandler(
        run_id=run_id,
        file_path=temp_csv_file_path,
        output_file=processed_csv_path,
        ai_connector=get_ai_connection(free_mode=free_mode),
        user_id=user_id,
        filename=filename,
        batched_processing=batched_processing,
        performance_optimization=performance_optimization
    )

    loaded = csv_handler.load_csv()
    if loaded is True:
        results = csv_handler.process_csv(prompts, max_records=max_recs)
        if RunsDbCore.is_run_cancelled(run_id):
            RunsDbCore.cancel_run(run_id)
    else:
        if os.path.exists(temp_csv_file_path):
            os.remove(temp_csv_file_path)
        raise HTTPException(status_code=400, detail=f"Invalid CSV file.\n\n{loaded}")

    if os.path.exists(temp_csv_file_path):
        os.remove(temp_csv_file_path)

    host_address = settings.backend_url
    file_url = f"{host_address}/downloads/{unique_filename}"

    response_data = {
        "file_url": file_url,
        "results": results
    }
    return response_data

async def handle_excel_file(excel_file, prompts, max_recs, run_id, free_mode:bool,
                            user_id, filename, batched_processing=False,
                            performance_optimization=False):
    """
    Handle Excel file processing, including 'batched_processing' and
    'performance_optimization'.
    """
    temp_excel_file_path = excel_file
    file_extension = os.path.splitext(temp_excel_file_path)[1]

    unique_filename = f"processed_{uuid.uuid4()}_{int(time.time()*1000)}{file_extension}"
    processed_excel_path = os.path.join('/tmp', unique_filename)

    if performance_optimization:
        engine = AdminSettings.get_ai_engine_performance_optimization()
    else:
        engine = AdminSettings.get_ai_engine()
    excel_handler = ExcelHandler(
        run_id=run_id,
        file_path=temp_excel_file_path,
        output_file=processed_excel_path,
        ai_connector=get_ai_connection(free_mode=free_mode),
        engine=engine,
        user_id=user_id,
        filename=filename,
        batched_processing=batched_processing,
        performance_optimization=performance_optimization
    )

    if excel_handler.load_excel():
        results = excel_handler.process_excel(prompts, max_records=max_recs)
        if RunsDbCore.is_run_cancelled(run_id):
            RunsDbCore.cancel_run(run_id)
    else:
        if os.path.exists(temp_excel_file_path):
            os.remove(temp_excel_file_path)
        raise HTTPException(status_code=400, detail="Invalid Excel file.")

    if os.path.exists(temp_excel_file_path):
        os.remove(temp_excel_file_path)

    host_address = settings.backend_url
    file_url = f"{host_address}/downloads/{unique_filename}"

    response_data = {
        "file_url": file_url,
        "results": results
    }
    return response_data
