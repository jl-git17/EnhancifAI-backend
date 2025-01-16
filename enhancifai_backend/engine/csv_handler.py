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

# Default concurrency
DEFAULT_MAX_THREADS = 2

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
        batched_processing=False,
        performance_optimization=False
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
        self.performance_optimization = performance_optimization

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

        # Store total # of prompts for final "processed" count
        self.num_prompts_total = len(prompts)

        # We assume load_csv() was already called externally
        letter_to_column = self.create_column_mapping()

        total_records = min(len(self.data), max_records) if max_records > 0 else len(self.data)
        total_tasks = total_records * len(prompts)
        runs_progress.add_run(self.run_id, total_tasks)

        # Basic concurrency approach
        max_workers = 4 if self.batched_processing else DEFAULT_MAX_THREADS

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}

            if not self.performance_optimization:
                # OLD approach: row-by-row
                processed_rows_set = set()
                for idx, row in enumerate(self.data):
                    if idx >= total_records:
                        break

                    for prompt_config in prompts:
                        if self._is_run_cancelled():
                            return self._handle_cancel(start_time)

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
            else:
                # NEW approach: send multiple rows in one AI call if performance_optimization
                # We'll chunk them in sets of, say, 5 for demonstration:
                chunk_size = 5
                for prompt_config in prompts:
                    for start_idx in range(0, total_records, chunk_size):
                        if self._is_run_cancelled():
                            return self._handle_cancel(start_time)

                        chunk_data = self.data[start_idx : start_idx + chunk_size]
                        future = executor.submit(
                            self.process_chunk,
                            start_idx,
                            chunk_data,  # subset of data
                            prompt_config,
                            letter_to_column
                        )
                        futures[future] = (start_idx, start_idx + chunk_size)

            results = self._gather_results(futures, len(prompts), start_time)

        self.update_rows_with_results(results)

        # 1) **After** we have all results, count how many rows completed all prompts
        for row_idx in range(len(self.data)):
            # If row_completion says it handled all prompts, it's fully processed
            if self.row_completion.get(row_idx, 0) == self.num_prompts_total:
                self.processed += 1

        end_time = time.time()

        if self._is_run_cancelled():
            return self._handle_cancel(start_time)

        self.save_csv()
        self._insert_log(end_time - start_time)
        return {
            "total_records": len(self.data),
            "processed_records": self.processed,
            "time_elapsed": end_time - start_time,
            "total_tokens_sum": self.total_tokens,
            "error_count": len(self.errors),
            "errors": self.errors
        }

    def process_row(self, idx, row, prompt_config, columns_list):
        """
        Original logic for one row => one AI call
        """
        if self._is_run_cancelled():
            return None
        RunsDbCore.set_run_checkin(self.run_id)

        result = {
            "row_index": idx,
            "prompt_number": prompt_config['prompt_number']
        }
        output_heading = prompt_config['output_heading']

        data = self.ai_connector.process_csv_row(
            columns=columns_list,
            rows=row,
            query=prompt_config['prompt'],
            run_id=self.run_id
        )
        if data['engine_used'] != self.engine:
            self.overflow = True

        result[f"{output_heading}"] = data.get("content", "")

        with self.lock:
            self.total_tokens += data.get('tokens', 0)
            self._increment_row_completion(idx)
            self.prompt_progress += 1
            runs_progress.update_progress(self.run_id, self.prompt_progress)

        return result

    def process_chunk(self, start_idx, chunk_data, prompt_config, columns_list):
        """
        Send multiple rows (chunk_data) in one request to the AI.
        'chunk_data' is a list of row dictionaries.
        """
        if self._is_run_cancelled():
            return []

        # Choose the columns used by this prompt
        selected_columns = self.get_selected_columns(prompt_config, columns_list)
        
        # Build a list of filtered row dicts, parallel to 'chunk_data'
        to_send = []
        indexes = []
        for i, row in enumerate(chunk_data):
            actual_idx = start_idx + i
            if self._is_run_cancelled():
                return []
            # Filter each row by the selected columns
            subset = {k: row[k] for k in selected_columns if k in row}
            to_send.append(subset)
            indexes.append(actual_idx)

        # Now call 'process_csv_rows' on the AI connector **once** for the entire chunk
        batch_data = self.ai_connector.process_csv_rows(
            columns=columns_list,
            rows=to_send,
            query=prompt_config['prompt'],
            run_id=self.run_id
        )
        # 'batch_data' should be a list of dicts, one per row in 'to_send'

        output_heading = prompt_config['output_heading']
        results_for_chunk = []
        with self.lock:
            for i, item in enumerate(batch_data):
                actual_idx = indexes[i]
                # Build a result dict for this row
                result = {
                    "row_index": actual_idx,
                    "prompt_number": prompt_config['prompt_number'],
                    f"{output_heading}": item.get("content", "")
                }
                # If engine used is different, mark overflow
                if item.get("engine_used") != self.engine:
                    self.overflow = True

                self.total_tokens += item.get('tokens', 0)

                # Bump row completion
                self._increment_row_completion(actual_idx)

                # Update progress once per row in the chunk
                self.prompt_progress += 1
                runs_progress.update_progress(self.run_id, self.prompt_progress)

                results_for_chunk.append(result)

        return results_for_chunk


    def get_selected_columns(self, prompt_config, letter_to_column):
        selected_columns = prompt_config['columns']
        if selected_columns == '*':
            return list(self.data[0].keys())
        else:
            selected_columns_letters = selected_columns.split('+')
            return [
                letter_to_column.get(letter)
                for letter in selected_columns_letters
                if letter in letter_to_column
            ]

    def update_rows_with_results(self, results):
        updated_data = []
        for idx, row in enumerate(self.data):
            new_row = dict(row)
            row_results = [res for res in results if res and res.get('row_index') == idx]
            row_results_sorted = sorted(row_results, key=lambda x: int(x['prompt_number']))

            for result in row_results_sorted:
                for key, value in result.items():
                    if key not in ('row_index', 'prompt_number'):
                        new_row[key] = value
            updated_data.append(new_row)
        self.data = updated_data

    def save_csv(self):
        if not self.data:
            print("No data to save.")
            return
        with open(self.output_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=self.data[0].keys())
            writer.writeheader()
            for row in self.data:
                writer.writerow(row)

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
        if index < 26:
            return string.ascii_uppercase[index]
        else:
            return self.column_index_to_letter(index // 26 - 1) + string.ascii_uppercase[index % 26]

    def _gather_results(self, futures, num_prompts, start_time):
        """
        Common method to gather results from futures in either row-by-row or chunk approach.
        """
        results = []
        for future in as_completed(futures):
            if self._is_run_cancelled():
                return self._handle_cancel(start_time)

            try:
                chunk_result = future.result()
                if isinstance(chunk_result, list):
                    # chunk_result => a list of row results
                    results.extend(chunk_result)
                elif chunk_result is not None:
                    # row-by-row => single dict
                    results.append(chunk_result)
            except Exception as e:
                self.errors.append(str(e))
        return results

    def _increment_row_completion(self, idx):
        """
        In row-by-row mode, we track the row's # of completed prompts.
        In chunk mode, we do similarly but row_idx is determined in chunk.
        """
        if idx in self.row_completion:
            self.row_completion[idx] += 1
        else:
            self.row_completion[idx] = 1

        # If row completed all prompts, increment 'processed'
        # But we only know total prompts at the very end, so we do that after gather_results or in final logic

    def _handle_cancel(self, start_time):
        """
        Mark the run as cancelled, log, and return partial results.
        """
        end_time = time.time()
        if not RunsDbCore.is_run_cancelled(self.run_id):
            RunsDbCore.cancel_run(self.run_id)
        self._insert_log(end_time - start_time)
        return {
            "total_records": len(self.data),
            "processed_records": self.processed,
            "time_elapsed": end_time - start_time,
            "total_tokens_sum": self.total_tokens,
            "error_count": len(self.errors),
            "errors": self.errors
        }

    def _insert_log(self, time_elapsed):
        _name = UsersDbCore.get_user_by_id(self.user_id)['name'] or f"user_{self.user_id}"
        RunLogsDbCore.insert_log(
            run_id=self.run_id,
            user_name=_name,
            engine_model=self.engine,
            log_timestamp=datetime.now(tz=timezone.utc),
            num_rows_processed=self.processed,
            time_elapsed=time_elapsed,
            num_rows_in_file=len(self.data),
            num_prompts=0,  # Or adjust if you track total prompts used
            num_tokens=self.total_tokens,
            errors=json.dumps(self.errors),
            filename=self.filename,
            overflow=self.overflow
        )
