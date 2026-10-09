"""
title: OpenCode Tasks
description: Run OpenCode coding tasks on the homelab repo (danjuv/homelab) via Argo Workflows. Each task clones main, makes the change and opens a PR.
author: danjuv
version: 0.1.0
license: MIT
requirements:
"""

import asyncio
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel, Field

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
TASK_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{0,252}$")
LABEL_VALUE = re.compile(r"[^A-Za-z0-9_.-]")
MAX_BRIEF_BYTES = 16 * 1024
MAX_TIMEOUT_MINUTES = 120


class ArgoError(Exception):
    pass


class Tools:
    class Valves(BaseModel):
        ARGO_URL: str = Field(
            default="http://argo-workflows-server.argo-workflows.svc.cluster.local:2746",
            description="Argo Server API (in-cluster).",
        )
        UI_URL: str = Field(
            default="https://argo-workflows.home.lab",
            description="Argo Workflows UI, used for links.",
        )
        TOKEN_FILE: str = Field(
            default="/var/run/secrets/argo-workflows/token",
            description="Projected ServiceAccount token sent to the Argo Server.",
        )
        NAMESPACE: str = Field(default="opencode")
        TEMPLATE: str = Field(default="opencode-task")
        ADMIN_ONLY: bool = Field(
            default=True,
            description="Only Open WebUI admins may use this tool.",
        )
        ALLOWED_EMAILS: str = Field(
            default="",
            description="Comma-separated emails allowed besides admins (empty: admins only).",
        )
        REQUIRE_CONFIRMATION: bool = Field(
            default=True,
            description="Ask the user to confirm before starting or stopping a task.",
        )
        DEFAULT_TIMEOUT_MINUTES: int = Field(default=45, ge=1, le=MAX_TIMEOUT_MINUTES)
        HTTP_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=120)

    def __init__(self):
        self.valves = self.Valves()

    def _check_user(self, user: Optional[dict]) -> None:
        user = user or {}
        if user.get("role") == "admin":
            return
        allowed = {e.strip().lower() for e in self.valves.ALLOWED_EMAILS.split(",") if e.strip()}
        if not self.valves.ADMIN_ONLY and not allowed:
            return
        if (user.get("email") or "").lower() in allowed:
            return
        raise ArgoError("you are not allowed to run OpenCode tasks")

    def _call(self, method: str, path: str, body: Any = None, query: Optional[dict] = None, raw: bool = False):
        try:
            with open(self.valves.TOKEN_FILE) as f:
                token = f.read().strip()
        except OSError as exc:
            raise ArgoError(f"cannot read {self.valves.TOKEN_FILE}: {exc.strerror}") from None
        url = self.valves.ARGO_URL.rstrip("/") + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.valves.HTTP_TIMEOUT_SECONDS) as resp:
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

    async def _acall(self, *args, **kwargs):
        return await asyncio.to_thread(self._call, *args, **kwargs)

    def _link(self, name: str) -> str:
        return f"{self.valves.UI_URL.rstrip('/')}/workflows/{self.valves.NAMESPACE}/{name}"

    @staticmethod
    def _param(wf: dict, name: str) -> str:
        for p in wf.get("spec", {}).get("arguments", {}).get("parameters", []):
            if p.get("name") == name:
                return p.get("value", "")
        return ""

    @staticmethod
    def _task_name(task: str) -> str:
        task = (task or "").strip()
        if not TASK_NAME.match(task):
            raise ArgoError(f"invalid task name: {task!r}")
        return task

    async def _status(self, emitter: Optional[Callable[[dict], Awaitable[None]]], text: str, done: bool = False):
        if emitter:
            await emitter({"type": "status", "data": {"description": text, "done": done}})

    async def _confirm(self, event_call: Optional[Callable[[dict], Awaitable[Any]]], title: str, message: str) -> bool:
        if not self.valves.REQUIRE_CONFIRMATION:
            return True
        if not event_call:
            return False
        answer = await event_call({"type": "confirmation", "data": {"title": title, "message": message}})
        return bool(answer)

    async def submit_coding_task(
        self,
        brief: str,
        title: str,
        timeout_minutes: Optional[int] = None,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
        __event_call__: Optional[Callable[[dict], Awaitable[Any]]] = None,
    ) -> str:
        """
        Start an OpenCode coding agent on the homelab Git repo (danjuv/homelab: k3s manifests, ArgoCD apps, Helm values, images, tools). The agent works in a fresh clone of main, makes the change, validates it and opens a pull request; it cannot merge or push to main. Runs asynchronously and takes minutes; use get_coding_task_status afterwards. Only call this when the user clearly asks for a code/repo change.
        :param brief: Complete, self-contained task description for the agent: goal, relevant files or apps, constraints and acceptance criteria. The agent sees nothing else from this chat.
        :param title: Short title for the task and PR (max 80 characters).
        :param timeout_minutes: Maximum run time in minutes (1-120). Omit to use the default.
        :return: Task name and a link to follow it.
        """
        try:
            self._check_user(__user__)
            brief = (brief or "").strip()
            if not brief:
                raise ArgoError("the brief is empty")
            if len(brief.encode()) > MAX_BRIEF_BYTES:
                raise ArgoError(f"the brief is longer than {MAX_BRIEF_BYTES} bytes")
            minutes = timeout_minutes or self.valves.DEFAULT_TIMEOUT_MINUTES
            if not 1 <= int(minutes) <= MAX_TIMEOUT_MINUTES:
                raise ArgoError(f"timeout_minutes must be between 1 and {MAX_TIMEOUT_MINUTES}")
            title = " ".join((title or "").replace("{", "").replace("}", "").split())[:80]

            if not await self._confirm(
                __event_call__,
                "Start OpenCode task?",
                f"**{title or '(untitled)'}** (timeout {minutes} min)\n\n{brief[:1500]}",
            ):
                return "The user did not confirm; no task was started."

            user = __user__ or {}
            requester = user.get("name") or user.get("email") or "unknown"
            text = f"{brief}\n\n(Requested by {requester} via Open WebUI.)"
            if text.startswith("-"):
                text = "Task:\n" + text
            labels = ["opencode.home.lab/source=open-webui"]
            user_id = LABEL_VALUE.sub("", str(user.get("id") or ""))[:63].strip("-_.")
            if user_id:
                labels.append(f"opencode.home.lab/owui-user={user_id}")

            await self._status(__event_emitter__, "Submitting OpenCode task...")
            ns = self.valves.NAMESPACE
            wf = await self._acall("POST", f"/api/v1/workflows/{ns}/submit", body={
                "namespace": ns,
                "resourceKind": "WorkflowTemplate",
                "resourceName": self.valves.TEMPLATE,
                "submitOptions": {
                    "parameters": [
                        f"brief={base64.b64encode(text.encode()).decode()}",
                        f"title={title}",
                        f"timeout={int(minutes) * 60}",
                    ],
                    "labels": ",".join(labels),
                },
            })
            name = wf["metadata"]["name"]
            await self._status(__event_emitter__, f"Started {name}", done=True)
            return (
                f"Started OpenCode task {name}: {title or '(untitled)'}\n"
                f"Timeout: {minutes} minutes\n"
                f"Watch: {self._link(name)}\n"
                "A Telegram message is sent when it finishes. Check progress with get_coding_task_status."
            )
        except ArgoError as exc:
            await self._status(__event_emitter__, "OpenCode task failed to start", done=True)
            return f"Error: {exc}"

    async def get_coding_task_status(
        self,
        task: str,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> str:
        """
        Get the phase, PR link and last output lines of an OpenCode coding task.
        :param task: Task (workflow) name returned by submit_coding_task, e.g. opencode-task-abc12.
        :return: Task status report.
        """
        try:
            self._check_user(__user__)
            name = self._task_name(task)
            ns = self.valves.NAMESPACE
            await self._status(__event_emitter__, f"Checking {name}...")
            wf = await self._acall("GET", f"/api/v1/workflows/{ns}/{name}")
            status = wf.get("status", {})
            out = [
                f"Task: {name}",
                f"Title: {self._param(wf, 'title') or '(untitled)'}",
                f"Phase: {status.get('phase') or 'Pending'}",
            ]
            if status.get("message"):
                out.append(f"Message: {status['message']}")
            out.append(f"Started: {status.get('startedAt', '-')}  Finished: {status.get('finishedAt', '-')}")
            out.append(f"Watch: {self._link(name)}")
            pr = (status.get("outputs", {}) or {}).get("parameters", [])
            pr = next((p.get("value") for p in pr if p.get("name") == "pr_url" and p.get("value") not in (None, "-")), None)
            try:
                payload = await self._acall("GET", f"/api/v1/workflows/{ns}/{name}/log", query={
                    "logOptions.container": "main",
                    "logOptions.tailLines": "200",
                }, raw=True)
                lines = []
                for line in payload.decode(errors="replace").splitlines():
                    try:
                        lines.append(json.loads(line).get("result", {}).get("content", ""))
                    except ValueError:
                        continue
                text = ANSI.sub("", "\n".join(lines)).strip()
            except ArgoError as exc:
                text = f"(logs unavailable: {exc})"
            prs = PR_URL.findall(text)
            pr = pr or (prs[-1] if prs else None)
            if pr:
                out.append(f"PR: {pr}")
            if text:
                out.append("\nLast output:\n" + "\n".join(text.splitlines()[-40:]))
            await self._status(__event_emitter__, f"{name}: {status.get('phase') or 'Pending'}", done=True)
            return "\n".join(out)
        except ArgoError as exc:
            await self._status(__event_emitter__, "Status check failed", done=True)
            return f"Error: {exc}"

    async def list_coding_tasks(
        self,
        limit: int = 10,
        __user__: Optional[dict] = None,
    ) -> str:
        """
        List recent OpenCode coding tasks (newest first), from any source.
        :param limit: Maximum number of tasks to list (1-50).
        :return: One line per task: name, phase, created time, title.
        """
        try:
            self._check_user(__user__)
            limit = max(1, min(int(limit or 10), 50))
            ns = self.valves.NAMESPACE
            data = await self._acall("GET", f"/api/v1/workflows/{ns}", query={
                "listOptions.labelSelector": f"workflows.argoproj.io/workflow-template={self.valves.TEMPLATE}",
            })
            items = sorted(data.get("items") or [],
                           key=lambda wf: wf["metadata"].get("creationTimestamp", ""), reverse=True)
            if not items:
                return "No tasks."
            rows = []
            for wf in items[:limit]:
                meta, status = wf["metadata"], wf.get("status", {})
                rows.append(f"{meta['name']}  {status.get('phase') or 'Pending':9}  "
                            f"{meta.get('creationTimestamp', '')}  {self._param(wf, 'title')}")
            return "\n".join(rows)
        except ArgoError as exc:
            return f"Error: {exc}"

    async def stop_coding_task(
        self,
        task: str,
        __user__: Optional[dict] = None,
        __event_call__: Optional[Callable[[dict], Awaitable[Any]]] = None,
    ) -> str:
        """
        Stop a running OpenCode coding task. Only call this when the user asks to stop or cancel a task.
        :param task: Task (workflow) name, e.g. opencode-task-abc12.
        :return: Confirmation message.
        """
        try:
            self._check_user(__user__)
            name = self._task_name(task)
            if not await self._confirm(__event_call__, "Stop OpenCode task?", f"Stop **{name}**?"):
                return "The user did not confirm; the task was not stopped."
            ns = self.valves.NAMESPACE
            await self._acall("PUT", f"/api/v1/workflows/{ns}/{name}/stop",
                              body={"namespace": ns, "name": name})
            return f"Stopping task {name}. Its logs stay available until it is cleaned up."
        except ArgoError as exc:
            return f"Error: {exc}"
