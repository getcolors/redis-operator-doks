# Redis operator on DOKS

## Current status: shut down

The user-requested shutdown completed on 2026-09-15. Redis was deleted through
its operator finalizer, then the controller namespace and PVC, DOKS cluster and
worker, task firewalls, and registry were removed. The registry subscription
no longer exists. Verified evidence: [shutdown.json](evidence/shutdown.json).

R2 buckets `doks-state`, `redis-state`, and `redis-backup` were retained and
remain accessible. Stored objects may continue to incur R2 storage charges.
The environment described below is the historical deployment, not a running service.

## Repositories

- [Plan](https://github.com/getcolors/redis-doks/blob/main/PLAN.md)
- [DOKS package](https://github.com/getcolors/doks)
- [Cluster configuration and cleanup](https://github.com/getcolors/doks-dev/blob/main/HANDOFF.md) (private)
- [Redis operator](https://github.com/getcolors/redis-operator)
- [Deployment commands](https://github.com/getcolors/redis-doks/blob/main/README.md) (private)

## Verified environment before shutdown

- DOKS cluster: `colors-doks-dev-20260915`, ID `a87775cd-de9f-4390-8dee-281f864bc9de`.
- Region/version: `ams3`, `1.36.3-do.5`.
- Worker: one `s-2vcpu-4gb`, Droplet `600715804`, public IP `209.38.46.78`.
- Context: `do-ams3-colors-doks-dev-20260915`.
- Namespace/resource: `colors-redis` / `RedisDeployment/redis-dev`.
- Profile: `redis-doks-20260915`.
- Registry: `registry.digitalocean.com/colors-redis-20260915`, basic tier;
  native DOKS integration manages image pull credentials.
- State buckets: `doks-state` and `redis-state`; backup bucket: `redis-backup`.
- SSH ingress: DOKS worker `209.38.46.78/32` and developer `89.168.97.254/32`.
- Redis listens on the Droplet's loopback interface and is accessed over SSH.

The private kubeconfig is `../doks-dev/.colors/doks-dev/cluster/kubeconfig`.
It expires after 24 hours; regenerate it using the DOKS package's kubeconfig workflow.
Credentials are in the workspace `.envrc.private` and Kubernetes Secrets, outside Git.

## Recovery boundaries

The controller restores service after confirmed Droplet loss. The existing Redis
package creates a fresh instance; it does **not** automatically restore the lost
Droplet's data. Backup rehearsal verifies a fresh backup in a scratch instance;
it is separate from restoring production data after infrastructure loss.

The controller runs one replica with Recreate updates. Its profile lock spans a
complete Redis convergence inside one process. This is not distributed fencing:
do not scale it above one replica, force-delete an active controller, or run another
human/CI controller against the same profile while it is active. The compute
journal lock covers the infrastructure stage, not every Redis workflow stage.

The PVC retains generated state and SSH keys. A graceful controller restart must
finish its active workflow before another process starts. Keep the PVC when
reinstalling the controller; remote infrastructure state alone does not retain
its SSH private key.

`spec.deletionPolicy` defaults to `Retain`. Explicit `Destroy` permits deletion;
normal convergence retains the package's protection against destructive replacement.
This first Redis resource supports `state: running`. Stopped state and one-shot
operations are not implemented; one-shot operations belong in a separate resource type.

## Verification

- R2 temporary-object write/read/delete passed for all three credential sets.
- DOKS provisioning, remote state persistence, and worker readiness passed.
- Operator tests passed on the host and in the actual AMD64 image on DOKS:
  8 tests, 50 assertions, no failures or errors. Deployment script safety tests:
  5 passing tests.
- Initial Redis convergence and authenticated health passed. The first Ansible
  attempt failed; the controller's retry completed successfully. During diagnosis
  reconciliation was suspended and an additional controlled Ansible run succeeded.
  No implementation change was required, and the initial cause was not retained.
  The adapter suppresses raw workflow errors to avoid exposing secrets; richer
  redacted diagnostics remain a follow-up.
- [Autonomous recovery passed](evidence/self-healing.json): original Droplet
  `600721546` (`165.22.198.189`) was deleted through the API at 16:07:44 UTC.
  Replacement `600724611` (`206.189.110.180`) was verified at 16:13:30 UTC:
  **5 minutes 46 seconds**. The resource UID and generation 3 stayed unchanged;
  no manual convergence request or workflow run occurred during recovery.
  The replacement's first Ansible attempt failed and its automatic retry passed.
  Authenticated reads/writes passed; the old marker did not survive.
- [Backup rehearsal passed](evidence/backup-rehearsal.json): reconciliation was
  suspended and acknowledged at generation 4, the package verified a fresh backup
  through a scratch restore, and reconciliation resumed at generation 5.
- [Graceful controller restart passed](evidence/controller-restart.json): the old
  pod stopped before the replacement started; the same Redis Droplet stayed healthy,
  and the persisted convergence-record timestamp was unchanged. SSH keys survived
  and no redundant full create ran.

Image: `registry.digitalocean.com/colors-redis-20260915/redis-operator@sha256:659414485f9686a7854cda8596a3cafa6ebf99862f4373422d1469524bb2d7b7`.
Source revision: `e072b43da92cf002da2d8bbd3a3615631bf06feb`.
See [source pins](evidence/source-revisions.json), [image](evidence/image.json),
and [native image test](evidence/native-image-test.json).

## Cleanup

These cleanup steps were completed on 2026-09-15. They are retained as a runbook
for a future deployment. Deleting the Redis custom resource with `Retain` would
leave its Droplet; the shutdown explicitly selected `Destroy`.

From this repository, with the refreshed private kubeconfig:

```bash
set -euo pipefail
export KUBECONFIG="$PWD/../doks-dev/.colors/doks-dev/cluster/kubeconfig"
kubectl --context do-ams3-colors-doks-dev-20260915 -n colors-redis patch redisdeployment redis-dev --type=merge -p '{"spec":{"deletionPolicy":"Destroy"}}'
kubectl --context do-ams3-colors-doks-dev-20260915 -n colors-redis delete redisdeployment redis-dev --timeout=30m
kubectl --context do-ams3-colors-doks-dev-20260915 delete namespace colors-redis --timeout=15m
cd ../doks-dev
COLORS_PAR_COMPUTE_PREVENT_DESTROY=false ./green delete
```

Do not remove the controller before the Redis finalizer finishes. The final
command requires the three DOKS credentials loaded privately, as described in
that repository. Remove the task registry and retained backup/state objects
only when they are no longer needed. Never target DOKS worker `600715804` in the
Redis failure test.
