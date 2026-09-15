#!/usr/bin/env python3
"""Delete the exact owned Redis Droplet and verify autonomous service recovery."""
from datetime import datetime, timezone
import json
import re
import sys
import time
import uuid
from common import ROOT, Kubernetes, digitalocean, parser, private_environment, write_evidence, ready, wait_active_ready


def now():
    return datetime.now(timezone.utc).isoformat()


def owned_droplet(droplet, probe, profile, workers):
    """Fail closed before deletion: exact recorded ID/name/profile, never a worker."""
    if not droplet or str(droplet.get("id")) != str(probe.get("providerId")):
        raise ValueError("Recorded provider ID does not match live Droplet")
    if not re.fullmatch(r"[0-9]+", str(probe["providerId"])):
        raise ValueError("Invalid Droplet ID")
    if probe.get("profile") != profile or droplet.get("name") != profile or probe.get("name") != profile:
        raise ValueError("Droplet does not belong to the exact deployment profile")
    if str(droplet["id"]) in workers or any(str(tag).startswith("k8s:") for tag in droplet.get("tags", [])):
        raise ValueError("Refusing a Kubernetes worker")
    addresses = {n.get("ip_address") for n in droplet.get("networks", {}).get("v4", []) if n.get("type") == "public"}
    if probe.get("ip") not in addresses:
        raise ValueError("Recorded address differs from live Droplet")


def main():
    cli = parser(__doc__)
    cli.add_argument("--cluster-id", required=True)
    cli.add_argument("--profile", default="redis-doks-20260915")
    cli.add_argument("--timeout", type=int, default=2400)
    cli.add_argument("--delete-owned-droplet", action="store_true", required=True,
                     help="Required acknowledgement of this script's destructive test")
    cli.add_argument("--evidence", default=str(ROOT / "evidence" / "self-healing.json"))
    args = cli.parse_args()
    kube = Kubernetes(args)
    token = private_environment(args.private_env)["COLORS_PAR_DO_TOKEN"]
    cr = wait_active_ready(kube)
    before = kube.probe("health")
    if not before.get("healthy"):
        raise ValueError("Redis must be healthy before disruption")
    cluster = digitalocean(token, "GET", "kubernetes/clusters/" + args.cluster_id)
    workers = {str(n["droplet_id"]) for p in cluster["kubernetes_cluster"]["node_pools"] for n in p["nodes"]}
    droplet = digitalocean(token, "GET", "droplets/" + before["providerId"])
    owned_droplet(droplet["droplet"] if droplet else None, before, args.profile, workers)
    marker_key, marker_value = "colors:self-heal:" + uuid.uuid4().hex, uuid.uuid4().hex
    if kube.probe("set-marker", marker_key, marker_value).get("marker") != marker_value:
        raise ValueError("Authenticated Redis SET/GET failed before disruption")
    evidence = {"startedAt": now(), "clusterId": args.cluster_id, "resourceUID": cr["metadata"]["uid"],
                "generation": cr["metadata"]["generation"], "before": before,
                "excludedWorkerIds": sorted(workers), "markerKey": marker_key, "markerValue": marker_value,
                "expectedDataRecovery": False}
    write_evidence(args.evidence, evidence)
    digitalocean(token, "DELETE", "droplets/" + before["providerId"])
    evidence["deleteAcceptedAt"] = now()
    write_evidence(args.evidence, evidence)
    deadline = time.monotonic() + args.timeout
    last_error = None
    while time.monotonic() < deadline:
        time.sleep(15)
        try:
            current = kube.resource()
            if current["metadata"]["uid"] != evidence["resourceUID"] or current["metadata"]["generation"] != evidence["generation"]:
                raise ValueError("Desired state changed during recovery test")
            after = kube.probe("health")
            if after["providerId"] == before["providerId"] or not after.get("healthy") or not ready(current):
                continue
            live = digitalocean(token, "GET", "droplets/" + after["providerId"])
            owned_droplet(live["droplet"] if live else None, after, args.profile, workers)
            if digitalocean(token, "GET", "droplets/" + before["providerId"]) is not None:
                raise ValueError("Original Droplet still exists")
            evidence.update(recoveredAt=now(), after=after,
                            priorMarkerSurvived=kube.probe("get-marker", marker_key).get("marker") == marker_value)
            recovered_value = uuid.uuid4().hex
            evidence["authenticatedWriteReadPassed"] = kube.probe("set-marker", marker_key, recovered_value).get("marker") == recovered_value
            if not evidence["authenticatedWriteReadPassed"]:
                raise ValueError("Replacement write/read failed")
            evidence["passed"] = True
            write_evidence(args.evidence, evidence)
            print("Service recovery verified; evidence: " + args.evidence)
            return
        except ValueError:
            raise
        except Exception as error:
            last_error = type(error).__name__
    evidence.update(passed=False, timedOutAt=now(), lastErrorType=last_error)
    write_evidence(args.evidence, evidence)
    raise RuntimeError("Recovery timed out; inspect recorded evidence and controller status")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Self-healing test failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
