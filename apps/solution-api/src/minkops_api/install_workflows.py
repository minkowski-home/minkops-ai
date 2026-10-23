"""Thin administrative CLI over repository composition services."""

import argparse
import os
from datetime import datetime, timedelta

import psycopg

from minkops_api.auth import link
from minkops_platform.errors import ServiceError
from minkops_platform.installation import install, load_solution, provision_tenant
from minkops_platform.members import INVITATION_DAYS
from minkops_platform.resources import REPOSITORY_ROOT


def invitation_expiry():
    return datetime.now() + timedelta(days=INVITATION_DAYS)


def main():
    parser = argparse.ArgumentParser(description="Validate or install a repository solution.")
    parser.add_argument("solution")
    parser.add_argument(
        "--actor-email",
        help="With --create-tenant, the workspace's first admin, sent a sign-up link; otherwise, optionally, the "
             "workspace admin the installation is attributed to",
    )
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--create-tenant", metavar="NAME",
        help="Create the solution's workspace, named NAME, and invite --actor-email as its first admin",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate against tenant state and roll back"
    )
    args = parser.parse_args()
    composition = load_solution(REPOSITORY_ROOT, args.solution)
    if args.validate_only:
        print(f"Validated {len(composition.workflows)} workflows for {composition.tenant_slug}.")
        return
    if args.create_tenant and not args.actor_email:
        parser.error("--create-tenant needs --actor-email: the first admin to invite")
    token = None
    try:
        with (
            psycopg.connect(os.environ["DATABASE_URL"]) as connection,
            connection.transaction(force_rollback=args.dry_run),
        ):
            if args.create_tenant:
                _, token = provision_tenant(connection, composition, name=args.create_tenant,
                                            admin_email=args.actor_email)
            # The operator installs a new workspace: its admin has no account until they follow the link.
            installed = install(connection, composition,
                                actor_email=None if args.create_tenant else args.actor_email)
    except ServiceError as error:
        # A refusal is the operator's to act on, such as a workspace another admin holds.
        parser.exit(1, f"{error}\n")
    print(
        f"{'Validated' if args.dry_run else 'Installed'}: {', '.join(installed) or '(empty composition)'}."
    )
    if args.create_tenant and not args.dry_run:
        # The operator sends the first admin their link; it is printed once and never stored.
        print(f"Send {args.actor_email} this sign-up link to join {args.create_tenant} as its admin. It works once, "
              f"until {invitation_expiry():%d %B %Y}:\n{link(f'/invite/{token}')}" if token
              else f"{args.actor_email} has already joined {args.create_tenant}; no link was needed.")


if __name__ == "__main__":
    main()
