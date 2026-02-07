"""
Amharic Recap Autopilot - Runner Service
Main FastAPI application that orchestrates the video recap pipeline.
"""

import asyncio
from datetime import datetime
import traceback
import logging
import uuid
import json
import shutil

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
from pathlib import Path
import httpx
from urllib.parse import urlparse

from modules.discovery import ChannelDiscovery
from modules.ingest import VideoIngest
from modules.jobs import JobStore
from modules.script import ScriptGenerator
from modules.voice import VoiceGenerator
from modules.timing import TimingMatcher
from modules.thumbnail import ThumbnailGenerator
from modules.upload import YouTubeUploader
from modules.growth import GrowthLoop
from modules.database import Database
from modules.gemini_client import gemini
from modules.gemini_client import GeminiCallFailed, GeminiNotConfigured

app = FastAPI(
    title="Amharic Recap Autopilot",
    description="End-to-end YouTube automation for Amharic recap videos",
    version="1.0.0"
)

logger = logging.getLogger("runner")

# --- Global JSON error handling + request ids ---

@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    # Keep FastAPI's default JSON shape for HTTPException ("detail": ...),
    # but ensure we always include an X-Request-ID header.
    resp = await http_exception_handler(request, exc)
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        resp.headers["X-Request-ID"] = request_id
    return resp


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "error": "validation_error",
            "message": "Invalid request",
            "details": exc.errors(),
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    logger.error("Unhandled exception request_id=%s: %s", request_id, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": "internal_error",
            "message": "Internal Server Error",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )

# Mount media (static)
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/app/media"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

# Mount UI (static)
UI_DIR = (Path(__file__).parent / "ui").resolve()
if UI_DIR.exists():
    # `html=True` allows `/ui/` to serve index.html.
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

# Initialize database
db = Database()

# Initialize modules
discovery = ChannelDiscovery(db)
ingest = VideoIngest(db)
script_gen = ScriptGenerator(db)
voice_gen = VoiceGenerator(db)
timing = TimingMatcher(db)
thumbnail_gen = ThumbnailGenerator(db)
uploader = YouTubeUploader(db)
growth = GrowthLoop(db)
job_store = JobStore(db)

# In-memory task handles for cancellation
_job_tasks: dict[str, asyncio.Task] = {}


class FullPipelineRequest(BaseModel):
    video_id: Optional[str] = None
    auto_select: bool = True

class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "am"
    source_lang: Optional[str] = None

# --- Helper Functions ---

def _utc_ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def _steps_progress(steps: Dict[str, Any]) -> float:
    if not steps: return 0.0
    done = sum(1 for s in steps.values() if s.get("status") in ("ok", "error"))
    total = sum(1 for s in steps.values() if s.get("status") not in ("skipped",))
    return float(done) / float(total) if total else 0.0

def _mark_step(steps: Dict[str, Any], name: str, status: str, **extra: Any) -> None:
    cur = dict(steps.get(name) or {})
    cur["status"] = status
    for k, v in extra.items():
        cur[k] = v
    steps[name] = cur

def _req_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""

def _json(request: Request, status_code: int, payload: Dict[str, Any]) -> JSONResponse:
    # Ensure all manual error responses include request_id for debugging.
    if payload.get("status") == "error" and "request_id" not in payload:
        payload["request_id"] = _req_id(request)
    return JSONResponse(status_code=status_code, content=payload, headers={"X-Request-ID": _req_id(request)})

