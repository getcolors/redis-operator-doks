#!/usr/bin/env python3
"""Manage only this development registry; never print Docker credentials."""
import argparse
import json
import os
from pathlib import Path
import shlex
from datetime import datetime, timezone

import requests

ROOT = Path(__file__).resolve().parents[1]
NAME = "colors-redis-20260915"


def token(path):
    for line in Path(path).read_text().splitlines():
        if line.startswith("export COLORS_PAR_DO_TOKEN="):
            return shlex.split(line.split("=", 1)[1], comments=True)[0]
    raise SystemExit("DigitalOcean token is missing")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["ensure", "credentials", "integrate", "check"])
    p.add_argument("--env-file", default=str(ROOT.parent / ".envrc.private"))
    p.add_argument("--auth-dir", default="/tmp/colors-redis-registry")
    p.add_argument("--cluster-id")
    args = p.parse_args()
    session = requests.Session()
    session.headers["Authorization"] = "Bearer " + token(args.env_file)

    def api(method, path, expected=(200,), **kwargs):
        r = session.request(method, "https://api.digitalocean.com/v2/" + path,
                            timeout=30, allow_redirects=False, **kwargs)
        if r.status_code not in expected:
            raise SystemExit(f"DigitalOcean {method} {path.split('?')[0]} returned {r.status_code}")
        return r

    registry = api("GET", "registry", expected=(200, 404))
    if registry.status_code == 404 and args.action == "ensure":
        registry = api("POST", "registry", expected=(201,),
                       json={"name": NAME, "region": "ams3", "subscription_tier_slug": "basic"})
        evidence = ROOT / "evidence/registry.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({"name": NAME, "region": "ams3", "tier": "basic",
                                       "created_at": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n")
    if registry.status_code != 200 and registry.status_code != 201:
        raise SystemExit("Create the task registry with ensure first")
    if registry.json().get("registry", {}).get("name") != NAME:
        raise SystemExit("Refusing to alter an unrelated existing registry")

    if args.action == "credentials":
        base = Path(args.auth_dir)
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        for kind, rw, expiry in [("push", "true", 3600), ("pull", "false", 2592000)]:
            directory = base / kind
            directory.mkdir(mode=0o700, exist_ok=True)
            response = api("GET", f"registry/docker-credentials?read_write={rw}&expiry_seconds={expiry}")
            config = response.json()
            path = directory / "config.json"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(config, f)
            print(f"Wrote private {kind} credentials to {path}; expires in {expiry}s")
    elif args.action == "integrate":
        if not args.cluster_id:
            raise SystemExit("--cluster-id is required")
        cluster = api("GET", "kubernetes/clusters/" + args.cluster_id).json()["kubernetes_cluster"]
        if cluster["name"] != "colors-doks-dev-20260915":
            raise SystemExit("Refusing to change an unrelated cluster")
        api("POST", "kubernetes/registry", expected=(204,), json={"cluster_uuids": [args.cluster_id]})
        print("Enabled native DOKS registry integration for the task cluster")
    else:
        print(f"Registry available: registry.digitalocean.com/{NAME}")


if __name__ == "__main__":
    main()
