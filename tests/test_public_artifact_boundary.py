"""Public artifact boundary contract; synthetic CI, no private workspace reads."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class PublicArtifactBoundaryTests(unittest.TestCase):
    def test_release_manifest_excludes_runtime_private_data(self):
        names=json.loads((ROOT/"release_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(names)
        forbidden_prefixes=("data/","inbox/","logs/","backups/","downloads/",
                            ".env",".jira-",".python-path")
        for name in names:
            with self.subTest(path=name):
                normalized=name.replace("\\","/")
                # An empty tracked directory placeholder is not a runtime file.
                if normalized == "inbox/.gitkeep":
                    self.assertEqual((ROOT/name).stat().st_size, 0)
                    continue
                self.assertFalse(normalized.startswith(forbidden_prefixes))
                self.assertFalse(normalized.endswith((".zip",".sqlite3",".db",".pem",".key")))
                self.assertTrue((ROOT/name).is_file())
        self.assertEqual(len(names),len(set(names)))

    def test_public_ci_upload_allowlist_is_synthetic_only(self):
        workflow=(ROOT/".github/workflows/quality.yml").read_text(encoding="utf-8")
        self.assertIn("browser-synthetic-results",workflow)
        self.assertIn("path: browser-artifacts/",workflow)
        self.assertIn("CCON_BROWSER_ARTIFACTS: browser-artifacts",workflow)
        self.assertIn("python browser_e2e.py",workflow)
        self.assertNotIn("path: data/",workflow)
        self.assertNotIn("path: inbox/",workflow)
        self.assertNotIn("path: backups/",workflow)
        self.assertNotIn("path: logs/",workflow)
        self.assertNotIn("path: .coverage",workflow)


if __name__=="__main__":
    unittest.main()
