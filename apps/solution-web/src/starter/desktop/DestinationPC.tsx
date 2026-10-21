import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { companionNotice, destinationAvailable, destinationDevices, destinationPreference, initialDestination, type DestinationDevice } from './destinationPCs';
import { useRead } from '../useRead';

export interface DestinationPCState {
  deviceId: string; available: boolean; loading: boolean; error: string; name: string;
}

/** Shared workflow destination selection. Persist identity, never choose a fallback for a lost PC. */
export function useDestinationPC(tenant: string, workflowKey: string) {
  const { user } = useAuth();
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const preference = destinationPreference(tenant, user?.id ?? '', workflowKey);
  const { data, loading, error, refresh } = useRead<DestinationDevice[]>(`${user?.id ?? ''}:${tenant}`,
    `/api/tenants/${tenant}/desktop/devices`, { interval: 5000 });
  const devices = useMemo(() => destinationDevices(data ?? [], user?.id ?? ''), [data, user?.id]);
  useEffect(() => {
    if (!data) return;
    let saved: string | null = null;
    try { saved = localStorage.getItem(preference); } catch { /* Preferences are optional. */ }
    setDeviceId(current => current ?? initialDestination(devices, saved));
  }, [data, devices, preference]);
  useEffect(() => {
    if (deviceId === null) return;
    try { localStorage.setItem(preference, JSON.stringify(deviceId)); } catch { /* Running works without storage. */ }
  }, [preference, deviceId]);
  const device = devices.find(item => item.id === deviceId);
  const state: DestinationPCState = {
    deviceId: deviceId ?? '', available: !loading && !error && destinationAvailable(device),
    loading, error, name: device?.name ?? '',
  };
  return { state, devices, select: setDeviceId, refresh };
}

export function DestinationPCPicker({ devices, value, onChange, busy = false, required = true, loading = false }: {
  devices: DestinationDevice[]; value: string; onChange: (id: string) => void;
  busy?: boolean; required?: boolean; loading?: boolean;
}) {
  const selected = devices.find(device => device.id === value);
  return <div className="workflow-destination">
    <label className="config-field">Destination PC
      <select aria-label="Destination PC" value={value} disabled={busy || loading} onChange={event => onChange(event.target.value)}>
        <option value="">{loading ? 'Loading PCs…' : required ? 'Choose a destination PC' : 'Process online without a PC'}</option>
        {value && !selected && <option value={value} disabled>Previously selected PC · unavailable</option>}
        {devices.map(device => <option key={device.id} value={device.id} disabled={!destinationAvailable(device)}>
          {device.name}{devices.filter(item => item.name === device.name).length > 1 ? ` · ${device.id.slice(0, 8)}` : ''}{!destinationAvailable(device) ? ' · reconnect required' : !device.last_seen_at || Date.now() - Date.parse(device.last_seen_at) >= 30000 ? ' · offline' : ' · ready'}
        </option>)}
      </select>
    </label>
    {!loading && !devices.length && required && <p role="status">Connect a PC in the Windows app to use a local destination.</p>}
    {value && !destinationAvailable(selected) && <p role="status">The selected PC is unavailable. Reconnect it or explicitly choose another PC.</p>}
    {selected && destinationAvailable(selected) && (!selected.last_seen_at || Date.now() - Date.parse(selected.last_seen_at) >= 30000) && <p className="quiet-state">This PC is offline. Local work waits for it to reconnect.</p>}
    {selected && companionNotice(selected) && <p role="status">{companionNotice(selected)}</p>}
  </div>;
}
