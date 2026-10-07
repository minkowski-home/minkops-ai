"""Thin administrative CLI over repository composition services."""

import argparse
import os

import psycopg
from minkops_platform.installation import install, load_solution
from minkops_platform.resources import REPOSITORY_ROOT


def main():
    parser = argparse.ArgumentParser(description="Validate or install a repository solution.")
    parser.add_argument("solution")
    parser.add_argument(
        "--actor-email", help="Existing verified administrator; required for installation"
    )
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate against tenant state and roll back"
    )
    args = parser.parse_args()
    composition = load_solution(REPOSITORY_ROOT, args.solution)
    if args.validate_only:
        print(f"Validated {len(composition.workflows)} workflows for {composition.tenant_slug}.")
        return
    if not args.actor_email:
        parser.error("--actor-email is required for tenant installation")
    with (
        psycopg.connect(os.environ["DATABASE_URL"]) as connection,
        connection.transaction(force_rollback=args.dry_run),
    ):
        installed = install(connection, composition, actor_email=args.actor_email)
    print(
        f"{'Validated' if args.dry_run else 'Installed'}: {', '.join(installed) or '(empty composition)'}."
    )


if __name__ == "__main__":
    main()
