import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { desktopBridge, type DesktopStatus } from "./bridge";

interface Device {
  id: string;
  name: string;
  owner_id: string;
  last_seen_at: string | null;
  revoked_at: string | null;
  expires_at: string;
}

export function DevicesScreen({
  tenant,
  routeSlug
}: {
  tenant: string;
  routeSlug: string;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [devices, setDevices] = useState<Device[]>([]);
  const [native, setNative] = useState<DesktopStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    const [loaded, status] = await Promise.all([
      api<Device[]>(`/api/tenants/${tenant}/desktop/devices`),
      desktopBridge()?.status() ?? null
    ]);
    setDevices(loaded);
    setNative(status);
  }, [tenant]);
  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        if (active) await refresh();
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Could not load your PCs.");
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [refresh]);
  async function action(work: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await work();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not complete this action.");
    } finally {
      setBusy(false);
    }
  }
  const mine = devices.filter((d) => d.owner_id === user?.id && !d.revoked_at);
  const connected =
    native?.device?.tenant === tenant && native.device.owner_id === user?.id;
  return (
    <section className="route-screen devices-screen">
      <header className="route-heading">
        <div>
          <p className="eyebrow">Connected PCs</p>
          <h2>Your PCs</h2>
          <p>
            Keep Minkops running on a connected PC to work with its Tally and local files.
          </p>
        </div>
      </header>
      {native ? (
        <article className="device-connect-card">
          <div>
            <h3>{native.name}</h3>
            <p>
              {connected
                ? "This PC is connected to your workspace."
                : "Connect this PC to run local work from Minkops on the web or desktop."}
            </p>
          </div>
          <button
            className="button button-primary"
            disabled={busy}
            onClick={() =>
              void action(async () => {
                if (connected) await desktopBridge()?.disconnect();
                else await desktopBridge()?.connect(tenant);
              })
            }
          >
            {connected ? "Disconnect this PC" : "Connect this PC"}
          </button>
        </article>
      ) : (
        <p className="quiet-state">
          Open the Minkops desktop app and sign in to connect a PC. You can then start its
          local work here.
        </p>
      )}
      <div className="device-grid">
        {mine.map((device) => {
          const expired = Date.parse(device.expires_at) < Date.now();
          const online =
            !expired &&
            device.last_seen_at &&
            Date.now() - Date.parse(device.last_seen_at) < 30000;
          return (
            <article className="device-card" key={device.id}>
              <div className="device-card-title">
                <h3>{device.name}</h3>
                <span className={`status status--${online ? "active" : "paused"}`}>
                  {online ? "Ready" : expired ? "Reconnect" : "Offline"}
                </span>
              </div>
              <p>
                {online
                  ? "Ready to check Tally on this PC."
                  : expired
                    ? "Open the desktop app to reconnect this PC."
                    : "Open Minkops on this PC. Queued work starts when it reconnects."}
              </p>
              <button
                className="button button-primary"
                disabled={busy || expired}
                onClick={() =>
                  void action(async () => {
                    const job = await api<{ task_id: string }>(
                      `/api/tenants/${tenant}/desktop/jobs`,
                      {
                        method: "POST",
                        body: JSON.stringify({
                          device_id: device.id,
                          operation: "tally.probe",
                          input: {},
                          request_key: crypto.randomUUID()
                        })
                      },
                      user?.csrf_token
                    );
                    navigate(`/${routeSlug}/tasks/${job.task_id}`);
                  })
                }
              >
                Check Tally
              </button>
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={() =>
                  void action(async () => {
                    await api(
                      `/api/tenants/${tenant}/desktop/devices/${device.id}`,
                      { method: "DELETE" },
                      user?.csrf_token
                    );
                    if (native?.device?.id === device.id)
                      await desktopBridge()?.disconnect();
                  })
                }
              >
                Disconnect
              </button>
            </article>
          );
        })}
      </div>
      {error && (
        <p role="alert" className="form-message">
          {error}
        </p>
      )}
      <p className="quiet-state">
        Tasks and results are saved in your workspace.{" "}
        <Link to={`/${routeSlug}/dashboard`}>See your recent work</Link>
      </p>
    </section>
  );
}
