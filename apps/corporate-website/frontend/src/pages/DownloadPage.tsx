import release from "../content/windows-release.json";
import { PageHero, Section } from "../layout/Section";
import SeoHead from "../layout/SeoHead";
import { ButtonLink } from "../ui/primitives";

export default function DownloadPage() {
  return (
    <>
      <SeoHead title="Download" description="Download the Minkops Windows release candidate." path="/download" />
      <PageHero
        eyebrow={`Windows · ${release.version} release candidate`}
        title="Your workflows, connected to your PC."
        lead="Connect selected folders and your local Tally installation to Source Discovery and Bill Entry. Sign in with your Minkops account; your workspace needs its workflows configured."
      >
        <a className="mk-btn mk-btn--primary mk-btn--lg" href={`/downloads/${release.filename}`} download>
          Download for Windows
        </a>
      </PageHero>
      <Section id="installation" narrow title="Before you install">
        <p>Windows 10 or 11, 64-bit. This release candidate is unsigned and Windows may display a publisher warning. Windows 11 installation is verified; Windows 10 testing is deferred.</p>
        <p>Open the intended companies in Tally and enable its local HTTP/XML service on port 9000. Source Discovery collects their masters and detailed vouchers for your chosen period. Excel discovery collects workbook structure and headers.</p>
        <p>Use a test company for your first run. Selected source context is processed by Minkops; your original files and Tally remain on your PC. Bill Entry asks for approval and verifies each save.</p>
        <ButtonLink to="https://app.minkops.com" variant="secondary">Open the web console</ButtonLink>
      </Section>
      <Section id="release" narrow title="Release details">
        <p>Version {release.version} · {Math.ceil(release.bytes / 1_000_000)} MB · Unsigned release candidate.</p>
        <p><a href={`/downloads/${release.filename}.sha256`} download>Download SHA-256 checksum</a> · <a href={`/downloads/release-notes-${release.version}.txt`}>Release notes</a></p>
        <p className="mk-release-hash">SHA-256: <code>{release.sha256}</code></p>
      </Section>
    </>
  );
}
