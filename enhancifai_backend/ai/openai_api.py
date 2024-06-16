import json
import os
import re
import time
from openai import OpenAI

from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.engine.rate_limit_manager import rate_limit_manager

BUFFER_MULTIPLIER = 2

RATE_LIMIT_PATTERN = re.compile(r'Please try again in ([\d\.]+)s')



class OpenAIConnector:
    """Class to manage connections and requests to OpenAI API."""

    def __init__(self, engine) -> None:
        self.engine = engine
        #self.temperature = temperature
        #self.top_p = top_p
        # Initialize OpenAI client with API key
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.rate_limit = False

    def process_csv_row(self, columns: list, rows: dict, query: str, run_id: int) -> dict:
        """
        Process a CSV row with specified columns and query using OpenAI API.

        :param columns: List of column headers.
        :param row: List of row data.
        :param query: String containing specific processing directives.
        :return: Dictionary with processed content and token usage.
        """
        if RunsDbCore.is_run_cancelled(run_id):
            raise RuntimeError("Job cancelled.")
        payload = {
            'columns': columns,
            'rows': rows,
        }

        initial_delay = 1  # Initial delay in seconds
        max_attempts = 3
        _err = None

        # Check rate limit manager
        self.engine = rate_limit_manager.can_make_api_call(model=self.engine,run_id=run_id)
        #print(f"Got engine from rlm: {self.engine}")

        for attempt in range(max_attempts):
            try:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "- You are an assistant with expertise in data analysis and can use your general knowledge to answer.\n"
                            "- Focus on providing direct answers to the user's queries based on the JSON data. Do not repeat or mention the JSON data or provide introductory statements in your responses.\n"
                            "- Keep responses brief, relevant, and focused on the query at hand.\n"
                            "- If unable to process a row or if the query requires information beyond the data, respond appropriately.\n"
                            "- Avoid referring to yourself as AI.\n"
                            "- Example of a good response: 'OFEV 100mg is commonly prescribed for treating idiopathic pulmonary fibrosis.'"
                            "- Another example of a good response: 'Unfortunately, I do not have enough information about the symptoms for which the drug Lyrica Caps 50mg 90s is prescribed.'"
                        )
                    },
                    {
                        "role": "assistant",
                        "content": "Ready to assist with your queries. Please provide your question."
                    }
                ]

                # User's query and payload are appended here
                messages.append(
                    {
                        "role": "user",
                        "content": f"{query}:\n\n```{json.dumps(payload)}```"
                    }
                )

                completion = self.client.chat.completions.create(
                    model=self.engine,
                    messages=messages,
                    temperature=0.6,
                    #temperature=self.temperature,
                    #top_p=self.top_p
                )

                data = completion.choices[0].message.content
                tokens_used = completion.usage.total_tokens

                # Update rate limit manager
                rate_limit_manager.update_make_api_call(self.engine, tokens_used=tokens_used)

                if 'SYS:NONE' in data:
                    data = data.replace('SYS:NONE', '').strip()
                
                # Save token usage entry
                user_id = RunsDbCore.get_user_id(run_id)
                UsersDbCore.add_token_usage(user_id, self.engine, tokens_used)

                return {"content": data.strip(), "tokens": tokens_used, 'engine_used': self.engine}

            except Exception as e:
                print(e)
                if e.status_code == 429: # pylint: disable=no-member
                    try:
                        # Use the compiled pattern to search the string
                        match = RATE_LIMIT_PATTERN.search(e.body['message']) # pylint: disable=no-member
                        # Extract the number of seconds
                        if match:
                            delay = float(match.group(1))
                        else:
                            delay = 5
                    except (ValueError, IndexError):
                        delay = 5  # Default to 5 seconds if parsing fails

                    sleep_time = delay * BUFFER_MULTIPLIER  # Add a buffer time
                    print(f"Rate limit exceeded. Waiting for {sleep_time} seconds before retrying...")
                    time.sleep(sleep_time)
                else:
                    print(f"OpenAI API error on attempt {attempt + 1}: {e}")
                    _err = e
                    if attempt < max_attempts - 1:
                        # Exponential backoff with a base delay of 1 second
                        time.sleep(1 * (2 ** attempt))


        if _err is None:
            raise RuntimeError("Failed to get answer from OpenAI API after 3 attempts.")
        else:
            print("Failed to get answer from OpenAI API after 3 attempts.")
            return {'content': _err, 'tokens': 0}
