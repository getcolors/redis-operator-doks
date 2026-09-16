# CLAUDE.md

Guidance for agents working in this deployment. Read
`~/code/getcolors/CLAUDE.md` first.

## What this is

Desired state only. No source code. `colors.yml` is the single file to edit;
everything else is generated (`.colors/`), secret (`.envrc.private`), tracked
evidence (`evidence/`), or an installed copy of the
[`redis-operator`](https://github.com/getcolors/redis-operator) Package Skill
launcher.

## Things specific to this deployment

- **The cluster belongs to `doks-dev`.** `KUBECONFIG` comes from that
  deployment's generated output; run `./green kubeconfig` there when it has
  expired. Never copy the kubeconfig into this repository.
- **The image is pinned by digest.** Build it from `redis-operator` at the
  same SHA the launcher pins, push it to the `doks-dev` registry with
  `redis-operator/scripts/image.sh`, and paste the printed digest into
  `colors.yml`.
- **`digitalocean-ssh-sources` must list the DOKS worker's public IP** (the
  controller reaches Redis over SSH from there) and the developer workstation.
  `../doks-dev/green check` prints the worker IP; update it after a node
  replacement.
- **Two guards, two overrides.** `delete` needs
  `COLORS_PAR_COMPUTE_PREVENT_DESTROY=false` and destroys the Droplet through
  the operator finalizer; `drill` needs
  `COLORS_PAR_DRILL_DELETE_OWNED_DROPLET=true` and deletes the owned Droplet
  to prove recovery. Neither runs without explicit authorization.
- **Evidence** is copied from `.colors/redis-operator-doks/evidence/` into
  `evidence/<date>/` when a verified run is recorded; it holds resource IDs,
  timestamps and synthetic markers, never credentials or state.

## The launcher is a copy

`./green` is a copy of `.agents/skills/package-redis-operator-green/green`.
After `npx skills update -p`, copy it again and compare; `skills-lock.json`
records the installed pin.

## Safety

- Never edit `.colors/`, never commit it, never read it as source.
- Keep `compute-prevent-destroy: true` and `deletion-policy: Retain`.
- Never export `COLORS_PAR_PROFILE`.
- Delete this deployment before `doks-dev`; the cluster cannot clean the
  Droplet once the controller is gone.
