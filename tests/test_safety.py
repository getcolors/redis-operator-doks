import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import private_environment, wait_active_ready
from self_heal import owned_droplet, ready
from rehearse import acknowledged_suspension


class SafetyTests(unittest.TestCase):
    def test_wait_active_ready_waits_for_current_generation(self):
        pending = {"metadata": {"generation": 2}, "spec": {}, "status": {"phase": "Reconciling"}}
        done = {"metadata": {"generation": 2}, "spec": {}, "status": {"observedGeneration": 2, "conditions": [{"type": "Ready", "status": "True"}]}}
        kube = Mock()
        kube.resource.side_effect = [pending, done]
        with patch("common.time.sleep"):
            self.assertEqual(done, wait_active_ready(kube))
        kube.resource.side_effect = None
        kube.resource.return_value = pending
        with self.assertRaises(RuntimeError):
            wait_active_ready(kube, timeout=0)
        kube.resource.return_value = dict(pending, spec={"suspend": True})
        with self.assertRaises(ValueError):
            wait_active_ready(kube)

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

    def test_suspend_request_alone_does_not_authorize_rehearsal(self):
        cr = {"metadata": {"generation": 2}, "spec": {"suspend": True}, "status": {"observedGeneration": 1, "phase": "Suspended"}}
        self.assertFalse(acknowledged_suspension(cr))
        cr["status"]["observedGeneration"] = 2
        self.assertTrue(acknowledged_suspension(cr))
        cr["metadata"]["deletionTimestamp"] = "now"
        self.assertFalse(acknowledged_suspension(cr))


if __name__ == "__main__":
    unittest.main()
