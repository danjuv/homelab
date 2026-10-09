#!/usr/bin/env python3
"""Run OpenCode coding tasks on the homelab repo via Argo Workflows.

  opencode_task.py submit --title "Short title" [--timeout-minutes 45] < brief.txt
  opencode_task.py submit --title "Short title" "brief text"
  opencode_task.py status <task>     phase, PR URL, last lines of output
  opencode_task.py list [--limit 10]
  opencode_task.py stop <task>

Talks to the Argo Server API with this pod's ServiceAccount token (mounted
at TOKEN_FILE; RBAC limits it to the opencode namespace). Standard library only.
"""

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ARGO_URL = "http://argo-workflows-server.argo-workflows.svc.cluster.local:2746"
UI_URL = "https://argo-workflows.home.lab"
TOKEN_FILE = "/var/run/secrets/argo-workflows/token"
NAMESPACE = "opencode"
TEMPLATE = "opencode-task"
SOURCE_LABEL = "opencode.home.lab/source=hermes"
MAX_BRIEF_BYTES = 16 * 1024
MAX_TIMEOUT_MINUTES = 120
TIMEOUT = 30

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


class ArgoError(Exception):
    pass


def call(method, path, body=None, query=None, raw=False):
    try:
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
    except OSError as exc:
        raise ArgoError(f"cannot read {TOKEN_FILE}: {exc.strerror}") from None
    url = ARGO_URL + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("message", detail)
        except ValueError:
            pass
        raise ArgoError(f"{method} {path}: HTTP {exc.code}: {detail[:300]}") from None
    except urllib.error.URLError as exc:
        raise ArgoError(f"cannot reach Argo Server: {exc.reason}") from None
    return payload if raw else json.loads(payload or b"{}")


def param(wf, name):
    for p in wf.get("spec", {}).get("arguments", {}).get("parameters", []):
        if p.get("name") == name:
            return p.get("value", "")
    return ""


def logs(name, lines=200):
    payload = call("GET", f"/api/v1/workflows/{NAMESPACE}/{name}/log", query={
        "logOptions.container": "main",
        "logOptions.tailLines": str(lines),
    }, raw=True)
    out = []
    for line in payload.decode(errors="replace").splitlines():
        try:
            out.append(json.loads(line).get("result", {}).get("content", ""))
        except ValueError:
            continue
    return ANSI.sub("", "\n".join(out)).strip()


def cmd_submit(args):
    brief = args.brief if args.brief not in (None, "-") else sys.stdin.read()
    brief = brief.strip()
    if not brief:
        raise ArgoError("the brief is empty")
    if len(brief.encode()) > MAX_BRIEF_BYTES:
        raise ArgoError(f"the brief is longer than {MAX_BRIEF_BYTES} bytes")
    # opencode would read a leading "-" as a flag.
    if brief.startswith("-"):
        brief = "Task:\n" + brief
    if not 1 <= args.timeout_minutes <= MAX_TIMEOUT_MINUTES:
        raise ArgoError(f"--timeout-minutes must be between 1 and {MAX_TIMEOUT_MINUTES}")
    # Argo would expand "{{...}}" in parameter values; titles are plain text.
    title = " ".join(args.title.replace("{", "").replace("}", "").split())[:80]
    encoded = base64.b64encode(brief.encode()).decode()
    wf = call("POST", f"/api/v1/workflows/{NAMESPACE}/submit", body={
        "namespace": NAMESPACE,
        "resourceKind": "WorkflowTemplate",
        "resourceName": TEMPLATE,
        "submitOptions": {
            "parameters": [
                f"brief={encoded}",
                f"title={title}",
                f"timeout={args.timeout_minutes * 60}",
            ],
            "labels": SOURCE_LABEL,
        },
    })
    name = wf["metadata"]["name"]
    print(f"Started task {name}: {title or '(untitled)'}")
    print(f"Timeout: {args.timeout_minutes} minutes")
    print(f"Watch: {UI_URL}/workflows/{NAMESPACE}/{name}")


def cmd_status(args):
    wf = call("GET", f"/api/v1/workflows/{NAMESPACE}/{args.task}")
    status = wf.get("status", {})
    phase = status.get("phase") or "Pending"
    print(f"Task: {args.task}")
    print(f"Title: {param(wf, 'title') or '(untitled)'}")
    print(f"Phase: {phase}")
    if status.get("message"):
        print(f"Message: {status['message']}")
    print(f"Started: {status.get('startedAt', '-')}  Finished: {status.get('finishedAt', '-')}")
    print(f"Watch: {UI_URL}/workflows/{NAMESPACE}/{args.task}")
    try:
        text = logs(args.task)
    except ArgoError as exc:
        text = f"(logs unavailable: {exc})"
    prs = PR_URL.findall(text)
    if prs:
        print(f"PR: {prs[-1]}")
    if text:
        tail = "\n".join(text.splitlines()[-40:])
        print(f"\nLast output:\n{tail}")


def cmd_list(args):
    data = call("GET", f"/api/v1/workflows/{NAMESPACE}", query={
        "listOptions.labelSelector": f"workflows.argoproj.io/workflow-template={TEMPLATE}",
    })
    items = sorted(data.get("items") or [],
                   key=lambda wf: wf["metadata"].get("creationTimestamp", ""), reverse=True)
    if not items:
        print("No tasks.")
    for wf in items[: args.limit]:
        meta, status = wf["metadata"], wf.get("status", {})
        print(f"{meta['name']}  {status.get('phase') or 'Pending':9}  "
              f"{meta.get('creationTimestamp', '')}  {param(wf, 'title')}")


def cmd_stop(args):
    call("PUT", f"/api/v1/workflows/{NAMESPACE}/{args.task}/stop",
         body={"namespace": NAMESPACE, "name": args.task})
    print(f"Stopping task {args.task}. Its logs stay available until it is cleaned up.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("submit", help="start a task")
    p.add_argument("brief", nargs="?", help='task text, or "-"/omitted to read stdin')
    p.add_argument("--title", default="")
    p.add_argument("--timeout-minutes", type=int, default=45)
    p.set_defaults(func=cmd_submit)
    p = sub.add_parser("status", help="show a task's state and output")
    p.add_argument("task")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("list", help="list recent tasks")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("stop", help="stop a running task")
    p.add_argument("task")
    p.set_defaults(func=cmd_stop)
    args = parser.parse_args()
    try:
        args.func(args)
    except ArgoError as exc:
        print(f"opencode: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
