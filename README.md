# Redis on Droplets, managed from DOKS

This private deployment repository installs `redis-operator` in an existing
DOKS cluster. The controller runs Green workflows to provision Redis on a
separate DigitalOcean Droplet. DOKS provisioning belongs to `doks-dev`.

See [PLAN.md](PLAN.md) for scope and [HANDOFF.md](HANDOFF.md) for the completed
live result, retained resources, and cleanup instructions.

## Desired configuration

`colors.yml` holds the Redis package configuration. `redis.yml` wraps that
configuration in a `RedisDeployment`; the installer reads `colors.yml` as
the authoritative configuration and inserts it into the resource.
Both files use JSON syntax, which is also valid YAML, so the tooling needs
only Python's standard library.

- Profile: `redis-doks-20260915`; resource: `colors-redis/redis-dev`.
- Redis: one `s-1vcpu-2gb` Ubuntu 24.04 Droplet in `ams3`.
- Remote compute state: `redis-state`; RDB backup sets: `redis-backup`.
- Redis listens on loopback and is checked through authenticated SSH.
- `deletionPolicy: Retain`; periodic reconciliation every 30 seconds.
- SSH allows worker `209.38.46.78/32` and developer `89.168.97.254/32`.
  Supply each approved public IPv4 `/32` explicitly at install.
  Update these sources if the DOKS worker is replaced or scaled.

## Install

Registry bootstrap uses Python `requests` and operates only the task registry
`colors-redis-20260915`. The following commands create the registry if absent,
write private short-lived Docker credentials, and enable DOKS-managed pull Secrets:

```bash
python3 scripts/registry.py ensure
python3 scripts/registry.py credentials
python3 scripts/registry.py integrate --cluster-id a87775cd-de9f-4390-8dee-281f864bc9de
```

The default auth directory is `/tmp/colors-redis-registry`; push credentials expire
in one hour. Use `docker --config /tmp/colors-redis-registry/push` to publish the
image from the operator repository. Keep those files outside Git. Native DOKS
integration supplies the `colors-redis-20260915` pull Secret in new namespaces.

Build and publish the image using the `redis-operator` repository, then record
its immutable digest. Install with explicit cluster targeting:

```bash
python3 scripts/install.py \
  --kubeconfig ../doks-dev/.colors/doks-dev/cluster/kubeconfig \
  --context do-ams3-colors-doks-dev-20260915 \
  --image registry.digitalocean.com/colors-redis-20260915/redis-operator@sha256:IMAGE_DIGEST \
  --registry-secret colors-redis-20260915 \
  --ssh-source 209.38.46.78/32 \
  --ssh-source 89.168.97.254/32
```

Alternatively use `--registry-config /private/path/config.json` to create a
pull Secret. Native DOKS registry integration is preferred for credential
rotation. The installer waits up to two minutes for the managed secret in `colors-redis`.

The installer parses literal assignments from the workspace `.envrc.private`
without executing it. It copies only five DigitalOcean, state, and backup
credential variables into the operator Secret. Secrets travel through stdin;
captured Kubernetes errors and their payloads are not printed. Use
`--private-env` to select another private credential file. Never commit it.

Use `--render-only` with the same flags to inspect the nonsecret custom resource
without contacting Kubernetes. Installation creates the namespace, credentials,
CRD, namespace-scoped permissions, persistent controller volume, and controller.
It waits for the controller rollout, then applies the RedisDeployment. The
initial infrastructure convergence continues asynchronously.

## Live self-healing test

Wait for `RedisDeployment` status `Ready=True` for its current generation.
The following command **deletes the managed Redis Droplet** after checking its
recorded provider ID, exact profile/name, public address, and DOKS worker IDs:

```bash
python3 scripts/self_heal.py \
  --kubeconfig ../doks-dev/.colors/doks-dev/cluster/kubeconfig \
  --context do-ams3-colors-doks-dev-20260915 \
  --cluster-id a87775cd-de9f-4390-8dee-281f864bc9de \
  --delete-owned-droplet
```

The script writes and reads a unique marker using authenticated Redis commands,
deletes exactly the recorded Droplet through the DigitalOcean API, and waits for
a different provider ID, current Ready status, and authenticated reads/writes.
It also requires the old Droplet to be absent and the custom resource's UID and
generation to remain unchanged. There is no manual convergence request.

Evidence is saved incrementally to `evidence/self-healing.json`. It contains
resource IDs, timestamps, and a synthetic test marker, never credentials or
Terraform state. Run backup rehearsal separately after service recovery, as described below.

**This tests service recovery, not restoration of previous data.** The current
package initializes a new host and does not automatically restore an earlier
backup. The pre-deletion marker is expected to be absent after recovery. Older
backup sets remain available subject to retention; the replacement also writes
new timestamped sets. The replacement host generates a new Redis password.

## Backup rehearsal

```bash
python3 scripts/rehearse.py \
  --kubeconfig ../doks-dev/.colors/doks-dev/cluster/kubeconfig \
  --context do-ams3-colors-doks-dev-20260915
```

The script suspends the custom resource and waits until the controller reports
`Suspended` for the new generation. This acknowledgement means the previous
convergence finished. It then invokes the existing Redis backup rehearsal,
which creates a fresh completed backup set and restores it into a scratch
container. The probe independently requires acknowledged suspension before it
runs the mutating workflow. A `finally` block resumes management after success
or a completed failure. The script leaves suspension intact if remote execution
completion is uncertain or another actor changes the resource; verify that no
workflow is running before manually resuming in those cases.

Evidence goes to `evidence/backup-rehearsal.json`. Do not run rehearsal probes
directly while convergence is active. Suspension is intended for this single
controller development setup; it does not coordinate independent human or CI
runners.

## Controller restart test

```bash
python3 scripts/restart.py \
  --kubeconfig ../doks-dev/.colors/doks-dev/cluster/kubeconfig \
  --context do-ams3-colors-doks-dev-20260915
```

This scales the controller to zero, waits for the old pod to finish, then scales
back to one. It verifies the same Redis Droplet stays healthy with the same
resource UID and generation. The persistent volume retains SSH keys and the
operator's convergence record. It does not force takeover of an uncertain run.

Do not scale this operator beyond one replica. The current design does not fence
multiple controller processes. The compute journal's ownership lock protects
compute operations; it does not cover the complete Redis Ansible workflow.

## Offline verification

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/common.py scripts/install.py scripts/self_heal.py scripts/restart.py scripts/rehearse.py
```

These checks use no cloud credentials and make no cloud changes.
