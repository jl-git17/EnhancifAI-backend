import time
from collections import deque
from threading import Lock

from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.config import settings

GLOBAL_RATE_LIMIT_DELAY = 0.1

MAIN_MODEL = settings.main_model_free
FALLBACK_MODEL_ONE = settings.fallback_model_one_free
FALLBACK_MODEL_TWO = settings.fallback_model_two_free

class RateLimitManagerFree:
    def __init__(self):
        self.limits = {
            'gpt-3.5-turbo': {'token_limit': 160000, 'rpm': 5000},
            'gpt-4': {'token_limit': 80000, 'rpm': 5000},
            'gpt-4-turbo': {'token_limit': 600000, 'rpm': 5000},
            'gpt-4o': {'token_limit': 800000, 'rpm': 5000},
            'gpt-4o-mini': {'token_limit': 160000, 'rpm': 5000},
            'gpt-4.1-nano': {'token_limit': 1600000, 'rpm': 5000},
            'gpt-4.1-mini': {'token_limit': 800000, 'rpm': 5000},
            'text-embedding-3-small': {'token_limit': 5000000, 'rpm': 5000}
        }
        self.request_logs = {model: deque() for model in self.limits}
        self.token_logs = {model: deque() for model, spec in self.limits.items() if 'token_limit' in spec}
        self.locks = {model: Lock() for model in self.limits}
        self.queue = {priority: deque() for priority in range(4)}
        self.awarded = {}
        self.queue_lock = Lock()
        self.awarded_lock = Lock()
        self.weights = [1, 2, 3, 4]  # Weights for each priority level (adjust as needed)
        self.current_priority = 0  # Track current priority for round robin

    def _is_request_allowed(self, model):
        with self.locks[model]:
            current_time = time.time()
            window_start = current_time - 60

            # Remove old requests
            while self.request_logs[model] and self.request_logs[model][0] < window_start:
                self.request_logs[model].popleft()

            req_limit = self.limits[model]['rpm'] * 0.8
            total_reqs = len(self.request_logs[model])

            if total_reqs < req_limit:
                return True
            else:
                return False

    def _are_tokens_available(self, model):
        with self.locks[model]:
            current_time = time.time()
            window_start = current_time - 60

            # Remove old token logs
            while self.token_logs[model] and self.token_logs[model][0][0] < window_start:
                self.token_logs[model].popleft()

            current_tokens = sum(token for _, token in self.token_logs[model])
            limit_tokens = self.limits[model]['token_limit'] * 0.8
            if current_tokens <= limit_tokens:
                return True
            else:
                return False

    def _update_tokens_available(self, model, tokens_used):
        with self.locks[model]:
            current_time = time.time()
            self.token_logs[model].append((current_time, tokens_used))

    def _check_cancelled_run_id(self, run_id) -> bool:
        return RunsDbCore.is_run_cancelled(run_id)

    def clean_cancelled_jobs(self):
        with self.queue_lock:
            for priority in self.queue:
                for unique_id in list(self.queue[priority]):
                    run_id = unique_id.split('-')[-1]
                    if self._check_cancelled_run_id(run_id):
                        self.queue[priority].remove(unique_id)
                        with self.awarded_lock:
                            if unique_id in self.awarded:
                                del self.awarded[unique_id]

    def update_make_api_call(self, model, tokens_used):
        if model not in self.limits:
            raise ValueError("Model not recognized")

        self._update_tokens_available(model=model, tokens_used=tokens_used)
        with self.locks[model]:
            self.request_logs[model].append(time.time())
        return True, "API call successful"

    def _weighted_round_robin_fallback(self):
        """
        Original fallback method kept for future reference.
        """
        with self.queue_lock:
            for _ in range(self.weights[self.current_priority]):  # Process based on weight
                if self.queue[self.current_priority]:
                    if self._is_request_allowed(MAIN_MODEL):
                        current_id = self.queue[self.current_priority].popleft()
                        if self._are_tokens_available(MAIN_MODEL):
                            with self.awarded_lock:
                                self.awarded[current_id] = MAIN_MODEL
                            break
                        else:
                            if self._are_tokens_available(FALLBACK_MODEL_ONE):
                                with self.awarded_lock:
                                    self.awarded[current_id] = FALLBACK_MODEL_ONE
                                break
                            elif self._are_tokens_available(FALLBACK_MODEL_TWO):
                                with self.awarded_lock:
                                    self.awarded[current_id] = FALLBACK_MODEL_TWO
                                break
        self.current_priority = (self.current_priority + 1) % len(self.weights)

    def can_make_api_call(self, model, run_id, priority=0):
        if model not in self.limits:
            raise ValueError("Model not recognized")

        # Generate unique ID
        unique_id = f"{id(self)}-{len(self.queue[priority])}-{run_id}"
        with self.queue_lock:
            self.queue[priority].append(unique_id)

        while True:
            time.sleep(0.001)
            with self.awarded_lock:
                if unique_id in self.awarded:
                    awarded_model = self.awarded.pop(unique_id)
                    return awarded_model

            # Time delay based processing using original model only
            with self.queue_lock:
                for _ in range(self.weights[self.current_priority]):  # Process based on weight
                    if self.queue[self.current_priority]:
                        if self._is_request_allowed(model) and self._are_tokens_available(model):
                            current_id = self.queue[self.current_priority].popleft()
                            with self.awarded_lock:
                                self.awarded[current_id] = model
                            break

            self.current_priority = (self.current_priority + 1) % len(self.weights)
            time.sleep(GLOBAL_RATE_LIMIT_DELAY)
            print(f"RLM:: Waiting for {GLOBAL_RATE_LIMIT_DELAY} seconds before retrying...")
            
# Example usage:
rate_limit_manager_free = RateLimitManagerFree()
