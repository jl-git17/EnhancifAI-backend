ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS check_in FLOAT;

ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS cancelled BOOLEAN;

CREATE INDEX IF NOT EXISTS idx_check_in ON enhancifai.runs (check_in);

CREATE INDEX IF NOT EXISTS idx_run_details ON enhancifai.runs USING GIN (run_details);

ALTER TABLE enhancifai.run_logs
ADD COLUMN IF NOT EXISTS batched BOOLEAN;

ALTER TABLE enhancifai.users
ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;

-- Table to store different account tiers
CREATE TABLE IF NOT EXISTS enhancifai.account_tiers (
    tier_id SERIAL PRIMARY KEY,
    tier_name VARCHAR(100) NOT NULL UNIQUE,
    max_tokens INT,
    max_rows INT,
    max_prompts INT,
    created_at TIMESTAMP DEFAULT now()
);

-- Table to link users to their account tiers
CREATE TABLE IF NOT EXISTS enhancifai.user_account_tiers (
    user_id INT REFERENCES enhancifai.users(user_id),
    tier_id INT REFERENCES enhancifai.account_tiers(tier_id),
    assigned_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (user_id, tier_id)
);

-- Create default account tiers (Free, Pro, Enterprise)
INSERT INTO enhancifai.account_tiers (tier_name, max_tokens, max_rows, max_prompts)
VALUES 
    ('Free', 1000, 20, 4),
    ('Basic', 2000, 0, 0),
    ('Pro', 10000, 0, 0),
    ('Enterprise', 100000, 0, 0);

-- Update the users table to add a reference to the current tier (optional, for convenience)
ALTER TABLE enhancifai.users
ADD COLUMN IF NOT EXISTS current_tier_id INT REFERENCES enhancifai.account_tiers(tier_id);
