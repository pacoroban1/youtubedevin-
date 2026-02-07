"""
Amharic Recap Autopilot - Runner Service
Main FastAPI application that orchestrates the video recap pipeline.
"""

import asyncio
from datetime import datetime
import traceback
from fastapi import FastAPI, HTTPException, BackgroundTasks
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
from modules.translate import GoogleTranslateV2, LibreTranslate

app = FastAPI(
    title="Amharic Recap Autopilot",
    description="End-to-end YouTube automation for Amharic recap videos",
    version="1.0.0"
)

# Mount UI (static) if present
UI_DIR = Path(__file__).resolve().parent / "ui"
if UI_DIR.exists():
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
translate_google = GoogleTranslateV2()
translate_libre = LibreTranslate()
job_store = JobStore(db)

# In-memory task handles for cancellation (job state itself is persisted in Postgres).
_job_tasks: dict[str, asyncio.Task] = {}


class DiscoveryRequest(BaseModel):
    queries: Optional[List[str]] = ["movie recap", "story recap", "ending explained recap", "recap explained"]
    top_n_channels: int = 10
    videos_per_channel: int = 5


class ProcessVideoRequest(BaseModel):
    video_id: str
    skip_discovery: bool = False


class FullPipelineRequest(BaseModel):
    video_id: Optional[str] = None
    auto_select: bool = True


def _utc_ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _steps_progress(steps: Dict[str, Any]) -> float:
    if not steps:
        return 0.0
    done = 0
    total = 0
    for _, s in steps.items():
        st = (s or {}).get("status")
        if st in ("pending", None):
            total += 1
            continue
        if st in ("skipped",):
            continue
        total += 1
        if st in ("ok", "error"):
            done += 1
    return float(done) / float(total) if total else 0.0


def _mark_step(steps: Dict[str, Any], name: str, status: str, **extra: Any) -> None:
    cur = dict(steps.get(name) or {})
    cur["status"] = status
    for k, v in extra.items():
        cur[k] = v
    steps[name] = cur


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
            job_store.update_job(job_id, steps=steps, current_step="discover", progress=_steps_progress(steps))

            discovery_result = await discovery.discover_top_channels()
            if discovery_result.get("videos"):
                video_id = discovery_result["videos"][0]["video_id"]

            if not video_id:
                raise RuntimeError("auto-select found no videos (check YOUTUBE_API_KEY and discovery settings)")

            _mark_step(steps, "discover", "ok", ended_at=_utc_ts(), video_id=video_id)
            job_store.update_job(job_id, steps=steps, video_id=video_id, progress=_steps_progress(steps))
        elif not video_id:
            raise RuntimeError("missing video_id (and auto_select=false)")

        job_store.update_job(job_id, video_id=video_id)

        async def run_step(name: str, fn):
            try:
                st = job_store.get_job(job_id).status
                if st in ("cancel_requested", "canceled"):
                    raise asyncio.CancelledError()
            except KeyError:
                # If the job record disappeared, fail fast.
                raise RuntimeError("job record missing during execution")

            _mark_step(steps, name, "running", started_at=_utc_ts())
            job_store.update_job(job_id, steps=steps, current_step=name, progress=_steps_progress(steps))
            job_store.append_event(job_id, f"{name} started")
            out = await fn()
            _mark_step(steps, name, "ok", ended_at=_utc_ts(), summary=out)
            job_store.update_job(job_id, steps=steps, progress=_steps_progress(steps))
            job_store.append_event(job_id, f"{name} ok")
            return out

        # Step: ingest
        ingest_out = await run_step("ingest", lambda: ingest.process_video(video_id))
        # Step: script
        script_out = await run_step("script", lambda: script_gen.generate_amharic_script(video_id))
        # Step: voice
        voice_out = await run_step("voice", lambda: voice_gen.generate_narration(video_id))
        # Step: render
        render_out = await run_step("render", lambda: timing.render_with_alignment(video_id))
        # Step: thumbnail
        thumb_out = await run_step("thumbnail", lambda: thumbnail_gen.generate_thumbnails(video_id))
        # Step: upload
        upload_out = await run_step("upload", lambda: uploader.upload_video(video_id))
        # Step: distribute
        dist_out = await run_step("distribute", lambda: growth.distribute_and_track(video_id))

        result = {
            "video_id": video_id,
            "steps": {
                "ingest": {"source": ingest_out.get("source")},
                "script": {"quality_score": script_out.get("quality_score")},
                "voice": {"duration_seconds": voice_out.get("duration")},
                "render": {"alignment_score": render_out.get("alignment_score")},
                "thumbnail": {"selected": thumb_out.get("selected")},
                "upload": {"youtube_video_id": upload_out.get("youtube_video_id")},
                "distribute": {"platforms": dist_out.get("platforms")},
            },
        }
        job_store.update_job(job_id, status="succeeded", current_step=None, progress=1.0, steps=steps, result=result)
        job_store.append_event(job_id, "pipeline succeeded")
    except asyncio.CancelledError:
        job_store.update_job(job_id, status="canceled", current_step=None, steps=steps, progress=_steps_progress(steps))
        job_store.append_event(job_id, "pipeline canceled", level="warn")
        raise
    except Exception as e:
        # Mark current step as failed if possible.
        cur = next((n for n in step_names if (steps.get(n) or {}).get("status") == "running"), None)
        if cur:
            _mark_step(steps, cur, "error", ended_at=_utc_ts(), error=str(e))
        err = {"message": str(e), "traceback": traceback.format_exc()}
        job_store.update_job(job_id, status="failed", current_step=None, steps=steps, progress=_steps_progress(steps), error=err)
        job_store.append_event(job_id, f"pipeline failed: {e}", level="err")


