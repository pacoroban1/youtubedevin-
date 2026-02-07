"""
Part D: Voice Generation Module
Generates Amharic narration using Gemini TTS models.
"""

import os
import asyncio
import base64
import logging
import wave
import contextlib
from typing import Dict, Any, List

from modules.gemini_client import gemini
from modules.gemini_client import GeminiCallFailed, GeminiNotConfigured

# Configure logging
logger = logging.getLogger("voice_generator")
logger.setLevel(logging.INFO)

class VoiceGenerator:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        
        # Gemini Voice settings
        # "Puck" is a good default for "futuristic captain" but we can change if needed
        self.voice_name = "Puck" 
    
    async def generate_narration(self, video_id: str) -> Dict[str, Any]:
        """
        Generate Amharic narration audio from script using Gemini TTS.
        """
        if not gemini.is_configured():
            return {
                "status": "error",
                "error": "missing_env",
                "message": "GEMINI_API_KEY is required for TTS",
                "video_id": video_id,
            }

        # Get script from database
        script_data = self.db.get_script(video_id)
        if not script_data or not script_data.get("full_script"):
            return {
                "status": "error",
                "error": "missing_script",
                "message": f"No script found for video {video_id}",
                "video_id": video_id,
            }
        
        full_script = script_data.get("full_script")
        # Handle if full_script is a string (legacy) or dict (new)
        if isinstance(full_script, str):
            try:
                import json
                script_obj = json.loads(full_script)
            except:
                script_obj = {"hook": full_script} # Fallback
        else:
            script_obj = full_script

        script_id = script_data["id"]

        # Create output directories
        # Requirement: also write under /app/media/tts
        tts_dir = os.path.join(self.media_dir, "tts")
        os.makedirs(tts_dir, exist_ok=True)
        tts_path = os.path.join(tts_dir, f"{video_id}.wav")

        # Also keep legacy pipeline path compatible.
        audio_dir = os.path.join(self.media_dir, "audio", video_id)
        os.makedirs(audio_dir, exist_ok=True)
        final_audio_path = os.path.join(audio_dir, "narration.wav")

        # Build a single narration string (truncate to keep within typical TTS limits).
        parts = []
        hook = (script_obj.get("hook") or "").strip()
        if hook:
            parts.append(hook)
        beats = script_obj.get("beats", []) or []
        if not beats:
            beats = script_data.get("main_recap_segments", []) or []
        for beat in beats:
            if isinstance(beat, dict):
                t = (beat.get("narration_text") or beat.get("text") or "").strip()
            else:
                t = str(beat).strip()
            if t:
                parts.append(t)
        payoff = (script_obj.get("payoff") or "").strip()
        if payoff:
            parts.append(payoff)
        cta = (script_obj.get("cta") or "").strip()
        if cta:
            parts.append(cta)

        narration_text = "\n\n".join(parts).strip()
        if not narration_text:
            return {
                "status": "error",
                "error": "empty_script_text",
                "message": "Script contains no narration text",
                "video_id": video_id,
            }

        # Hard cap for safety.
        max_chars = int(os.getenv("TTS_MAX_CHARS") or "8000")
        narration_text = narration_text[:max_chars]

        try:
            # The Gemini SDK call is synchronous; run it in a thread with a hard wall-clock timeout
            # so the HTTP request can never "hang" the FastAPI worker.
            audio_bytes, model_used, attempts = await asyncio.wait_for(
                asyncio.to_thread(
                    gemini.generate_speech_with_fallback,
                    narration_text,
                    voice_name=self.voice_name,
                    timeout_s=60.0,
                    retries_per_model=2,
                ),
                timeout=150.0,  # wall-clock upper bound across retries/models
            )
        except GeminiNotConfigured:
            return {
                "status": "error",
                "error": "missing_env",
                "message": "GEMINI_API_KEY is required for TTS",
                "video_id": video_id,
            }
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "error": "tts_timeout",
                "message": "TTS request timed out",
                "video_id": video_id,
                "attempts": [],
                "hint": "check network, quotas, or whether Gemini TTS is enabled for this key/tier",
            }
        except GeminiCallFailed as e:
            return {
                "status": "error",
                "error": "tts_generation_failed",
                "video_id": video_id,
                "attempts": e.attempts_as_dicts(),
                "hint": "check if Gemini TTS is enabled for this key/tier",
            }

        # Write required path + legacy pipeline path.
        # The SDK sometimes returns raw PCM bytes (no RIFF header) or base64 text bytes.
        # Ensure we always write a valid WAV container.
        wav_bytes = audio_bytes
        if not wav_bytes.startswith(b"RIFF"):
            # Try base64 decode first (common for inline_data).
            try:
                dec = base64.b64decode(wav_bytes, validate=False)
                if dec.startswith(b"RIFF"):
                    wav_bytes = dec
            except Exception:
                pass

        if wav_bytes.startswith(b"RIFF"):
            with open(tts_path, "wb") as f:
                f.write(wav_bytes)
            with open(final_audio_path, "wb") as f:
                f.write(wav_bytes)
        else:
            # Assume raw 16-bit PCM mono. Wrap into a WAV file so tools can read it.
            sample_rate = int(os.getenv("TTS_SAMPLE_RATE") or "24000")
            for p in (tts_path, final_audio_path):
                with wave.open(p, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(sample_rate)
                    w.writeframes(wav_bytes)

        duration = self._get_wav_duration(tts_path)

        # Save to database
        audio_data = {
            "voice_provider": "gemini",
            "voice_id": self.voice_name,
            "audio_file_path": final_audio_path,
            "duration_seconds": duration,
            "model_used": model_used,
        }
        
        audio_id = self.db.save_audio(video_id, script_id, audio_data)
        self.db.update_video_status(video_id, "voiced")
        
        return {
            "status": "success",
            "video_id": video_id,
            "audio_id": audio_id,
            "audio_path": tts_path,
            "audio_url": f"/api/media/tts/{video_id}.wav",
            "audio_file": final_audio_path,
            "narration_url": f"/api/media/audio/{video_id}/narration.wav",
            "duration_sec": duration,
            "duration": duration,
            "model_used": model_used,
            "attempts": attempts,
        }

    def _get_wav_duration(self, path: str) -> float:
        try:
            with contextlib.closing(wave.open(path, 'r')) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                return frames / float(rate)
        except Exception:
            return 0.0

    def _concatenate_wavs(self, input_paths: List[str], output_path: str):
        data = []
        params = None
        for p in input_paths:
            try:
                with wave.open(p, 'rb') as w:
                    if not params:
                        params = w.getparams()
                    data.append(w.readframes(w.getnframes()))
            except Exception as e:
                logger.error(f"Error reading wav {p}: {e}")
        
        if params and data:
            with wave.open(output_path, 'wb') as w:
                w.setparams(params)
                for d in data:
                    w.writeframes(d)
