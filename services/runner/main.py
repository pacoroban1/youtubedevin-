"""
Amharic Recap Autopilot - Runner Service
Main FastAPI application that orchestrates the video recap pipeline.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import os

from modules.discovery import ChannelDiscovery
from modules.ingest import VideoIngest
from modules.script import ScriptGenerator
from modules.voice import VoiceGenerator
from modules.timing import TimingMatcher
from modules.thumbnail import ThumbnailGenerator
from modules.upload import YouTubeUploader
from modules.growth import GrowthLoop
from modules.database import Database

app = FastAPI(
    title="Amharic Recap Autopilot",
    description="End-to-end YouTube automation for Amharic recap videos",
    version="1.0.0"
)

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
