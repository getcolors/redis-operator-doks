# Handoff: redis-operator on DOKS, as Package Skills

Date: 2026-09-16. Plan: [PLAN.md](PLAN.md). Audit that motivated it:
[reports/audit-2026-09-16.md](reports/audit-2026-09-16.md). Previous,
script-driven deployment (`redis-doks`): [history/2026-09-15/](history/2026-09-15/).

## Current status: shut down

The full lifecycle was proven live on 2026-09-16 and then torn down in order:
this deployment through the operator finalizer (`Destroy`), then the cluster
and registry through `doks-dev`. See [Shutdown](#shutdown) for the verified
end state. R2 buckets `doks-state`, `redis-state` and `redis-backup` are
retained with their objects (retired compute journals, the `redis-operator-doks`
backup sets); they are the only remaining billable items.

## What shipped

| Repository | Result | Final SHA |
|---|---|---|
| [`doks`](https://github.com/getcolors/doks) | Green-only Package Skill `package-doks-green` on colors-compute's `managed-kubernetes` kind (DigitalOcean and Vultr advertised), optional deployment-owned registry with DOKS integration, verbs `build create check kubeconfig registry delete`; 36 tests, two goldens, launcher check | `49c5b2e` (launcher pin `41e12fc`) |
| [`doks-dev`](https://github.com/getcolors/doks-dev) | conventional deployment: installed payload + `skills-lock.json`, devenv, per-deployment private env, default-deny `.gitignore`; cluster `doks-dev` + registry `doks-dev` | see `git log` |
| [`redis-operator`](https://github.com/getcolors/redis-operator) | Package Skill `package-redis-operator-green` beside the controller image source; verbs `build create check rehearse drill restart delete`; the Python installer and drills ported to tested Clojure; 43 tests, golden, launcher check | `e9fe076` (launcher pin `5f37868`) |
| `redis-operator-doks` (this repo) | conventional deployment, renamed from `redis-doks`; `colors.yml` renders the RedisDeployment; evidence under `evidence/2026-09-16/` | see `git log` |
| [`workspace`](https://github.com/getcolors/workspace) | the four repositories added to the map and `repositories.json` | `542c858` |

Pins: green `215e298`, redis `ec260f5`, colors-compute `7e1c234` (bumped from
`ae28ea7` in both packages: the reviewed repair for interrupted operations).

## Live verification (all evidence in `evidence/2026-09-16/`)

- **doks-dev create**: cluster `2e927b38-90a5-4d73-98af-d974f9fe9fd1`
  (`doks-dev`, `ams3`, `1.36.3-do.5`, one `s-2vcpu-4gb` worker
  `doks-dev-3fd5ld` at `134.209.92.109`), registry `doks-dev` created and
  integrated. Infrastructure 356 s, registry 19 s. A second `create` was a
  no-op in 13 s. `check` printed the node and the integration; `registry`
  wrote a one-hour push config. [live-run.json](evidence/2026-09-16/live-run.json).
- **Image**: built for `linux/amd64` on this arm64 host with buildx and
  pushed to `registry.digitalocean.com/doks-dev/redis-operator`; two digests
  over the day, both recorded in `live-run.json` with their source revisions.
- **First operator create**: Ready/Converged at generation 1; Droplet
  `600954837` at `206.189.98.100`; resource UID `d1e760f1-2d2c-404f-8365-2d643d36ebed`.
  The first Ansible attempt failed at 06:53:20 and the controller's retry
  converged at 06:55:40
  ([controller-log-first-create.txt](evidence/2026-09-16/controller-log-first-create.txt)),
  the same pattern as 2026-09-15.
- **Image update**: the second digest rolled the controller; it observed the
  existing Droplet healthy and ran no create.
- **Drill** ([self-healing.json](evidence/2026-09-16/self-healing.json)):
  ownership proven (id, name, profile, worker exclusion `600945297`, IP,
  marker round-trip); Droplet `600954837` deleted at 07:49:33; replacement
  `600968621` at `161.35.157.65` verified at 07:54:54: **5 min 21 s**. UID and
  generation unchanged; prior marker did not survive (service recovery, not
  data recovery). The replacement converged on its **first** Ansible
  attempt, so the new failure-log retention captured nothing this time
  ([controller-log-drill.txt](evidence/2026-09-16/controller-log-drill.txt)).
- **Rehearsal** ([backup-rehearsal.json](evidence/2026-09-16/backup-rehearsal.json)):
  suspended and acknowledged at generation 2, fresh backup set restored into
  a scratch container, resumed at generation 3, Ready again.
- **Restart**: the first attempt **failed**
  ([controller-restart-failed-attempt-1.json](evidence/2026-09-16/controller-restart-failed-attempt-1.json),
  [.log](evidence/2026-09-16/controller-restart-failed-attempt-1.log)): the
  verb accepted the old controller's draining status write as proof of the
  new one, then exec'd a probe into a pod still downloading its dependency
  cache and hit a truncated zip. Fixed in the package (probe gate on the new
  pod's own "controller running" log line, reconcile time compared to the
  new pod's start, dependency caches on the PVC); the second attempt
  **passed** ([controller-restart.json](evidence/2026-09-16/controller-restart.json)):
  new pod up in about 20 s from the cached volume, same Droplet, same UID,
  same convergence record.
- **Delete**: the first attempt **failed**
  ([delete-failed-attempt-1.log](evidence/2026-09-16/delete-failed-attempt-1.log))
  on a JSON-patch resourceVersion test that raced the controller's status
  writes. Fixed in the package (guarded retry when only status moved); the
  second attempt ([delete.log](evidence/2026-09-16/delete.log)) patched
  `Destroy`, the finalizer destroyed the Droplet, then the namespace and CRD
  were removed. The compute journal in `redis-state` is `retired`.

## Package fixes made during the live run

1. `check` and every Ready precondition poll through the periodic
   `Reconciling` pass instead of reading once (with `reconcile-interval: 30s`
   the observe pass occupies most of the interval).
2. The controller retains masked failure logs at
   `/data/work/<profile>/failures/` (20 newest); `check` reports the count.
3. Probe gate on the new controller pod's log; restart compares
   `lastReconcileTime` to the new pod's start; `/root/.gitlibs`, `/root/.m2`,
   `/root/.deps.clj`, `/app/.cpcache` live on the PVC.
4. `patch-resource!` retries a resourceVersion race caused by status writes,
   refuses when `spec` or `deletionTimestamp` changed.
5. `doks` delete cleanup reports leftovers and each stage; `image.sh` keeps
   root-owned docker state out of `.colors/`.

## Open items (not fixed here)

- **First-attempt Ansible failure** on a fresh Droplet: 3 of 4 creates across
  two days failed once and converged on retry. Cause still unknown; the
  retention path is now armed and the next occurrence will be readable with
  `kubectl exec deployment/colors-redis-operator -- cat /data/work/<profile>/failures/<file>`.
- The unexplained Droplet `600730033` in the 2026-09-15 shutdown record.
- Token-relative DigitalOcean 404 in the adapter's absence proof; benign slug
  drift (`image.slug`, `size_slug`) causing a converge loop; suspension is a
  one-shot check, not a lease; no liveness or readiness probes on the
  controller. All documented in the audit and in `redis-operator/README.md`.
- `doks` and `redis-operator` have no `index.html` landing page and no Pages;
  `repositories.json` carries an empty homepage for both.
- The kind cluster `colors-green` and `/tmp/green-kubernetes-kubeconfig` from
  the green controller work are still present on this machine.

## Recreate

```sh
cd ../doks-dev && direnv allow && ./green create && ./green check && ./green registry
cd ../redis-operator && DOCKER_CONFIG=../doks-dev/.colors/doks-dev/registry/push scripts/image.sh registry.digitalocean.com/doks-dev
# paste the printed digest into colors.yml as `image`; put the worker IP from
# `doks-dev check` into `digitalocean-ssh-sources`; set `doks-cluster-id`
cd ../redis-operator-doks && direnv allow && ./green create && ./green check
```

Credentials: `doks-dev/.envrc.private` (DO token, `COLORS_PAR_R2_*` for
`doks-state`) and `redis-operator-doks/.envrc.private` (the five operator
variables). Both exist on this machine, gitignored.

## Shutdown

Verified at 08:14 UTC on 2026-09-16 ([shutdown.json](evidence/2026-09-16/shutdown.json)):

1. `redis-operator-doks`: `deletionPolicy` patched to `Destroy`, the finalizer
   destroyed Droplet `600968621`, then the namespace and the CRD were removed;
   the compute journal in `redis-state` is `retired`.
2. `doks-dev`: registry integration removed, cluster destroyed (the library
   returned in 15 s), registry destroyed. DigitalOcean removed the worker
   Droplet `600945297` and the two `k8s-<cluster-id>-*` firewalls
   asynchronously about four minutes later. The package's final cleanup step
   then failed on a non-empty `registry/push` directory
   ([doks-dev-delete-attempt-1.log](evidence/2026-09-16/doks-dev-delete-attempt-1.log)):
   the image build had run docker as root with that directory as its config
   and left a root-owned `buildx/` subtree. Nothing billable was affected.
   Fixed twice over: `doks` now reports leftovers instead of throwing and
   prints one line per delete stage, and `redis-operator/scripts/image.sh`
   builds from a private temp config directory. A second `delete` on the
   destroyed deployment completed every stage and the cleanup
   ([doks-dev-delete-attempt-2.log](evidence/2026-09-16/doks-dev-delete-attempt-2.log));
   its "registry destroyed" line on an already-empty registry state is
   cosmetic.
3. Account after: 0 Droplets, 0 clusters, 0 firewalls, no registry, no
   profile-named SSH keys.

Retained on purpose: R2 buckets `doks-state`, `redis-state`, `redis-backup`
and their objects.
