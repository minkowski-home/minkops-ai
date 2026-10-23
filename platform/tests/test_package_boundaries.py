"""Repository boundaries: shared packages stay usable without the web application,
and every tracked path resolves identically on case-sensitive and case-insensitive
file systems."""

import ast
import shutil
import subprocess
from collections import defaultdict
from pathlib import PurePosixPath
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


# Shared packages and what each must never import.
FORBIDDEN_IMPORTS = {
    "platform/src/minkops_platform": ("minkops_api", "fastapi", "starlette"),
    "connectors/src/minkops_connectors": ("minkops_api", "fastapi", "starlette", "minkops_platform"),
}


def imported_names(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


class PackageBoundaryTests(TestCase):
    def test_every_shared_module_imports_without_the_web_application(self):
        """The worker, companion jobs and connectors run without the API process;
        dependencies flow apps -> platform -> connectors, never back."""
        checked = 0
        for package, forbidden in FORBIDDEN_IMPORTS.items():
            for path in sorted((REPOSITORY_ROOT / package).rglob("*.py")):
                checked += 1
                for name in imported_names(path):
                    with self.subTest(module=str(path.relative_to(REPOSITORY_ROOT)), imports=name):
                        self.assertFalse(name.startswith(forbidden))
        self.assertGreater(checked, 30)  # the scan found the packages, not an empty glob