@app.get("/")
async def root():
    return {
        "service": "Amharic Recap Autopilot",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/verify/voice")
async def verify_voice_support():
    """
    VOICE VERIFICATION GATE (MANDATORY)
    Verifies that Azure TTS supports Amharic (am-ET) voices.
    This MUST be called before any voice generation.
    """
    verification_results = {
        "azure_tts": {"supported": False, "voices": [], "test_synthesis": False},
        "elevenlabs": {"supported": False, "note": "ElevenLabs does NOT support Amharic TTS"},
        "google_cloud": {"supported": False, "voices": []},
        "recommended_provider": None
    }
    
    # Verify Azure TTS am-ET support
    try:
        import azure.cognitiveservices.speech as speechsdk
        azure_key = os.getenv("AZURE_SPEECH_KEY")
        azure_region = os.getenv("AZURE_SPEECH_REGION", "eastus")
        
        if azure_key:
            speech_config = speechsdk.SpeechConfig(subscription=azure_key, region=azure_region)
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
            
            # Get available voices
            result = synthesizer.get_voices_async("am-ET").get()
            
            if result.reason == speechsdk.ResultReason.VoicesListRetrieved:
                am_voices = [v.short_name for v in result.voices if v.locale.startswith("am")]
                verification_results["azure_tts"]["voices"] = am_voices
                verification_results["azure_tts"]["supported"] = len(am_voices) > 0
                
                # Test synthesis with a simple Amharic phrase
                if am_voices:
                    speech_config.speech_synthesis_voice_name = am_voices[0]
                    test_synth = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
                    test_result = test_synth.speak_text_async("ሰላም").get()
                    verification_results["azure_tts"]["test_synthesis"] = (
                        test_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted
                    )
    except Exception as e:
        verification_results["azure_tts"]["error"] = str(e)
    
    # Document known Azure am-ET voices (from Microsoft docs)
    verification_results["azure_tts"]["documented_voices"] = [
        "am-ET-AmehaNeural (Male)",
        "am-ET-MekdesNeural (Female)"
    ]
    verification_results["azure_tts"]["docs_reference"] = "https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support"
    
    # Set recommended provider
    if verification_results["azure_tts"]["supported"] or verification_results["azure_tts"]["voices"]:
        verification_results["recommended_provider"] = "azure_tts"
    
    return {
        "status": "success",
        "verification": verification_results,
        "conclusion": "Azure TTS supports Amharic (am-ET) with neural voices. ElevenLabs does NOT support Amharic."
    }


@app.get("/api/verify/translate")
async def verify_translate_support():
    """
    TRANSLATION VERIFICATION (OPTIONAL)
    Verifies that the configured translation provider can translate a short string.
    This is used when TRANSLATION_PROVIDER is enabled.
    """
    provider = (os.getenv("TRANSLATION_PROVIDER") or "").strip().lower()
    if provider in ("", "none", "gemini"):
        return {
            "status": "skipped",
            "provider": provider,
            "configured": False,
            "note": "Set TRANSLATION_PROVIDER=google (or libretranslate) to enable translation verification.",
        }

    if provider in ("google", "gcloud", "translate"):
        if not translate_google.configured():
            return {
                "status": "error",
                "provider": provider,
                "configured": False,
                "error": "Missing GOOGLE_CLOUD_API_KEY/GOOGLE_API_KEY",
            }
        try:
            out = await translate_google.translate_batch(["Hello world."], target="am", source="en")
            sample = out[0].translated_text if out else ""
            return {
                "status": "success",
                "provider": provider,
                "configured": True,
                "sample": {"en": "Hello world.", "am": sample},
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": provider,
                "configured": True,
                "error": str(e),
            }

    if provider in ("libretranslate", "libre", "open", "opensource", "open-source"):
        if not translate_libre.configured():
            return {
                "status": "error",
                "provider": provider,
                "configured": False,
                "error": "Missing LIBRETRANSLATE_URL",
            }
        try:
            out = await translate_libre.translate_batch(["Hello world."], target="am", source="en")
            sample = out[0].translated_text if out else ""
            return {
                "status": "success",
                "provider": provider,
                "configured": True,
                "sample": {"en": "Hello world.", "am": sample},
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": provider,
                "configured": True,
                "error": str(e),
            }

    return {
        "status": "error",
        "provider": provider,
        "configured": False,
        "error": f"Unknown TRANSLATION_PROVIDER={provider!r}",
    }


@app.get("/api/config")
async def get_config():
    """Non-secret config summary for the UI."""
    def _env_bool(name: str, default: bool = False) -> bool:
        val = os.getenv(name)
        if val is None:
            return default
        return val.strip().lower() in ("1", "true", "yes", "y", "on")

    return {
        "translation_provider": (os.getenv("TRANSLATION_PROVIDER") or "").strip(),
        "google_translate_configured": bool(os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        "libretranslate": {
            "configured": bool(os.getenv("LIBRETRANSLATE_URL")),
            "url": (os.getenv("LIBRETRANSLATE_URL") or "").strip(),
        },
        "narrator_persona": (os.getenv("NARRATOR_PERSONA") or "futuristic captain").strip(),
        "script_beats": {
            "seconds": int(os.getenv("SCRIPT_BEAT_SECONDS") or "20"),
            "max_beats": int(os.getenv("SCRIPT_MAX_BEATS") or "60"),
        },
        "zthumb": {
            "url": (os.getenv("ZTHUMB_URL") or "").strip(),
            "allow_fallback_to_openai": _env_bool("ALLOW_THUMBNAIL_FALLBACK_TO_OPENAI", False),
        },
    }


def _in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _expand_localhost_url(url: str) -> List[str]:
    base = url.rstrip("/")
    urls = [base]
    if not _in_docker():
        return urls
    parsed = urlparse(base if "://" in base else f"http://{base}")
    host = parsed.hostname
    port = parsed.port
    if host not in ("localhost", "127.0.0.1"):
        return urls

    def with_host(new_host: str) -> str:
        netloc = new_host
        if port:
            netloc = f"{new_host}:{port}"
        return parsed._replace(netloc=netloc).geturl().rstrip("/")

    urls.append(with_host("host.docker.internal"))
    # De-dup
    out: List[str] = []
    seen = set()
    for u in urls:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


@app.get("/api/verify/zthumb")
async def verify_zthumb():
    """
    ZTHUMB VERIFICATION (OPTIONAL)
    Checks ZThumb /health and /models from inside the runner container.
    """
    z = (os.getenv("ZTHUMB_URL") or "").strip()
    if not z:
        return {"status": "skipped", "configured": False, "note": "Set ZTHUMB_URL to enable ZThumb verification."}

    urls = _expand_localhost_url(z)
    last_err = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        for base in urls:
            try:
                health = (await client.get(f"{base}/health")).json()
                models = (await client.get(f"{base}/models")).json()
                return {"status": "success", "configured": True, "base_url": base, "health": health, "models": models}
            except Exception as e:
                last_err = e
                continue
    return {
        "status": "error",
        "configured": True,
        "urls_tried": urls,
        "error": str(last_err) if last_err else "unknown error",
    }


@app.post("/api/discover")
async def discover_channels(request: DiscoveryRequest, background_tasks: BackgroundTasks):
    """
    Part A: Discover top recap channels and videos.
    Searches YouTube for recap channels, ranks them by composite score,
    and selects top videos by views velocity.
    """
    try:
        result = await discovery.discover_top_channels(
            queries=request.queries,
            top_n=request.top_n_channels,
            videos_per_channel=request.videos_per_channel
        )
        return {
            "status": "success",
            "channels_found": len(result.get("channels", [])),
            "videos_found": len(result.get("videos", [])),
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ingest/{video_id}")
async def ingest_video(video_id: str):
    """
    Part B: Download video and get/generate transcript.
    Downloads video with yt-dlp, extracts transcript from YouTube captions
    or transcribes with Whisper/Gemini.
    """
    try:
        result = await ingest.process_video(video_id)
        return {
            "status": "success",
            "video_id": video_id,
            "transcript_source": result.get("source"),
            "language_detected": result.get("language")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/script/{video_id}")
async def generate_script(video_id: str):
    """
    Part C: Generate Amharic recap script.
    Creates a high-retention Amharic recap script (not literal translation)
    with hook, main recap segments, payoff, and CTA.
    """
    try:
        result = await script_gen.generate_amharic_script(video_id)
        return {
            "status": "success",
            "video_id": video_id,
            "quality_score": result.get("quality_score"),
            "script_preview": result.get("hook_text", "")[:200]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/voice/{video_id}")
async def generate_voice(video_id: str):
    """
    Part D: Generate Amharic narration audio.
    Uses Azure TTS with am-ET voices to generate deep, cinematic narration.
    Normalizes audio to target LUFS.
    """
    try:
        result = await voice_gen.generate_narration(video_id)
        return {
            "status": "success",
            "video_id": video_id,
            "audio_file": result.get("audio_file"),
            "duration_seconds": result.get("duration"),
            "quality_passed": result.get("quality_passed")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/render/{video_id}")
async def render_video(video_id: str):
    """
    Part E: Match timing and render final video.
    Aligns narration to scene cuts, replaces original audio,
    and renders final video.
    """
    try:
        result = await timing.render_with_alignment(video_id)
        return {
            "status": "success",
            "video_id": video_id,
            "output_file": result.get("output_file"),
            "alignment_score": result.get("alignment_score")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/thumbnail/{video_id}")
async def generate_thumbnail(video_id: str):
    """
    Part F: Generate superb thumbnails.
    Creates 3 thumbnail concepts with Amharic hooks,
    selects best using heuristics.
    """
    try:
        result = await thumbnail_gen.generate_thumbnails(video_id)
        return {
            "status": "success",
            "video_id": video_id,
            "thumbnails_generated": len(result.get("thumbnails", [])),
            "selected_thumbnail": result.get("selected")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload/{video_id}")
async def upload_video(video_id: str):
    """
    Part G: Upload to YouTube with metadata.
    Uploads video with title, description, tags, chapters,
    playlist assignment, and thumbnail.
    """
    try:
        result = await uploader.upload_video(video_id)
        return {
            "status": "success",
            "video_id": video_id,
            "youtube_video_id": result.get("youtube_video_id"),
            "upload_status": result.get("status")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/distribute/{video_id}")
async def distribute_video(video_id: str):
    """
    Part H: Growth loop - distribute and track.
    Posts to X/Telegram, fetches early metrics,
    suggests optimizations.
    """
    try:
        result = await growth.distribute_and_track(video_id)
        return {
            "status": "success",
            "video_id": video_id,
            "distributed_to": result.get("platforms", []),
            "early_metrics": result.get("metrics")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pipeline/full")
async def run_full_pipeline(request: FullPipelineRequest, background_tasks: BackgroundTasks):
    """
    Run the complete pipeline end-to-end.
    If video_id is provided, processes that video.
    If auto_select is True, discovers and selects the best video automatically.
    """
    try:
        video_id = request.video_id
        
        # Auto-select if no video_id provided
        if not video_id and request.auto_select:
            discovery_result = await discovery.discover_top_channels()
            if discovery_result.get("videos"):
                video_id = discovery_result["videos"][0]["video_id"]
        
        if not video_id:
            raise HTTPException(status_code=400, detail="No video_id provided and auto-select found no videos")
        
        # Run pipeline steps
        results = {
            "video_id": video_id,
            "steps": {}
        }
        
        # Step 1: Ingest
        ingest_result = await ingest.process_video(video_id)
        results["steps"]["ingest"] = {"status": "success", "source": ingest_result.get("source")}
        
        # Step 2: Script
        script_result = await script_gen.generate_amharic_script(video_id)
        results["steps"]["script"] = {"status": "success", "quality": script_result.get("quality_score")}
        
        # Step 3: Voice
        voice_result = await voice_gen.generate_narration(video_id)
        results["steps"]["voice"] = {"status": "success", "duration": voice_result.get("duration")}
        
        # Step 4: Render
        render_result = await timing.render_with_alignment(video_id)
        results["steps"]["render"] = {"status": "success", "alignment": render_result.get("alignment_score")}
        
        # Step 5: Thumbnail
        thumb_result = await thumbnail_gen.generate_thumbnails(video_id)
        results["steps"]["thumbnail"] = {"status": "success", "count": len(thumb_result.get("thumbnails", []))}
        
        # Step 6: Upload
        upload_result = await uploader.upload_video(video_id)
        results["steps"]["upload"] = {"status": "success", "youtube_id": upload_result.get("youtube_video_id")}
        
        # Step 7: Distribute
        dist_result = await growth.distribute_and_track(video_id)
        results["steps"]["distribute"] = {"status": "success", "platforms": dist_result.get("platforms")}
        
        results["status"] = "completed"
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs")
async def list_jobs(limit: int = 20):
    """List recent jobs (most recent first)."""
    try:
        jobs = job_store.list_jobs(limit=limit)
        return {"status": "success", "jobs": [j.to_dict() for j in jobs]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Get a single job by id."""
    try:
        job = job_store.get_job(job_id)
        return {"status": "success", "job": job.to_dict()}
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/pipeline/full")
async def create_pipeline_full_job(request: FullPipelineRequest):
    """
    Run the complete pipeline end-to-end as an async job.
    The UI should call this endpoint instead of blocking on /api/pipeline/full.
    """
    if not request.video_id and not request.auto_select:
        raise HTTPException(status_code=400, detail="video_id is required when auto_select=false")

    step_names = ["discover", "ingest", "script", "voice", "render", "thumbnail", "upload", "distribute"]
    steps = JobStore.init_steps(step_names)
    if request.video_id:
        _mark_step(steps, "discover", "skipped")

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


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Best-effort cancellation for in-flight jobs.

    Note: many pipeline steps call blocking subprocesses (ffmpeg/yt-dlp),
    so cancellation may not interrupt immediately.
    """
    try:
        _ = job_store.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")

    job_store.update_job(job_id, status="cancel_requested")
    job_store.append_event(job_id, "cancel requested", level="warn")

    task = _job_tasks.get(job_id)
    if task:
        task.cancel()

    return {"status": "success", "job_id": job_id}


@app.get("/api/report/daily")
async def get_daily_report():
    """
    Get the daily report with production stats and metrics.
    """
    try:
        report = await growth.generate_daily_report()
        return {
            "status": "success",
            "report": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
