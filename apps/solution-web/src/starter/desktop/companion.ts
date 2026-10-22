/** What the console tells a member about a PC's companion before Tally work depends on it. */
export interface Device {
  id: string; name: string; owner_id: string; revoked_at: string | null;
  expires_at: string; last_seen_at: string | null;
  companion_version?: string | null; hostname?: string | null; remote_session?: boolean | null;
  /** The port this PC's Tally serves on; on a shared server each Windows user's Tally has its own. */
  tally_port?: number;
}

/** Mirrors the server's gate for Tally work (desktop.require_companion). */
export const MINIMUM_COMPANION = [0, 11, 0];
function older(version: number[], minimum: number[]) {
  for (let i = 0; i < minimum.length; i++)
    if (version[i] !== minimum[i]) return version[i] < minimum[i];
  return false;
}
export function companionNotice(device: Device) {
  if (!device.last_seen_at) return '';
  const minimum = MINIMUM_COMPANION;
  const version = device.companion_version?.split('.').map(Number);
  const outdated = !version || version.length !== 3 || version.some(Number.isNaN) || older(version, minimum);
  if (outdated) return `Update Minkops on ${device.name} to ${minimum.join('.')} or later before running Tally work.`;
  if (device.remote_session) return `${device.name} runs in a remote session. Minkops reads only the Tally open in this `
    + `Windows user's session, on port ${device.tally_port ?? 9000}.`;
  return '';
}
