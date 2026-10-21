import {
  app,
  BrowserWindow,
  ipcMain,
  Menu,
  Tray,
  nativeImage,
  safeStorage,
  session,
  net,
  dialog,
  shell,
  clipboard,
} from "electron";
import { hostname, release } from "node:os";
import { join, basename } from "node:path";
import { existsSync } from "node:fs";
import {
  readFile,
  writeFile,
  rename,
  realpath,
  mkdir,
  readdir,
  stat,
  open,
} from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import {
  inventory,
  checkTally,
  inspectExcel,
  excelSchemaBytes,
  discoverClientContext,
  saveDiscoveryPackage,
  tallyTransport,
  tallyProcesses,
  readTallyIni,
  inspectTallyAttention,
  tallyCrashEvents,
  saveVoucher,
  saveCatalogSnapshot,
} from "@minkops/desktop-connectors";
import { collectSources, reportDiscoveryProgress } from "../../../platform/desktop-runtime/src/discovery.js";
import { CompanionWorker } from "@minkops/desktop-runtime";
import electronUpdater from "electron-updater";
import { startUpdates } from "./updater.js";
import {
  trustedOrigin,
  validateSender,
  validateFolderReconnect,
} from "./policy.js";

const localDemo = process.argv.includes("--local-demo");
const origin = trustedOrigin(
  process.env.MINKOPS_APP_URL ||
    (localDemo ? "http://127.0.0.1:3018" : "https://app.minkops.com"),
  !app.isPackaged || localDemo,
);
if (localDemo)
  app.setPath("userData", join(app.getPath("appData"), "Minkops Local Demo"));
let window;
let tray;
let quitting = false;
let worker;
let timer;
let state = {
  server_origin: origin,
  installation_id: randomUUID(),
  device: null,
  bindings: {},
  pending: null,
};
const pendingGrants = new Map();
let update = null;
let updates = null;
// Support evidence kept in memory: the latest diagnostic per running job and
// a short history of outcomes for Send diagnostics. Never bill contents.
const jobDiagnostics = new Map();
const recentJobs = [];
const pcName = () => hostname().slice(0, 80);
const remoteSession = () => /^RDP-/i.test(process.env.SESSIONNAME ?? "");
let persistence = Promise.resolve();
const uuid = (value) =>
  typeof value === "string" &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const slug = (value) =>
  typeof value === "string" && /^[a-z0-9][a-z0-9-]{0,79}$/.test(value);

function statePath() {
  return join(app.getPath("userData"), "companion.bin");
}
async function persist() {
  persistence = persistence
    .catch(() => {})
    .then(async () => {
      if (!safeStorage.isEncryptionAvailable())
        throw new Error("Windows credential storage is unavailable.");
      const encrypted = safeStorage.encryptString(JSON.stringify(state));
      const temporary = statePath() + ".tmp";
      await writeFile(temporary, encrypted, { mode: 0o600 });
      await rename(temporary, statePath());
    });
  return persistence;
}

async function cloud(path, options = {}) {
  if (!path.startsWith("/api/")) throw new Error("Invalid cloud operation.");
  const response = await net.fetch(origin + path, {
    signal: AbortSignal.timeout(30000),
    ...options,
    credentials: "include",
    redirect: "error",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "Minkops could not complete this action.",
    );
  }
  return response;
}

async function profile(tenant) {
  if (!slug(tenant)) throw new Error("Invalid workspace.");
  const user = await (await cloud("/api/auth/me")).json();
  if (
    !user.is_platform_admin &&
    !user.memberships.some((m) => m.slug === tenant)
  )
    throw new Error("Workspace access required.");
  return user;
}

function binding(tenant, sourceId, user) {
  if (!uuid(sourceId)) throw new Error("Invalid source.");
  const value = state.bindings[`${tenant}:${sourceId}`];
  if (!value || value.owner_id !== user.id)
    throw new Error("Reconnect the original folder on this PC.");
  return value;
}

