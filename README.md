# redis-operator-doks

Desired state for the [`redis-operator`](https://github.com/getcolors/redis-operator)
Package Skill installed in the sibling [`doks-dev`](https://github.com/getcolors/doks-dev)
cluster. The controller runs in namespace `colors-redis` and manages one Redis
7.2 Droplet (`s-1vcpu-2gb`, `ams3`, loopback only, reached over SSH) whose
compute state lives in the `redis-state` bucket and whose RDB backup sets go to
`redis-backup`. `colors.yml` is the only file to edit.

```sh
direnv allow                 # once; loads devenv, the five credentials, and KUBECONFIG
./green build                # render .colors/redis-operator-doks/operator/ — no cluster contact
./green create --dry-run     # walk the graph, skip every side effect
./green create               # install the operator and converge the RedisDeployment
./green check                # Ready at the current generation, authenticated Redis health
./green rehearse             # suspend, fresh backup set restored into a scratch container, resume
COLORS_PAR_DRILL_DELETE_OWNED_DROPLET=true ./green drill   # delete the owned Droplet, wait for recovery
./green restart              # graceful controller restart; same Droplet, same UID
COLORS_PAR_COMPUTE_PREVENT_DESTROY=false ./green delete    # Destroy policy, finalizer, namespace
```

`KUBECONFIG` is exported by `.envrc` and points at `../doks-dev/.colors/doks-dev/kubeconfig`,
generated output of the doks deployment (`./green kubeconfig` there refreshes it).
The image digest in `colors.yml` is produced by `redis-operator/scripts/image.sh`
pushing to the registry `doks-dev` owns; DOKS registry integration supplies the
`doks-dev` pull Secret in every namespace.

Credentials live only in the gitignored `.envrc.private`: `COLORS_PAR_DO_TOKEN`,
`COLORS_PAR_R2_ACCESS_KEY_ID`, `COLORS_PAR_R2_SECRET_ACCESS_KEY`,
`COLORS_PAR_REDIS_BACKUP_R2_ACCESS_KEY_ID`, `COLORS_PAR_REDIS_BACKUP_R2_SECRET_ACCESS_KEY`.
Never export `COLORS_PAR_PROFILE`.

See `HANDOFF.md` for the latest verified state and evidence, `PLAN.md` for the
plan this repository executed, and `history/2026-09-15/` for the previous
script-driven deployment (`redis-doks`).
