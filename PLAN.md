# Redis operator on DOKS

## Goal

Run `green.kubernetes` in a new DigitalOcean Kubernetes cluster. The operator
reuses the existing Redis package to provision Redis on a separate Droplet.
Delete only that task-owned Droplet through the DigitalOcean API and verify
that the operator detects its absence and restores a healthy Redis service.

## Repositories

- `getcolors/doks`: reusable Green workflow for DOKS provisioning.
- `getcolors/doks-dev`: private configuration for the development cluster.
- `getcolors/redis-operator`: RedisDeployment CRD, Clojure controller adapter,
  image build, and installation workflow. Pins Green and Redis.
- `getcolors/redis-doks`: private operator/deployment configuration, live test,
  evidence, this plan, and the final handoff.
- Reuse `green`, `redis`, and `colors-compute`. Change existing libraries only
  when required by the integration and verify any changes independently.

## Decisions

- One DOKS worker for this development test, in an available European region.
  Choose a currently supported Kubernetes version and a worker with enough RAM
  for the controller, its toolchain, and infrastructure operations.
- Redis runs on a dedicated small DigitalOcean Droplet. Its Redis port stays
  bound to loopback; the controller configures and checks it over SSH.
- R2 buckets are `doks-state`, `redis-state`, and `redis-backup`. Use separate
  credential sets from the workspace's private environment file. Never commit
  credentials, kubeconfigs, Terraform state, SSH private keys, or registry tokens.
- Use remote infrastructure state and a persistent controller volume for SSH
  keys, generated files, and package caches. Restart the controller gracefully;
  no distributed failover or forced takeover of an uncertain workflow.
- The CRD exposes `deletionPolicy`, defaulting to Retain. Package destruction
  protection stays enabled during convergence. Only an explicit Destroy deletion
  permits the adapter's deletion callback to lift the package's workflow guard.
  It does not enable automatic destructive replacement of existing infrastructure.
- Provision and heal with direct Green workflow calls, not package skill/CLI Jobs.
- Observation must distinguish API/state errors from confirmed Droplet absence,
  and must check Redis health. An unknown error must never cause blind recreation.
- Pin source revisions and the deployed image. Build locally; publish the image
  through an authenticated registry available to DOKS.

## Work

1. Synchronize existing repos, initialize the four repos, and publish this plan.
2. Verify all credential sets, including temporary-object write/read/delete probes
   in dedicated test prefixes. Check DigitalOcean permissions and current DOKS
   versions/sizes without changing existing resources.
3. Implement/test DOKS provisioning and write development configuration. Create a
   uniquely named task cluster and save a private kubeconfig outside Git.
4. Implement/test the Redis operator, ownership checks, observation, remote-state
   recovery, persistent keys, CRD, credentials wiring, and installation workflow.
5. Build and install the operator; create a dedicated RedisDeployment. Wait for
   provider, SSH, Redis authentication, and backup acceptance checks to pass.
6. Record the original Droplet ID, profile, owner, and health. Confirm it is not
   a DOKS worker or another deployment. Delete that exact ID through the API.
7. Verify autonomous replacement with a different Droplet ID, healthy Redis,
   working authenticated reads/writes, and a healthy custom-resource status.
   Also verify controller restart with retained keys and state.
8. Record service recovery separately from data recovery. Write a marker before
   disruption and report whether it survives. Automatic backup restoration is
   not assumed from a healthy replacement. Exercise the existing backup rehearsal
   where practical; do not claim whole-node data recovery without proving it.
9. Write HANDOFF.md with evidence, exact commands, resource IDs, data behavior,
   limitations, and cleanup commands. Keep the successful development deployment
   available for inspection and state its ongoing billable resources explicitly.
10. Commit and push every changed repository to main, with real pinned SHAs.

## Acceptance

- All four repositories have runnable code/configuration and documentation.
- The live Redis controller executes on DOKS, while Redis executes on a Droplet.
- The deletion test proves ownership before DELETE and never targets shared or
  pre-existing infrastructure.
- The operator heals confirmed Droplet loss without a manual create command or
  a Kubernetes desired-state change.
- Tests and evidence distinguish service recovery, backup integrity, and data loss.
- Secrets stay private. The plan and handoff links are shared with the user.

## Progress

- Existing Green, Redis, and colors-compute repositories synchronized to main.
- Four new repositories created; deployment repositories are private.
- Implementation and live verification are in progress.
