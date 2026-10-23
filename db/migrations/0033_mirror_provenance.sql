-- The PC each mirror version was read from. Markers and AlterIDs belong to one
-- Tally copy, so a company that moves to the PC replacing a disconnected one
-- is read there afresh, in full: another copy's markers never drive a delta,
-- and a run never pins another PC's copy. Until now a company never changed
-- PC, so every version was read on the PC its company is on.
ALTER TABLE mirror_versions ADD COLUMN device_id uuid;
UPDATE mirror_versions v SET device_id = c.device_id FROM companies c WHERE c.id = v.company_id;
ALTER TABLE mirror_versions ALTER COLUMN device_id SET NOT NULL;
ALTER TABLE mirror_versions ADD CONSTRAINT mirror_versions_device
    FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id);
