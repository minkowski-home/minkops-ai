"""Repository boundaries: shared packages stay usable without the web application,
and every tracked path resolves identically on case-sensitive and case-insensitive
file systems."""

import ast
import hashlib
import importlib
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path, PurePosixPath
from unittest import TestCase, skipUnless

from minkops_platform.resources import REPOSITORY_ROOT

# Import specifiers omit these extensions, so `./RunSettings` and `./runSettings`
# name the same module on macOS/Windows even when the files differ by extension.
MODULE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}


def case_collisions(paths):
    """Groups of tracked paths or module specifiers that differ only by case."""
    groups = defaultdict(set)
    for path in map(PurePosixPath, paths):
        groups[str(path).lower()].add(str(path))
        if path.suffix in MODULE_SUFFIXES:
            groups[f"module:{path.with_suffix('')}".lower()].add(str(path.with_suffix("")))
    return sorted(sorted(group) for group in groups.values() if len(group) > 1)


class RepositoryLayoutTests(TestCase):
    def test_detects_module_names_that_differ_only_by_case(self):
        self.assertEqual(
            case_collisions(["web/RunSettings.tsx", "web/runSettings.ts", "web/api.ts"]),
            [["web/RunSettings", "web/runSettings"]],
        )
        self.assertEqual(case_collisions(["a/README.md", "b/readme.md", "a/x.ts"]), [])

    @skipUnless(shutil.which("git") and (REPOSITORY_ROOT / ".git").exists(), "needs a git checkout")
    def test_no_tracked_paths_differ_only_by_case(self):
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=REPOSITORY_ROOT, check=True, capture_output=True
        ).stdout.decode().split("\0")
        self.assertEqual(case_collisions(filter(None, tracked)), [])


class PackageBoundaryTests(TestCase):
    def test_shared_services_import_without_web_application_dependencies(self):
        for name in (
            "minkops_platform.desktop",
            "minkops_platform.attention",
            "minkops_platform.accounts.attention",
            "minkops_platform.accounts.service",
            "minkops_platform.accounts.repository",
            "minkops_platform.accounts.checks",
            "minkops_platform.accounts.catalog",
            "minkops_platform.accounts.agent",
            "minkops_platform.accounts.worker",
            "minkops_platform.runtime.openai_hosted",
            "minkops_platform.runtime.workflow",
            "minkops_platform.runtime.bundles",
            "minkops_platform.runtime.lifecycle",
            "minkops_platform.accounts.run_store",
            "minkops_connectors.excel",
        ):
            module = importlib.import_module(name)
            tree = ast.parse(Path(module.__file__).read_text())
            for node in ast.walk(tree):
                names = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
                self.assertFalse(any(n.startswith(("minkops_api", "fastapi")) for n in names), name)
                if name.startswith("minkops_connectors"):
                    self.assertFalse(any(n.startswith("minkops_platform") for n in names), name)

    def test_versioned_workflow_prompts_match_reviewed_schema_context_contract(self):
        from minkops_platform.accounts.agent import bill_prompt, discovery_prompt

        self.assertEqual(
            hashlib.sha256(discovery_prompt().encode()).hexdigest(),
            "1689b7e187dc39ff7fbc443543dfd928994b88355d8b8233545bc460ae76852e",
        )
        self.assertEqual(
            hashlib.sha256(bill_prompt().encode()).hexdigest(),
            "79e8c1597a3f6829bad1c4b7a252c965bc444927ba73d082cc0d82ae754cf3c9",
        )
