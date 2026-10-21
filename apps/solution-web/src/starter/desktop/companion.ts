/** What the console tells a member about a PC's companion before Tally work depends on it. */
export interface Device {
  id: string; name: string; owner_id: string; revoked_at: string | null;
  expires_at: string; last_seen_at: string | null;
  companion_version?: string | null; hostname?: string | null; remote_session?: boolean | null;
}

/** Mirrors the server's gate for a run's Tally refresh (accounts/sync.queue). */
export const MINIMUM_COMPANION = [0, 10, 0];
function older(version: number[]) {
  for (let i = 0; i < MINIMUM_COMPANION.length; i++)
    if (version[i] !== MINIMUM_COMPANION[i]) return version[i] < MINIMUM_COMPANION[i];
  return false;
}
export function companionNotice(device: Device) {
  if (!device.last_seen_at) return '';
  const version = device.companion_version?.split('.').map(Number);
  const outdated = !version || version.length !== 3 || version.some(Number.isNaN) || older(version);
  if (outdated) return `Update Minkops on ${device.name} to ${MINIMUM_COMPANION.join('.')} or later before running Tally work.`;
  if (device.remote_session) return `${device.name} is a Remote Desktop session. Run Minkops on the PC where Tally is open.`;
  return '';
}