function startWorker() {
  clearInterval(timer);
  if (!state.device) return;
  const identity = state.device;
  const request = async (path, body) => {
    if (state.device !== identity) throw new Error("PC connection changed.");
    const response = await fetch(origin + path, {
      method: body === undefined ? "GET" : "POST",
      redirect: "error",
      // A full discovery receipt can take longer to upload than a control
      // request. Keep its durable retry, with presence reported independently.
      signal: AbortSignal.timeout(path.endsWith("/finish") ? 120000 : 45000),
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${identity.credential}`,
        // Plan 5 adds the shared N-line voucher writer for every family.
        "X-Minkops-Plan-Version": "5",
        // Each poll tells the console which PC and companion run the work.
        "X-Minkops-Companion-Version": app.getVersion(),
        "X-Minkops-Host": pcName().replace(/[^\x20-\x7e]/g, "?"),
        "X-Minkops-Session": remoteSession() ? "remote" : "console",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const error = new Error(typeof body?.detail === "string" ? body.detail.slice(0,300) : "Companion request failed.");
      error.status = response.status;
      throw error;
    }
    return response.json();
  };
  worker = new CompanionWorker({
    request,
    heartbeat: () => request("/api/desktop/worker/heartbeat", {}),
    execute: async (job) => {
      if (state.device !== identity) throw new Error("PC connection changed.");
      // Minkops never starts, closes or restarts Tally; failures become typed
      // states naming this PC, and each one leaves a local diagnostic record.
      const pc = pcName();
      const tallyRequest = tallyTransport({
        pc,
        diagnose: async (diagnostic) => {
          const root = join(app.getPath("userData"), "tally-diagnostics");
          await mkdir(root, { recursive: true });
          const record = {
            ...diagnostic,
            job_id: job.id,
            collected_at: new Date().toISOString(),
            windows_events: await tallyCrashEvents(),
          };
          await writeFile(
            join(root, `${job.id}.json`),
            JSON.stringify(record, null, 2),
            { mode: 0o600 },
          );
          jobDiagnostics.set(job.id, {
            ...diagnostic,
            windows_events: (record.windows_events ?? []).slice(0, 3).map((event) => ({
              ...event,
              Message: String(event.Message ?? "").slice(0, 500),
            })),
          });
        },
      });
      if (
        job.operation === "tally.probe" &&
        !Object.keys(job.input || {}).length
      ) {
        // Check connection uses the same read-only check as discovery and saves.
        try {
          const ready = await checkTally({ pc });
          return { available: true, companies: ready.companies.map((c) => c.company) };
        } catch (error) {
          jobDiagnostics.set(job.id, {
            state: error.tallyState ?? "error", cause: error.detail?.cause,
            running: error.detail?.running, error: String(error.message).slice(0, 300),
          });
          throw error;
        }
      }
      const grantFor = (sourceId) =>
        binding(identity.tenant, sourceId, { id: identity.owner_id });
      if (job.operation === "sources.discover") {
        const plan = await request(
          `/api/desktop/worker/jobs/${job.id}/plan?claim_token=${job.claim_token}`,
        );
        const result = await collectSources(plan, {
          folderFor: (id) => grantFor(id).root,
          inventory,
          inspectExcel,
          excelSchemaBytes,
          discoverClientContext: (config, options) =>
            discoverClientContext(config, { ...options, request: tallyRequest, pc }),
          onProgress: async (source_key, status, category = null, progress = null) => {
            try {
              await reportDiscoveryProgress(() => request(`/api/desktop/worker/jobs/${job.id}/progress`, {
                claim_token: job.claim_token,
                source_key,
                status,
                category,
                ...(progress ? { progress } : {}),
              }));
            } catch (error) {
              if (error.code === "TASK_STOPPED" || [401, 404, 409].includes(error.status)) throw error;
            }
          },
        });
        await saveDiscoveryPackage(
          join(
            app.getPath("userData"),
            "discovery",
            identity.tenant,
            "collected",
          ),
          {
            format_version: "2",
            run_id: job.input.discovery_run_id,
            device_id: identity.id,
            sources: result.sources,
            partial: result.sources.some(
              (s) => s.status !== "ready" || s.snapshot?.partial,
            ),
            context_notes: [],
          },
        );
        return result;
      }
      if (job.operation === "files.refresh")
        return { files: await inventory(grantFor(job.input.source_id).root) };
      if (job.operation === "attention.refresh" || job.operation === "attention.supplier") {
        const plan = await request(`/api/desktop/worker/jobs/${job.id}/plan?claim_token=${job.claim_token}`);
        return inspectTallyAttention(plan, {request: tallyRequest, createSupplier: job.operation === "attention.supplier"});
      }
      // An encrypted, fsynced intent per remote ID: once written, no later
      // attempt may import that voucher again. Statement plans keep their
      // remote ID across retries, so this directory must stay the one they used.
      const durableIntent = async intent => {
        if (state.device !== identity || !safeStorage.isEncryptionAvailable()) throw new Error("PC connection changed.");
        const directory = join(app.getPath("userData"), "statement-manifests");
        await mkdir(directory, {recursive: true});
        let handle;
        try { handle = await open(join(directory, `${intent.remote_id}.bin`), "wx", 0o600); }
        catch (error) { if (error.code === "EEXIST") return false; throw error; }
        try {
          await handle.writeFile(safeStorage.encryptString(JSON.stringify({job_id:job.id,attempted_at:new Date().toISOString(),plan:intent})));
          await handle.sync();
        } finally { await handle.close(); }
        return state.device === identity;
      };
      if (job.operation === "tally.statement" || job.operation === "tally.save") {
        const plan = await request(`/api/desktop/worker/jobs/${job.id}/plan?claim_token=${job.claim_token}`);
        // Protocol 5: one writer for every voucher family; servers serve nothing older.
        if (plan.format_version !== 5) throw new Error("Unsupported voucher plan.");
        return saveVoucher(plan, {request: tallyRequest, beforeImport: durableIntent, pc,
          diagnose: (record) => jobDiagnostics.set(job.id, record)});
      }
      throw new Error("Unsupported local operation.");
    },
    diagnosticFor: (job, receipt) => {
      recentJobs.unshift({
        id: job.id,
        operation: job.operation,
        outcome: receipt.error ? "failed" : "completed",
        ...(receipt.error ? { error: receipt.error } : {}),
        at: new Date().toISOString(),
      });
      recentJobs.length = Math.min(recentJobs.length, 20);
      const diagnostic = jobDiagnostics.get(job.id) ?? null;
      jobDiagnostics.delete(job.id);
      return diagnostic;
    },
    pending: () => state.pending,
    savePending: async (pending) => {
      if (state.device === identity) {
        state.pending = pending;
        await persist();
      }
    },
    afterTick: async () => {
      if (state.device !== identity) return;
      try {
        const after = state.discovery_archived[identity.id];
        const catalog = await request(
          "/api/desktop/discovery/package" +
            (after ? `?after_id=${after}` : ""),
        );
        if (catalog) {
          await saveDiscoveryPackage(
            join(
              app.getPath("userData"),
              "discovery",
              identity.tenant,
              "confirmed",
            ),
            catalog,
          );
          state.discovery_archived[identity.id] = catalog.run_id;
          await persist();
        }
        state.discovery_archive_error = null;
      } catch (error) {
        state.discovery_archive_error =
          "The local discovery copy could not be refreshed. Keep Minkops open to retry.";
        throw error;
      }
    },
  });
  state.discovery_archived ??= {};
  const tick = () =>
    void worker
      .tick()
      .catch((error) => {
        // No tokens, documents, paths or raw protocol responses in console logs.
        if (error.status === 401 && state.device === identity) {
          state.device = null;
          state.pending = null;
          clearInterval(timer);
          void persist();
        }
      });
  timer = setInterval(tick, 4000);
  tick();
}

/** A technical summary for support: versions, this PC, the Tally session and
 * recent outcomes. Never bill data, file contents, XML or credentials. */
async function collectDiagnostics() {
  const pc = pcName();
  const processes = await tallyProcesses().catch(() => null);
  let session;
  try {
    const ready = await checkTally({ pc, retries: 0 });
    session = { state: "ready", companies: ready.companies, warnings: ready.warnings.map((w) => w.state) };
  } catch (error) {
    session = { state: error.tallyState ?? "error", message: String(error.message).slice(0, 300), cause: error.detail?.cause };
  }
  const folder = join(app.getPath("userData"), "tally-diagnostics");
  const records = [];
  try {
    const files = await Promise.all(
      (await readdir(folder)).filter((name) => name.endsWith(".json")).map(async (name) => ({
        name, modified: (await stat(join(folder, name))).mtimeMs,
      })),
    );
    for (const file of files.sort((a, b) => b.modified - a.modified).slice(0, 5))
      records.push(JSON.parse((await readFile(join(folder, file.name), "utf8")).slice(0, 4000)));
  } catch {
    /* No local records yet, or one is unreadable; send the rest. */
  }
  return {
    collected_at: new Date().toISOString(),
    companion: { version: app.getVersion(), plan_version: 5, connected: Boolean(state.device) },
    windows: { hostname: pc, release: release(), remote_session: remoteSession() },
    tally: {
      session,
      processes: processes?.map(({ product, version, session: windowsSession }) => ({ product, version, session: windowsSession })) ?? null,
      settings: await readTallyIni(processes?.[0]?.exe),
    },
    jobs: recentJobs,
    records: records.filter(Boolean),
  };
}

/** Send to Minkops when connected; otherwise copy, so the user can paste it. */
async function sendDiagnostics() {
  const bundle = await collectDiagnostics();
  const identity = state.device;
  if (identity) {
    try {
      const response = await fetch(origin + "/api/desktop/worker/diagnostics", {
        method: "POST",
        redirect: "error",
        signal: AbortSignal.timeout(30000),
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${identity.credential}` },
        body: JSON.stringify(bundle),
      });
      if (response.ok) return { reference: (await response.json()).reference };
    } catch {
      /* Offline: fall back to the clipboard below. */
    }
  }
  clipboard.writeText(JSON.stringify(bundle, null, 2));
  return { copied: true };
}

