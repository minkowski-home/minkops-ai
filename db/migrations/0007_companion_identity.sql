-- What each connected PC reports on every poll, so the console can name the
-- machine, warn about Remote Desktop sessions and refuse Tally work that an
-- outdated companion would mishandle. NULL means not reported.
ALTER TABLE desktop_devices
    ADD COLUMN companion_version text CHECK (companion_version ~ '^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$'),
    ADD COLUMN hostname text CHECK (length(hostname) BETWEEN 1 AND 80),
    ADD COLUMN remote_session boolean;
