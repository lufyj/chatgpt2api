from __future__ import annotations

import copy
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Callable

from fastapi import HTTPException


TASK_RETENTION_SECONDS = 24 * 60 * 60
DEFAULT_POLL_AFTER_MS = 2000


def _extract_error_message(exc: Exception) -> tuple[str, int | None]:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("error") or detail.get("message") or detail).strip()
        else:
            message = str(detail).strip()
        return message or "task failed", exc.status_code
    return str(exc).strip() or exc.__class__.__name__, None


class AsyncTaskService:
    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="image-task")
        self._lock = Lock()
        self._tasks: dict[str, dict[str, object]] = {}

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def create_task(
        self,
        *,
        model: str | None,
        runner: Callable[[], dict[str, object]],
        status_url_builder: Callable[[str], str],
        poll_after_ms: int = DEFAULT_POLL_AFTER_MS,
    ) -> dict[str, object]:
        task_id = f"task_{uuid.uuid4().hex}"
        created = int(time.time())
        status_url = status_url_builder(task_id)
        task = {
            "id": task_id,
            "object": "generation.task",
            "created": created,
            "model": str(model or "").strip() or None,
            "status": "queued",
            "progress": 0,
            "poll_after_ms": poll_after_ms,
            "task": {
                "id": task_id,
                "object": "generation.task",
                "status": "queued",
                "status_url": status_url,
                "poll_after_ms": poll_after_ms,
            },
            "_expires_at": created + TASK_RETENTION_SECONDS,
        }
        with self._lock:
            self._prune_locked()
            self._tasks[task_id] = task

        created_snapshot = self._public_task(task)
        self._executor.submit(self._run_task, task_id, runner)
        return created_snapshot

    def get_task(self, task_id: str) -> dict[str, object] | None:
        with self._lock:
            self._prune_locked()
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return self._public_task(task)

    def _run_task(self, task_id: str, runner: Callable[[], dict[str, object]]) -> None:
        self._update_task(task_id, status="in_progress", progress=25)
        try:
            result = runner()
        except Exception as exc:
            message, status_code = _extract_error_message(exc)
            error_payload: dict[str, object] = {
                "message": message,
                "type": "server_error",
            }
            if status_code is not None:
                error_payload["status_code"] = status_code
            self._update_task(task_id, status="failed", progress=100, error=error_payload)
            return

        self._update_task(task_id, status="completed", progress=100, result=result)

    def _update_task(self, task_id: str, *, status: str, progress: int, result: object = None, error: object = None) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["status"] = status
            task["progress"] = progress
            nested = task.get("task")
            if isinstance(nested, dict):
                nested["status"] = status
            if result is not None:
                task["result"] = result
                task.pop("error", None)
            elif error is not None:
                task["error"] = error
                task.pop("result", None)
            task["_expires_at"] = int(time.time()) + TASK_RETENTION_SECONDS

    def _prune_locked(self) -> None:
        now = int(time.time())
        expired_ids = [
            task_id
            for task_id, task in self._tasks.items()
            if int(task.get("_expires_at") or 0) <= now
        ]
        for task_id in expired_ids:
            self._tasks.pop(task_id, None)

    @staticmethod
    def _public_task(task: dict[str, object]) -> dict[str, object]:
        public_task = copy.deepcopy(task)
        public_task.pop("_expires_at", None)
        if public_task.get("model") is None:
            public_task.pop("model", None)
        return public_task


task_service = AsyncTaskService()
