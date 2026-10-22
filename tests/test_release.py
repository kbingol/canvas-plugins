"""Exercise the deliverable, including archive portability and reproducibility."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from package import build
from validate import contained_file


class ReleaseChecks(unittest.TestCase):
    def test_archive_is_reproducible_and_contains_installable_root_and_license(self):
        with tempfile.TemporaryDirectory() as directory:
            first = build(Path(directory) / "first")
            second = build(Path(directory) / "second")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first.with_suffix(".zip.sha256").read_text().split()[0],
                             hashlib.sha256(first.read_bytes()).hexdigest())
            with zipfile.ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("plugin.json", archive.namelist())
                self.assertIn("mcp.json", archive.namelist())
                self.assertEqual(archive.read("LICENSE"), (ROOT / "LICENSE").read_bytes())
                self.assertEqual(json.loads(archive.read("plugin.json"))["name"], "canvas")
                self.assertIn("skills/setup/SKILL.md", archive.namelist())
                for name in archive.namelist():
                    self.assertFalse(name.startswith(("/", "\\")))
                    self.assertNotIn("..", Path(name).parts)
                    self.assertNotIn(".git", Path(name).parts)

    def test_resources_cannot_reference_a_parent_or_absolute_path(self):
        package = ROOT / "plugins/canvas"
        for value in ("../LICENSE", "./../LICENSE", str(ROOT / "LICENSE"), "./skills/../../LICENSE"):
            with self.subTest(path=value), self.assertRaises(ValueError):
                contained_file(package, value)


if __name__ == "__main__":
    unittest.main()
