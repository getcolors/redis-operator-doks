# Native operator verification

Verified on 2026-09-16 against the DigitalOcean `doks-dev` cluster. Source revision `8251d68edef252902f32da68d4b46ec19e9a760f` supplies the final images and all installed launcher library pins.

## Results

| Check | Blue | Red |
|---|---|---|
| Standalone build and create dry-run | Passed | Passed |
| Live controller convergence | Created the Redis Droplet | Adopted the same Droplet |
| Authenticated health | Passed | Passed |
| Fresh backup and restore rehearsal | Passed | Passed |
| Restart with new pod and fresh reconciliation | Passed | Passed |
| Droplet-loss recovery drill | Not run | Passed |

Green, Red and Blue launchers all successfully probed the Red controller image. A temporary pod verified Red adapter imports on native amd64 and was removed.

The initial Blue creation used source `7f55d9b`, then the final `8251d68` image passed health, rehearsal and restart. That final change aligns Blue IPv4 validation with Green and Red. The final Red image performed all Red checks and recovery.

The recovery drill deleted test-owned Droplet `601089393`, then verified its absence and replacement by `601094147` at `146.190.24.194`. The resource retained UID `e92793d1-546f-4779-86a8-d0405649c755` and generation 5. An authenticated write succeeded after recovery. The initial Redis data was synthetic test data; this drill proves service recovery, not automatic restoration of the deleted Droplet's data. Backup restoration was verified separately by both rehearsal runs.

Ubuntu held the dpkg frontend lock during the first recovery installation. The controller retained one masked failure log, retried automatically and converged. `red/recovered-apt-lock.json` records that recovered failure. The final check was healthy with one historical retained failure. No manual lock removal or workflow repair was required.

## Running deployment

The final controller is Red, Ready at observed generation 5, with suspension false and zero pod restarts. The DOKS cluster, registry, persistent volume and Redis Droplet remain running. Destruction protection and Retain policy remain enabled in desired state.

Final images:

- Red: `registry.digitalocean.com/doks-dev/redis-operator-red@sha256:8d53eb6932dddc3e9b512545ae02f7123f54acbc0d0d3346d7bd8331c21f3d8c`
- Blue: `registry.digitalocean.com/doks-dev/redis-operator-blue@sha256:5caa4c9df3e4e969895dfb8d68dac0372e144203d140de920fc9d9d578bd72ba`

Credentials came from the sibling deployment repositories' ignored `.envrc.private` files. Package create supplied them to the Kubernetes Secret through stdin. No credentials or Terraform state are included in this evidence.

The JSON records and operation logs in `blue/` and `red/` contain each run's assertions and timestamps. `final-status.json` records the final resource and pod identities.
