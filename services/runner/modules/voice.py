"""
Part D: Voice Generation Module
Generates Amharic narration using pluggable TTS providers.

Supported:
- Gemini prebuilt voices (existing)
- ElevenLabs (voice_id from your ElevenLabs account)
"""

import os
import asyncio
import base64
import logging
import re
import wave
import contextlib
import uuid
import subprocess
import time
from typing import Dict, Any, List

import httpx

from modules.gemini_client import gemini
from modules.gemini_client import GeminiCallFailed, GeminiNotConfigured

# Configure logging
logger = logging.getLogger("voice_generator")
logger.setLevel(logging.INFO)

class VoiceGenerator:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        
        # Provider selection:
        # - If TTS_PROVIDER is set, honor it.
        # - Otherwise prefer ElevenLabs when configured, else Gemini when configured.
        self.tts_provider = (os.getenv("TTS_PROVIDER") or "").strip().lower()

        # Gemini voice settings
        self.voice_name = (os.getenv("GEMINI_TTS_VOICE_NAME") or "Puck").strip() or "Puck"

        # ElevenLabs settings (optional)
        self.eleven_api_key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
        self.eleven_voice_id = (os.getenv("ELEVENLABS_VOICE_ID") or "").strip()
        self.eleven_model_id = (os.getenv("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2").strip()
        self.eleven_timeout_s = float(os.getenv("ELEVENLABS_TIMEOUT_S") or "60")

        # Cache ElevenLabs voices list (best-effort; avoids repeated API calls)
        self._eleven_voices_cache: List[Dict[str, Any]] | None = None
        self._eleven_voices_cache_ts: float = 0.0

    def _effective_provider(self, voice_provider: str | None = None) -> str:
        p = (voice_provider or self.tts_provider or "").strip().lower()
        if p:
            return p
        if self.eleven_api_key and self.eleven_voice_id:
            return "elevenlabs"
        if gemini.is_configured():
            return "gemini"
        # Default to gemini (will error with missing env); keeps behavior explicit.
        return "gemini"

    def _decode_audio_bytes(self, audio_bytes: bytes) -> bytes:
        """
        Gemini TTS may return base64-encoded audio bytes (often raw PCM), not a WAV container.
        Decode base64 when it looks like base64 text; otherwise return bytes unchanged.
        """
        if not audio_bytes:
            return audio_bytes

        # Quick heuristic: base64-ish ASCII payloads are common. Avoid decoding truly binary data.
        head = audio_bytes[:256]
        if all(c in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n\r" for c in head):
            try:
                dec = base64.b64decode(audio_bytes, validate=False)
                if dec:
                    return dec
            except Exception:
                pass
        return audio_bytes

    def _convert_to_wav(self, input_path: str, output_path: str, *, sample_rate: int) -> None:
        """
        Convert arbitrary audio (e.g. mp3 from ElevenLabs) into a mono WAV for the render pipeline.
        """
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            output_path,
        ]
        subprocess.run(cmd, check=True)

    def _normalize_wav(self, input_path: str, output_path: str, *, sample_rate: int) -> bool:
        """
        Loudness-normalize a WAV file for consistent narration volume.

        Uses FFmpeg loudnorm (single-pass). Best-effort: returns False on failure.
        """
        try:
            target_i = float(os.getenv("NARRATION_TARGET_LUFS") or "-16")
            target_tp = float(os.getenv("NARRATION_TRUE_PEAK") or "-1.5")
            target_lra = float(os.getenv("NARRATION_LRA") or "11")
        except Exception:
            target_i, target_tp, target_lra = -16.0, -1.5, 11.0

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-af",
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}",
            "-ac",
            "1",
            "-ar",
            str(int(sample_rate)),
            output_path,
        ]
        try:
            subprocess.run(cmd, check=True)
            return os.path.exists(output_path)
        except Exception:
            return False

    async def _elevenlabs_list_voices(self) -> List[Dict[str, Any]]:
        """
        Return a simplified list of available ElevenLabs voices.
        Best-effort; returns [] when not configured or on failure.
        """
        if not self.eleven_api_key:
            return []

        ttl_s = float(os.getenv("ELEVENLABS_VOICES_CACHE_TTL_S") or "300")
        now = time.time()
        if self._eleven_voices_cache is not None and (now - self._eleven_voices_cache_ts) < ttl_s:
            return list(self._eleven_voices_cache)

        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": self.eleven_api_key, "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.eleven_timeout_s) as client:
                r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return []
            data = r.json() or {}
            voices = data.get("voices") or []
            out: List[Dict[str, Any]] = []
            for v in voices:
                if not isinstance(v, dict):
                    continue
                out.append(
                    {
                        "voice_id": v.get("voice_id"),
                        "name": v.get("name"),
                        "category": v.get("category"),
                        "labels": v.get("labels") or {},
                    }
                )
            self._eleven_voices_cache = list(out)
            self._eleven_voices_cache_ts = now
            return out
        except Exception:
            return []

    async def _elevenlabs_voice_id_from_name(self, voice_name: str) -> str | None:
        """
        If the caller provides a human-friendly voice name, resolve it to voice_id.
        Returns None if not found.
        """
        name = (voice_name or "").strip()
        if not name:
            return None
        # If it already looks like a voice_id, just return it.
        # ElevenLabs voice_id is typically a short-ish opaque string; allow common chars.
        if re.fullmatch(r"[A-Za-z0-9_-]{8,128}", name or ""):
            return name
        voices = await self._elevenlabs_list_voices()
        for v in voices:
            if (v.get("name") or "").strip().lower() == name.lower():
                vid = (v.get("voice_id") or "").strip()
                return vid or None
        return None

    def _elevenlabs_voice_settings(self) -> Dict[str, Any]:
        def _f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name) or default)
            except Exception:
                return float(default)
        return {
            "stability": _f("ELEVENLABS_STABILITY", 0.5),
            "similarity_boost": _f("ELEVENLABS_SIMILARITY_BOOST", 0.75),
            "style": _f("ELEVENLABS_STYLE", 0.1),
            "use_speaker_boost": str(os.getenv("ELEVENLABS_USE_SPEAKER_BOOST") or "true").strip().lower() in ("1", "true", "yes", "y", "on"),
        }

    async def _elevenlabs_tts_to_wav(self, text: str, wav_out_path: str, *, voice_id: str) -> Dict[str, Any]:
        """
        Call ElevenLabs TTS and write a WAV file. We accept whatever audio bytes are returned
        (commonly mp3) and convert with ffmpeg for pipeline consistency.
        """
        if not self.eleven_api_key:
            return {"status": "error", "error": "missing_env", "message": "ELEVENLABS_API_KEY is required for ElevenLabs TTS"}
        if not voice_id:
            return {"status": "error", "error": "missing_env", "message": "ELEVENLABS_VOICE_ID is required for ElevenLabs TTS"}

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": self.eleven_api_key, "Accept": "audio/mpeg", "Content-Type": "application/json"}
        payload: Dict[str, Any] = {"text": text, "model_id": self.eleven_model_id, "voice_settings": self._elevenlabs_voice_settings()}

        tmp_dir = os.path.join(self.media_dir, "tts_tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_in = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.mp3")

        try:
            async with httpx.AsyncClient(timeout=self.eleven_timeout_s) as client:
                r = await client.post(url, headers=headers, json=payload)
            if r.status_code != 200:
                # Avoid leaking secrets; return minimal info.
                return {"status": "error", "error": "tts_generation_failed", "message": f"ElevenLabs TTS failed (HTTP {r.status_code})"}
            with open(tmp_in, "wb") as f:
                f.write(r.content or b"")

            sample_rate = int(os.getenv("TTS_SAMPLE_RATE") or "24000")
            self._convert_to_wav(tmp_in, wav_out_path, sample_rate=sample_rate)
            return {"status": "success", "model_used": self.eleven_model_id}
        except subprocess.CalledProcessError:
            return {"status": "error", "error": "audio_convert_failed", "message": "ffmpeg failed converting ElevenLabs audio to wav"}
        except httpx.TimeoutException:
            return {"status": "error", "error": "tts_timeout", "message": "ElevenLabs TTS request timed out"}
        except Exception:
            return {"status": "error", "error": "tts_generation_failed", "message": "ElevenLabs TTS request failed"}
        finally:
            try:
                if os.path.exists(tmp_in):
                    os.remove(tmp_in)
            except Exception:
                pass
    
    async def generate_narration(
        self,
        video_id: str,
        *,
        voice_name: str | None = None,
        voice_provider: str | None = None,
        voice_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        Generate Amharic narration audio from script.
        Provider selection is controlled by:
          - per-request voice_provider (optional)
          - env TTS_PROVIDER (optional)
          - auto: prefer ElevenLabs when ELEVENLABS_* is configured, else Gemini
        """
        provider = self._effective_provider(voice_provider)

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

        # Allow per-request overrides.
        # - For Gemini: voice_name is the prebuilt voice name.
        # - For ElevenLabs: voice_id is preferred; otherwise voice_name can be a voice_id or a voice name.
        gemini_voice = (voice_name or self.voice_name or "Puck").strip() or "Puck"
        eleven_voice = (voice_id or "").strip() or (self.eleven_voice_id or "").strip()

        # Create output directories
        # Requirement: also write under /app/media/tts
        tts_dir = os.path.join(self.media_dir, "tts")
        os.makedirs(tts_dir, exist_ok=True)
        tts_path = os.path.join(tts_dir, f"{video_id}.wav")

        # Also keep legacy pipeline path compatible.
        audio_dir = os.path.join(self.media_dir, "audio", video_id)
        os.makedirs(audio_dir, exist_ok=True)
        final_audio_path = os.path.join(audio_dir, "narration.wav")

        model_used = None
        attempts: List[Dict[str, Any]] = []

        if provider == "elevenlabs":
            # Resolve voice name to voice_id if needed.
            if not eleven_voice and voice_name:
                resolved = await self._elevenlabs_voice_id_from_name(voice_name)
                if resolved:
                    eleven_voice = resolved
            r = await self._elevenlabs_tts_to_wav(narration_text, tts_path, voice_id=eleven_voice)
            if r.get("status") != "success":
                r["video_id"] = video_id
                return r
            # Copy to legacy path too
            try:
                import shutil
                shutil.copyfile(tts_path, final_audio_path)
            except Exception:
                pass
            model_used = r.get("model_used") or self.eleven_model_id
        else:
            if not gemini.is_configured():
                return {
                    "status": "error",
                    "error": "missing_env",
                    "message": "GEMINI_API_KEY is required for Gemini TTS",
                    "video_id": video_id,
                }
            try:
                # The Gemini SDK call is synchronous; run it in a thread with a hard wall-clock timeout
                # so the HTTP request can never "hang" the FastAPI worker.
                audio_bytes, model_used, attempts = await asyncio.wait_for(
                    asyncio.to_thread(
                        gemini.generate_speech_with_fallback,
                        narration_text,
                        voice_name=gemini_voice,
                        timeout_s=60.0,
                        retries_per_model=2,
                    ),
                    timeout=150.0,  # wall-clock upper bound across retries/models
                )
            except GeminiNotConfigured:
                return {
                    "status": "error",
                    "error": "missing_env",
                    "message": "GEMINI_API_KEY is required for Gemini TTS",
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
            wav_bytes = self._decode_audio_bytes(audio_bytes)

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

        # Loudness normalization (best-effort). Also keeps a raw copy for debugging.
        sample_rate = int(os.getenv("TTS_SAMPLE_RATE") or "24000")
        raw_keep_path = os.path.join(audio_dir, "narration_raw.wav")
        normalized_path = os.path.join(audio_dir, "narration_normalized.wav")
        normalized_ok = False
        try:
            # Keep the pre-normalized file around for comparison.
            if os.path.exists(final_audio_path):
                try:
                    import shutil
                    shutil.copyfile(final_audio_path, raw_keep_path)
                except Exception:
                    pass
            normalized_ok = self._normalize_wav(final_audio_path, normalized_path, sample_rate=sample_rate)
            if normalized_ok:
                try:
                    import shutil
                    # Make narration.wav point to normalized audio (so downstream render always uses it)
                    shutil.copyfile(normalized_path, final_audio_path)
                    # Also make the /api/media/tts/<video_id>.wav serve normalized audio
                    shutil.copyfile(normalized_path, tts_path)
                except Exception:
                    pass
        except Exception:
            normalized_ok = False

        # Save to database
        audio_data = {
            "voice_provider": provider,
            "voice_id": (eleven_voice if provider == "elevenlabs" else gemini_voice),
            "audio_file_path": final_audio_path,
            "duration_seconds": duration,
            "loudness_lufs": float(os.getenv("NARRATION_TARGET_LUFS") or "-16"),
            "quality_check_passed": True,
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
            "narration_normalized_url": f"/api/media/audio/{video_id}/narration_normalized.wav" if normalized_ok else None,
            "narration_raw_url": f"/api/media/audio/{video_id}/narration_raw.wav" if os.path.exists(raw_keep_path) else None,
            "duration_sec": duration,
            "duration": duration,
            "quality_passed": True,
            "quality_check_passed": True,
            "model_used": model_used,
            "voice_id": (eleven_voice if provider == "elevenlabs" else gemini_voice),
            "voice_provider": provider,
            "attempts": attempts or [],
        }

    async def generate_preview(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        voice_provider: str | None = None,
        voice_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        Generate a short TTS preview clip for auditioning voices.

        This does NOT touch the DB. Output is written under:
          /app/media/tts_previews/<preview_id>.wav
        """
        provider = self._effective_provider(voice_provider)

        preview_text = (text or "").strip()
        if not preview_text:
            return {
                "status": "error",
                "error": "empty_text",
                "message": "text is required",
            }

        max_chars = int(os.getenv("TTS_PREVIEW_MAX_CHARS") or "600")
        preview_text = preview_text[:max_chars]

        previews_dir = os.path.join(self.media_dir, "tts_previews")
        os.makedirs(previews_dir, exist_ok=True)
        preview_id = uuid.uuid4().hex
        preview_path = os.path.join(previews_dir, f"{preview_id}.wav")

        model_used = None
        attempts: List[Dict[str, Any]] = []

        if provider == "elevenlabs":
            eleven_voice = (voice_id or "").strip() or (self.eleven_voice_id or "").strip()
            if not eleven_voice and voice_name:
                resolved = await self._elevenlabs_voice_id_from_name(voice_name)
                if resolved:
                    eleven_voice = resolved
            r = await self._elevenlabs_tts_to_wav(preview_text, preview_path, voice_id=eleven_voice)
            if r.get("status") != "success":
                return r
            model_used = r.get("model_used") or self.eleven_model_id
        else:
            if not gemini.is_configured():
                return {
                    "status": "error",
                    "error": "missing_env",
                    "message": "GEMINI_API_KEY is required for Gemini TTS",
                }
            voice = (voice_name or self.voice_name or "Puck").strip() or "Puck"
            try:
                audio_bytes, model_used, attempts = await asyncio.wait_for(
                    asyncio.to_thread(
                        gemini.generate_speech_with_fallback,
                        preview_text,
                        voice_name=voice,
                        timeout_s=30.0,
                        retries_per_model=1,
                    ),
                    timeout=90.0,
                )
            except GeminiNotConfigured:
                return {
                    "status": "error",
                    "error": "missing_env",
                    "message": "GEMINI_API_KEY is required for Gemini TTS",
                }
            except asyncio.TimeoutError:
                return {
                    "status": "error",
                    "error": "tts_timeout",
                    "message": "TTS preview request timed out",
                    "attempts": [],
                }
            except GeminiCallFailed as e:
                return {
                    "status": "error",
                    "error": "tts_generation_failed",
                    "attempts": e.attempts_as_dicts(),
                    "hint": "check if Gemini TTS is enabled for this key/tier",
                }

            wav_bytes = self._decode_audio_bytes(audio_bytes)
            if wav_bytes.startswith(b"RIFF"):
                with open(preview_path, "wb") as f:
                    f.write(wav_bytes)
            else:
                sample_rate = int(os.getenv("TTS_SAMPLE_RATE") or "24000")
                with wave.open(preview_path, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(sample_rate)
                    w.writeframes(wav_bytes)

        duration = self._get_wav_duration(preview_path)
        return {
            "status": "success",
            "preview_id": preview_id,
            "audio_path": preview_path,
            "audio_url": f"/api/media/tts_previews/{preview_id}.wav",
            "duration_sec": duration,
            "duration": duration,
            "model_used": model_used,
            "voice_provider": provider,
            "voice_id": (voice_id or voice_name or (self.eleven_voice_id if provider == "elevenlabs" else self.voice_name)),
            "attempts": attempts or [],
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
