import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import private_environment
from self_heal import owned_droplet, ready


class SafetyTests(unittest.TestCase):
    def test_literal_credentials_do_not_execute_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "credentials"
            source.write_text("export COLORS_PAR_DO_TOKEN='test-token'\nexport UNRELATED_SECRET='ignore'\n")
            self.assertEqual({"COLORS_PAR_DO_TOKEN": "test-token"}, private_environment(source))
            source.write_text("export COLORS_PAR_DO_TOKEN='$(touch secret)'\n")
            with self.assertRaises(ValueError):
                private_environment(source)

    def test_deletion_requires_owned_nonworker_identity(self):
        probe = {"providerId": "123", "profile": "redis-dev", "name": "redis-dev", "ip": "1.2.3.4"}
        droplet = {"id": 123, "name": "redis-dev", "tags": [], "networks": {"v4": [{"type": "public", "ip_address": "1.2.3.4"}]}}
        owned_droplet(droplet, probe, "redis-dev", {"456"})
        for changed, workers in [(dict(droplet, id=456), set()), (dict(droplet, name="foreign"), set()),
                                  (droplet, {"123"}), (dict(droplet, tags=["k8s:worker"]), set())]:
            with self.assertRaises(ValueError):
                owned_droplet(changed, probe, "redis-dev", workers)

    def test_stale_ready_does_not_authorize_disruption(self):
        cr = {"metadata": {"generation": 2}, "status": {"observedGeneration": 1, "conditions": [{"type": "Ready", "status": "True"}]}}
        self.assertFalse(ready(cr))
        cr["status"]["observedGeneration"] = 2
        self.assertTrue(ready(cr))


if __name__ == "__main__":
    unittest.main()
