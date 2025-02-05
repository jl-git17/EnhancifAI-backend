TRUNCATE TABLE enhancifai.stripe_invoices
RESTART IDENTITY CASCADE;
--,
               --enhancifai.runs,
               --enhancifai.prompt_improver_run_logs,
               --enhancifai.users_token_usage,
               --enhancifai.users_token_usage_pi,
               --enhancifai.run_logs


-- Reset the invoice_number_seq to start at 1
SELECT setval('enhancifai.invoice_number_seq', 1, false);

-- Truncate invoices table (stripe_invoices) and reset its sequence with cascade
TRUNCATE TABLE enhancifai.stripe_invoices
RESTART IDENTITY CASCADE;

-- Additionally, reset the invoice_number_seq if necessary
SELECT setval('enhancifai.invoice_number_seq', 1, false);

