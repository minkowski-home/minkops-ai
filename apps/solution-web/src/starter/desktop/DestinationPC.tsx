import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../contexts/AuthContext';
import { destinationAvailable, destinationDevices, destinationPreference, initialDestination, type DestinationDevice } from './destinationPCs';

export interface DestinationPCState {
  deviceId: string; available: boolean; loading: boolean; error: string; name: string;
}

/** Shared workflow destination selection. Persist identity, never choose a fallback for a lost PC. */
export function useDestinationPC(tenant: string, workflowKey: string) {
  const { user } = useAuth();
  const [devices, setDevices] = useState<DestinationDevice[]>([]);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const preference = destinationPreference(tenant, user?.id ?? '', workflowKey);
  const refresh = useCallback(async (active: () => boolean = () => true) => {
    try {
      const all = await api<DestinationDevice[]>(`/api/tenants/${tenant}/desktop/devices`);
      if (!active()) return;
      const owned = destinationDevices(all, user?.id ?? '');
      let saved: string | null = null;
      try { saved = localStorage.getItem(preference); } catch { /* Preferences are optional. */ }
      setDevices(owned);
      setDeviceId(current => current ?? initialDestination(owned, saved));
      setError('');
    } catch (e) {
      if (active()) setError(e instanceof Error ? e.message : 'Could not load destination PCs.');
    } finally { if (active()) setLoading(false); }
  }, [tenant, user?.id, preference]);
  useEffect(() => {
    let active = true;
    void refresh(() => active);
    const timer = setInterval(() => void refresh(() => active), 5000);
    return () => { active = false; clearInterval(timer); };
  }, [refresh]);
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
  </div>;
}
