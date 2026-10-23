-- A held bill or bank row later found in Tally is noted as entered by hand, or
-- as saved by Minkops from another run when a run saved that voucher. The
-- vouchers runs saved are looked up by their Tally GUID within the tenant.
CREATE INDEX run_records_saved_voucher ON run_records (tenant_id, (current->>'guid')) WHERE status = 'saved';
