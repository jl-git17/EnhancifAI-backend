import json
import os
import re
import time
from typing import Dict, List
from fastapi import HTTPException
from openai import OpenAI

from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.admin import PromptsDbCore
from enhancifai_backend.engine.rate_limit_manager import rate_limit_manager

BUFFER_MULTIPLIER = 2

RATE_LIMIT_PATTERN = re.compile(r'Please try again in ([\d\.]+)s')

PI_DEFAULT_PROMPT = (
    "Please review and improve the prompt for clarity, effectiveness, and engagement. "
    "Make sure the prompt takes the role of an expert in the relevant field. "
    "Feel free to enhance the wording, structure, and tone as needed."
)
PI_DEFAULT_AI_ENGINE = "gpt-4o-mini"
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))

DEFAULT_PROMPT = (
    "- You are an assistant with expertise in data analysis and can use your general knowledge "
    "to answer.\n"
    "- Focus on providing direct answers to the user's queries based on the JSON data. "
    "Do not repeat or mention the JSON data or provide introductory statements in your responses.\n"
    "- Keep responses brief, relevant, and focused on the query at hand.\n"
    "- If unable to process a row or if the query requires information beyond the data, "
    "respond appropriately.\n"
    "- Avoid referring to yourself as AI.\n"
    "- Example of a good response: 'OFEV 100mg is commonly prescribed for treating idiopathic "
    "pulmonary fibrosis.'"
    "- Another example of a good response: 'Unfortunately, I do not have enough information "
    "about the symptoms for which the drug Lyrica Caps 50mg 90s is prescribed.'"
)

DEFAULT_PROMPT_BATCHED = (
    "- You are a data analysis assistant, operating in JSON mode.\n"
    "- Answer based on the JSON data without mentioning it or adding introductions.\n"
    "- Return a JSON array with one concise answer per row, matching the row index.\n"
    "- Example: `[\"answer-for-row-1\", \"answer-for-row-2\", ...]`.\n"
    "- Be brief, relevant, and avoid referring to yourself.\n"
)


class PromptImproverSettings:
    def __init__(self, prompt: str=PI_DEFAULT_PROMPT, ai_engine: str=PI_DEFAULT_AI_ENGINE):
        self._prompt = prompt
        self._ai_engine = ai_engine
        self._update_from_db()

    def _update_from_db(self):
        try:
            from_db = PromptsDbCore.get_latest_prompt_by_user(ADMIN_USER_ID)
            if from_db:
                self._prompt = from_db['prompt']
                self._ai_engine = from_db['ai_engine']
        except Exception as e:
            print(e)

    # Getter for prompt
    @property
    def prompt(self):
        self._update_from_db()
        return self._prompt

    # Setter for prompt
    @prompt.setter
    def prompt(self, value: str):
        self._prompt = value

    # Getter for ai_engine
    @property
    def ai_engine(self):
        self._update_from_db()
        return self._ai_engine

    # Setter for ai_engine
    @ai_engine.setter
    def ai_engine(self, value: str):
        self._ai_engine = value

