from typing import List
import pandas as pd
from fastapi import HTTPException

from enhancifai_backend.config import settings
from enhancifai_backend.server.models.execution import PromptObject

GLOBAL_MAX_PROMPTS = settings.global_max_prompts

class PromptsProcessor:

    @classmethod
    def read_prompt_file(cls, prompt_file_path: str, max_prompts: int, file_format: str = 'csv'):
        """
        Reads and validates prompts from a CSV or Excel file.
        """
        if file_format not in ['csv', 'excel']:
            raise ValueError(
                "Invalid file format. Supported formats are 'csv' and 'excel'."
            )


        valid_prompts = []
        errors = []
        # Default values fetched from environment variables
        # default_temperature = validate_and_parse_float(
        #   os.getenv('DEFAULT_OPENAI_TEMPERATURE'), 0.0)
        # default_top_p = validate_and_parse_float(
        #   os.getenv('DEFAULT_OPENAI_TOP_P'), 0.0)

        # Read file using pandas
        try:
            if file_format == 'csv':
                df = pd.read_csv(prompt_file_path, encoding='utf-8')
            else:  # Excel
                df = pd.read_excel(prompt_file_path, engine='openpyxl')
        except Exception as e:
            errors.append(f"Error reading file: {e}")
            df = pd.DataFrame()  # Ensure df is defined in case of an error

        i = 1
        for _, row in df.iterrows():
            try:
                prompt_number = str(row['Line Number'])
                columns = str(row['Columns being Referenced'])
                prompt = str(row['The Prompt'])
                output_heading = str(row['Output Heading'])
                #temperature = validate_and_parse_float(
                #   row.get('Temperature', default_temperature), default_temperature)
                #top_p = validate_and_parse_float(
                #   row.get('Top_P', default_top_p), default_top_p)

                if not prompt_number.isdigit():
                    errors.append(
                        f"Row {i} >> Invalid prompt number: '{prompt_number}'. "
                        "Prompt number must be a digit."
                    )
                    continue


                columns = columns.replace(" ", "").upper()
                if (
                    columns != '*'
                    and not all(c.isalpha() and len(c) == 1 for c in columns.split('+'))
                ):
                    if '+' not in columns:
                        errors.append(
                            f"Row {i} >> 'Columns being Referenced' "
                            "must be separated by a '+' "
                            f"(plus) character. Provided: '{columns}'"
                        )
                    else:
                        errors.append(
                            f"Row {i} >> Invalid 'Columns being Referenced' "
                            f"format: '{columns}'. "
                            "Only single letters or '*' are allowed."
                        )
                    continue

                if not prompt:
                    errors.append(f"Row {i} >> Missing prompt text.")
                    continue

                valid_prompts.append({
                    'prompt_number': prompt_number,
                    'columns': columns,
                    'prompt': prompt,
                    'output_heading': output_heading
                    # 'temperature': temperature,
                    # 'top_p': top_p
                })
                if max_prompts > 0 and len(valid_prompts) > max_prompts:
                    errors.append(
                        f"A maximum of {max_prompts} prompts is allowed."
                    )
                    break
                i += 1
            except KeyError as e:
                errors.append(f"Row {i} >> Missing required column: {e}")
                break

        if errors:
            raise HTTPException(status_code=400, detail='\n\n'.join(errors).strip())

        return valid_prompts

    @classmethod
    def read_prompt_objects(cls, prompts: List[PromptObject], max_prompts: int):
        """
        Reads and validates prompts from a list of PromptObject instances.
        """
        valid_prompts = []
        errors = []
        i = 1

        for prompt_obj in prompts:
            try:
                prompt_number = str(i)
                columns = str(prompt_obj.columns)
                prompt = str(prompt_obj.prompt)
                output_heading = str(prompt_obj.output_heading)
                #temperature = validate_and_parse_float(
                #   row.get('Temperature', default_temperature), default_temperature)
                #top_p = validate_and_parse_float(
                #   row.get('Top_P', default_top_p), default_top_p)

                if not prompt_number.isdigit():
                    errors.append(
                        f"Prompt {i} >> Invalid prompt number: '{prompt_number}'. "
                        "Prompt number must be a digit."
                    )
                    continue

                columns = columns.replace(" ", "").upper()
                if columns != '*' and not all(
                    c.isalpha() and len(c) == 1 for c in columns.split('+')
                ):
                    if '+' not in columns:
                        errors.append(
                            f"Prompt {i} >> 'Columns being Referenced' "
                            "must be separated by a '+' "
                            f"(plus) character. Provided: '{columns}'"
                        )
                    else:
                        errors.append(
                            f"Prompt {i} >> Invalid 'Columns being Referenced' "
                            f"format: '{columns}'. "
                            "Only single letters or '*' are allowed."
                        )
                    continue

                if not prompt:
                    errors.append(f"Prompt {i} >> Missing prompt text.")
                    continue

                valid_prompts.append({
                    'prompt_number': prompt_number,
                    'columns': columns,
                    'prompt': prompt,
                    'output_heading': output_heading
                    # 'temperature': temperature,
                    # 'top_p': top_p
                })
                if max_prompts > 0 and len(valid_prompts) > max_prompts:
                    errors.append(
                        f"A maximum of {max_prompts} prompts is allowed."
                    )
                    break
                i += 1
            except Exception as e:
                errors.append(f"Error processing prompt {i}: {e}")
                break

        if errors:
            raise HTTPException(status_code=400, detail='\n\n'.join(errors).strip())

        return valid_prompts
