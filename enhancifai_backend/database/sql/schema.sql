
CREATE TABLE IF NOT EXISTS enhancifai.users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(100),
    google_oauth_token TEXT,
    email_verified BOOLEAN DEFAULT false,
    password_hash VARCHAR,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.users_token_usage (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    model VARCHAR,
    tokens INT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.google_sheets_credentials (
    user_id INT REFERENCES enhancifai.users(user_id),
    credentials JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.google_oauth_state (
    user_id INT REFERENCES enhancifai.users(user_id),
    state VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (user_id, state)
);

CREATE TABLE IF NOT EXISTS enhancifai.user_register_tokens (
    email VARCHAR(100) NOT NULL,
    token VARCHAR(64) NOT NULL,
    redeemed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.user_login_tokens (
    email VARCHAR(100) NOT NULL,
    token VARCHAR(64) NOT NULL,
    redeemed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.user_password_reset_tokens (
    email VARCHAR(100) NOT NULL,
    token VARCHAR(64) NOT NULL,
    redeemed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.login_events (
    user_id INT REFERENCES enhancifai.users(user_id),
    logged_in_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.stripe_checkout_sessions (
    session_id VARCHAR(255) PRIMARY KEY, -- Adjust VARCHAR length as needed
    user_id INT REFERENCES enhancifai.users(user_id),
    created_at TIMESTAMP DEFAULT now()
);

-- Create an ENUM type for source_type values
DO $$ BEGIN
    CREATE TYPE source_type AS ENUM ('csv', 'excel', 'google_sheets');
EXCEPTION
    WHEN duplicate_object THEN null; -- Avoid error if the type already exists
END $$;

CREATE TABLE IF NOT EXISTS enhancifai.runs (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES enhancifai.users(user_id),
    source_type source_type,
    run_details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enhancifai.runs_calls (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES enhancifai.runs(id),
    prompt TEXT,
    tokens_used INT
);

CREATE TABLE IF NOT EXISTS enhancifai.run_logs (
    log_id SERIAL PRIMARY KEY,
    run_id INT REFERENCES enhancifai.runs(id),
    user_name VARCHAR(100),
    engine_model VARCHAR(50),
    log_timestamp TIMESTAMP DEFAULT now(),
    time_elapsed FLOAT,
    num_rows_processed INT,
    num_rows_in_file INT,
    num_prompts INT,
    num_tokens INT,
    errors TEXT,
    filename VARCHAR,
    overflow BOOLEAN,
    batched BOOLEAN
);