pi_settings = PromptImproverSettings(prompt=PI_DEFAULT_PROMPT, ai_engine=PI_DEFAULT_AI_ENGINE)


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
        print(f"payload:  {payload}")

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
                        "content": DEFAULT_PROMPT
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
                    temperature=0.5,
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
                UsersDbCore.add_user_token_usage(user_id, run_id, self.engine, tokens_used)

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
    
    def process_csv_rows(
        self,
        columns: Dict[str, str],
        rows: List[Dict[str, str]],
        query: str,
        run_id: int
    ) -> List[Dict[str, object]]:
        """
        Process multiple CSV rows in a single OpenAI call for performance optimization.

        Converts row keys from descriptive names to their corresponding letter representations.

        Returns a list of dictionaries, each containing:
            {
                "content": <the AI-generated answer for that row>,
                "tokens": <the token usage for this batch (shared)>,
                "engine_used": <which engine was used>
            }
        The returned list is aligned with the order of `rows` input.
        """

        if RunsDbCore.is_run_cancelled(run_id):
            raise RuntimeError("Job cancelled.")

        # Create a reverse mapping from column names to letters
        name_to_letter = {v: k for k, v in columns.items()}

        # Transform each row's keys from names to letters
        transformed_rows = []
        for row in rows:
            transformed_row = {}
            for name, value in row.items():
                letter = name_to_letter.get(name)
                if letter:
                    transformed_row[letter] = value
                else:
                    # Handle unexpected column names
                    raise ValueError(f"Column name '{name}' does not exist in columns mapping.")
            transformed_rows.append(transformed_row)

        # Construct the payload with transformed rows
        payload = {
            'columns': columns,          # Keep columns as is (letter to name)
            'rows': transformed_rows      # Use transformed rows with letter keys
        }

        print(f"payload:  {payload}")

        max_attempts = 3
        _err = None

        # Use the same logic your single-row method uses:
        self.engine = rate_limit_manager.can_make_api_call(model=self.engine, run_id=run_id)

        for attempt in range(max_attempts):
            try:
                # For clarity, instruct the AI:
                # 1) We show it the query and the entire 'payload' with many rows.
                # 2) We TELL it to return exactly one answer per row in a JSON list
                #    so we can map them back properly.
                messages = [
                    {
                        "role": "system",
                        "content": DEFAULT_PROMPT_BATCHED
                    },
                    {
                        "role": "assistant",
                        "content": "I am ready to process multiple rows in one request. Please provide them."
                    },
                    {
                        "role": "user",
                        "content": (
                            f"{query}:\n\n"
                            f"```{json.dumps(payload)}```\n\n"
                        )
                    }
                ]

                completion = self.client.chat.completions.create(
                    model=self.engine,
                    messages=messages,
                    temperature=1,
                )

                raw_data = completion.choices[0].message.content
                tokens_used = completion.usage.total_tokens

                # Rate limit manager housekeeping
                rate_limit_manager.update_make_api_call(self.engine, tokens_used=tokens_used)

                user_id = RunsDbCore.get_user_id(run_id)
                UsersDbCore.add_user_token_usage(user_id, run_id, self.engine, tokens_used)

                # Attempt to parse the AI's response as JSON array
                #
                # The AI hopefully returns something like:
                #   ["answer for row 0", "answer for row 1", ...]
                # or an array of objects. We'll do minimal validation.
                try:
                    print(f"Raw data: {raw_data}")
                    parsed = json.loads(raw_data)
                    # If it's not a list, we treat it as error
                    if not isinstance(parsed, list):
                        raise ValueError("Expected a JSON array, got something else.")

                    # Ensure the number of answers matches the number of rows
                    if len(parsed) != len(rows):
                        raise ValueError(
                            f"Number of answers ({len(parsed)}) does not match number of rows ({len(rows)})."
                        )

                    # Build the output. Each row gets a dict with the row's content, tokens, etc.
                    # Use the same tokens for each item because the call is shared
                    results = []
                    for answer in parsed:
                        # If it's just a string, wrap it up. If it's a dict, also handle it
                        content_text = answer if isinstance(answer, str) else json.dumps(answer)
                        results.append({
                            "content": content_text.strip(),
                            "tokens": tokens_used,
                            "engine_used": self.engine
                        })

                    return results

                except json.JSONDecodeError:
                    # The AI returned something that's not valid JSON. We'll treat that as an error
                    print(f"Failed to parse JSON array from AI: {raw_data}")
                    raise RuntimeError("AI did not return valid JSON array")

            except Exception as e:
                print(f"Attempt {attempt + 1} failed with error: {e}")
                if hasattr(e, 'status_code'):
                    if e.status_code == 429:
                        # Rate-limiting
                        match = RATE_LIMIT_PATTERN.search(e.body['message']) if hasattr(e, 'body') else None
                        if match:
                            delay = float(match.group(1))
                        else:
                            delay = 5
                        sleep_time = delay * BUFFER_MULTIPLIER
                        print(f"Rate limit reached. Waiting {sleep_time} seconds before retrying...")
                        time.sleep(sleep_time)
                else:
                    _err = e
                    if attempt < max_attempts - 1:
                        backoff_time = 2 ** attempt
                        print(f"Error encountered. Retrying in {backoff_time} seconds...")
                        time.sleep(backoff_time)

        # If we got here, attempts all failed
        if _err is None:
            raise RuntimeError("Failed to get answer from OpenAI API after 3 attempts.")
        else:
            print("Failed to get answer from OpenAI API after 3 attempts.")
            return [{'content': str(_err), 'tokens': 0, 'engine_used': self.engine}]


    def improve_prompt(self, prompt: str, user_id: int):
        _err = None
        for attempt in range(3):
            try:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "- You are an expert OpenAI prompt engineer You take a string input of the prompt, "
                            "improve it and respond with the new and improved prompt. Do not add anything else.\n"
                            f"- Rules: {pi_settings.prompt} Respond with the new prompt in a codeblock."
                        )
                    },
                    {
                        "role": "assistant",
                        "content": "Ready to assist with your prompts. Please provide your prompt to improve."
                    }
                ]

                # User's query and payload are appended here
                messages.append(
                    {
                        "role": "user",
                        "content": f"```{prompt}```"
                    }
                )

                completion = self.client.chat.completions.create(
                    model=self.engine,
                    messages=messages,
                    temperature=1,
                    #temperature=self.temperature,
                    #top_p=self.top_p
                )

                data = completion.choices[0].message.content
                tokens_used = completion.usage.total_tokens
                print(data)
                new_prompt = data.replace("```", "").strip()
                UsersDbCore.add_user_token_usage_pi(user_id, self.engine, tokens_used)
                return {"content": new_prompt, "tokens": tokens_used, 'engine_used': self.engine}

            except json.JSONDecodeError:
                # Handle the case where the response is not a valid JSON string
                raise HTTPException(status_code=500, detail="Failed to parse JSON from assistant response.")
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
                    if attempt < 2:
                        # Exponential backoff with a base delay of 1 second
                        time.sleep(1 * (2 ** attempt))

        if _err is None:
            raise RuntimeError("Failed to get answer from OpenAI API after 3 attempts.")
        else:
            print("Failed to get answer from OpenAI API after 3 attempts.")
            print(_err)
            raise HTTPException(status_code=500, detail="Failed to get answer from OpenAI API after 3 attempts.")
