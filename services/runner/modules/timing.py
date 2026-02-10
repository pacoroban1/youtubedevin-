"""
Part E: Timing & Scene Matching Module
Aligns narration to scene cuts and renders final video.
"""

import os
import subprocess
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import tempfile

# Lazy-loaded Whisper model for "no English bleed" checks.
_BLEED_WHISPER_MODEL = None
_BLEED_WHISPER_MODEL_NAME = None


class TimingMatcher:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.logger = logging.getLogger("timing")
        
        # Scene detection threshold (0.0-1.0, lower = more sensitive)
        self.scene_threshold = 0.3
        
        # Timing tolerance in seconds
        self.timing_tolerance = 0.5
    
    async def render_with_alignment(self, video_id: str) -> Dict[str, Any]:
        """
        Align narration to scenes and render final video.
        
        Args:
            video_id: YouTube video ID
        
        Returns:
            Dict with output file path and alignment score
        """
        # Get paths
        video_dir = os.path.join(self.media_dir, "videos", video_id)
        audio_dir = os.path.join(self.media_dir, "audio", video_id)
        output_dir = os.path.join(self.media_dir, "output", video_id)
        os.makedirs(output_dir, exist_ok=True)
        
        # Find source video
        source_video = await self._find_source_video(video_dir)
        if not source_video:
            raise Exception(f"Source video not found for {video_id}")
        
        # Get audio data
        audio_data = self.db.get_audio(video_id)
        if not audio_data:
            raise Exception(f"No audio found for {video_id}")
        
        narration_file = audio_data.get("audio_file_path")
        if not narration_file or not os.path.exists(narration_file):
            raise Exception(f"Narration file not found: {narration_file}")
        
        # Step 1: Detect scene boundaries
        scene_cuts = await self._detect_scenes(source_video)
        
        # Step 2: Get narration timestamps (forced alignment)
        narration_timestamps = await self._get_narration_timestamps(narration_file, video_id)
        
        # Step 3: Map narration segments to scenes
        alignment_map = await self._align_narration_to_scenes(
            narration_timestamps,
            scene_cuts,
            audio_data.get("duration_seconds", 0)
        )
        
        # Step 4: Render final video
        output_file = os.path.join(output_dir, "final_video.mp4")
        ok = await self._render_video(
            source_video,
            narration_file,
            output_file,
            alignment_map,
            video_id=video_id,
        )
        if not ok or (not os.path.exists(output_file)):
            raise Exception(f"Render failed: output file not created at {output_file}")

        # Step 4b: "No English bleed" gate. If English is detected near the end of the
        # final mix, auto-retry with the strongest setting (replace original audio).
        bleed_check = await self._no_english_bleed_check(output_file)
        retried_replace = False
        if bleed_check.get("english_detected") and ((os.getenv("AUDIO_MIX_MODE") or "replace").strip().lower() != "replace"):
            retried_replace = True
            ok2 = await self._render_video(
                source_video,
                narration_file,
                output_file,
                alignment_map,
                video_id=video_id,
                audio_mode_override="replace",
            )
            if not ok2 or (not os.path.exists(output_file)):
                raise Exception(f"Render retry failed (replace mode): output file not created at {output_file}")
            bleed_check2 = await self._no_english_bleed_check(output_file)
            bleed_check = {**bleed_check2, "retried_replace": True}

        if bleed_check.get("english_detected"):
            raise Exception(f"No-English-Bleed gate failed: {bleed_check}")

        # Step 5: Calculate alignment score
        alignment_score = self._calculate_alignment_score(alignment_map, scene_cuts)
        
        # Quality check
        quality_passed = alignment_score >= 0.7
        
        # Get duration
        duration = await self._get_video_duration(output_file)
        
        # Save to database
        render_data = {
            "output_file_path": output_file,
            "duration_seconds": duration,
            "scene_alignment_score": alignment_score,
            "quality_check_passed": bool(quality_passed) and (not bleed_check.get("english_detected", False))
        }
        
        render_id = self.db.save_render(video_id, audio_data["id"], render_data)
        self.db.update_video_status(video_id, "rendered")
        
        return {
            "render_id": render_id,
            "output_file": output_file,
            "output_url": f"/api/media/output/{video_id}/final_video.mp4",
            "duration": duration,
            "alignment_score": alignment_score,
            "scene_count": len(scene_cuts),
            "quality_passed": bool(quality_passed) and (not bleed_check.get("english_detected", False)),
            "no_english_bleed": bleed_check,
            "retried_replace": retried_replace,
        }
    
    async def _find_source_video(self, video_dir: str) -> Optional[str]:
        """Find the source video file."""
        for ext in ["mp4", "mkv", "webm"]:
            for filename in os.listdir(video_dir) if os.path.exists(video_dir) else []:
                if filename.endswith(f".{ext}"):
                    return os.path.join(video_dir, filename)
        return None
    
    async def _detect_scenes(self, video_path: str) -> List[Dict[str, Any]]:
        """Detect scene boundaries using ffmpeg."""
        try:
            # Use ffmpeg scene detection
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-vf", f"select='gt(scene,{self.scene_threshold})',showinfo",
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            # Parse scene timestamps from output
            scenes = []
            import re
            
            # Look for pts_time in showinfo output
            for line in result.stderr.split('\n'):
                if 'pts_time' in line:
                    match = re.search(r'pts_time:(\d+\.?\d*)', line)
                    if match:
                        timestamp = float(match.group(1))
                        scenes.append({
                            "timestamp": timestamp,
                            "type": "scene_change"
                        })
            
            # Add start and end
            if not scenes or scenes[0]["timestamp"] > 0.5:
                scenes.insert(0, {"timestamp": 0.0, "type": "start"})
            
            # Get video duration and add end
            duration = await self._get_video_duration(video_path)
            scenes.append({"timestamp": duration, "type": "end"})
            
            return scenes
            
        except Exception as e:
            print(f"Scene detection error: {e}")
            # Return basic scenes if detection fails
            duration = await self._get_video_duration(video_path)
            return [
                {"timestamp": 0.0, "type": "start"},
                {"timestamp": duration, "type": "end"}
            ]
    
    async def _get_narration_timestamps(
        self,
        audio_file: str,
        video_id: str
    ) -> List[Dict[str, Any]]:
        """Get timestamps for narration segments using forced alignment."""
        try:
            # Try using stable-ts for forced alignment
            import stable_whisper
            
            model = stable_whisper.load_model("base")
            result = model.transcribe(audio_file)
            
            timestamps = []
            for segment in result.segments:
                timestamps.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text
                })
            
            return timestamps
            
        except Exception as e:
            print(f"Forced alignment error: {e}")
            
            # Fallback: estimate timestamps from script segments
            script_data = self.db.get_script(video_id)
            if script_data:
                segments = script_data.get("main_recap_segments", [])
                if isinstance(segments, str):
                    segments = json.loads(segments)
                
                timestamps = []
                current_time = 0
                
                for segment in segments:
                    duration = segment.get("estimated_duration", 30)
                    timestamps.append({
                        "start": current_time,
                        "end": current_time + duration,
                        "text": segment.get("text", "")[:50]
                    })
                    current_time += duration
                
                return timestamps
            
            return []
    
    async def _align_narration_to_scenes(
        self,
        narration_timestamps: List[Dict],
        scene_cuts: List[Dict],
        narration_duration: float
    ) -> List[Dict[str, Any]]:
        """Map narration segments to scene ranges."""
        if not narration_timestamps or not scene_cuts:
            return []
        
        alignment_map = []
        
        # Calculate video duration
        video_duration = scene_cuts[-1]["timestamp"] if scene_cuts else narration_duration
        
        # Calculate time scaling factor
        scale_factor = video_duration / narration_duration if narration_duration > 0 else 1.0
        
        for narr_segment in narration_timestamps:
            # Scale narration time to video time
            video_start = narr_segment["start"] * scale_factor
            video_end = narr_segment["end"] * scale_factor
            
            # Find nearest scene cut
            nearest_scene = min(
                scene_cuts,
                key=lambda s: abs(s["timestamp"] - video_start)
            )
            
            alignment_map.append({
                "narration_start": narr_segment["start"],
                "narration_end": narr_segment["end"],
                "video_start": video_start,
                "video_end": video_end,
                "nearest_scene": nearest_scene["timestamp"],
                "offset": abs(nearest_scene["timestamp"] - video_start)
            })
        
        return alignment_map
    
    async def _render_video(
        self,
        source_video: str,
        narration_audio: str,
        output_file: str,
        alignment_map: List[Dict],
        *,
        video_id: Optional[str] = None,
        audio_mode_override: Optional[str] = None,
    ) -> bool:
        """
        Render final video with narration and (optionally) selective original-audio "breathing" windows.

        Modes (env AUDIO_MIX_MODE):
          - replace (default): narration replaces original audio entirely
          - windows: original audio is heavily ducked, but fades in/out during configured windows
          - duck: original audio is always ducked under narration (no windows)
        """
        try:
            # Get video and audio durations
            video_duration = await self._get_video_duration(source_video)
            audio_duration = await self._get_audio_duration(narration_audio)
            
            # Determine how to handle duration mismatch
            if abs(video_duration - audio_duration) > 5:
                # Significant mismatch - adjust video speed or trim
                if audio_duration > video_duration:
                    # Audio longer than video - slow down video slightly
                    speed_factor = video_duration / audio_duration
                    video_filter = f"setpts={1/speed_factor}*PTS"
                else:
                    # Video longer than audio - use original speed, audio will end early
                    video_filter = "null"
            else:
                video_filter = "null"
            
            # Build ffmpeg command
            audio_mode = (audio_mode_override or os.getenv("AUDIO_MIX_MODE") or "replace").strip().lower()

            # Final mix loudness normalization (single-pass; best-effort).
            try:
                final_i = float(os.getenv("FINAL_TARGET_LUFS") or "-14")
                final_tp = float(os.getenv("FINAL_TRUE_PEAK") or "-1.5")
                final_lra = float(os.getenv("FINAL_LRA") or "11")
            except Exception:
                final_i, final_tp, final_lra = -14.0, -1.5, 11.0
            final_norm = f"loudnorm=I={final_i}:TP={final_tp}:LRA={final_lra}"

            # Mix tuning (safe defaults: mostly narration, occasional original audio windows)
            # Default outside-window gain is 0.0 to fully mute the source audio by default.
            # Recap videos often include an English narrator; leaving any bleed tends to sound bad.
            # Users can raise this (e.g. 0.01-0.05) if they want a constant ambience bed.
            orig_duck = float(os.getenv("ORIG_AUDIO_DUCK_GAIN") or "0.0")  # outside windows
            orig_full = float(os.getenv("ORIG_AUDIO_FULL_GAIN") or "1.0")   # inside windows
            nar_gain = float(os.getenv("NARRATION_GAIN") or "1.0")
            nar_duck = float(os.getenv("NARRATION_DUCK_GAIN") or "0.15")    # inside windows
            default_fade = float(os.getenv("ORIG_AUDIO_FADE_SECONDS") or "0.25")

            def _nest(op: str, exprs: List[str]) -> str:
                if not exprs:
                    return ""
                out = exprs[0]
                for e in exprs[1:]:
                    out = f"{op}({out},{e})"
                return out

            def _orig_window_expr(st: float, en: float, fade: float) -> str:
                # Smooth ramp between orig_duck and orig_full.
                fade = max(0.01, float(fade))
                a = max(0.0, st - fade)
                b = st
                c = en
                d = en + fade
                return (
                    f"if(between(t,{b},{c}),{orig_full},"
                    f"if(between(t,{a},{b}),{orig_duck}+({orig_full}-{orig_duck})*(t-{a})/{fade},"
                    f"if(between(t,{c},{d}),{orig_full}-({orig_full}-{orig_duck})*(t-{c})/{fade},{orig_duck})))"
                )

            def _nar_window_expr(st: float, en: float, fade: float) -> str:
                # Smooth ramp between 1.0 and nar_duck (duck narration when original audio is highlighted).
                fade = max(0.01, float(fade))
                a = max(0.0, st - fade)
                b = st
                c = en
                d = en + fade
                return (
                    f"if(between(t,{b},{c}),{nar_duck},"
                    f"if(between(t,{a},{b}),1-(1-{nar_duck})*(t-{a})/{fade},"
                    f"if(between(t,{c},{d}),{nar_duck}+(1-{nar_duck})*(t-{c})/{fade},1)))"
                )

            def _load_windows() -> tuple[List[Dict[str, Any]], bool]:
                if not video_id:
                    return [], False

                # Optional override file: these windows are assumed to already be in
                # narration-time seconds (no scaling).
                override_path = os.path.join(
                    self.media_dir, "output", video_id, "audio_windows.override.json"
                )
                if os.path.exists(override_path):
                    try:
                        with open(override_path, "r", encoding="utf-8") as f:
                            obj = json.load(f)
                        wins = obj.get("windows") if isinstance(obj, dict) else obj
                        if isinstance(wins, list):
                            return wins, True
                    except Exception:
                        # Best-effort; fall through to DB-backed windows.
                        pass

                try:
                    s = self.db.get_script(video_id) or {}
                    raw = s.get("full_script")
                    if not raw:
                        return [], False
                    if isinstance(raw, str):
                        obj = json.loads(raw)
                    elif isinstance(raw, dict):
                        obj = raw
                    else:
                        return [], False
                    wins = obj.get("original_audio_windows") or []
                    return (wins, False) if isinstance(wins, list) else ([], False)
                except Exception:
                    return [], False

            def _scale_windows(wins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                if not video_id or not wins:
                    return []
                # Determine planned duration from script beats (best-effort), then scale to narration length.
                planned_total = 0.0
                try:
                    s = self.db.get_script(video_id) or {}
                    raw = s.get("full_script")
                    obj = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
                    beats = obj.get("beats") or []
                    if isinstance(beats, list) and beats:
                        for b in beats:
                            if not isinstance(b, dict):
                                continue
                            try:
                                planned_total = max(planned_total, float(b.get("end_time") or 0.0))
                            except Exception:
                                pass
                except Exception:
                    planned_total = 0.0

                if planned_total <= 0.0:
                    return []
                if audio_duration <= 0.0:
                    return []
                scale = float(audio_duration) / float(planned_total)

                out: List[Dict[str, Any]] = []
                for w in wins:
                    if not isinstance(w, dict):
                        continue
                    try:
                        st = float(w.get("start_time") or 0.0) * scale
                        en = float(w.get("end_time") or 0.0) * scale
                    except Exception:
                        continue
                    if en <= st:
                        continue
                    # Clamp to actual narration duration.
                    st = max(0.0, min(st, float(audio_duration)))
                    en = max(0.0, min(en, float(audio_duration)))
                    if en <= st:
                        continue
                    fade = float(w.get("fade_seconds") or default_fade)
                    out.append({"start_time": st, "end_time": en, "fade_seconds": fade})

                out.sort(key=lambda x: float(x.get("start_time") or 0.0))
                return out

            def _build_audio_filtergraph() -> Optional[str]:
                """
                Returns a filter_complex string or None if we should fall back to replace mode.
                """
                if audio_mode not in ("windows", "duck"):
                    return None

                wins_raw, already_scaled = _load_windows() if audio_mode == "windows" else ([], False)
                wins_scaled = wins_raw if already_scaled else _scale_windows(wins_raw)

                # Always emit a suggested scaled windows file so users can tweak without
                # digging into the DB. Do this best-effort and never block rendering.
                if video_id and audio_mode == "windows":
                    try:
                        out_dir = os.path.dirname(output_file)
                        os.makedirs(out_dir, exist_ok=True)
                        suggested_path = os.path.join(out_dir, "audio_windows.suggested.json")
                        with open(suggested_path, "w", encoding="utf-8") as f:
                            json.dump({"windows": wins_scaled}, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

                # Expressions are evaluated per-frame.
                orig_expr = f"{orig_duck}"
                nar_expr = "1"

                if audio_mode == "windows" and wins_scaled:
                    orig_exprs = [_orig_window_expr(float(w["start_time"]), float(w["end_time"]), float(w["fade_seconds"])) for w in wins_scaled]
                    nar_exprs = [_nar_window_expr(float(w["start_time"]), float(w["end_time"]), float(w["fade_seconds"])) for w in wins_scaled]
                    orig_expr = _nest("max", orig_exprs) if orig_exprs else f"{orig_duck}"
                    nar_expr = _nest("min", nar_exprs) if nar_exprs else "1"
                elif audio_mode == "duck":
                    # Always keep original very low.
                    orig_expr = f"{orig_duck}"
                    nar_expr = "1"

                # NOTE: quote expressions because `if()` uses commas.
                # Normalize formats for amix.
                return (
                    f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume='{orig_expr}':eval=frame[orig];"
                    f"[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume='{nar_gain}*({nar_expr})':eval=frame[nar];"
                    f"[orig][nar]amix=inputs=2:duration=shortest:dropout_transition=0,{final_norm},alimiter=limit=0.98[aout]"
                )

            filter_complex = _build_audio_filtergraph()

            cmd = [
                "ffmpeg",
                "-i", source_video,
                "-i", narration_audio,
            ]

            if filter_complex:
                cmd += ["-filter_complex", filter_complex, "-map", "0:v", "-map", "[aout]"]
            else:
                # Replace mode (legacy): narration replaces original audio entirely.
                cmd += ["-map", "0:v", "-map", "1:a"]
                # Normalize + hard-limit final audio even in replace mode.
                cmd += ["-filter:a", f"{final_norm},alimiter=limit=0.98"]

            # Apply video speed adjustment when audio is longer than video.
            # (Previously computed but not actually applied.)
            if video_filter != "null":
                cmd += ["-filter:v", video_filter]

            cmd += [
                "-c:v", "libx264",       # Video codec
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac",           # Audio codec
                "-b:a", "192k",
                "-movflags", "+faststart",
                "-shortest",             # End when shortest stream ends
                "-y",                    # Overwrite output
                output_file
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout
            )
            
            if result.returncode != 0:
                # If mixed-audio mode fails (missing original audio stream etc.), fall back to replace mode.
                if filter_complex:
                    self.logger.warning("Render mix failed, falling back to replace audio: %s", result.stderr.strip()[:500])
                    cmd_fallback = [
                        "ffmpeg",
                        "-i", source_video,
                        "-i", narration_audio,
                        "-map", "0:v",
                        "-map", "1:a",
                    ]
                    if video_filter != "null":
                        cmd_fallback += ["-filter:v", video_filter]
                    cmd_fallback += [
                        "-c:v", "libx264",
                        "-preset", "medium",
                        "-crf", "23",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-shortest",
                        "-y",
                        output_file,
                    ]
                    result2 = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=1800)
                    if result2.returncode != 0:
                        print(f"Render error: {result2.stderr}")
                        return False
                    return os.path.exists(output_file)

                print(f"Render error: {result.stderr}")
                return False
            
            return os.path.exists(output_file)
            
        except Exception as e:
            print(f"Video render error: {e}")
            return False

    async def _no_english_bleed_check(self, video_path: str) -> Dict[str, Any]:
        """
        Best-effort "no English bleed" check.

        We sample the last ~10% (clamped) of the final video's audio, and use Whisper's
        language detection. If it detects English with high confidence, we fail the gate.
        """
        enabled = (os.getenv("NO_ENGLISH_BLEED_CHECK") or "1").strip().lower() not in ("0", "false", "no", "off")
        if not enabled:
            return {"checked": False, "english_detected": False, "reason": "disabled"}

        dur = await self._get_video_duration(video_path)
        if not dur or dur <= 0:
            return {"checked": False, "english_detected": False, "reason": "unknown_duration"}

        # Segment selection: last 10% of the timeline, clamped.
        seg_len = max(8.0, min(25.0, float(dur) * 0.10))
        start = max(0.0, float(dur) - seg_len)

        # Threshold: require reasonably high confidence before we auto-fail.
        try:
            th = float(os.getenv("ENGLISH_BLEED_PROB_THRESHOLD") or "0.60")
        except Exception:
            th = 0.60

        with tempfile.NamedTemporaryFile(prefix="bleed_", suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(start),
                "-t",
                str(seg_len),
                "-i",
                video_path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                tmp_path,
            ]
            subprocess.run(cmd, check=True)

            lang, prob = self._whisper_detect_language(tmp_path)
            english = (lang == "en" and (prob is None or float(prob) >= th))
            return {
                "checked": True,
                "english_detected": bool(english),
                "detected_language": lang,
                "language_prob": prob,
                "threshold": th,
                "sample_start_sec": start,
                "sample_duration_sec": seg_len,
            }
        except Exception as e:
            # Fail closed: if the check is enabled but cannot run, we surface it.
            return {"checked": True, "english_detected": True, "error": f"bleed_check_failed: {e}"}
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _whisper_detect_language(self, wav_path: str) -> tuple[Optional[str], Optional[float]]:
        global _BLEED_WHISPER_MODEL, _BLEED_WHISPER_MODEL_NAME
        model_name = (os.getenv("BLEED_CHECK_WHISPER_MODEL") or "tiny").strip() or "tiny"
        try:
            import whisper  # type: ignore
        except Exception:
            raise RuntimeError("whisper_unavailable")

        if _BLEED_WHISPER_MODEL is None or _BLEED_WHISPER_MODEL_NAME != model_name:
            _BLEED_WHISPER_MODEL = whisper.load_model(model_name)
            _BLEED_WHISPER_MODEL_NAME = model_name

        audio = whisper.load_audio(wav_path)
        audio = whisper.pad_or_trim(audio)
        mel = whisper.log_mel_spectrogram(audio).to(_BLEED_WHISPER_MODEL.device)
        _, probs = _BLEED_WHISPER_MODEL.detect_language(mel)
        if not probs:
            # Treat "no confident speech detected" as non-English for bleed purposes.
            return None, 0.0
        lang = max(probs, key=probs.get)
        return lang, float(probs.get(lang) or 0.0)
    
    def _calculate_alignment_score(
        self,
        alignment_map: List[Dict],
        scene_cuts: List[Dict]
    ) -> float:
        """Calculate how well narration aligns with scene cuts."""
        if not alignment_map:
            return 0.5  # Default score
        
        total_offset = sum(a.get("offset", 0) for a in alignment_map)
        avg_offset = total_offset / len(alignment_map)
        
        # Score: 1.0 if avg offset is 0, decreasing as offset increases
        # 0.5 second tolerance = 1.0 score
        # 2.0 second offset = 0.5 score
        # 5.0 second offset = 0.0 score
        
        score = max(0.0, 1.0 - (avg_offset / 5.0))
        return round(score, 2)
    
    async def _get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return float(result.stdout.strip())
            
        except Exception as e:
            print(f"Duration check error: {e}")
            return 0.0
    
    async def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds."""
        return await self._get_video_duration(audio_path)  # Same ffprobe command works