async function sendDiagnosticsFromTray() {
  const sent = await sendDiagnostics().catch(() => null);
  await dialog.showMessageBox({
    type: sent ? "info" : "warning",
    title: "Minkops diagnostics",
    message: sent?.reference
      ? `Diagnostics sent. Reference: ${sent.reference}`
      : sent?.copied
        ? "Minkops could not be reached, so the diagnostics were copied. Paste them to your Minkops contact."
        : "Diagnostics could not be collected. Restart Minkops and try again.",
  });
}

function handle(channel, operation) {
  ipcMain.handle(channel, async (event, payload) => {
    validateSender(event, window, origin);
    return operation(payload);
  });
}

function setupBridge() {
  handle("desktop:save-catalog", async ({ tenant, discoveryId }) => {
    await profile(tenant);
    if (!uuid(discoveryId)) throw new Error("Choose a valid source catalog.");
    const catalog = await (
      await cloud(
        `/api/tenants/${tenant}/discovery/runs/${discoveryId}/catalog.json`,
      )
    ).json();
    if (!catalog || !Array.isArray(catalog.sources))
      throw new Error("Source catalog is unavailable.");
    const selected = await dialog.showSaveDialog(window, {
      title: "Save source catalog",
      defaultPath: join(
        app.getPath("documents"),
        `minkops-sources-${discoveryId}.json`,
      ),
      filters: [{ name: "JSON source catalog", extensions: ["json"] }],
    });
    if (selected.canceled || !selected.filePath) return false;
    await saveCatalogSnapshot(selected.filePath, catalog);
    return true;
  });
  handle("desktop:send-diagnostics", () => sendDiagnostics());
  handle("desktop:check-updates", () => updates?.check());
  handle("desktop:install-update", () => updates?.requestInstall() ?? false);
  handle("desktop:tally-diagnostics", async () => {
    await shell.openPath(join(app.getPath("userData"), "tally-diagnostics"));
  });
  handle("desktop:status", async () => ({
    discovery_archive_error: state.discovery_archive_error ?? null,
    version: app.getVersion(),
    update,
    name: hostname(),
    device: state.device
      ? {
          id: state.device.id,
          tenant: state.device.tenant,
          owner_id: state.device.owner_id,
        }
      : null,
  }));
  handle("desktop:connect", async (tenant) => {
    const user = await profile(tenant);
    const device = await (
      await cloud(`/api/tenants/${tenant}/desktop/devices`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-csrf-token": user.csrf_token,
        },
        body: JSON.stringify({
          name: hostname().slice(0, 80),
          installation_id: state.installation_id,
        }),
      })
    ).json();
    clearInterval(timer);
    state.device = {
      id: device.id,
      tenant,
      owner_id: user.id,
      credential: device.credential,
    };
    state.pending = null;
    await persist();
    startWorker();
    return { id: device.id };
  });
  handle("desktop:disconnect", async () => {
    clearInterval(timer);
    const device = state.device;
    state.device = null;
    state.pending = null;
    pendingGrants.clear();
    await persist();
    if (device) {
      try {
        const user = await profile(device.tenant);
        if (user.id === device.owner_id)
          await cloud(
            `/api/tenants/${device.tenant}/desktop/devices/${device.id}`,
            {
              method: "DELETE",
              headers: { "x-csrf-token": user.csrf_token },
            },
          );
      } catch {
        /* Worker is stopped locally even when server revocation is offline. */
      }
    }
  });
  handle(
    "desktop:pick-folder",
    async ({ tenant, sourceId, schemaOnly = false }) => {
      const user = await profile(tenant);
      if (state.device?.tenant !== tenant || state.device?.owner_id !== user.id)
        throw new Error(
          "Connect this PC in Connections before choosing a folder.",
        );
      const selected = await dialog.showOpenDialog(window, {
        title: "Choose a folder for Minkops",
        properties: ["openDirectory"],
      });
      if (selected.canceled) return null;
      const root = await realpath(selected.filePaths[0]);
      if (sourceId) {
        if (!uuid(sourceId)) throw new Error("Invalid source.");
        validateFolderReconnect(
          state.bindings[`${tenant}:${sourceId}`],
          root,
          user.id,
        );
      }
      let files = await inventory(root);
      if (schemaOnly === true) {
        files = await Promise.all(
          files
            .filter((f) => /\.xlsx$/i.test(f.path))
            .map(async (file) => ({
              path: file.path,
              content: (
                await excelSchemaBytes(Buffer.from(file.content, "base64"))
              ).toString("base64"),
            })),
        );
        if (!files.length)
          throw new Error(
            "Choose a folder containing supported Excel workbooks.",
          );
      }
      const grantId = randomUUID();
      pendingGrants.set(grantId, {
        root,
        tenant,
        owner_id: user.id,
        files: files.map((file) => ({
          path: file.path,
          sha256: createHash("sha256")
            .update(Buffer.from(file.content, "base64"))
            .digest("hex"),
        })),
      });
      return { grantId, label: basename(root), files };
    },
  );
  handle("desktop:bind-folder", async ({ tenant, sourceId, grantId }) => {
    const user = await profile(tenant);
    const grant = pendingGrants.get(grantId);
    if (
      !uuid(sourceId) ||
      !grant ||
      grant.tenant !== tenant ||
      grant.owner_id !== user.id
    )
      throw new Error("Choose the folder again.");
    const sources = await (
      await cloud(`/api/tenants/${tenant}/accounts/sources`)
    ).json();
    const source = sources.find((s) => s.id === sourceId && s.writable);
    if (
      !source ||
      source.files.length !== grant.files.length ||
      grant.files.some(
        (file) =>
          !source.files.some(
            (remote) =>
              remote.path === file.path && remote.sha256 === file.sha256,
          ),
      )
    ) {
      throw new Error(
        "The source does not match the selected folder. Choose the folder again.",
      );
    }
    state.bindings[`${tenant}:${sourceId}`] = {
      root: grant.root,
      tenant,
      owner_id: user.id,
    };
    pendingGrants.delete(grantId);
    await persist();
    if (state.device?.tenant !== tenant || state.device?.owner_id !== user.id)
      throw new Error("Connect this PC first.");
    await cloud(
      `/api/tenants/${tenant}/desktop/devices/${state.device.id}/sources/${sourceId}`,
      {
        method: "POST",
        headers: { "x-csrf-token": user.csrf_token },
      },
    );
  });
  handle("desktop:refresh-folder", async ({ tenant, sourceId }) => {
    const user = await profile(tenant);
    return inventory(binding(tenant, sourceId, user).root);
  });
}

