export interface DestinationDevice {
  id: string; name: string; owner_id: string; revoked_at: string | null;
  expires_at: string; last_seen_at: string | null;
  companion_version?: string | null; hostname?: string | null; remote_session?: boolean | null;
}

/** Mirrors the server's Tally gate (desktop.require_companion). */
const MINIMUM_COMPANION = [0, 7, 0];
function older(version: number[]) {
  for (let i = 0; i < MINIMUM_COMPANION.length; i++)
    if (version[i] !== MINIMUM_COMPANION[i]) return version[i] < MINIMUM_COMPANION[i];
  return false;
}
export function companionNotice(device: DestinationDevice) {
  if (!device.last_seen_at) return '';
  const version = device.companion_version?.split('.').map(Number);
  const outdated = !version || version.length !== 3 || version.some(Number.isNaN) || older(version);
  if (outdated) return `Update Minkops on ${device.name} to ${MINIMUM_COMPANION.join('.')} or later before running Tally work.`;
  if (device.remote_session) return `${device.name} is a Remote Desktop session. Run Minkops on the PC where Tally is open.`;
  return '';
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
