"""Prepare the isolated release demo through verified first-party signup.

This does not seed fake users, platform-admin access, resource grants or tasks.
The owner must verify the email before the trusted mock-client is installed.
Generated credentials are written only to the operator's private state folder.
"""

import argparse
import json
import os
from pathlib import Path
import secrets
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg
from psycopg.conninfo import make_conninfo
from minkops_platform.installation import install, load_solution

ORIGIN = "https://minkops-ai-console.web.app"
ROOT = Path(__file__).resolve().parents[1]


def main(email, state_dir, install_workflows):
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    credentials_file = state_dir / "demo-owner.json"
    if not credentials_file.exists():
        if install_workflows:
            raise RuntimeError("Register and verify the owner first")
        credentials = {"email": email, "password": secrets.token_urlsafe(32)}
        with os.fdopen(os.open(credentials_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(credentials, stream)
    credentials = json.loads(credentials_file.read_text())
    if credentials["email"] != email:
        raise RuntimeError("State folder belongs to a different demo owner")
    database = json.loads((state_dir / "database.json").read_text())
    url = make_conninfo(host="127.0.0.1", port=5433, dbname="minkops", user="minkops_app", password=database["runtime_password"])
    with psycopg.connect(url) as connection:
        user = connection.execute("SELECT id,email_verified_at FROM users WHERE lower(email)=lower(%s)", (email,)).fetchone()
        if not install_workflows:
            if user:
                print("Owner already registered; no password change or email resend.")
                return
            request = Request(ORIGIN + "/api/auth/signup", data=json.dumps({**credentials, "name": "Minkops Demo Owner"}).encode(),
                              headers={"Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=60) as response:
                    if response.status != 201:
                        raise RuntimeError("Owner signup did not complete")
            except HTTPError as error:
                raise RuntimeError(f"Owner signup HTTP {error.code}; no credentials logged") from None
            print("Owner registered through production signup. Verify the email before installation.")
            return
        if not user or not user[1]:
            raise RuntimeError("Owner must verify the production email first")
        tenant = connection.execute("INSERT INTO tenants(slug,name) VALUES('mock-tenant','Minkops release demo') ON CONFLICT(slug) DO NOTHING RETURNING id").fetchone()
        if not tenant:
            tenant = connection.execute("SELECT id FROM tenants WHERE slug='mock-tenant'").fetchone()
            member = connection.execute("SELECT role FROM memberships WHERE tenant_id=%s AND user_id=%s", (tenant[0], user[0])).fetchone()
            if not member or member[0] != "admin":
                raise RuntimeError("Existing workspace is not owned by this demo administrator")
        else:
            connection.execute("INSERT INTO memberships(tenant_id,user_id,role) VALUES(%s,%s,'admin')", (tenant[0], user[0]))
        installed = install(connection, load_solution(ROOT, "mock-client"), actor_email=email)
    print(f"Installed {len(installed)} trusted demo workflows. No resource access granted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    main(args.email, args.state_dir, args.install)
