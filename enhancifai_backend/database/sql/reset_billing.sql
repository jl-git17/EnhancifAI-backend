-- Delete all records from stripe_invoices
DELETE FROM enhancifai.stripe_invoices;

-- Delete all records from model_price_history


-- Reset the invoice_number_seq to start at 1
SELECT setval('enhancifai.invoice_number_seq', 1, false);

-- Truncate invoices table and reset its sequence
TRUNCATE TABLE enhancifai.stripe_invoices RESTART IDENTITY CASCADE;

-- Additionally, reset the invoice_number_seq if necessary
SELECT setval('enhancifai.invoice_number_seq', 1, false);


-- Check if invoices table is empty
SELECT COUNT(*) FROM enhancifai.stripe_invoices;

-- Check the current value of the invoice_number_seq
SELECT currval('enhancifai.invoice_number_seq');

