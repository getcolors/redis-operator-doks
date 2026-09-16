# Plan: doks and redis-operator become Package Skills

Date: 2026-09-16. Follows the audit in
`workspace/reports/redis-doks-audit-2026-09-16/` and the assessment that
preceded it. Everything in this plan is executed autonomously; the decisions
below are the recommended options from that assessment.

## Goal

Turn `doks` into a conforming Green Package Skill built on colors-compute's
`managed-kubernetes` kind, and split `redis-doks` into the Package Skill
`redis-operator` (the existing controller repository gains a payload) and
the deployment `redis-operator-doks` (this repository, renamed from
`redis-doks`). Verify both with live deployments, then tear them down.

## Decisions

- **Names.** Skill `doks`, deployment `doks-dev` (existing). Skill
  `redis-operator` (existing repository), deployment `redis-operator-doks`
  (GitHub rename of `redis-doks`, history and evidence kept under
  `history/2026-09-15/`).
- **Colour.** Green only. `green.kubernetes` exists in no other colour, so
  there is no parity suite; `bb golden` and `scripts/launcher.sh` are the nets.
- **doks is a colors-compute consumer.** It calls `plan-managed-kubernetes`,
  `managed-kubernetes` and `read-managed-kubernetes` as `agent-network-doks`
  does. DigitalOcean and Vultr are advertised from birth because the library
  recipes exist for both. The cluster is named after the profile
  (Compute Name Standard); the backend uses `provider-backend: r2`,
  `r2-bucket`, `r2-endpoint` and `COLORS_PAR_R2_*`. The hand-rolled tofu
  runner, the `cluster-name` key, the `doks-state-r2-*` keys and the
  `<profile>/cluster.tfstate` key all go away.
- **doks owns an optional registry.** `digitalocean-registry-tier` present
  means the deployment owns a profile-named DigitalOcean container registry
  with a rotated read-only pull credential, integrated with the cluster so
  DOKS injects the pull Secret into every namespace, plus a `registry` verb
  that writes a short-lived push docker config under `.colors/`. Absent means
  no registry. On Vultr the key is a validation error. Modelled on
  `agent-network-doks`'s registry templates.
- **Verbs.** doks: `build`, `create`, `check`, `kubeconfig`, `registry`,
  `delete`. redis-operator: `build`, `create`, `check`, `rehearse`, `drill`,
  `restart`, `delete`. `drill` is the Droplet-deletion recovery test; it runs
  only with `COLORS_PAR_DRILL_DELETE_OWNED_DROPLET=true` for one run and
  keeps every ownership check the Python script had. `delete` is guarded by
  `compute-prevent-destroy`; lifting it patches the policy to Destroy and
  waits for the finalizer before removing the namespace.
- **The Python goes away.** Installer, drills and the private-env parser are
  ported to tested Clojure in the package. Credentials come from the five
  `COLORS_PAR_*` variables green already reads; nothing parses
  `.envrc.private`. Manifests come from the pinned library, never from a
  working tree. `redis.yml` is dropped; the custom resource is rendered from
  `colors.yml` at build.
- **Pins.** colors-compute moves to 7e1c234 in both packages (the reviewed
  repair for interrupted operations). green stays at 215e298, redis at
  ec260f5. Real pushed SHAs only, stamped by `bb pin`.
- **Audit fixes taken in passing.** Termination grace above the workflow
  caps; `create` refuses to un-suspend a suspended resource; one log line
  per reconcile outcome in the adapter; tofu output no longer swallowed
  (the library reports it). Not in scope: the token-relative 404, the
  unexplained Droplet 600730033 (now documented as an open item), controller
  probes.
- **Image.** Built for amd64 from the redis-operator repository at its pinned
  SHA and pushed to the doks-owned registry with the `registry` verb's push
  config; the deployment pins the digest in `colors.yml`.
- **End state.** Full lifecycle proven: create, check, drill, rehearse,
  restart, delete, for both deployments. Nothing billable remains; R2 state
  and backup objects are retained.

## Work

1. Sync every repository; rename `redis-doks`; write this plan; push.
2. Subagent A: rewrite `doks` as the Package Skill described above
   (`io.github.getcolors.doks.*` namespaces, payload, launcher check, golden
   for two providers, pin task, devenv, CI). Push; `bb pin`; push.
3. Subagent B: add `skills/package-redis-operator-green` to `redis-operator`
   with the launcher-side namespaces, port the scripts, bump pins, apply the
   audit fixes, keep the controller image entry point. Push; `bb pin`; push.
4. Retrofit `doks-dev` and `redis-operator-doks` as conventional deployments:
   `npx skills add`, root launcher copies, `skills-lock.json`, `devenv.nix`,
   `.envrc`, per-deployment `.envrc.private`, default-deny `.gitignore`,
   new `colors.yml`, `CLAUDE.md`, `README.md`.
5. Live: `doks-dev` create and check; build and push the image; record the
   digest; `redis-operator-doks` create and check; drill, rehearse, restart;
   `redis-operator-doks` delete; `doks-dev` delete; confirm the account is
   empty. Evidence under `evidence/2026-09-16/`.
6. Update `workspace/CLAUDE.md` and `repositories.json` with the four
   repositories; commit and push every repository to main.
7. Write `HANDOFF.md` with results, pins, evidence, open items and cleanup.

## Acceptance

- `doks` and `redis-operator` pass `bb test`, `bb golden` and
  `scripts/launcher.sh`; builds and dry runs work from a fresh checkout with
  no credentials.
- Both deployments track a payload and a lockfile, and the root launcher
  equals the payload.
- The live cycle above completes with the ownership checks intact and the
  resource UID unchanged across the drill.
- No secret or generated file is tracked anywhere.
