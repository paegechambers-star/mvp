"""
Hintergrund-Jobs für die Desktop-App.

Lange Schritte (Bible, Kapitel, Komplettlauf, Agent) laufen in Threads. Pro
Buch (bzw. Agent-Sitzung) darf nur ein Job gleichzeitig laufen — sonst könnten
zwei Schreiber dieselben Kapitel-Versionen und Register-IDs belegen.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


class JobConflict(RuntimeError):
    """Für diese Ressource läuft bereits ein Job."""


@dataclass
class Job:
    id: str
    kind: str
    resource: str
    status: str = "queued"  # queued | running | done | error
    log: List[str] = field(default_factory=list)
    result: Any = None
    error: str = ""
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


JobFn = Callable[[Callable[[str], None]], Any]


class JobManager:
    def __init__(self, workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scriptor-job")
        self._jobs: Dict[str, Job] = {}
        self._busy: Dict[str, str] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, resource: str, fn: JobFn) -> Job:
        with self._lock:
            if resource in self._busy:
                raise JobConflict(f"Für '{resource}' läuft bereits Job {self._busy[resource]}")
            job = Job(id=uuid.uuid4().hex[:12], kind=kind, resource=resource)
            self._jobs[job.id] = job
            self._busy[resource] = job.id
        self._pool.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: JobFn) -> None:
        job.status = "running"
        try:
            job.result = fn(job.log.append)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - Fehler gehören in den Job, nicht in den Thread
            job.error = f"{type(exc).__name__}: {exc}"
            job.log.append(traceback.format_exc(limit=3))
            job.status = "error"
        finally:
            job.finished = datetime.now(timezone.utc).isoformat()
            with self._lock:
                self._busy.pop(job.resource, None)

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)[:limit]

    def wait(self, job_id: str, timeout: float = 30.0) -> Job:
        """Nur für Tests: blockiert, bis der Job fertig ist."""
        import time

        end = time.monotonic() + timeout
        job = self._jobs[job_id]
        while job.status in ("queued", "running") and time.monotonic() < end:
            time.sleep(0.01)
        return job

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
