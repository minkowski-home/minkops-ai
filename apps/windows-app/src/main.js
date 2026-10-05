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
} from "electron";
import { hostname } from "node:os";
import { join, basename } from "node:path";
import { existsSync } from "node:fs";
import {
  readFile,
  writeFile,
  rename,
  realpath,
  unlink,
  mkdir,
} from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import {
  inventory,
  replaceApproved,
  tallyProbe,
  inspectExcel,
  discoverTally,
} from "@minkops/desktop-connectors";
import { collectSources } from "../../../platform/desktop-runtime/src/discovery.js";
import { CompanionWorker } from "@minkops/desktop-runtime";
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
      signal: AbortSignal.timeout(45000),
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${identity.credential}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      const error = new Error("Companion request failed.");
      error.status = response.status;
      throw error;
    }
    return response.json();
  };
  worker = new CompanionWorker({
    request,
    execute: async (job) => {
      if (state.device !== identity) throw new Error("PC connection changed.");
      if (
        job.operation === "tally.probe" &&
        !Object.keys(job.input || {}).length
      )
        return tallyProbe();
      const grantFor = (sourceId) =>
        binding(identity.tenant, sourceId, { id: identity.owner_id });
      if (job.operation === "sources.discover") {
        const plan = await request(
          `/api/desktop/worker/jobs/${job.id}/plan?claim_token=${job.claim_token}`,
        );
        return collectSources(plan, {
          folderFor: (id) => grantFor(id).root,
          inventory,
          inspectExcel,
          discoverTally,
          onProgress: async (source_key, status, category = null) => {
            try {
              await request(`/api/desktop/worker/jobs/${job.id}/progress`, {
                claim_token: job.claim_token,
                source_key,
                status,
                category,
              });
            } catch (error) {
              if ([401, 404, 409].includes(error.status)) throw error;
            }
          },
        });
      }
      if (job.operation === "files.refresh")
        return { files: await inventory(grantFor(job.input.source_id).root) };
      if (job.operation !== "accounts.save")
        throw new Error("Unsupported local operation.");
      const spec = await request(
        `/api/desktop/worker/jobs/${job.id}/plan?claim_token=${job.claim_token}`,
      );
      const grant = grantFor(spec.source_id);
      const backups = join(app.getPath("userData"), "backups");
      await mkdir(backups, { recursive: true });
      const saved = await replaceApproved(
        grant.root,
        spec,
        Buffer.from(spec.content, "base64"),
        async (bytes) => {
          if (state.device !== identity || !safeStorage.isEncryptionAvailable())
            throw new Error("PC connection changed.");
          await writeFile(
            join(backups, `${job.id}.bin`),
            safeStorage.encryptString(bytes.toString("base64")),
            { mode: 0o600 },
          );
          if (state.device !== identity)
            throw new Error("PC connection changed.");
        },
      );
      return { content: saved.toString("base64") };
    },
    pending: () => state.pending,
    savePending: async (pending) => {
      if (state.device === identity) {
        state.pending = pending;
        await persist();
      }
    },
    acknowledge: async (jobId) => {
      await unlink(
        join(app.getPath("userData"), "backups", `${jobId}.bin`),
      ).catch(() => {});
    },
  });
  const tick = () =>
    void worker.tick().catch((error) => {
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

function handle(channel, operation) {
  ipcMain.handle(channel, async (event, payload) => {
    validateSender(event, window, origin);
    return operation(payload);
  });
}

function setupBridge() {
  handle("desktop:status", async () => ({
    version: app.getVersion(),
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
  handle("desktop:pick-folder", async ({ tenant, sourceId }) => {
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
    const files = await inventory(root);
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
  });
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
