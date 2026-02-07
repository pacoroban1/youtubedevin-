"""
Job tracking for long-running operations.

This is intentionally simple: jobs are persisted in Postgres (JSONB fields) so
the UI can poll status/progress without keeping state only in memory.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


_UNSET = object()


def _jsonify(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return v


@dataclass
class Job:
    id: str
    job_type: str
    status: str
    video_id: Optional[str]
    current_step: Optional[str]
    progress: float
    request: Optional[dict]
    steps: Optional[dict]
    result: Optional[dict]
    error: Optional[dict]
    events: Optional[list]
    created_at: Optional[str]
    updated_at: Optional[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "video_id": self.video_id,
            "current_step": self.current_step,
            "progress": self.progress,
            "request": self.request,
            "steps": self.steps,
            "result": self.result,
            "error": self.error,
            "events": self.events,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobStore:
    def __init__(self, db):
        self.db = db
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self.db.get_session() as session:
            session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                      id TEXT PRIMARY KEY,
                      job_type TEXT NOT NULL,
                      status TEXT NOT NULL,
                      video_id TEXT,
                      current_step TEXT,
                      progress FLOAT DEFAULT 0,
                      request JSONB,
                      steps JSONB,
                      result JSONB,
                      error JSONB,
                      events JSONB,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            )
            session.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);"))
            session.commit()
        self._schema_ready = True

    @staticmethod
    def init_steps(step_names: List[str]) -> Dict[str, Dict[str, Any]]:
        return {name: {"status": "pending"} for name in step_names}

    def create_job(
        self,
        job_type: str,
        request: Optional[dict] = None,
        *,
        video_id: Optional[str] = None,
        steps: Optional[dict] = None,
    ) -> Job:
        self.ensure_schema()
        job_id = str(uuid.uuid4())
        req_json = json.dumps(request or {})
        steps_json = json.dumps(steps or {})
        events_json = json.dumps([{"ts": _now_iso(), "level": "info", "msg": "job created"}])

        with self.db.get_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO jobs (id, job_type, status, video_id, current_step, progress, request, steps, events)
                    VALUES (:id, :job_type, :status, :video_id, NULL, 0,
                            CAST(:request AS JSONB), CAST(:steps AS JSONB), CAST(:events AS JSONB))
                    """
                ),
                {
                    "id": job_id,
                    "job_type": job_type,
                    "status": "queued",
                    "video_id": video_id,
                    "request": req_json,
                    "steps": steps_json,
                    "events": events_json,
                },
            )
            session.commit()

        return self.get_job(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        video_id: Optional[str] = None,
        current_step: Any = _UNSET,
        progress: Optional[float] = None,
        steps: Optional[dict] = None,
        result: Optional[dict] = None,
        error: Optional[dict] = None,
    ) -> None:
        self.ensure_schema()

        fields = []
        params: Dict[str, Any] = {"id": job_id}

        if status is not None:
            fields.append("status = :status")
            params["status"] = status
        if video_id is not None:
            fields.append("video_id = :video_id")
            params["video_id"] = video_id
        if current_step is not _UNSET:
            fields.append("current_step = :current_step")
            params["current_step"] = current_step
        if progress is not None:
            fields.append("progress = :progress")
            params["progress"] = progress
        if steps is not None:
            fields.append("steps = CAST(:steps AS JSONB)")
            params["steps"] = json.dumps(steps)
        if result is not None:
            fields.append("result = CAST(:result AS JSONB)")
            params["result"] = json.dumps(result)
        if error is not None:
            fields.append("error = CAST(:error AS JSONB)")
            params["error"] = json.dumps(error)

        if not fields:
            return

        with self.db.get_session() as session:
            session.execute(
                text(
                    f"""
                    UPDATE jobs
                    SET {", ".join(fields)},
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                params,
            )
            session.commit()

    def append_event(self, job_id: str, msg: str, *, level: str = "info") -> None:
        self.ensure_schema()
        event = json.dumps([{"ts": _now_iso(), "level": level, "msg": msg}])
        with self.db.get_session() as session:
            session.execute(
                text(
                    """
                    UPDATE jobs
                    SET events = COALESCE(events, '[]'::jsonb) || CAST(:event AS JSONB),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"id": job_id, "event": event},
            )
            session.commit()

    def get_job(self, job_id: str) -> Job:
        self.ensure_schema()
        with self.db.get_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT id, job_type, status, video_id, current_step, progress,
                           request, steps, result, error, events, created_at, updated_at
                    FROM jobs
                    WHERE id = :id
                    """
                ),
                {"id": job_id},
            ).fetchone()

        if not row:
            raise KeyError(f"Job not found: {job_id}")

        m = row._mapping
        return Job(
            id=m["id"],
            job_type=m["job_type"],
            status=m["status"],
            video_id=m.get("video_id"),
            current_step=m.get("current_step"),
            progress=float(m.get("progress") or 0.0),
            request=_jsonify(m.get("request")),
            steps=_jsonify(m.get("steps")),
            result=_jsonify(m.get("result")),
            error=_jsonify(m.get("error")),
            events=_jsonify(m.get("events")),
            created_at=m.get("created_at").isoformat() if m.get("created_at") else None,
            updated_at=m.get("updated_at").isoformat() if m.get("updated_at") else None,
        )

    def list_jobs(self, limit: int = 20) -> List[Job]:
        self.ensure_schema()
        with self.db.get_session() as session:
            rows = session.execute(
                text(
                    """
                    SELECT id, job_type, status, video_id, current_step, progress,
                           request, steps, result, error, events, created_at, updated_at
                    FROM jobs
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).fetchall()

        out: List[Job] = []
        for row in rows:
            m = row._mapping
            out.append(
                Job(
                    id=m["id"],
                    job_type=m["job_type"],
                    status=m["status"],
                    video_id=m.get("video_id"),
                    current_step=m.get("current_step"),
                    progress=float(m.get("progress") or 0.0),
                    request=_jsonify(m.get("request")),
                    steps=_jsonify(m.get("steps")),
                    result=_jsonify(m.get("result")),
                    error=_jsonify(m.get("error")),
                    events=_jsonify(m.get("events")),
                    created_at=m.get("created_at").isoformat() if m.get("created_at") else None,
                    updated_at=m.get("updated_at").isoformat() if m.get("updated_at") else None,
                )
            )
        return out
