ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS check_in FLOAT;

ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS cancelled BOOLEAN;

ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS source_filename VARCHAR;

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

-- Create default account tiers (Free, Basic, Pro, Enterprise) if not already present
INSERT INTO enhancifai.account_tiers (tier_name, max_tokens, max_rows, max_prompts)
SELECT 'Free', 1000, 20, 4
WHERE NOT EXISTS (SELECT 1 FROM enhancifai.account_tiers)
UNION ALL
SELECT 'Basic', 2000, 0, 0
WHERE NOT EXISTS (SELECT 1 FROM enhancifai.account_tiers WHERE tier_name = 'Free')
UNION ALL
SELECT 'Pro', 10000, 0, 0
WHERE NOT EXISTS (SELECT 1 FROM enhancifai.account_tiers WHERE tier_name = 'Basic')
UNION ALL
SELECT 'Enterprise', 100000, 0, 0
WHERE NOT EXISTS (SELECT 1 FROM enhancifai.account_tiers WHERE tier_name = 'Pro');

-- Update the users table to add a reference to the current tier
ALTER TABLE enhancifai.users
ADD COLUMN IF NOT EXISTS current_tier_id INT DEFAULT 1 REFERENCES enhancifai.account_tiers(tier_id);

ALTER TABLE enhancifai.users
ADD COLUMN IF NOT EXISTS ai_consent TIMESTAMP;

-- Add Stripe-related fields to users table
ALTER TABLE enhancifai.users
ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50),  -- active, trialing, canceled, etc.
ADD COLUMN IF NOT EXISTS subscription_start TIMESTAMP,
ADD COLUMN IF NOT EXISTS subscription_end TIMESTAMP;
