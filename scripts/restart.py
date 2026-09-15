#!/usr/bin/env python3
"""Restart one idle operator without overlapping controller processes."""
from datetime import datetime, timezone
import json
import sys
import time
from common import ROOT, Kubernetes, parser, write_evidence
from self_heal import ready


def main():
    cli = parser(__doc__)
    cli.add_argument("--evidence", default=str(ROOT / "evidence" / "controller-restart.json"))
    args = cli.parse_args()
    kube = Kubernetes(args)
    cr = kube.resource()
    if not ready(cr) or cr["spec"].get("suspend") or cr["metadata"].get("deletionTimestamp"):
        raise ValueError("Restart test requires an active Ready deployment")
    before = kube.probe("health")
    if not before.get("healthy"):
        raise ValueError("Redis is unhealthy")
    deployment = json.loads(kube.run("get", "deployment", args.deployment, "-n", args.namespace, "-o", "json"))
    if deployment["spec"]["replicas"] != 1:
        raise ValueError("Restart test requires exactly one controller replica")
    evidence = {"startedAt": datetime.now(timezone.utc).isoformat(), "before": before,
                "resourceUID": cr["metadata"]["uid"], "generation": cr["metadata"]["generation"]}
    write_evidence(args.evidence, evidence)
    kube.run("scale", "deployment/" + args.deployment, "-n", args.namespace, "--replicas=0")
    # Do not force deletion or start another controller while the old process may run.
    deadline = time.monotonic() + 7800
    while time.monotonic() < deadline:
        pods = json.loads(kube.run("get", "pods", "-n", args.namespace,
                                   "-l", "app=" + args.deployment, "-o", "json"))["items"]
        if not pods:
            break
        time.sleep(5)
    else:
        raise RuntimeError("Old controller did not stop; intentionally leaving replicas at zero")
    kube.run("scale", "deployment/" + args.deployment, "-n", args.namespace, "--replicas=1")
    kube.run("rollout", "status", "deployment/" + args.deployment, "-n", args.namespace, "--timeout=600s", timeout=630)
    # Allow the restarted controller to observe at least one scheduled reconciliation.
    time.sleep(45)
    after, current = kube.probe("health"), kube.resource()
    if not after.get("healthy") or before["providerId"] != after["providerId"] or not ready(current):
        raise RuntimeError("Restart did not preserve healthy infrastructure")
    if not before.get("convergenceRecordModifiedMs") or before["convergenceRecordModifiedMs"] != after.get("convergenceRecordModifiedMs"):
        raise RuntimeError("Restart unexpectedly ran another convergence workflow")
    if current["metadata"]["uid"] != evidence["resourceUID"] or current["metadata"]["generation"] != evidence["generation"]:
        raise RuntimeError("Desired state changed during restart test")
    evidence.update(passed=True, after=after, completedAt=datetime.now(timezone.utc).isoformat())
    write_evidence(args.evidence, evidence)
    print("Controller restart preserved Redis; evidence: " + args.evidence)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Restart test failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
