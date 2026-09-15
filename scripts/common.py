"""Shared private-input and Kubernetes helpers. Never print subprocess payloads."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = (
    "COLORS_PAR_DO_TOKEN", "COLORS_PAR_R2_ACCESS_KEY_ID",
    "COLORS_PAR_R2_SECRET_ACCESS_KEY", "COLORS_PAR_REDIS_BACKUP_R2_ACCESS_KEY_ID",
    "COLORS_PAR_REDIS_BACKUP_R2_SECRET_ACCESS_KEY",
)


def private_environment(path):
    """Parse literal export assignments without executing a shell or substitutions."""
    result = {}
    for line in Path(path).read_text().splitlines():
        parts = shlex.split(line, comments=True)
        if parts[:1] == ["export"]:
            parts = parts[1:]
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if key in CREDENTIALS:
                if "$" in value or "`" in value or not value.strip():
                    raise ValueError("Credentials must be nonempty literal assignments")
                result[key] = value
    return result


def parser(description):
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--kubeconfig", required=True)
    result.add_argument("--context", required=True)
    result.add_argument("--namespace", default="colors-redis")
    result.add_argument("--resource", default="redis-dev")
    result.add_argument("--deployment", default="colors-redis-operator")
    result.add_argument("--private-env", default=str(ROOT.parent / ".envrc.private"))
    return result


class Kubernetes:
    def __init__(self, args):
        self.args = args
        self.base = ["kubectl", "--kubeconfig", str(Path(args.kubeconfig).resolve()),
                     "--context", args.context]

    def run(self, *args, body=None, timeout=120):
        result = subprocess.run(self.base + list(args), input=body, text=True,
                                capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError("kubectl command failed; inspect the cluster separately (output suppressed)")
        return result.stdout

    def apply(self, document):
        return self.run("apply", "-f", "-", body=json.dumps(document))

    def resource(self):
        return json.loads(self.run("get", "redisdeployment", self.args.resource,
                                   "-n", self.args.namespace, "-o", "json"))

    def probe(self, operation, *args):
        output = self.run("exec", "deployment/" + self.args.deployment,
                          "-n", self.args.namespace, "--", "bb", "-m", "colors.probe",
                          self.args.resource, self.args.namespace, operation, *args,
                          timeout=1200 if operation == "rehearse" else 180)
        return json.loads(output)


def digitalocean(token, method, path):
    request = urllib.request.Request("https://api.digitalocean.com/v2/" + path,
                                     method=method,
                                     headers={"Authorization": "Bearer " + token,
                                              "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        if error.code == 404 and method == "GET":
            return None
        raise RuntimeError(f"DigitalOcean {method} failed: HTTP {error.code}") from None


def write_evidence(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(temporary, path)
