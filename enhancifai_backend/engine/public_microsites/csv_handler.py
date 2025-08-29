import csv
from datetime import datetime, timezone
import json
import logging
import string
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from enhancifai_backend.database.handlers.microsites import MicrositesRunsDbCore
from enhancifai_backend.engine.public_microsites.runs_progress import runs_progress

# Default concurrency
DEFAULT_MAX_THREADS = 2
PERFORMANCE_OPTIMIZATION_CHUNK_SIZE = 10

class CSVHandler:
    def __init__(
        self,
        file_path,
        output_file,
        ai_connector,
        run_id,
        engine,
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
        self.errors = []
        self.overflow = False
        self.num_prompts_total = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.batched_processing = batched_processing
        self.performance_optimization = performance_optimization

    def _is_run_cancelled(self):
        return MicrositesRunsDbCore.is_run_cancelled(self.run_id)

    def load_csv(self):
        encodings = ['utf-8', 'ISO-8859-1', 'Windows-1252']
        errors = []
        for encoding in encodings:
            try:
                with open(self.file_path, mode='r', newline='', encoding=encoding) as file:
                    csv_reader = csv.DictReader(file)
                    self.data = [row for row in csv_reader]
                    if not self.data:
                        logging.debug("CSV is empty.")
                        return False
                    return True
            except UnicodeDecodeError as e:
                logging.error("Error with encoding %s: %s", encoding, e)
            except Exception as e:
                errors.append(str(e))
                logging.error("Error loading CSV: %s", e)
                return '\n'.join(errors)
        logging.error("Failed to read CSV with all attempted encodings.")
        return False

    def _compute_dynamic_chunk_size(self, max_records):
        """
        Dynamically compute chunk size based on data characteristics:
        - Target a chunk to use up to ~128 KB of memory.
        - For small files, use larger chunks.
        - For very large files, use smaller chunks.
        - Always stay within min/max bounds.
        """
        if not self.data:
            return PERFORMANCE_OPTIMIZATION_CHUNK_SIZE

        MIN_CHUNK = 5
        MAX_CHUNK = 20
        TARGET_CHUNK_BYTES = 1024 * 3  # 3 KB

        num_rows = len(self.data)
        # Estimate average row size in bytes
        avg_row_size = (
            sum(sum(len(str(v).encode('utf-8')) for v in row.values()) for row in self.data[:min(100, num_rows)])
            / min(100, num_rows)
        )

        # Log size of row in bytes
        logging.debug(f"Average row size: {avg_row_size} bytes")

        # Compute chunk size to target ~128KB per chunk
        est_chunk_size = int(TARGET_CHUNK_BYTES // max(avg_row_size, 1))

        # Clamp to min/max
        chunk_size = max(MIN_CHUNK, min(MAX_CHUNK, est_chunk_size))
        if max_records > 0:
            chunk_size = min(chunk_size, max_records)
        return chunk_size

    def process_csv(self, prompts: list, max_records=0):
        start_time = time.time()

        # Store total # of prompts for final "processed" count
        self.num_prompts_total = len(prompts)

        # We assume load_csv() was already called externally
        letter_to_column = self.create_column_mapping()

        total_records = min(len(self.data), max_records) if max_records > 0 else len(self.data)
        total_tasks = total_records * len(prompts)
        runs_progress.add_run(self.run_id, total_tasks)

        # Duplicate-check start (limit to the subset we actually process to reduce memory usage)
        seen_rows = set()
        for row in self.data[:total_records]:
            row_tuple = tuple(sorted(row.items()))
            if row_tuple in seen_rows:
                logging.warning("Duplicate row found in CSV data. Row: %s", row)
            seen_rows.add(row_tuple)
        # Duplicate-check end

        # Basic concurrency approach
        max_workers = DEFAULT_MAX_THREADS
        if self.batched_processing:
            max_workers = 4
        elif self.performance_optimization:
            max_workers = 2

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}

            if not self.performance_optimization:
                # OLD approach: row-by-row
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
                # Dynamically compute chunk size
                chunk_size = self._compute_dynamic_chunk_size(max_records)
                logging.debug(f"Using chunk size: {chunk_size} for performance optimization")
                for prompt_config in prompts:
                    for start_idx in range(0, total_records, chunk_size):
                        if self._is_run_cancelled():
                            return self._handle_cancel(start_time)

                        # Ensure we do not exceed total_records (which is min(len(self.data), max_records))
                        end_idx = min(start_idx + chunk_size, total_records)
                        chunk_data = self.data[start_idx:end_idx]
                        future = executor.submit(
                            self.process_chunk,
                            start_idx,
                            chunk_data,  # subset of data
                            prompt_config,
                            letter_to_column
                        )
                        futures[future] = (start_idx, end_idx)

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
            "input_tokens_sum": self.input_tokens,
            "output_tokens_sum": self.output_tokens,
            "error_count": len(self.errors),
            "errors": self.errors
        }

    def process_row(self, idx, row, prompt_config, columns_list):
        """
        Original logic for one row => one AI call
        """
        if self._is_run_cancelled():
            return None
        MicrositesRunsDbCore.set_run_checkin(self.run_id)

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
            self.input_tokens += data.get('input_tokens', 0)
            self.output_tokens += data.get('output_tokens', 0)
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
        # Avoid logging entire payloads to keep memory footprint small
        try:
            logging.debug("Batch returned %d items.", len(batch_data) if hasattr(batch_data, '__len__') else -1)
        except Exception:
            pass
        # 'batch_data' should be a list of dicts, one per row in 'to_send'

        output_heading = prompt_config['output_heading']
        results_for_chunk = []
        with self.lock:
            _last_item = {}
            for i, item in enumerate(batch_data):
                _last_item = item
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


                # Bump row completion
                self._increment_row_completion(actual_idx)

                # Update progress once per row in the chunk
                self.prompt_progress += 1
                runs_progress.update_progress(self.run_id, self.prompt_progress)

                results_for_chunk.append(result)

            self.input_tokens += _last_item.get("input_tokens", 0)
            self.output_tokens += _last_item.get("output_tokens", 0)

        return results_for_chunk


    def get_selected_columns(self, prompt_config, letter_to_column):
        selected_columns = prompt_config['columns']
        if selected_columns == ['*'] or selected_columns == '*':
            return list(self.data[0].keys())
        else:
            selected_columns_letters = selected_columns.split('+')
            return [
                letter_to_column.get(letter)
                for letter in selected_columns_letters
                if letter in letter_to_column
            ]

    def update_rows_with_results(self, results):
        # Group results by row_index to avoid repeated full scans (reduces memory churn)
        grouped = {}
        for res in results or []:
            if not res:
                continue
            idx = res.get('row_index')
            if idx is None:
                continue
            grouped.setdefault(idx, []).append(res)

        updated_data = []
        for idx, row in enumerate(self.data):
            new_row = dict(row)
            row_results = grouped.get(idx, [])
            row_results_sorted = sorted(row_results, key=lambda x: int(x['prompt_number']))

            for result in row_results_sorted:
                for key, value in result.items():
                    if key not in ('row_index', 'prompt_number'):
                        new_row[key] = value
            updated_data.append(new_row)
        self.data = updated_data

    def save_csv(self):
        if not self.data:
            logging.error("No data to save.")
            return
        with open(self.output_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(
                file,
                fieldnames=self.data[0].keys(),
                quoting=csv.QUOTE_MINIMAL,
                escapechar='\\'
            )
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

    def _gather_results(self, futures, _num_prompts, start_time):
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
        if not MicrositesRunsDbCore.is_run_cancelled(self.run_id):
            MicrositesRunsDbCore.cancel_run(self.run_id)
        self._insert_log(end_time - start_time)
        return {
            "total_records": len(self.data),
            "processed_records": self.processed,
            "time_elapsed": end_time - start_time,
            "input_tokens_sum": self.input_tokens,
            "output_tokens_sum": self.output_tokens,
            "error_count": len(self.errors),
            "errors": self.errors
        }

    def _insert_log(self, time_elapsed):
        pass # TODO