function openConsole() {
  if (window) {
    window.show();
    window.focus();
    return;
  }
  window = new BrowserWindow({
    title: "Minkops",
    width: 1280,
    height: 860,
    minWidth: 860,
    minHeight: 640,
    backgroundColor: "#f8f7f4",
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(app.getAppPath(), "dist/preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    const target = new URL(url);
    // Evidence opens in a separate sandbox without the privileged preload.
    if (
      target.origin === origin &&
      /^\/api\/tenants\/[a-z0-9-]+\/accounts\/files\/[a-f0-9-]+\/content$/.test(
        target.pathname,
      )
    ) {
      const evidence = new BrowserWindow({
        title: "Source document",
        autoHideMenuBar: true,
        webPreferences: {
          nodeIntegration: false,
          contextIsolation: true,
          sandbox: true,
          webSecurity: true,
        },
      });
      evidence.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
      evidence.webContents.on("will-navigate", (event) =>
        event.preventDefault(),
      );
      evidence.webContents.on("will-redirect", (event) =>
        event.preventDefault(),
      );
      void evidence.loadURL(url).catch(() => evidence.close());
    }
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, url) => {
    if (new URL(url).origin !== origin) {
      event.preventDefault();
      if (url.startsWith("https://")) void shell.openExternal(url);
    }
  });
  window.webContents.on("will-redirect", (event, url) => {
    if (new URL(url).origin !== origin) event.preventDefault();
  });
  window.webContents.on("will-attach-webview", (event) =>
    event.preventDefault(),
  );
  window.on("close", (event) => {
    if (!quitting) {
      event.preventDefault();
      window.hide();
    }
  });
  window.on("closed", () => {
    window = null;
  });
  void window
    .loadURL(origin)
    .catch(() =>
      window?.loadFile(join(app.getAppPath(), "assets/offline.html")),
    );
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", openConsole);
  app.on("before-quit", () => {
    quitting = true;
    clearInterval(timer);
  });
  app.on("window-all-closed", () => {});
  app
    .whenReady()
    .then(async () => {
      app.setAppUserModelId("com.minkops.desktop");
      if (existsSync(statePath()) && safeStorage.isEncryptionAvailable()) {
        try {
          const restored = JSON.parse(
            safeStorage.decryptString(await readFile(statePath())),
          );
          // Credentials and grants belong to one server. Changing deployments
          // requires explicit pairing; never send a prior server's token away.
          if (restored.server_origin === origin) state = restored;
          // Releases before 0.7.0 remembered how to restart Tally. Minkops no
          // longer controls Tally, so that local state is discarded.
          delete state.tally_startup;
          delete state.tally_company_numbers;
        } catch {
          /* Damaged local credentials require explicit reconnection. */
        }
      }
      session.defaultSession.setPermissionRequestHandler(
        (_contents, _permission, callback) => callback(false),
      );
      session.defaultSession.setPermissionCheckHandler(() => false);
      setupBridge();
      const image = nativeImage.createFromPath(
        join(app.getAppPath(), "assets/tray.png"),
      );
      tray = new Tray(image);
      tray.setToolTip("Minkops");
      tray.setContextMenu(
        Menu.buildFromTemplate([
          { label: "Open Minkops", click: openConsole },
          { label: "Send diagnostics", click: () => void sendDiagnosticsFromTray() },
          {
            label: "Reconnect to Minkops",
            click: () => {
              openConsole();
              void window.loadURL(origin);
            },
          },
          { type: "separator" },
          { label: "Quit Minkops", click: () => app.quit() },
        ]),
      );
      tray.on("double-click", openConsole);
      startWorker();
      updates = startUpdates({
        updater: electronUpdater.autoUpdater,
        isPackaged: app.isPackaged && !localDemo,
        // Never restart over a claimed job, an unsent receipt or an active user.
        isIdle: () => !worker?.busy && !state.pending && !window?.isFocused(),
        canRestart: () => !worker?.busy && !state.pending,
        onState: (value) => {
          update = value;
        },
      });
      openConsole();
    })
    .catch(() => {
      dialog.showErrorBox(
        "Minkops could not start",
        "Restart Minkops. If this continues, contact your administrator.",
      );
      app.quit();
    });
}
