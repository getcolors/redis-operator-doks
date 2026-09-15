#!/usr/bin/env python3
"""Install the Redis operator and desired state into one explicit cluster."""
import base64
import ipaddress
import json
from pathlib import Path
import sys
import time
from common import ROOT, CREDENTIALS, Kubernetes, parser, private_environment


def main():
    cli = parser(__doc__)
    cli.add_argument("--image", required=True, help="Immutable controller image reference with @sha256 digest")
    registry_group = cli.add_mutually_exclusive_group(required=True)
    registry_group.add_argument("--registry-config", help="Private Docker config.json")
    registry_group.add_argument("--registry-secret", help="Existing pull Secret in the target namespace (for native registry integration)")
    cli.add_argument("--ssh-source", action="append", required=True, help="Allowed IPv4 /32; repeat for every worker and developer")
    cli.add_argument("--operator-root", default=str(ROOT.parent / "redis-operator"))
    cli.add_argument("--render-only", action="store_true", help="Print only the nonsecret RedisDeployment")
    args = cli.parse_args()
    if "@sha256:" not in args.image:
        raise ValueError("Pin the controller image by digest")
    sources = []
    for value in args.ssh_source:
        network = ipaddress.ip_network(value, strict=True)
        if network.version != 4 or network.prefixlen != 32 or not network.network_address.is_global:
            raise ValueError("SSH sources must be individual public IPv4 /32 networks")
        sources.append(str(network))
    resource = json.loads((ROOT / "redis.yml").read_text())
    config = json.loads((ROOT / "colors.yml").read_text())
    config["digitalocean-ssh-sources"] = sorted(set(sources))
    resource["spec"]["config"] = config
    resource["metadata"].update(name=args.resource, namespace=args.namespace)
    if args.render_only:
        print(json.dumps(resource, indent=2))
        return
    credentials = private_environment(args.private_env)
    if any(not credentials.get(key) for key in CREDENTIALS):
        raise ValueError("Five operator credentials are required")
    registry = Path(args.registry_config).read_bytes() if args.registry_config else None
    if registry is not None and not json.loads(registry).get("auths"):
        raise ValueError("Registry configuration has no auth entries")
    kube = Kubernetes(args)
    kube.apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": args.namespace}})
    kube.apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "redis-credentials", "namespace": args.namespace},
                "type": "Opaque", "stringData": credentials})
    if registry is not None:
        kube.apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "registry-credentials", "namespace": args.namespace},
                    "type": "kubernetes.io/dockerconfigjson", "data": {".dockerconfigjson": base64.b64encode(registry).decode()}})
    else:
        deadline = time.monotonic() + 120
        while True:
            try:
                kube.run("get", "secret", args.registry_secret, "-n", args.namespace, "-o", "name")
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Managed registry Secret did not appear within 120 seconds") from None
                time.sleep(5)
    operator = Path(args.operator_root)
    # The operator's install renderer owns RBAC, PVC and Deployment definitions.
    import subprocess
    rendered = subprocess.run(["bb", "-m", "colors.install", args.namespace, args.image],
                              cwd=operator, capture_output=True, text=True, timeout=120)
    if rendered.returncode:
        raise RuntimeError("Operator installation renderer failed (output suppressed)")
    manifests = json.loads(rendered.stdout)
    if args.registry_secret:
        for document in manifests["items"]:
            if document["kind"] == "Deployment":
                document["spec"]["template"]["spec"]["imagePullSecrets"] = [{"name": args.registry_secret}]
    kube.apply(manifests)
    kube.run("wait", "--for=condition=Established", "crd/redisdeployments.colors.getcolors.ai", "--timeout=60s")
    kube.run("rollout", "status", "deployment/" + args.deployment, "-n", args.namespace,
             "--timeout=600s", timeout=630)
    kube.apply(resource)
    print("Installed Redis operator and applied desired configuration.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Installation failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
