"""Client procedures layer over the core without replacing its runtime contract."""

import json
import shutil
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase
from jsonschema import ValidationError

from minkops_platform.installation import load_solution
from minkops_platform.resources import REPOSITORY_ROOT
from minkops_platform.runtime.bundles import validate_snapshot


class ClientVariantTests(TestCase):
    def test_client_procedure_is_additive_pinned_and_isolated_from_core(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            shutil.copytree(REPOSITORY_ROOT / "employees", root / "employees")
            shutil.copytree(REPOSITORY_ROOT / "solutions/mock-client", root / "solutions/client-a")
            directory = root / "solutions/client-a/employees/accounts-desk"
            binding = json.loads((directory / "binding.json").read_text())
            binding["employee"] = {"name": "Client A Accounts"}
            binding["workflows"][0]["variant"] = "variant.json"
            variant_dir = directory / "workflows" / binding["workflows"][0]["key"]
            variant_dir.mkdir(parents=True)
            (variant_dir / "variant.json").write_text(
                json.dumps(
                    {
                        "version": "1.0.0",
                        "instructions": "client.md",
                        "defaults": {"discovery_depth": "structure"},
                    }
                )
            )
            (variant_dir / "client.md").write_text("Client A: explain mappings in plain language.")
            (directory / "binding.json").write_text(json.dumps(binding))
            installed = load_solution(root, "client-a")
            key = binding["workflows"][0]["key"]
            definition = installed.workflows[key]
            self.assertEqual(installed.employees[0].metadata["name"], "Client A Accounts")
            snapshot = validate_snapshot(definition.execution_snapshot)
            self.assertEqual(snapshot["variant"]["solution"], "client-a")
            self.assertEqual(snapshot["variant"]["version"], "1.0.0")
            self.assertIn("Client A:", snapshot["files"][snapshot["execution"]["instructions"]])
            self.assertIn("Client A:", definition.instructions)
            core = (root / "employees/accounts-desk/workflows" / key / "SKILL.md").read_text()
            self.assertNotIn("Client A:", core)
            self.assertEqual(installed.bindings[key]["solution"], "client-a")

    def test_variant_cannot_replace_handlers_schemas_or_escape_its_client_layer(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            shutil.copytree(REPOSITORY_ROOT / "employees", root / "employees")
            shutil.copytree(REPOSITORY_ROOT / "solutions/mock-client", root / "solutions/client-a")
            directory = root / "solutions/client-a/employees/accounts-desk"
            binding = json.loads((directory / "binding.json").read_text())
            binding["workflows"][0]["variant"] = "variant.json"
            (directory / "binding.json").write_text(json.dumps(binding))
            variant_dir = directory / "workflows" / binding["workflows"][0]["key"]
            variant_dir.mkdir(parents=True)
            for override in ({"handler": "unsafe"}, {"instructions": "../outside.md"}):
                (variant_dir / "variant.json").write_text(
                    json.dumps({"version": "1.0.0", **override})
                )
                with (
                    self.subTest(override=override),
                    self.assertRaises((ValueError, ValidationError)),
                ):
                    load_solution(root, "client-a")
