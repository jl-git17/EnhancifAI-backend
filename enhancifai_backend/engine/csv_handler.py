import csv
from datetime import datetime, timezone
import json
import string
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from enhancifai_backend.database.handlers.run_logs import RunLogsDbCore
from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.engine.runs_progress import runs_progress

# Default number of threads if batched_processing=False
MAX_THREADS = 2

class CSVHandler:
    def __init__(
        self,
        file_path,
        output_file,
        ai_connector,
        run_id,
        engine,
        user_id,
        filename,
        batched_processing=False
    ):
        self.file_path = file_path
        self.filename = filename
        self.output_file = output_file
        self.ai_connector = ai_connector
        self.lock = threading.Lock()
        self.data = []
        self.processed = 0
        self.prompt_progress = 0
        self.row_completion = {}
        self.run_id = run_id
        self.engine = engine
        self.user_id = user_id
        self.errors = []
        self.overflow = False
        self.total_tokens = 0
        self.batched_processing = batched_processing

    def _is_run_cancelled(self):
        return RunsDbCore.is_run_cancelled(self.run_id)

    def load_csv(self):
        encodings = ['utf-8', 'ISO-8859-1', 'Windows-1252']
        errors = []
        for encoding in encodings:
            print(f"Attempting to read CSV with encoding '{encoding}'")
            try:
                with open(self.file_path, mode='r', newline='', encoding=encoding) as file:
                    csv_reader = csv.DictReader(file)
                    self.data = [row for row in csv_reader]
                    if not self.data:
                        print("CSV is empty.")
                        return False
                    return True
            except UnicodeDecodeError as e:
                print(f"Error with encoding {encoding}: {e}")
            except Exception as e:
                errors.append(str(e))
                print(f"Error loading CSV: {e}")
                return '\n'.join(errors)
        print("Failed to read CSV with all attempted encodings.")
        return False

    def process_csv(self, prompts: list, max_records=0):
        start_time = time.time()

        loaded = True  # Because we already call load_csv() from outside
        if not loaded:
            return {"total_records": 0, "processed_records": 0, "time_elapsed": 0}

        letter_to_column = self.create_column_mapping()

        total_records = min(len(self.data), max_records) if max_records > 0 else len(self.data)
        total_tasks = total_records * len(prompts)
        runs_progress.add_run(self.run_id, total_tasks)

        # If batched_processing is True, let's increase concurrency
        # (One minimal approach to allow more data to process simultaneously)
        max_workers = 5 if self.batched_processing else MAX_THREADS

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            processed_rows_set = set()

            for idx, row in enumerate(self.data):
                if idx >= total_records:
                    break

                for prompt_config in prompts:
                    if self._is_run_cancelled():
                        print(f"Run {self.run_id} cancelled, stopping processing.")
                        if self._is_run_cancelled():
                            end_time = time.time()
                            RunLogsDbCore.insert_log(
                                run_id=self.run_id,
                                user_name=UsersDbCore.get_user_by_id(self.user_id)['name'] or f"user_{self.user_id}",
                                engine_model=self.engine,
                                log_timestamp=datetime.now(tz=timezone.utc),
                                num_rows_processed=self.processed,
                                time_elapsed=end_time - start_time,
                                num_rows_in_file=len(self.data),
                                num_prompts=len(prompts),
                                num_tokens=self.total_tokens,
                                errors=json.dumps(self.errors),
                                filename=self.filename,
                                overflow=self.overflow
                            )
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
                        future = executor.submit(
                            self.process_row,
                            idx,
                            {k: row[k] for k in selected_columns},
                            prompt_config,
                            letter_to_column
                        )
                        futures[future] = idx
                        if self.ai_connector.rate_limit is True:
                            time.sleep(0.2)

            num_prompts = len(prompts)
            for future in as_completed(futures):
                if self._is_run_cancelled():
                    print(f"Run {self.run_id} cancelled, stopping processing.")
                    if self._is_run_cancelled():
                        end_time = time.time()
                        RunLogsDbCore.insert_log(
                            run_id=self.run_id,
                            user_name=UsersDbCore.get_user_by_id(self.user_id)['name'] or f"user_{self.user_id}",
                            engine_model=self.engine,
                            log_timestamp=datetime.now(tz=timezone.utc),
                            num_rows_processed=self.processed,
                            time_elapsed=time.time() - start_time,
                            num_rows_in_file=len(self.data),
                            num_prompts=len(prompts),
                            num_tokens=self.total_tokens,
                            errors=json.dumps(self.errors),
                            filename=self.filename,
                            overflow=self.overflow
                        )
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
                        runs_progress.update_progress(self.run_id, self.prompt_progress)
                        if self.row_completion.get(row_index, 0) == num_prompts:
                            if row_index not in processed_rows_set:
                                processed_rows_set.add(row_index)
                                self.processed += 1
                except Exception as e:
                    print(f"Error in processing row {futures[future]}: {e}")
                    self.errors.append(f"Row {futures[future]}: {e}")

        self.update_rows_with_results(results)
        end_time = time.time()
        _name = UsersDbCore.get_user_by_id(self.user_id)['name'] or f"user_{self.user_id}"

        if self._is_run_cancelled():
            RunLogsDbCore.insert_log(
                run_id=self.run_id,
                user_name=_name,
                engine_model=self.engine,
                log_timestamp=datetime.now(tz=timezone.utc),
                num_rows_processed=self.processed,
                time_elapsed=end_time - start_time,
                num_rows_in_file=len(self.data),
                num_prompts=len(prompts),
                num_tokens=self.total_tokens,
                errors=json.dumps(self.errors),
                filename=self.filename,
                overflow=self.overflow
            )
            RunsDbCore.cancel_run(self.run_id)
            return {
                "total_records": len(self.data),
                "processed_records": self.processed,
                "time_elapsed": end_time - start_time,
                "total_tokens_sum": self.total_tokens,
                "error_count": len(self.errors),
                "errors": self.errors
            }

        self.save_csv()

        RunLogsDbCore.insert_log(
            run_id=self.run_id,
            user_name=_name,
            engine_model=self.engine,
            log_timestamp=datetime.now(tz=timezone.utc),
            num_rows_processed=self.processed,
            time_elapsed=end_time - start_time,
            num_rows_in_file=len(self.data),
            num_prompts=len(prompts),
            num_tokens=self.total_tokens,
            errors=json.dumps(self.errors),
            filename=self.filename,
            overflow=self.overflow
        )
        return {
            "total_records": len(self.data),
            "processed_records": self.processed,
            "time_elapsed": end_time - start_time,
            "total_tokens_sum": self.total_tokens,
            "error_count": len(self.errors),
            "errors": self.errors
        }

    def process_row(self, idx, row, prompt_config, columns_list):
        if self._is_run_cancelled():
            return None
        RunsDbCore.set_run_checkin(self.run_id)

        result = {
            "row_index": idx,
            "prompt_number": prompt_config['prompt_number']
        }
        output_heading = prompt_config['output_heading']

        # Filter the row to only include selected columns
        filtered_row = row

        # AI process
        data = self.ai_connector.process_csv_row(
            columns=columns_list,
            rows=filtered_row,
            query=prompt_config['prompt'],
            run_id=self.run_id
        )
        if data['engine_used'] != self.engine:
            self.overflow = True
        result[f"{output_heading}"] = data.get("content", "")

        with self.lock:
            self.total_tokens += data.get('tokens', 0)
            if idx in self.row_completion:
                self.row_completion[idx] += 1
            else:
                self.row_completion[idx] = 1

        return result

    def create_column_mapping(self):
        if not self.data:
            return {}
        columns = list(self.data[0].keys())
        letter_to_column = {}
        for index, column in enumerate(columns):
            letter = self.column_index_to_letter(index)
            letter_to_column[letter] = column
        return letter_to_column

    def column_index_to_letter(self, index):
        import string
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
        updated_data = []
        for idx, row in enumerate(self.data):
            new_row = {k: v for k, v in row.items()}
            row_results = [res for res in results if res and res['row_index'] == idx]
            row_results_sorted = sorted(row_results, key=lambda x: int(x['prompt_number']))

            total_tokens = 0
            for result in row_results_sorted:
                new_row.update({
                    k: v for k, v in result.items()
                    if k not in ('row_index', 'prompt_number')
                })
                for key, value in result.items():
                    if key.startswith('tokens_'):
                        try:
                            total_tokens += int(value)
                        except ValueError:
                            print(f"Warning: Non-integer value '{value}' in {key} for row {idx}")
            updated_data.append(new_row)
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
