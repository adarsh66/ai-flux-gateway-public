"""Offline launcher safety checks; never queues a cloud build."""
import tempfile
from pathlib import Path
import unittest

from scripts.deployment import customer_catalog_validate as validation


class CustomerCatalogValidationTests(unittest.TestCase):
    def test_acr_null_output_images_are_not_publication(self):
        for images in (None, [], [None]):
            self.assertTrue(validation.no_published_images(images))
        for images in ([{"digest": "sha256:example"}], [{}], ["image:tag"], "unexpected"):
            self.assertFalse(validation.no_published_images(images))

    def test_only_bounded_no_push_command(self):
        args = validation.build_args()
        self.assertIn("--no-push", args)
        self.assertEqual(args[args.index("--timeout") + 1], "1800")
        self.assertEqual(args[args.index("--platform") + 1], "linux/amd64")
        self.assertNotIn("--image", args)
        self.assertNotIn("--no-wait", args)

    def test_curated_current_copy_sources_and_byte_hashes(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            manifest = validation.stage(folder)
            paths = {e["path"] for e in manifest["entries"]}
            self.assertTrue(validation.REQUIRED <= paths)
            self.assertFalse(any("node_modules" in p or "/dist/" in p or p.startswith("services/") for p in paths))
            for entry in manifest["entries"]:
                self.assertEqual(validation.portals.digest((folder / "context" / entry["path"]).read_bytes()), entry["sha256"])
            with self.assertRaises(FileExistsError):
                validation.stage(folder)

    def test_logs_redact_signed_urls_and_bearer_values(self):
        text = validation.redact("\x1b[32mOK\x1b[0m https://host/path?sig=sensitive Bearer abc.xyz.123")
        self.assertNotIn("sensitive", text)
        self.assertNotIn("abc.xyz", text)
        self.assertNotIn("\x1b", text)


if __name__ == "__main__":
    unittest.main()