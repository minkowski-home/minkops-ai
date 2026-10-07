-- Native paths and folder grants stay encrypted on the PC. The server stores
-- only which approved source can be serviced by that user's registered device.
CREATE TABLE desktop_source_bindings (
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    source_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, source_id),
    FOREIGN KEY (tenant_id, device_id) REFERENCES desktop_devices(tenant_id, id),
    FOREIGN KEY (tenant_id, source_id) REFERENCES account_sources(tenant_id, id)
);
ALTER TABLE desktop_jobs DROP CONSTRAINT desktop_jobs_operation_check;
ALTER TABLE desktop_jobs ADD CONSTRAINT desktop_jobs_operation_check
    CHECK (operation IN ('tally.probe', 'files.refresh', 'accounts.save'));
