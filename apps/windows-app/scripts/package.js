/** Package the Windows installer: a release signed by its publisher, or, with
 * --unsigned, a release candidate unsigned on purpose, or, with --dev, Minkops Dev:
 * the local stack's companion, installed beside the production one.
 *
 * A release needs the code-signing certificate electron-builder reads
 * (WIN_CSC_LINK and WIN_CSC_KEY_PASSWORD, or CSC_LINK and CSC_KEY_PASSWORD)
 * and MINKOPS_WINDOWS_PUBLISHER, the certificate's common name. electron-builder
 * signs with it and pins that name in the update feed's settings, so an
 * installed companion accepts only updates signed by the same publisher. After
 * the build, Windows must trust the installer's signature, and the pinned name
 * must be the expected one; otherwise nothing is released.
 */
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseDn } from "builder-util-runtime";
import { load } from "js-yaml";

const CERTIFICATE = ["WIN_CSC_LINK", "CSC_LINK"];
const PASSWORD = ["WIN_CSC_KEY_PASSWORD", "CSC_KEY_PASSWORD"];
const given = (env, names) => names.map((name) => env[name]?.trim()).find(Boolean);

// Minkops Dev is another app: its own ID, install folder, shortcuts and profile, and no update feed, so it can
// neither replace the production companion nor be replaced by its updates.
const DEV = {
  appId: "com.minkops.desktop.dev", productName: "Minkops Dev",
  win: { executableName: "Minkops Dev" },
  nsis: { artifactName: "Minkops-Dev-Setup-${version}.${ext}" },
  publish: null,
};

/** The build environment, the publisher the installer must be signed by (null for a release candidate or the
 * dev channel), and how the build differs from the release's own configuration: exactly what electron-builder is
 * given, over the package.json "build" it reads itself. */
export function packaging({ argv, env }) {
  if (argv.includes("--unsigned") || argv.includes("--dev")) {
    const unsigned = { ...env, CSC_IDENTITY_AUTO_DISCOVERY: "false" };
    for (const name of [...CERTIFICATE, ...PASSWORD]) delete unsigned[name];
    return { env: unsigned, publisher: null, config: argv.includes("--dev") ? DEV : {} };
  }
  const publisher = env.MINKOPS_WINDOWS_PUBLISHER?.trim();
  if (!given(env, CERTIFICATE) || !given(env, PASSWORD) || !publisher)
    throw new Error("A release installer is signed. Set WIN_CSC_LINK, WIN_CSC_KEY_PASSWORD and MINKOPS_WINDOWS_PUBLISHER "
      + "(the certificate's common name), or pass --unsigned for a release candidate.");
  return { env: { ...env }, publisher, config: {} };
}

/** Why a signed build must not be released, or null when Windows trusts it and updates check its publisher. */
export function verdict(signature, updateSettings, publisher) {
  if (signature.status !== "Valid") return `The installer is not validly signed (${signature.status}).`;
  const signer = signature.subject ? parseDn(signature.subject).get("CN") : null;
  if (signer !== publisher) return `The installer is signed by ${signer}, not ${publisher}.`;
  // electron-updater reads the same file and refuses updates signed by anyone not listed.
  const pinned = [load(updateSettings)?.publisherName ?? []].flat();
  if (!pinned.includes(publisher)) return "Installed companions' updates would not check their publisher.";
  return null;
}

function authenticode(file) {
  const script = "$s=Get-AuthenticodeSignature -LiteralPath $env:MINKOPS_INSTALLER; "
    + "ConvertTo-Json -Compress @{status=[string]$s.Status; subject=$s.SignerCertificate.Subject}";
  const result = spawnSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script],
    { env: { ...process.env, MINKOPS_INSTALLER: file }, encoding: "utf8" });
  if (result.status !== 0) throw new Error("Windows could not read the installer's signature.");
  return JSON.parse(result.stdout);
}

async function main() {
  if (process.platform !== "win32") throw new Error("Package the Windows installer on Windows.");
  const { env, publisher, config } = packaging({ argv: process.argv.slice(2), env: process.env });
  // The programmatic build reads signing settings from the process environment.
  for (const name of Object.keys(process.env)) if (!(name in env)) delete process.env[name];
  Object.assign(process.env, env);
  const { build, Platform, Arch } = await import("electron-builder");
  // electron-builder reads the release's own configuration (package.json "build") and lays `config`, this build's
  // differences, over it. Passed the release's configuration again, it would merge the publish list into its own
  // first entry and refuse it (tests/package.test.js).
  await build({ targets: Platform.WINDOWS.createTarget(["nsis"], Arch.x64), config });
  const { version } = JSON.parse(await readFile("package.json", "utf8"));
  const installer = resolve("release", `Minkops${config === DEV ? "-Dev" : ""}-Setup-${version}.exe`);
  if (config === DEV) {
    console.log(`${installer} is Minkops Dev: unsigned, for the local stack at http://127.0.0.1:3000, with no updates.`);
    return;
  }
  if (!publisher) {
    console.warn(`${installer} is an unsigned release candidate: Windows SmartScreen warns on first install, `
      + "and its updates do not check their publisher. Its release notes must say so.");
    return;
  }
  const settings = await readFile(join("release", "win-unpacked", "resources", "app-update.yml"), "utf8");
  const refusal = verdict(authenticode(installer), settings, publisher);
  if (refusal) throw new Error(`${refusal} Do not release ${installer}.`);
  console.log(`${installer} is signed by ${publisher}, and its updates must be too.`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
