import gspread
from oauth2client.service_account import ServiceAccountCredentials
import string
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from enhancifai_backend.ai.openai_api import OpenAIConnector

MAX_THREADS = 4

class GoogleSheetsHandler:
    def __init__(self, spreadsheet_id, sheet_name, engine, creds_json):
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.engine = engine
        self.creds_json = creds_json
        self.lock = threading.Lock()
        self.data = []
        self.processed = 0
        self.row_completion = {}
        self.gc = self.authenticate_google_sheets(self.creds_json)
        self.sheet = self.gc.open_by_key(self.spreadsheet_id).worksheet(self.sheet_name)

    def authenticate_google_sheets(self, creds_json):
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_json, scope)
        return gspread.authorize(creds)

    def load_sheet(self):
        # Load all records from the sheet
        records = self.sheet.get_all_records()
        if not records:
            print("Sheet is empty.")
            return False
        self.data = records
        return True

    def process_row(self, idx, row, prompt_config):
        result = {"row_index": idx, "prompt_number": prompt_config['prompt_number']}
        output_heading = prompt_config['output_heading']

        # Call the OpenAIConnector with the row
        data = self.openai_connector.process_csv_row(rows=row, query=prompt_config['prompt'])
        result[f"tokens_{output_heading}"] = data.get("tokens", "")
        result[f"{output_heading}"] = data.get("content", "")

        # Thread-safe increment of the row completion count
        with self.lock:
            if idx in self.row_completion:
                self.row_completion[idx] += 1
            else:
                self.row_completion[idx] = 1

        return result
    
    def process_sheet(self, prompts: list, openai_api_key: str, max_records=None):
        self.openai_connector = OpenAIConnector(self.engine, openai_api_key)
        start_time = time.time()

        loaded = self.load_sheet()
        if not loaded:
            return {"total_records": 0, "processed_records": 0, "time_elapsed": 0}

        total_records = min(len(self.data), max_records) if max_records else len(self.data)
        results = []

        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = {}
            processed_rows_set = set()

            for idx, row in enumerate(self.data):
                if idx >= total_records:
                    break
                for prompt_config in prompts:
                    future = executor.submit(self.process_row, idx, row, prompt_config)
                    futures[future] = idx
                    time.sleep(1)

            num_prompts = len(prompts)
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    row_index = futures[future]

                    with self.lock:
                        if self.row_completion.get(row_index, 0) == num_prompts:
                            if row_index not in processed_rows_set:
                                processed_rows_set.add(row_index)
                                self.processed += 1
                except Exception as e:
                    print(f"Error in processing row {futures[future]}: {e}")

        # Update sheet with results
        self.update_sheet_with_results(results)

        end_time = time.time()
        return {
        "total_records": len(self.data),
        "processed_records": self.processed,
        "time_elapsed": end_time - start_time,
    }

    def update_sheet_with_results(self, results):
        # Assuming all results pertain to new columns to be added, find last column
        all_values = self.sheet.get_all_values()
        last_col_letter = string.ascii_uppercase[len(all_values[0])]
        new_col_start = chr(ord(last_col_letter) + 1)

        # Organize results by row
        results_by_row = {}
        for result in results:
            row_idx = result['row_index']
            if row_idx not in results_by_row:
                results_by_row[row_idx] = []
            results_by_row[row_idx].append(result)

        # Append results to sheet
        for row_idx, row_results in results_by_row.items():
            # Sort results by prompt number to maintain order
            row_results_sorted = sorted(row_results, key=lambda x: int(x['prompt_number']))
            update_values = [result[f"{self.sheet_name}"] for result in row_results_sorted]
            self.sheet.insert_row(update_values, row_idx + 2, value_input_option='RAW', table_range=f"{new_col_start}1")
