-- Presence has its own short transaction; slow authenticated receipts retain
-- their device authorization lock without blocking concurrent heartbeats.
CREATE TABLE desktop_device_presence (
    device_id uuid PRIMARY KEY REFERENCES desktop_devices(id) ON DELETE CASCADE,
    last_seen_at timestamptz NOT NULL
);
INSERT INTO desktop_device_presence(device_id,last_seen_at)
SELECT id,last_seen_at FROM desktop_devices WHERE last_seen_at IS NOT NULL;
