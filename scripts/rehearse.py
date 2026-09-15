#!/usr/bin/env python3
"""Suspend the controller, verify backup restoration, then resume management."""
from datetime import datetime, timezone
import json
import subprocess
import sys
import time
from common import ROOT, Kubernetes, parser, write_evidence
from self_heal import ready


def acknowledged_suspension(resource):
    return (resource["spec"].get("suspend") is True
            and not resource["metadata"].get("deletionTimestamp")
            and resource.get("status", {}).get("phase") == "Suspended"
            and resource["metadata"]["generation"] == resource.get("status", {}).get("observedGeneration"))


def set_suspended(kube, resource, value):
    # A concurrent edit must fail the operation rather than be silently overwritten.
    patch = [{"op": "test", "path": "/metadata/resourceVersion", "value": resource["metadata"]["resourceVersion"]},
             {"op": "add", "path": "/spec/suspend", "value": value}]
    return json.loads(kube.run("patch", "redisdeployment", kube.args.resource,
                               "-n", kube.args.namespace, "--type=json", "-p", json.dumps(patch), "-o", "json"))


def main():
    cli = parser(__doc__)
    cli.add_argument("--timeout", type=int, default=7800, help="Maximum seconds to wait for an active convergence to finish")
    cli.add_argument("--evidence", default=str(ROOT / "evidence" / "backup-rehearsal.json"))
    args = cli.parse_args()
    kube = Kubernetes(args)
    original = kube.resource()
    if original["spec"].get("suspend") or original["metadata"].get("deletionTimestamp") or not ready(original):
        raise ValueError("Backup rehearsal requires an active Ready resource")
    evidence = {"startedAt": datetime.now(timezone.utc).isoformat(),
                "resourceUID": original["metadata"]["uid"], "passed": False}
    write_evidence(args.evidence, evidence)
    suspended = set_suspended(kube, original, True)
    evidence["suspendedGeneration"] = suspended["metadata"]["generation"]
    write_evidence(args.evidence, evidence)
    uncertain_execution = False
    try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            current = kube.resource()
            if current["metadata"]["uid"] != evidence["resourceUID"] or current["metadata"]["generation"] != evidence["suspendedGeneration"]:
                raise ValueError("Resource changed while awaiting suspension")
            if acknowledged_suspension(current):
                break
            time.sleep(3)
        else:
            raise RuntimeError("Controller did not acknowledge suspension")
        evidence["suspensionAcknowledgedAt"] = datetime.now(timezone.utc).isoformat()
        write_evidence(args.evidence, evidence)
        try:
            result = kube.probe("rehearse")
        except (subprocess.TimeoutExpired, KeyboardInterrupt, RuntimeError):
            # kubectl termination cannot prove the remote workflow stopped.
            uncertain_execution = True
            raise
        evidence["result"] = result
        if not result.get("rehearsalPassed"):
            raise RuntimeError("Backup rehearsal failed")
        evidence["passed"] = True
    finally:
        current = kube.resource()
        if uncertain_execution:
            evidence["resumeBlocked"] = "Remote execution completion is uncertain; confirm it stopped before resuming"
        elif current["metadata"]["uid"] != evidence["resourceUID"] or current["metadata"]["generation"] != evidence["suspendedGeneration"]:
            evidence["resumeBlocked"] = "Resource changed during rehearsal; suspension was not overwritten"
        else:
            resumed = set_suspended(kube, current, False)
            evidence["resumedGeneration"] = resumed["metadata"]["generation"]
            evidence["resumedAt"] = datetime.now(timezone.utc).isoformat()
        write_evidence(args.evidence, evidence)
    if "resumeBlocked" in evidence:
        raise RuntimeError(evidence["resumeBlocked"])
    print("Backup rehearsal completed and controller resumed; evidence: " + args.evidence)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Backup rehearsal failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
