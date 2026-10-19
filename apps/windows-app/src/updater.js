/** Background updates from the public download feed (electron-updater).
 *
 * Updates download quietly and are verified against the feed's SHA-512. One
 * installs when Minkops quits, or once the companion is idle: no claimed job,
 * no receipt waiting to be sent, and nobody using the window. A financial
 * save is therefore never interrupted by an update.
 */
const CHECK_EVERY = 6 * 3600 * 1000;
const IDLE_EVERY = 60_000;

export function startUpdates({ updater, isPackaged, isIdle, canRestart = isIdle, onState = () => {}, timers = globalThis }) {
  if (!isPackaged) return { stop() {}, check: async () => {}, requestInstall: () => false };
  updater.logger = null; // Never write update URLs or paths to the console.
  updater.autoDownload = true;
  // Quitting already ends any job, and pending receipts are persisted.
  updater.autoInstallOnAppQuit = true;
  let ready = false;
  let requested = false;
  let version;
  updater.on("update-available", (info) => {
    version = info?.version;
    onState({ state: "downloading", version });
  });
  updater.on("update-downloaded", (info) => {
    ready = true;
    version = info?.version;
    onState({ state: "ready", version });
  });
  updater.on("error", () => onState({ state: "error" }));
  const check = () => updater.checkForUpdates().catch(() => onState({ state: "error" }));
  check();
  const checker = timers.setInterval(check, CHECK_EVERY);
  const installer = timers.setInterval(() => {
    if (!ready || !(requested ? canRestart() : isIdle())) return;
    stop();
    updater.quitAndInstall(true, true);
  }, IDLE_EVERY);
  function stop() {
    timers.clearInterval(checker);
    timers.clearInterval(installer);
  }
  return { stop, check, requestInstall() {
    if (!ready) return false;
    requested = true;
    onState({ state: "waiting", version });
    return true;
  } };
}