def _cached_full_script(video_id: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort cache layer: if we already have a full_script stored in the DB,
    return the parsed JSON object. This avoids re-calling Gemini (cost + 429s).
    """
    try:
        s = db.get_script(video_id)
        if not s:
            return None
        raw = s.get("full_script")
        if not raw:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            return json.loads(raw)
    except Exception:
        return None
    return None

async def _run_pipeline_full_job(job_id: str, request: FullPipelineRequest) -> None:
    step_names = ["discover", "ingest", "script", "voice", "render", "thumbnail", "upload", "distribute"]
    steps = JobStore.init_steps(step_names)
    if request.video_id:
        _mark_step(steps, "discover", "skipped")

    job_store.update_job(job_id, status="running", steps=steps, current_step="discover", progress=0.0)
    job_store.append_event(job_id, "pipeline started")

    try:
        video_id = request.video_id
        if not video_id and request.auto_select:
            _mark_step(steps, "discover", "running", started_at=_utc_ts())
            job_store.update_job(job_id, steps=steps, current_step="discover")
            
            discovery_result = await discovery.discover_top_channels()
            if discovery_result.get("videos"):
                video_id = discovery_result["videos"][0]["video_id"]
            
            if not video_id:
                raise RuntimeError("auto-select found no videos")
            
            _mark_step(steps, "discover", "ok", ended_at=_utc_ts(), video_id=video_id)
            job_store.update_job(job_id, steps=steps, video_id=video_id, progress=_steps_progress(steps))
        elif not video_id:
            raise RuntimeError("missing video_id")

        job_store.update_job(job_id, video_id=video_id)

        async def run_step(name: str, fn):
            _mark_step(steps, name, "running", started_at=_utc_ts())
            job_store.update_job(job_id, steps=steps, current_step=name)
            job_store.append_event(job_id, f"{name} started")
            out = await fn()
            _mark_step(steps, name, "ok", ended_at=_utc_ts(), summary=str(out)[:100])
            job_store.update_job(job_id, steps=steps, progress=_steps_progress(steps))
            job_store.append_event(job_id, f"{name} ok")
            return out

        # Execution
        await run_step("ingest", lambda: ingest.process_video(video_id))
        await run_step("script", lambda: script_gen.generate_full_script(video_id))
        await run_step("voice", lambda: voice_gen.generate_narration(video_id))
        await run_step("render", lambda: timing.render_with_alignment(video_id))
        await run_step("thumbnail", lambda: thumbnail_gen.generate_thumbnails(video_id))
        await run_step("upload", lambda: uploader.upload_video(video_id))
        await run_step("distribute", lambda: growth.distribute_and_track(video_id))

        job_store.update_job(job_id, status="succeeded", current_step=None, progress=1.0, steps=steps)
        job_store.append_event(job_id, "pipeline succeeded")

    except Exception as e:
        logger = logging.getLogger("pipeline")
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        job_store.update_job(job_id, status="failed", error={"message": str(e)})
        job_store.append_event(job_id, f"failed: {e}", level="error")

# --- Endpoints ---

@app.get("/")
async def root():
    # Convenience redirect to UI if mounted.
    if UI_DIR.exists():
        return RedirectResponse(url="/ui/")
    return {"status": "ok"}

@app.get("/api/config")
async def get_config(request: Request):
    """Non-secret config summary."""
    return _json(request, 200, {
        "narrator_persona": (os.getenv("NARRATOR_PERSONA") or "futuristic captain").strip(),
        "zthumb": {
            "enabled": False,
        },
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY"))
    })

@app.post("/api/script/{video_id}")
async def generate_script_preview(video_id: str, request: Request, force: bool = False):
    """Legacy preview endpoint."""
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        return _json(request, 400, {"status": "error", "error": "missing_env", "message": "GEMINI_API_KEY is required", "video_id": video_id})

    if not force:
        cached = _cached_full_script(video_id)
        if cached:
            beats = cached.get("beats") or []
            hook = (cached.get("hook") or "").strip()
            out = {
                "script_id": video_id,
                "hook_text": hook,
                "segments_count": len(beats),
                "full_script_length": len(json.dumps(cached, ensure_ascii=False)),
                "quality_score": cached.get("quality_score", 0.8),
                "script_preview": hook,
                "cached": True,
            }
            return _json(request, 200, {"status": "success", "video_id": video_id, **out})

    # If transcript missing, attempt ingest automatically to avoid confusing failures.
    try:
        t = db.get_transcript(video_id)
        if not t or not t.get("cleaned_transcript"):
            await ingest.process_video(video_id)
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "ingest_failed", "message": str(e), "video_id": video_id})

    try:
        out = await script_gen.generate_amharic_script(video_id)
        return _json(request, 200, {"status": "success", "video_id": video_id, **out})
    except GeminiNotConfigured:
        return _json(request, 400, {"status": "error", "error": "missing_env", "message": "GEMINI_API_KEY is required", "video_id": video_id})
    except GeminiCallFailed as e:
        return _json(request, 502, {"status": "error", "error": "script_generation_failed", "message": "Gemini call failed", "video_id": video_id, "attempts": e.attempts_as_dicts()})
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "script_generation_failed", "message": str(e), "video_id": video_id})

@app.post("/api/script/full/{video_id}")
async def generate_full_script(video_id: str, request: Request, force: bool = False):
    """Generate full structured script."""
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        return _json(request, 400, {"status": "error", "error": "missing_env", "message": "GEMINI_API_KEY is required", "video_id": video_id})

    if not force:
        cached = _cached_full_script(video_id)
        if cached:
            # Keep backward-compatible field name; downstream expects this.
            out = dict(cached)
            out["full_script"] = json.dumps(cached, ensure_ascii=False)
            out["cached"] = True
            return _json(request, 200, {"status": "success", "video_id": video_id, **out})

    try:
        t = db.get_transcript(video_id)
        if not t or not t.get("cleaned_transcript"):
            await ingest.process_video(video_id)
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "ingest_failed", "message": str(e), "video_id": video_id})

    try:
        out = await script_gen.generate_full_script(video_id)
        return _json(request, 200, {"status": "success", "video_id": video_id, **out})
    except GeminiNotConfigured:
        return _json(request, 400, {"status": "error", "error": "missing_env", "message": "GEMINI_API_KEY is required", "video_id": video_id})
    except GeminiCallFailed as e:
        return _json(request, 502, {"status": "error", "error": "script_generation_failed", "message": "Gemini call failed", "video_id": video_id, "attempts": e.attempts_as_dicts()})
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "script_generation_failed", "message": str(e), "video_id": video_id})

@app.post("/api/tts/{video_id}")
@app.post("/api/voice/{video_id}") # Alias
async def generate_tts(video_id: str, request: Request, force: bool = False):
    """Generate narration audio."""
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        return _json(request, 400, {"status": "error", "error": "missing_env", "message": "GEMINI_API_KEY is required", "video_id": video_id})

    # Idempotent: if we already generated audio for this video, return it instead
    # of re-running TTS (which can be slow / flaky / expensive).
    if not force:
        try:
            tts_path = MEDIA_DIR / "tts" / f"{video_id}.wav"
            narration_path = MEDIA_DIR / "audio" / video_id / "narration.wav"
            if (not tts_path.exists()) and narration_path.exists():
                tts_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(narration_path, tts_path)
            if tts_path.exists():
                a = db.get_audio(video_id) or {}
                dur = float(a.get("duration_seconds") or 0.0) or float(voice_gen._get_wav_duration(str(tts_path)) or 0.0)
                return _json(
                    request,
                    200,
                    {
                        "status": "success",
                        "video_id": video_id,
                        "audio_id": a.get("id"),
                        "audio_path": str(tts_path),
                        "audio_url": f"/api/media/tts/{video_id}.wav",
                        "audio_file": a.get("audio_file_path") or str(narration_path),
                        "narration_url": f"/api/media/audio/{video_id}/narration.wav",
                        "duration_sec": dur,
                        "duration": dur,
                        "model_used": "cached",
                        "attempts": [],
                        "cached": True,
                    },
                )
        except Exception:
            # Cache is best-effort; fall through to generation.
            pass

    # Ensure script exists; auto-generate if missing.
    try:
        s = db.get_script(video_id)
        if not s or not s.get("full_script"):
            t = db.get_transcript(video_id)
            if not t or not t.get("cleaned_transcript"):
                await ingest.process_video(video_id)
            await script_gen.generate_full_script(video_id)
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "precondition_failed", "message": str(e), "video_id": video_id})

    out = await voice_gen.generate_narration(video_id)
    if isinstance(out, dict) and out.get("status") == "error":
        code = 400 if out.get("error") == "missing_env" else 502
        return _json(request, code, out)
    return _json(request, 200, out if isinstance(out, dict) else {"status": "success", "video_id": video_id, "result": out})

@app.post("/api/thumbnail/{video_id}")
async def generate_thumbnail(video_id: str, request: Request):
    """Generate thumbnails."""
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        return _json(request, 400, {"status": "error", "error": "missing_env", "message": "GEMINI_API_KEY is required", "video_id": video_id})

    out = await thumbnail_gen.generate_thumbnails(video_id)
    if isinstance(out, dict) and out.get("status") == "error":
        code = 400 if out.get("error") == "missing_env" else 502
        return _json(request, code, out)
    return _json(request, 200, out if isinstance(out, dict) else {"status": "success", "video_id": video_id, "result": out})

@app.post("/api/translate")
async def translate_text(req: TranslateRequest):
    """Translate text using Gemini."""
    prompt = f"Translate the following text to {req.target_lang}. Return ONLY the translation.\n\nText: {req.text}"
    translated = gemini.generate_text(prompt)
    return {"text": req.text, "translated": translated, "target_lang": req.target_lang}

@app.post("/api/jobs/pipeline/full")
async def create_pipeline_full_job(request: FullPipelineRequest):
    """Run full pipeline as async job."""
    step_names = ["discover", "ingest", "script", "voice", "render", "thumbnail", "upload", "distribute"]
    steps = JobStore.init_steps(step_names)
    
    job = job_store.create_job(
        "pipeline_full",
        request=request.model_dump(),
        video_id=request.video_id,
        steps=steps,
    )

    task = asyncio.create_task(_run_pipeline_full_job(job.id, request))
    _job_tasks[job.id] = task
    task.add_done_callback(lambda _t, jid=job.id: _job_tasks.pop(jid, None))

    return {"status": "success", "job": job.to_dict()}

@app.get("/api/jobs")
async def list_jobs(limit: int = 20, request: Request = None):
    try:
        jobs = job_store.list_jobs(limit=limit)
        return _json(request, 200, {"status": "success", "jobs": [j.to_dict() for j in jobs]})
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "jobs_list_failed", "message": str(e)})

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    return {"status": "success", "job": job_store.get_job(job_id).to_dict()}

@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    task = _job_tasks.get(job_id)
    if not task:
        return _json(request, 404, {"status": "error", "error": "job_not_found", "message": f"Job not running: {job_id}"})
    try:
        job_store.update_job(job_id, status="cancel_requested")
        job_store.append_event(job_id, "cancel requested", level="warn")
        task.cancel()
        job_store.update_job(job_id, status="canceled", current_step=None)
        job_store.append_event(job_id, "canceled", level="warn")
        return _json(request, 200, {"status": "success", "job_id": job_id})
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "cancel_failed", "message": str(e), "job_id": job_id})

@app.post("/api/discover")
async def discover(request: Request):
    out = await discovery.discover_top_channels()
    # discovery may return {"error": "..."} if not configured; keep JSON always.
    status = "success" if not out.get("error") else "error"
    return _json(request, 200, {"status": status, **out})

@app.post("/api/ingest/{video_id}")
async def ingest_video(video_id: str, request: Request):
    try:
        out = await ingest.process_video(video_id)
        return _json(request, 200, {"status": "success", **out})
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "ingest_failed", "message": str(e), "video_id": video_id})

@app.post("/api/render/{video_id}")
async def render_video(video_id: str, request: Request):
    try:
        out = await timing.render_with_alignment(video_id)
        return _json(request, 200, {"status": "success", **out})
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "render_failed", "message": str(e), "video_id": video_id})

@app.post("/api/upload/{video_id}")
async def upload_video(video_id: str, request: Request):
    try:
        out = await uploader.upload_video(video_id)
        return _json(request, 200, {"status": "success", **out})
    except Exception as e:
        return _json(request, 502, {"status": "error", "error": "upload_failed", "message": str(e), "video_id": video_id})

@app.get("/api/report/daily")
async def daily_report(request: Request):
    # Growth loop has no dedicated report method; keep a minimal snapshot for UI.
    return _json(request, 200, {"status": "success", "message": "not_implemented", "hint": "daily reporting not wired yet"})

@app.get("/api/verify/voice")
async def verify_voice(request: Request):
    return _json(
        request,
        200,
        {
            "status": "success" if gemini.is_configured() else "error",
            "provider": "gemini",
            "gemini_configured": gemini.is_configured(),
            "note": "TTS is Gemini-only; endpoint checks GEMINI_API_KEY presence (no secrets).",
        },
    )

@app.get("/api/verify/translate")
async def verify_translate(request: Request):
    return _json(
        request,
        200,
        {
            "status": "success" if gemini.is_configured() else "error",
            "provider": "gemini",
            "gemini_configured": gemini.is_configured(),
            "note": "Translation is Gemini-only in this build.",
        },
    )

@app.get("/api/verify/zthumb")
async def verify_zthumb(request: Request):
    return _json(
        request,
        200,
        {
            "status": "success",
            "available": False,
            "note": "ZThumb is disabled in this build (Gemini-only).",
        },
    )

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
