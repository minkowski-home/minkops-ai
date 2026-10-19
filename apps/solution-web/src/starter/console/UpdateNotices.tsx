import { useEffect, useState } from 'react';
import { desktopBridge, type DesktopStatus } from '../desktop/bridge';

/** Both checks are read-only. Never reload a session or interrupt a local save. */
export function UpdateNotices() {
  const [webUpdate, setWebUpdate] = useState<string | null>(null);
  const [native, setNative] = useState<DesktopStatus['update']>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function check() {
      await Promise.allSettled([
        fetch('/version.json', { cache: 'no-store', credentials: 'omit' }).then(async response => {
          if (!response.ok) return;
          const version: unknown = await response.json();
          if (active && version && typeof version === 'object' && 'id' in version &&
              typeof version.id === 'string' && version.id && version.id !== __MINKOPS_BUILD_ID__) setWebUpdate(version.id);
        }),
        desktopBridge()?.status().then(status => { if (active) setNative(status.update); }),
      ]);
      if (active) timer = setTimeout(() => void check(), 30_000);
    }
    void check();
    return () => { active = false; clearTimeout(timer); };
  }, []);
  async function restart() {
    setError('');
    try {
      if (!await desktopBridge()?.restartForUpdate?.()) throw new Error('The update is not ready yet.');
      setNative(value => value ? { ...value, state: 'waiting' } : value);
    } catch { setError('Could not schedule the restart. Try again.'); }
  }
  async function retryCheck() {
    setError('');
    try { await desktopBridge()?.checkUpdates?.(); }
    catch { setError('Could not check for updates.'); }
  }
  return <div className="update-notices">
    {webUpdate && <div className="update-notice" role="status">
      <span>A newer version of Minkops is available. Refresh when you are ready; running workflows keep their progress.</span>
      <button className="button button-ghost" onClick={() => {
        // Electron may reuse fresh cached navigation HTML on a normal reload.
        // One public cache key per build preserves the route and forces a fetch.
        const target = new URL(window.location.href);
        target.searchParams.set('_minkops_build', webUpdate);
        window.location.replace(target.href);
      }}>Refresh for latest version</button>
    </div>}
    {native && <div className="update-notice" role="status">
      <span>{native.state === 'downloading' ? `Downloading Minkops ${native.version ?? 'update'}… You can keep working.`
        : native.state === 'waiting' ? 'Restart scheduled. Minkops will restart after local work and pending receipts finish.'
          : native.state === 'error' ? 'App updates could not be checked or downloaded. Minkops will retry automatically.'
            : `Minkops ${native.version ?? 'update'} is ready. Completed saves and progress are retained.`}</span>
      {native.state === 'ready' && desktopBridge()?.restartForUpdate &&
        <button className="button button-ghost" onClick={() => void restart()}>Restart when safe</button>}
      {native.state === 'ready' && !desktopBridge()?.restartForUpdate && <span>The update installs when Minkops is idle or quits.</span>}
      {native.state === 'error' && desktopBridge()?.checkUpdates &&
        <button className="button button-ghost" onClick={() => void retryCheck()}>Retry update check</button>}
      {error && <span role="alert">{error}</span>}
    </div>}
  </div>;
}
