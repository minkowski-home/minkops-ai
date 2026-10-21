"""Client procedures layer over the core without replacing its runtime contract."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from jsonschema import ValidationError

from minkops_platform.installation import load_solution
from minkops_platform.resources import REPOSITORY_ROOT


class ClientVariantTests(TestCase):
    def test_a_client_procedure_extends_the_instructions_pinned_with_both_versions_and_adds_no_resources(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            shutil.copytree(REPOSITORY_ROOT / "employees", root / "employees")
            shutil.copytree(REPOSITORY_ROOT / "solutions/mock-client", root / "solutions/client-a")
            directory = root / "solutions/client-a/employees/accounts-desk"
            binding = json.loads((directory / "binding.json").read_text())
            binding["employee"] = {"name": "Client A Accounts"}
            entry = next(w for w in binding["workflows"] if w["key"] == "statement-entry")
            entry["variant"] = "variant.json"
            (directory / "binding.json").write_text(json.dumps(binding))
            variant_dir = directory / "workflows/statement-entry"
            variant_dir.mkdir(parents=True)
            (variant_dir / "client.md").write_text("Client A: book both legs of a NEFT return.")
            (variant_dir / "variant.json").write_text(json.dumps(
                {"version": "1.2.0", "instructions": "client.md", "defaults": {"review_mode": "only_exceptions"}}))
            installed = load_solution(root, "client-a")
            definition = installed.workflows["statement-entry"]
            bundle = definition.session_bundle
            self.assertEqual(installed.employees[0].metadata["name"], "Client A Accounts")
            self.assertTrue(bundle["instructions"].endswith(
                "## Client procedure\n\nClient A: book both legs of a NEFT return."))
            self.assertEqual(bundle["variant"], {"solution": "client-a", "core_version": "1.0.0", "version": "1.2.0"})
            self.assertNotIn("---", bundle["instructions"].split("\n", 1)[0])  # the skill manifest is not sent
            self.assertEqual(installed.bindings["statement-entry"]["defaults"]["review_mode"], "only_exceptions")
            self.assertEqual(installed.bindings["statement-entry"]["solution"], "client-a")
            core = (root / "employees/accounts-desk/workflows/statement-entry/SKILL.md").read_text()
            self.assertNotIn("Client A:", core)
            (variant_dir / "variant.json").write_text(json.dumps({"version": "1.2.0", "resources": ["client.md"]}))
            with self.assertRaisesRegex(ValidationError, "resources"):
                load_solution(root, "client-a")

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
