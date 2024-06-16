import csv
from datetime import datetime, timezone
import json
import os
import string
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from enhancifai_backend.database.handlers.run_logs import RunLogsDbCore
from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.engine.runs_progress import runs_progress

MAX_THREADS = 2

class CSVHandler:
    def __init__(self, file_path, output_file, ai_connector, run_id, engine, user_id, filename):
        self.file_path = file_path
        self.filename = filename
        self.output_file = output_file
        self.ai_connector = ai_connector
        self.lock = threading.Lock()
        self.data = []
        self.processed = 0
        self.prompt_progress = 0  # Initialize prompt_progress
        self.row_completion = {}
        self.run_id = run_id
        self.engine = engine
        self.user_id = user_id
        self.errors = []
        self.overflow = False
    
    def _is_run_cancelled(self):
        return RunsDbCore.is_run_cancelled(self.run_id)

    def load_csv(self):
        encodings = ['utf-8', 'ISO-8859-1', 'Windows-1252']  # List of encodings to try
        errors =[]
        for encoding in encodings:
            print(f"Attempting to read CSV with encoding '{encoding}'")
            try:
                with open(self.file_path, mode='r', newline='', encoding=encoding) as file:
                    csv_reader = csv.DictReader(file)
                    self.data = [row for row in csv_reader]
                    if not self.data:
                        print("CSV is empty.")
                        return False
                    return True  # Successfully read, break the loop
            except UnicodeDecodeError as e:
                print(f"Error with encoding {encoding}: {e}")
            except Exception as e:
                errors.append(str(e))
                print(f"Error loading CSV: {e}")
                return '\n'.join(errors)
        print("Failed to read CSV with all attempted encodings.")
        return False

    def process_row(self, idx, row, prompt_config, columns_list):
        if self._is_run_cancelled():
            #print(f"Run {self.run_id} is cancelled. Skipping row {idx}.")
            return None
        RunsDbCore.set_run_checkin(self.run_id)
        result = {"row_index": idx, "prompt_number": prompt_config['prompt_number']}
        output_heading = prompt_config['output_heading']
        #temperature = prompt_config['temperature']
        #top_p = prompt_config['top_p']

        # Get the selected columns for this prompt
        selected_columns = self.get_selected_columns(prompt_config, columns_list)

        # Filter the row to only include selected columns
        filtered_row = {k: row[k] for k in selected_columns if k in row}

        # Call the OpenAIConnector with the filtered row
        data = self.ai_connector.process_csv_row(
            columns=columns_list,
            rows=filtered_row,
            query=prompt_config['prompt'],
            run_id=self.run_id
        )
        if data['engine_used'] != self.engine:
            self.overflow = True
        #result[f"tokens_{output_heading}"] = data.get("tokens", "")
        result[f"{output_heading}"] = data.get("content", "")

        # Thread-safe increment of the row completion count
        with self.lock:
            if idx in self.row_completion:
                self.row_completion[idx] += 1
            else:
                self.row_completion[idx] = 1

        return result
    
    def process_csv(self, prompts: list, max_records=0):
        start_time = time.time()

        loaded = self.load_csv()
        if not loaded:
            return {"total_records": 0, "processed_records": 0, "time_elapsed": 0}

        letter_to_column = self.create_column_mapping()

        total_records = min(len(self.data), max_records) if max_records > 0 else len(self.data)
        total_tasks = total_records * len(prompts)  # Calculate total tasks as records times prompts
        runs_progress.add_run(self.run_id, total_tasks)

        results = []

        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = {}
            processed_rows_set = set()  # Set to track completely processed rows

            for idx, row in enumerate(self.data):
                if idx >= total_records:
                    break
                
                for prompt_config in prompts:
                    if self._is_run_cancelled():  # Check if the run is cancelled
                        print(f"Run {self.run_id} cancelled, stopping processing.")
                        if self._is_run_cancelled():
                            end_time = time.time()
                            RunLogsDbCore.insert_log(
                                run_id=self.run_id,
                                user_name=UsersDbCore.get_user_name_by_id(self.user_id)['name'] or f"user_{self.user_id}",
                                engine_model=self.engine,
                                log_timestamp=datetime.now(tz=timezone.utc),
                                num_rows_processed=self.processed,
                                time_elapsed= end_time - start_time,
                                num_rows_in_file=len(self.data),
                                num_prompts=len(prompts),
                                num_tokens=sum(int(row.get('Total Tokens', 0)) for row in self.data),
                                errors=json.dumps(self.errors),
                                filename=self.filename,
                                overflow=self.overflow
                            )
                            # if job status changed in the leftover threads, make sure DB is consistent
                            RunsDbCore.cancel_run(self.run_id)
                            return {
                                "total_records": len(self.data),
                                "processed_records": self.processed,
                                "time_elapsed": end_time - start_time,
                                "total_tokens_sum": sum(int(row.get('Total Tokens', 0)) for row in self.data),
                                "error_count": len(self.errors),
                                "errors": self.errors
                            }
                    selected_columns = self.get_selected_columns(prompt_config, letter_to_column)
                    if selected_columns:
                        future = executor.submit(self.process_row, idx, {k: row[k] for k in selected_columns}, prompt_config, letter_to_column)
                        futures[future] = idx
                        if self.ai_connector.rate_limit is True:
                            time.sleep(0.2)

            num_prompts = len(prompts)
            for future in as_completed(futures):
                if self._is_run_cancelled():  # Check if the run is cancelled
                    print(f"Run {self.run_id} cancelled, stopping processing.")
                    if self._is_run_cancelled():
                        end_time = time.time()
                        RunLogsDbCore.insert_log(
                            run_id=self.run_id,
                            user_name=UsersDbCore.get_user_name_by_id(self.user_id)['name'] or f"user_{self.user_id}",
                            engine_model=self.engine,
                            log_timestamp=datetime.now(tz=timezone.utc),
                            num_rows_processed=self.processed,
                            time_elapsed=time.time() - start_time,
                            num_rows_in_file=len(self.data),
                            num_prompts=len(prompts),
                            num_tokens=sum(int(row.get('Total Tokens', 0)) for row in self.data),
                            errors=json.dumps(self.errors),
                            filename=self.filename,
                            overflow=self.overflow
                        )
                        # if job status changed in the leftover threads, make sure DB is consistent
                        RunsDbCore.cancel_run(self.run_id)
                        return {
                            "total_records": len(self.data),
                            "processed_records": self.processed,
                            "time_elapsed": end_time - start_time,
                            "total_tokens_sum": sum(int(row.get('Total Tokens', 0)) for row in self.data),
                            "error_count": len(self.errors),
                            "errors": self.errors
                        }
                try:
                    result = future.result()
                    results.append(result)
                    row_index = futures[future]

                    with self.lock:
                        self.prompt_progress += 1
                        runs_progress.update_progress(self.run_id, self.prompt_progress)  # Update progress for each prompt
                        if self.row_completion.get(row_index, 0) == num_prompts:
                            if row_index not in processed_rows_set:
                                processed_rows_set.add(row_index)
                                self.processed += 1
                except Exception as e:
                    print(f"Error in processing row {futures[future]}: {e}")
                    self.errors.append(f"Row {futures[future]}: {e}")

        # Updating rows with results and saving to CSV
        self.update_rows_with_results(results)
        total_tokens_sum = sum(int(row.get('Total Tokens', 0)) for row in self.data)
        end_time = time.time()
        _name = UsersDbCore.get_user_name_by_id(self.user_id)['name'] or f"user_{self.user_id}"

        if self._is_run_cancelled():
            RunLogsDbCore.insert_log(
                run_id=self.run_id,
                user_name=UsersDbCore.get_user_name_by_id(self.user_id)['name'] or f"user_{self.user_id}",
                engine_model=self.engine,
                log_timestamp=datetime.now(tz=timezone.utc),
                num_rows_processed=self.processed,
                time_elapsed=time.time() - start_time,
                num_rows_in_file=len(self.data),
                num_prompts=len(prompts),
                num_tokens=sum(int(row.get('Total Tokens', 0)) for row in self.data),
                errors=json.dumps(self.errors),
                filename=self.filename,
                overflow=self.overflow
            )
            # if job status changed in the leftover threads, make sure DB is consistent
            RunsDbCore.cancel_run(self.run_id)
            return {
                "total_records": len(self.data),
                "processed_records": self.processed,
                "time_elapsed": end_time - start_time,
                "total_tokens_sum": total_tokens_sum,
                "error_count": len(self.errors),
                "errors": self.errors
            }
        self.save_csv()

        end_time = time.time()
        _name = UsersDbCore.get_user_name_by_id(self.user_id)['name'] or f"user_{self.user_id}"
        RunLogsDbCore.insert_log(
            run_id=self.run_id,
            user_name=_name,
            engine_model=self.engine,
            log_timestamp=datetime.now(tz=timezone.utc),
            num_rows_processed=self.processed,
            time_elapsed=end_time - start_time,
            num_rows_in_file=len(self.data),
            num_prompts=len(prompts),
            num_tokens=total_tokens_sum,
            errors=json.dumps(self.errors),
            filename=self.filename,
            overflow=self.overflow
        )
        return {
            "total_records": len(self.data),
            "processed_records": self.processed,
            "time_elapsed": end_time - start_time,
            "total_tokens_sum": total_tokens_sum,
            "error_count": len(self.errors),
            "errors": self.errors
        }


    def create_column_mapping(self):
        # Assuming that the first row contains column headers
        if not self.data:
            return {}

        columns = list(self.data[0].keys())
        letter_to_column = {}
        for index, column in enumerate(columns):
            letter = self.column_index_to_letter(index)
            letter_to_column[letter] = column
        return letter_to_column

    def column_index_to_letter(self, index):
        # This method converts a column index to a column letter (supports more than 26 columns)
        if index < 26:
            return string.ascii_uppercase[index]
        else:
            return self.column_index_to_letter(index // 26 - 1) + string.ascii_uppercase[index % 26]

    def get_selected_columns(self, prompt_config, letter_to_column):
        selected_columns = prompt_config['columns']
        if selected_columns == '*':
            return list(self.data[0].keys())
        else:
            selected_columns_letters = selected_columns.split('+')
            return [letter_to_column.get(letter) for letter in selected_columns_letters if letter in letter_to_column]

    def update_rows_with_results(self, results):
        # Find the last original column's position
        original_columns = list(self.data[0].keys())

        # Initialize a new list for the updated data with ordered columns
        updated_data = []

        # Iterate over the original data rows
        for idx, row in enumerate(self.data):
            # Start with original columns for the new row
            new_row = {k: v for k, v in row.items()}

            # Find the results for this row and sort them by the prompt number
            row_results = [res for res in results if res['row_index'] == idx]
            # Sorting using the prompt number
            row_results_sorted = sorted(row_results, key=lambda x: int(x['prompt_number']))

            # Initialize the total tokens counter for the row
            total_tokens = 0

            # Add the sorted results to the new row dictionary and calculate total tokens
            for result in row_results_sorted:
                new_row.update({k: v for k, v in result.items() if k != 'row_index' and k != 'prompt_number'})
                # If the result key starts with 'tokens_', add its value to the total tokens
                for key, value in result.items():
                    if key.startswith('tokens_'):
                        try:
                            total_tokens += int(value)  # Ensure the value is an integer
                        except ValueError:
                            # In case the value is not an integer, print an error or handle it accordingly
                            print(f"Warning: Non-integer value '{value}' encountered in {key} for row {idx}")

            # Add the total tokens to the new row
            #new_row['Total Tokens'] = total_tokens

            # Append the new row to the updated data list
            updated_data.append(new_row)

        # Replace the original data with updated data
        self.data = updated_data



    def save_csv(self):
        if not self.data:
            print("No data to save.")
            return

        with open(self.output_file, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=self.data[0].keys())
            writer.writeheader()
            for row in self.data:
                writer.writerow(row)
