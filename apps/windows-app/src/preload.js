import { contextBridge, ipcRenderer } from "electron";

// Individual calls, never raw IPC, filesystem paths, shell access or credentials.
contextBridge.exposeInMainWorld(
  "minkopsDesktop",
  Object.freeze({
    version: 1,
    schemaOnlyFolders: true,
    status: () => ipcRenderer.invoke("desktop:status"),
    connect: (tenant) => ipcRenderer.invoke("desktop:connect", tenant),
    disconnect: () => ipcRenderer.invoke("desktop:disconnect"),
    saveCatalog: (tenant, discoveryId) => ipcRenderer.invoke("desktop:save-catalog", {tenant, discoveryId}),
    pickFolder: (tenant, sourceId, schemaOnly = false) =>
      ipcRenderer.invoke("desktop:pick-folder", { tenant, sourceId, schemaOnly }),
    bindFolder: (tenant, sourceId, grantId) =>
      ipcRenderer.invoke("desktop:bind-folder", { tenant, sourceId, grantId }),
    refreshFolder: (tenant, sourceId) =>
      ipcRenderer.invoke("desktop:refresh-folder", { tenant, sourceId }),
  }),
);
