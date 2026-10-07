/** Production origin is a release setting, never supplied by a web page. */
export function trustedOrigin(value, development = false) {
  const url = new URL(value);
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    (url.protocol !== "https:" &&
      !(
        development &&
        url.protocol === "http:" &&
        ["localhost", "127.0.0.1"].includes(url.hostname)
      ))
  ) {
    throw new Error("Configure a trusted HTTPS Minkops application URL.");
  }
  return url.origin;
}

export function validateSender(event, window, origin) {
  if (
    !window ||
    event.sender !== window.webContents ||
    event.senderFrame !== window.webContents.mainFrame ||
    new URL(event.senderFrame.url).origin !== origin
  )
    throw new Error("This page cannot access the desktop companion.");
}

/** Lost local state needs a fresh explicit grant. A known grant cannot silently
 * switch to another folder; approved saves still verify server before/after hashes. */
export function validateFolderReconnect(previous, root, ownerId) {
  if (previous && (previous.owner_id !== ownerId || previous.root !== root)) {
    throw new Error(
      "Choose the original folder, or connect this folder as a new source.",
    );
  }
}
