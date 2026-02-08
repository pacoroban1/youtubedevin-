"""
Part C: Amharic Script Generation Module
Generates high-retention Amharic recap scripts using Gemini.
"""

import os
import json
import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

from modules.gemini_client import gemini
from pydantic import BaseModel

# Configure logging
logger = logging.getLogger("script_generator")
logger.setLevel(logging.INFO)

# Pydantic models for structured output
class ScriptBeat(BaseModel):
    start_time: float
    end_time: float
    narration_text: str
    visual_prompt: str
    on_screen_text: str

class FullScript(BaseModel):
    hook: str
    beats: List[ScriptBeat]
    payoff: str
    cta: str
    language: str
    persona: str
    quality_score: float

class ScriptGenerator:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.narrator_persona = (os.getenv("NARRATOR_PERSONA") or "futuristic captain").strip()
        self.beat_seconds = int(os.getenv("SCRIPT_BEAT_SECONDS") or "20")
        self.max_beats = int(os.getenv("SCRIPT_MAX_BEATS") or "60")
        self.quality_min = float(os.getenv("SCRIPT_QUALITY_MIN") or "0.85")
        self.max_attempts = int(os.getenv("SCRIPT_MAX_ATTEMPTS") or "2")

    async def generate_full_script(self, video_id: str) -> Dict[str, Any]:
        """Generates a full structured script for the video."""
        transcript_data = self.db.get_transcript(video_id)
        if not transcript_data or not transcript_data.get("cleaned_transcript"):
            raise ValueError(f"No transcript found for video {video_id}")

        transcript = transcript_data["cleaned_transcript"]
        video_data = self.db.get_video(video_id)
        video_title = video_data.get("title", "") if video_data else ""

        # Limit transcript context to avoid context window issues (though Gemini 2.0 is huge)
        # using 50k chars is safe and usually enough for a movie recap
        transcript_context = transcript[:50000]

        base_prompt = f"""
You are an expert Amharic scriptwriter for YouTube movie recaps.
Your persona is: {self.narrator_persona}.

Task: Write a full movie recap script in Amharic (Ge'ez script).
Critical: This must be a NEW retelling (transformative), not a literal translation and not copied phrasing.
Style: High energy, suspenseful, Ethiopian audience context, short punchy sentences, rhetorical questions, open loops.

Video Title: {video_title}
Transcript Source:
{transcript_context}

Requirements:
1. HOOK: 15-second intro that grabs attention immediately.
2. BEATS: Break the story into segments. For each beat:
   - Narration: The Amharic voiceover (engaging, not literal translation).
   - Visual Prompt: Description for a thumbnail/scene generator (in English).
   - On Screen Text: Short Amharic text to show on screen (optional).
   - Timing: start_time/end_time in seconds, strictly increasing, covering the recap after the hook.
3. PAYOFF: Satisfying conclusion.
4. CTA: Call to action (Subscribe/Like).

Output JSON format matches this schema:
{{
  "hook": "string",
  "beats": [
    {{
      "start_time": 0.0,
      "end_time": 20.0,
      "narration_text": "Amharic narration...",
      "visual_prompt": "English image description...",
      "on_screen_text": "Short text"
    }}
  ],
  "payoff": "string",
  "cta": "string",
  "language": "am",
  "persona": "{self.narrator_persona}",
  "quality_score": 0.95
}}
"""
        
        try:
            # We use the generate_json method from our client.
            # Add a small quality loop to avoid flat/literal outputs (bounded attempts to control cost).
            revision_notes = ""
            last_err: Optional[Exception] = None
            structured: Dict[str, Any] = {}
            legacy: Dict[str, Any] = {}
            script_obj: Any = None

            for attempt in range(max(1, self.max_attempts)):
                prompt = base_prompt
                if revision_notes:
                    prompt += f"\n\nRevision notes:\n{revision_notes}\n"

                script_obj = gemini.generate_json(prompt, FullScript)
            
                if not script_obj:
                    raise RuntimeError("Empty response from Gemini")
            
                # The Gemini client returns parsed JSON (dict/list). Coerce into a dict and
                # normalize keys to what downstream modules + DB schema expect.
                if isinstance(script_obj, BaseModel):
                    script_obj = script_obj.model_dump()
                if isinstance(script_obj, str):
                    script_obj = json.loads(script_obj)
                if not isinstance(script_obj, dict):
                    raise RuntimeError(f"unexpected_script_type:{type(script_obj)}")

                structured = self._normalize_structured_script(script_obj)
                legacy = self._structured_to_legacy_fields(structured)

                # Basic validity/quality heuristics (cheap, local).
                q = float(structured.get("quality_score") or 0.0)
                beats = structured.get("beats") or []
                hook = str(structured.get("hook") or "")
                latin = sum(1 for c in hook if ("a" <= c.lower() <= "z"))
                if hook:
                    latin_ratio = float(latin) / float(len(hook))
                else:
                    latin_ratio = 0.0

                ok_shape = bool(hook.strip()) and isinstance(beats, list) and len(beats) >= 3
                ok_quality = (q >= self.quality_min) and (latin_ratio <= 0.15)

                if ok_shape and ok_quality:
                    last_err = None
                    break

                if attempt >= (max(1, self.max_attempts) - 1):
                    # Last attempt: accept what we got (still stored; downstream may regenerate later).
                    break

                revision_notes = (
                    "Make it more cinematic and high-energy for Ethiopian viewers. "
                    "Avoid literal translation. Use short punchy Amharic sentences (Ge'ez script). "
                    "Stronger hook in first 5-10 seconds. Add rhetorical questions and suspense. "
                    "Return valid JSON only."
                )

            # Persist (DB schema expects legacy fields; also store full structured JSON).
            db_record = {
                **legacy,
                "full_script": json.dumps(structured, ensure_ascii=False),
                "quality_score": float(structured.get("quality_score") or 0.0),
            }
            script_id = self.db.save_script(video_id, db_record)
            if script_id == -1:
                raise RuntimeError("db_save_script_failed")
            self.db.update_video_status(video_id, "scripted")

            # Write a timestamped recap markdown artifact (best-effort; never fail script generation).
            recap = {}
            try:
                recap = self._write_recap_markdown(video_id, structured, legacy)
            except Exception:
                recap = {}

            return {**structured, **legacy, **recap, "full_script": db_record["full_script"], "script_id": script_id}

        except Exception as e:
            logger.error(f"Full script generation failed: {e}")
            raise

    async def generate_amharic_script(self, video_id: str) -> Dict[str, Any]:
        """Legacy wrapper for compatibility with existing endpoints."""
        full_script = await self.generate_full_script(video_id)
        
        return {
            "script_id": video_id,
            "hook_text": full_script.get("hook", ""),
            "segments_count": len(full_script.get("beats", [])),
            "full_script_length": len(json.dumps(full_script)),
            "quality_score": full_script.get("quality_score", 0.8),
            "script_preview": full_script.get("hook", "")
        }

    async def compress_script(self, script: str, target_duration: float) -> str:
        """Compress script to fit target duration."""
        # Simple implementation using text generation
        prompt = f"Compress this Amharic text to be spoken in {target_duration} seconds:\n{script}"
        return gemini.generate_text(prompt)

    def _normalize_structured_script(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize/clean the model output into a stable structured schema."""
        hook = str(obj.get("hook") or "").strip()
        payoff = str(obj.get("payoff") or "").strip()
        cta = str(obj.get("cta") or "").strip()
        language = (obj.get("language") or "am") if isinstance(obj.get("language"), str) else "am"
        persona = str(obj.get("persona") or self.narrator_persona).strip()

        beats_in = obj.get("beats") or []
        if not isinstance(beats_in, list):
            beats_in = []

        beats_out: List[Dict[str, Any]] = []
        for b in beats_in[: self.max_beats]:
            if not isinstance(b, dict):
                continue
            start = self._coerce_float(b.get("start_time"), default=None)
            end = self._coerce_float(b.get("end_time"), default=None)
            narration = str(b.get("narration_text") or "").strip()
            visual = str(b.get("visual_prompt") or "").strip()
            on_screen = str(b.get("on_screen_text") or "").strip()
            beats_out.append(
                {
                    "start_time": start,
                    "end_time": end,
                    "narration_text": narration,
                    "visual_prompt": visual,
                    "on_screen_text": on_screen,
                }
            )

        quality = self._coerce_float(obj.get("quality_score"), default=0.8)
        # Keep in [0,1] range; some prompts might return 95.
        if quality > 1.0:
            quality = quality / 100.0
        quality = max(0.0, min(1.0, quality))

        return {
            "hook": hook,
            "beats": beats_out,
            "payoff": payoff,
            "cta": cta,
            "language": language,
            "persona": persona,
            "quality_score": quality,
        }

    def _structured_to_legacy_fields(self, structured: Dict[str, Any]) -> Dict[str, Any]:
        """Convert the structured script into legacy DB/API fields used by other modules."""
        hook_text = str(structured.get("hook") or "").strip()
        payoff_text = str(structured.get("payoff") or "").strip()
        cta_text = str(structured.get("cta") or "").strip()

        segments: List[Dict[str, Any]] = []
        beats = structured.get("beats") or []
        if isinstance(beats, list):
            for beat in beats:
                if not isinstance(beat, dict):
                    continue
                start = self._coerce_float(beat.get("start_time"), default=None)
                end = self._coerce_float(beat.get("end_time"), default=None)
                est = None
                if start is not None and end is not None and end >= start:
                    est = float(end - start)
                if est is None:
                    est = float(self.beat_seconds)
                segments.append(
                    {
                        "text": str(beat.get("narration_text") or "").strip(),
                        "visual_prompt": str(beat.get("visual_prompt") or "").strip(),
                        "on_screen_text": str(beat.get("on_screen_text") or "").strip(),
                        "estimated_duration": est,
                        "start_time": start,
                        "end_time": end,
                    }
                )

        return {
            "hook_text": hook_text,
            "main_recap_segments": segments,
            "payoff_text": payoff_text,
            "cta_text": cta_text,
        }

    def _write_recap_markdown(self, video_id: str, structured: Dict[str, Any], legacy: Dict[str, Any]) -> Dict[str, Any]:
        out_dir = os.path.join(self.media_dir, "output", video_id)
        os.makedirs(out_dir, exist_ok=True)
        md_path = os.path.join(out_dir, "recap.md")

        hook = str(structured.get("hook") or "").strip()
        segments = legacy.get("main_recap_segments") or []
        payoff = str(structured.get("payoff") or "").strip()
        cta = str(structured.get("cta") or "").strip()

        # Chapters derived from estimated durations (hook fixed at 15s).
        hook_seconds = 15.0
        t = hook_seconds
        chapter_lines = [f"{self._fmt_ts(0)} - መግቢያ"]
        for i, seg in enumerate(segments):
            title = self._chapter_title_from_segment(seg, i + 1)
            chapter_lines.append(f"{self._fmt_ts(t)} - {title}")
            dur = self._coerce_float((seg or {}).get("estimated_duration"), default=float(self.beat_seconds))
            t += max(1.0, dur)
        if payoff or cta:
            chapter_lines.append(f"{self._fmt_ts(t)} - መደምደሚያ")

        md: List[str] = []
        md.append(f"# Timestamped Recap ({video_id})")
        md.append("")
        md.append("## Chapters")
        md.extend([f"- {line}" for line in chapter_lines])
        md.append("")
        md.append("## Hook")
        md.append(hook or "(empty)")
        md.append("")
        md.append("## Beats")
        for i, seg in enumerate(segments):
            md.append(f"### Beat {i+1}")
            md.append(str((seg or {}).get("text") or "(empty)").strip())
            md.append("")
        md.append("## Payoff")
        md.append(payoff or "(empty)")
        md.append("")
        md.append("## CTA")
        md.append(cta or "(empty)")
        md.append("")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md).strip() + "\n")

        return {
            "recap_markdown_path": md_path,
            "recap_markdown_url": f"/api/media/output/{video_id}/recap.md",
        }

    def _chapter_title_from_segment(self, seg: Dict[str, Any], idx: int) -> str:
        on_screen = str((seg or {}).get("on_screen_text") or "").strip()
        if on_screen:
            return self._short_title(on_screen)
        text = str((seg or {}).get("text") or "").strip()
        if text:
            return self._short_title(text)
        return f"ክፍል {idx}"

    def _short_title(self, s: str, *, max_len: int = 28) -> str:
        s = re.sub(r"\s+", " ", s or "").strip()
        if not s:
            return ""
        # Strip obvious punctuation; keep Ethiopic/latin/numbers.
        s = re.sub(r"[\\[\\]{}()<>\"“”'`]", "", s)
        s = re.sub(r"[,:;!?]+", "", s).strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 3].rstrip() + "..."

    def _fmt_ts(self, seconds: float) -> str:
        try:
            s = int(max(0, seconds))
        except Exception:
            s = 0
        m = s // 60
        sec = s % 60
        return f"{m}:{sec:02d}"

    def _coerce_float(self, v: Any, *, default: Optional[float]) -> Optional[float]:
        if v is None:
            return default
        try:
            return float(v)
        except Exception:
            return default
