"""Publication must reject a bad installer before making any cloud mutation."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))
spec = importlib.util.spec_from_file_location("hosting_release", INFRA / "deploy_hosting.py")
hosting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosting)


@pytest.mark.parametrize("problem", ["missing", "size", "digest", "symlink"])
def test_invalid_installer_cannot_create_a_hosting_version(tmp_path, monkeypatch, problem):
    build = tmp_path / "site/dist"
    build.mkdir(parents=True)
    (build / "index.html").write_text("release page")
    content = tmp_path / "site/src/content"
    content.mkdir(parents=True)
    payload = b"reviewed installer"
    manifest = {"filename": "setup.exe", "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(), "unsigned": True}
    (content / "windows-release.json").write_text(json.dumps(manifest))
    (tmp_path / "firebase.json").write_text(json.dumps({"hosting": [
        {"target": "corporate", "public": "site/dist"}]}))
    monkeypatch.setattr(hosting, "__file__", str(tmp_path / "deploy_hosting.py"))

    def forbidden_api(*args):
        pytest.fail("Invalid artifacts must never reach the cloud client")

    monkeypatch.setattr(hosting, "GoogleApi", forbidden_api)
    installer = tmp_path / "installer.exe"
    if problem == "size":
        installer.write_bytes(b"short")
    elif problem == "digest":
        installer.write_bytes(b"x" * len(payload))
    elif problem == "symlink":
        target = tmp_path / "actual.exe"
        target.write_bytes(payload)
        installer.symlink_to(target)
    with pytest.raises(RuntimeError, match="installer|Installer"):
        hosting.deploy("corporate", installer)
    assert not (build / "downloads").exists()


def release_tree(tmp_path, monkeypatch, payload=b"reviewed installer", publisher=None):
    """A corporate build with a manifest-matching installer and its update feed.

    Without a `publisher`, the manifest declares an unsigned release candidate.
    """
    import base64

    build = tmp_path / "site/dist"
    build.mkdir(parents=True)
    (build / "index.html").write_text("release page")
    content = tmp_path / "site/src/content"
    content.mkdir(parents=True)
    manifest = {"version": "0.7.0", "filename": "Minkops-Setup-0.7.0.exe", "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                **({"publisher": publisher} if publisher else {"unsigned": True})}
    (content / "windows-release.json").write_text(json.dumps(manifest))
    (tmp_path / "firebase.json").write_text(json.dumps({"hosting": [{"target": "corporate", "public": "site/dist"}]}))
    monkeypatch.setattr(hosting, "__file__", str(tmp_path / "deploy_hosting.py"))
    installer = tmp_path / "release/Minkops-Setup-0.7.0.exe"
    installer.parent.mkdir()
    installer.write_bytes(payload)
    sha512 = base64.b64encode(hashlib.sha512(payload).digest()).decode()
    feed = tmp_path / "release/latest.yml"
    feed.write_text(f"version: 0.7.0\nfiles:\n  - url: Minkops-Setup-0.7.0.exe\n    sha512: {sha512}\n"
                    f"    size: {len(payload)}\npath: Minkops-Setup-0.7.0.exe\nsha512: {sha512}\n"
                    "releaseDate: '2026-10-14T00:00:00.000Z'\n")
    (tmp_path / "release/Minkops-Setup-0.7.0.exe.blockmap").write_bytes(b"blockmap")
    return build, installer, feed


@pytest.mark.parametrize("problem", ["missing", "version", "path", "sha512"])
def test_an_update_feed_must_describe_exactly_the_released_installer(tmp_path, monkeypatch, problem):
    build, installer, feed = release_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(hosting, "GoogleApi", lambda *args: pytest.fail("Invalid feeds never reach the cloud"))
    if problem == "missing":
        feed.unlink()
    else:
        text = feed.read_text()
        feed.write_text({"version": text.replace("version: 0.7.0", "version: 0.7.1"),
                         "path": text.replace("path: Minkops", "path: Other"),
                         "sha512": text.replace("\nsha512: ", "\nsha512: AAAA")}[problem])
    with pytest.raises(RuntimeError, match="update feed"):
        hosting.deploy("corporate", installer)
    assert not (build / "downloads").exists()


def test_a_valid_feed_is_published_next_to_the_installer(tmp_path, monkeypatch):
    build, installer, feed = release_tree(tmp_path, monkeypatch)

    class StopBeforeUploadError(Exception):
        pass

    def stop(*args):
        raise StopBeforeUploadError()

    monkeypatch.setattr(hosting, "GoogleApi", stop)
    with pytest.raises(StopBeforeUploadError):
        hosting.deploy("corporate", installer)
    downloads = build / "downloads"
    assert (downloads / "Minkops-Setup-0.7.0.exe").read_bytes() == installer.read_bytes()
    assert (downloads / "latest.yml").read_text() == feed.read_text()
    assert (downloads / "Minkops-Setup-0.7.0.exe.blockmap").read_bytes() == b"blockmap"


@pytest.mark.parametrize("problem", ["url", "digest", "size", "empty", "malformed", "duplicate", "duplicate_same", "scalar"])
def test_updater_file_entries_are_checked_before_any_publication(tmp_path, monkeypatch, problem):
    build, installer, feed = release_tree(tmp_path, monkeypatch)
    text = feed.read_text()
    changed = {
        "url": text.replace("  - url: Minkops", "  - url: Other"),
        "digest": text.replace("    sha512: ", "    sha512: AAAA"),
        "size": text.replace(f"    size: {installer.stat().st_size}", "    size: 1"),
        "empty": text[:text.index("files:")] + "files: []\n" + text[text.index("\npath:"):],
        "malformed": text + "invalid: [\n",
        "duplicate": text + "files: []\n",
        "duplicate_same": text + "version: 0.7.0\n",
        "scalar": "not a feed\n",
    }[problem]
    feed.write_text(changed)
    monkeypatch.setattr(hosting, "GoogleApi", lambda *args: pytest.fail("Invalid file entries reached publication"))
    with pytest.raises(RuntimeError, match="update feed"):
        hosting.deploy("corporate", installer)
    assert not (build / "downloads").exists()


def signed_installer(common_name, ends_in_zero=False):
    """A minimal Windows executable carrying an Authenticode-shaped PKCS#7 signature by `common_name`.

    With `ends_in_zero`, the signature's last byte is 0, as about one real signature in 256 is.
    """
    import datetime
    import struct

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import pkcs7
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                   .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
                   .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=False)
                   .sign(key, hashes.SHA256()))
    builder = pkcs7.PKCS7SignatureBuilder().set_data(b"installer digest").add_signer(certificate, key, hashes.SHA256())
    signature = builder.sign(serialization.Encoding.DER, [])
    while ends_in_zero and signature[-1] != 0:  # ECDSA signatures differ each time
        signature = builder.sign(serialization.Encoding.DER, [])
    headers = bytearray(64 + 4 + 20 + 240)
    headers[:2], headers[0x3C:0x40] = b"MZ", (64).to_bytes(4, "little")
    headers[64:68] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", headers, 68, 0x8664, 0, 0, 0, 0, 240, 0x22)
    struct.pack_into("<H", headers, 88, 0x20B)  # PE32+
    entry = bytes(signature) + b"\0" * (-len(signature) % 8)
    struct.pack_into("<II", headers, 88 + 112 + 4 * 8, len(headers), 8 + len(entry))  # the security directory
    return bytes(headers) + struct.pack("<IHH", 8 + len(entry), 0x0200, 2) + entry


@pytest.mark.parametrize(("signer", "refusal"), [
    (None, "is not signed by Example Publisher Ltd"),
    ("Someone Else", "is not signed by Example Publisher Ltd"),
])
def test_a_signed_release_ships_only_an_installer_its_publisher_signed(tmp_path, monkeypatch, signer, refusal):
    payload = signed_installer(signer) if signer else b"reviewed installer"
    build, installer, feed = release_tree(tmp_path, monkeypatch, payload=payload, publisher="Example Publisher Ltd")
    monkeypatch.setattr(hosting, "GoogleApi", lambda *args: pytest.fail("A wrongly signed release reached publication"))
    with pytest.raises(RuntimeError, match=refusal):
        hosting.deploy("corporate", installer)
    assert not (build / "downloads").exists()


def test_a_signature_that_ends_in_a_zero_byte_still_names_its_signer(tmp_path):
    installer = tmp_path / "setup.exe"
    installer.write_bytes(signed_installer("Example Publisher Ltd", ends_in_zero=True))
    assert hosting.authenticode_publisher(installer) == "Example Publisher Ltd"


def test_an_installer_signed_by_its_publisher_is_published(tmp_path, monkeypatch):
    payload = signed_installer("Example Publisher Ltd")
    build, installer, feed = release_tree(tmp_path, monkeypatch, payload=payload, publisher="Example Publisher Ltd")
    assert hosting.authenticode_publisher(installer) == "Example Publisher Ltd"

    class StopBeforeUploadError(Exception):
        pass

    def stop(*args):
        raise StopBeforeUploadError()

    monkeypatch.setattr(hosting, "GoogleApi", stop)
    with pytest.raises(StopBeforeUploadError):
        hosting.deploy("corporate", installer)
    assert (build / "downloads" / "Minkops-Setup-0.7.0.exe").read_bytes() == payload
