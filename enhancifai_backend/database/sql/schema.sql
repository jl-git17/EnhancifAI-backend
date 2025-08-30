-- Schema for EnhancifAI - Microsites

CREATE TABLE IF NOT EXISTS enhancifai.global_settings (
    active BOOLEAN PRIMARY KEY DEFAULT TRUE,
    openai_temperature FLOAT,
    openai_temperature_batched FLOAT
);
INSERT INTO enhancifai.global_settings (active, openai_temperature, openai_temperature_batched)
VALUES (TRUE, 0.5, 0.5)
ON CONFLICT (active) DO NOTHING;


CREATE TABLE IF NOT EXISTS enhancifai.microsite_functions (
    id SERIAL PRIMARY KEY,
    function_name VARCHAR(100) UNIQUE, -- e.g FixProductTitles
    prompts JSONB -- JSON ARRAY OF {"prompt": "<prompt_text>", "columns": ["<column1>", "<column2>"], "output_heading": "<output_heading>"}
);
ALTER TABLE enhancifai.microsite_functions
    ALTER COLUMN function_name TYPE VARCHAR(100);

CREATE TABLE IF NOT EXISTS enhancifai.microsite_function_runs (
    id SERIAL PRIMARY KEY,
    function_id INT REFERENCES enhancifai.microsite_functions(id),
    ip_address VARCHAR(45),
    source_type source_type,
    run_details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT now(),
    check_in FLOAT,
    cancelled BOOLEAN,
    source_filename VARCHAR
);

-- temp
ALTER TABLE enhancifai.microsite_function_runs
    ADD COLUMN IF NOT EXISTS source_filename VARCHAR;

-- Table to store microsite function run calls
CREATE TABLE IF NOT EXISTS enhancifai.microsite_function_runs_calls (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES enhancifai.microsite_function_runs(id),
    prompt TEXT,
    tokens_used INT
);