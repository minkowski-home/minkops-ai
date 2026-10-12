export interface DestinationDevice {
  id: string; name: string; owner_id: string; revoked_at: string | null;
  expires_at: string; last_seen_at: string | null;
}

export function destinationDevices(devices: DestinationDevice[], owner: string) {
  return devices.filter(device => device.owner_id === owner && !device.revoked_at);
}

export function destinationAvailable(device: DestinationDevice | undefined, now = Date.now()) {
  return Boolean(device && !device.revoked_at && Date.parse(device.expires_at) > now);
}

export function initialDestination(devices: DestinationDevice[], saved: string | null, now = Date.now()): string {
  try {
    const value: unknown = saved === null ? null : JSON.parse(saved);
    if (typeof value === 'string') return value;
  } catch { /* Obsolete preferences do not select an unrelated PC. */ }
  const available = devices.filter(device => destinationAvailable(device, now));
  return available.length === 1 ? available[0].id : '';
}

export function destinationPreference(tenant: string, owner: string, workflow: string) {
  return `${tenant}:${owner}:${workflow}:destination-pc:v1`;
}
