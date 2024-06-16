ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS check_in FLOAT;

ALTER TABLE enhancifai.runs
ADD COLUMN IF NOT EXISTS cancelled BOOLEAN;

CREATE INDEX IF NOT EXISTS idx_check_in ON enhancifai.runs (check_in);

CREATE INDEX IF NOT EXISTS idx_run_details ON enhancifai.runs USING GIN (run_details);

ALTER TABLE enhancifai.run_logs
ADD COLUMN IF NOT EXISTS batched BOOLEAN;
