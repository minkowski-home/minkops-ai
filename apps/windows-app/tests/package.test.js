import test from "node:test";
import assert from "node:assert/strict";
import { packaging, verdict } from "../scripts/package.js";

const signing = {
  WIN_CSC_LINK: "C:\\keys\\release.pfx", WIN_CSC_KEY_PASSWORD: "secret",
  MINKOPS_WINDOWS_PUBLISHER: "Example Publisher Ltd",
};

test("a release is signed by the publisher it names", () => {
  const { env, publisher } = packaging({ argv: [], env: { PATH: "p", ...signing } });
  assert.equal(publisher, "Example Publisher Ltd");
  assert.equal(env.WIN_CSC_LINK, signing.WIN_CSC_LINK);
  // electron-builder's own variable names are accepted too.
  const shared = { CSC_LINK: "C:\\keys\\release.pfx", CSC_KEY_PASSWORD: "secret", MINKOPS_WINDOWS_PUBLISHER: "Example Publisher Ltd" };
  assert.equal(packaging({ argv: [], env: shared }).publisher, "Example Publisher Ltd");
});

test("a release without its certificate, password or publisher is refused, never built unsigned", () => {
  for (const missing of ["WIN_CSC_LINK", "WIN_CSC_KEY_PASSWORD", "MINKOPS_WINDOWS_PUBLISHER"])
    assert.throws(() => packaging({ argv: [], env: { ...signing, [missing]: " " } }), /--unsigned/);
});

test("a release candidate is unsigned on purpose, even where a certificate is at hand", () => {
  const { env, publisher } = packaging({ argv: ["--unsigned"], env: { PATH: "p", CSC_LINK: "x", CSC_KEY_PASSWORD: "y", ...signing } });
  assert.equal(publisher, null);
  for (const name of ["CSC_LINK", "WIN_CSC_LINK", "CSC_KEY_PASSWORD", "WIN_CSC_KEY_PASSWORD"]) assert.equal(env[name], undefined);
  // Nor is one picked from the Windows certificate store.
  assert.equal(env.CSC_IDENTITY_AUTO_DISCOVERY, "false");
  assert.equal(env.PATH, "p");
});

test("Minkops Dev is another app beside the production companion, unsigned and without updates", () => {
  const { env, publisher, config } = packaging({ argv: ["--dev"], env: { PATH: "p", ...signing } });
  assert.equal(publisher, null);
  assert.equal(env.WIN_CSC_LINK, undefined);
  // Its own ID and name give it its own install folder, shortcuts and uninstall entry.
  assert.deepEqual([config.appId, config.productName, config.win.executableName, config.nsis.artifactName],
    ["com.minkops.desktop.dev", "Minkops Dev", "Minkops Dev", "Minkops-Dev-Setup-${version}.${ext}"]);
  // No feed: neither does it update itself, nor can a production update replace it.
  assert.equal(config.publish, null);
  assert.deepEqual(packaging({ argv: ["--unsigned"], env: {} }).config, {});
});

test("a signed installer passes only when Windows trusts its signature and updates check the same publisher", () => {
  const subject = 'CN="Example Publisher, Ltd.", O="Example Publisher, Ltd.", L=Bengaluru, C=IN';
  const update = 'provider: generic\nurl: https://minkops.com/downloads/\npublisherName:\n  - "Example Publisher, Ltd."\n';
  assert.equal(verdict({ status: "Valid", subject }, update, "Example Publisher, Ltd."), null);
  assert.match(verdict({ status: "NotSigned", subject: null }, update, "Example Publisher, Ltd."), /not validly signed \(NotSigned\)/);
  assert.match(verdict({ status: "Valid", subject: "CN=Someone Else, C=IN" }, update, "Example Publisher, Ltd."),
    /signed by Someone Else, not Example Publisher, Ltd\./);
  assert.match(verdict({ status: "Valid", subject }, "provider: generic\n", "Example Publisher, Ltd."),
    /updates would not check their publisher/);
});
