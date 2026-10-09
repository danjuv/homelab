---
name: opencode
description: Run background coding tasks on the homelab repo
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [coding, homelab, kubernetes, argo]
    category: devops
    requires_toolsets: [terminal]
---

# OpenCode coding tasks

OpenCode is a coding agent that runs as an Argo Workflow in the cluster. Each
task gets its own pod with a fresh clone of github.com/danjuv/homelab (the
GitOps repo: Kubernetes manifests, Helm values, ArgoCD apps, Bazel images).
It makes the change, validates it, and opens a pull request. It has
read-only cluster access (no Secrets), so it can inspect live state but
can't change the cluster; nothing is deployed until the user merges the PR.

Script: `python3 ${HERMES_SKILL_DIR}/scripts/opencode_task.py`

## When to Use

- The user wants a change in the homelab repo: add or upgrade an app, change
  Helm values or manifests, fix CI, write a script.
- The user wants a cluster problem investigated, with or without a fix PR.
- Not for questions you can answer directly, and not for tasks that need a
  new secret value (the user seals secrets themselves).

## Procedure

1. Write a self-contained brief. The agent can't see this chat: include the
   goal, names (app, namespace, hostname, versions), constraints, and what
   "done" looks like. Say whether a PR is wanted; for a question or
   investigation, say "Do not create a branch or PR." Ask the user first if
   something essential is unclear.
2. Submit it, passing the brief on stdin:

       python3 ${HERMES_SKILL_DIR}/scripts/opencode_task.py submit \
         --title "Add Jellyfin to media" <<'BRIEF'
       <brief>
       BRIEF

   Tell the user the task ID and the Watch link. Tasks take minutes; don't
   wait for them in a loop.
3. When asked how it's going: `opencode_task.py status <task>`. Phases:
   Pending, Running, Succeeded, Failed, Error. When finished, report the PR
   URL, or the agent's final message if there is no PR.
4. `opencode_task.py list` shows recent tasks. `opencode_task.py stop <task>`
   stops one (only when the user asks).

Use `--timeout-minutes` (default 45, max 120) for unusually large tasks.

## Pitfalls

- `cannot read /var/run/secrets/argo-workflows/token`: the Hermes pod lacks
  the token mount; tell the user.
- `HTTP 403`: the token works but RBAC denies the action; tell the user.
- A Failed task with no PR: report the last output lines from `status`.
- Up to 5 workflows run at once cluster-wide; extra tasks wait as Pending.

## Verification

`opencode_task.py list` prints tasks or "No tasks."
