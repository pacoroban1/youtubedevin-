"""
Part C: Amharic Script Generation Module
Generates high-retention Amharic recap scripts (not literal translation).
"""

import os
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import google.generativeai as genai

from modules.translate import GoogleTranslateV2, LibreTranslate


class ScriptGenerator:
    def __init__(self, db):
        self.db = db
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")

        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel("gemini-1.5-pro")
            self.model_fast = genai.GenerativeModel("gemini-1.5-flash")
        else:
            self.model = None
            self.model_fast = None

        # Optional translation step. Default keeps existing behavior (Gemini rewrite in Amharic).
        #
        # If you provide GOOGLE_CLOUD_API_KEY but forget to set TRANSLATION_PROVIDER, we
        # default to Google translation so the "translate -> persona style" pipeline
        # is push-button.
        raw_provider = (os.getenv("TRANSLATION_PROVIDER") or "").strip().lower()
        if raw_provider in ("", "auto"):
            if os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_API_KEY"):
                raw_provider = "google"
            else:
                raw_provider = ""
        self.translation_provider = raw_provider
        self.translate_google = GoogleTranslateV2()
        self.translate_libre = LibreTranslate()

        # Optional narrator persona for the "scene reaction" vibe.
        self.narrator_persona = (os.getenv("NARRATOR_PERSONA") or "futuristic captain").strip()
        self.beat_seconds = int(os.getenv("SCRIPT_BEAT_SECONDS") or "20")
        self.max_beats = int(os.getenv("SCRIPT_MAX_BEATS") or "60")

    def _get_translator(self):
        provider = self.translation_provider
        if provider in ("", "none", "gemini"):
            return None
        if provider in ("google", "gcloud", "translate"):
            if not self.translate_google.configured():
                raise RuntimeError("TRANSLATION_PROVIDER=google but GOOGLE_CLOUD_API_KEY/GOOGLE_API_KEY is missing")
            return self.translate_google
        if provider in ("libretranslate", "libre", "open", "opensource", "open-source"):
            if not self.translate_libre.configured():
                raise RuntimeError("TRANSLATION_PROVIDER=libretranslate but LIBRETRANSLATE_URL is missing")
            return self.translate_libre
        raise RuntimeError(f"Unknown TRANSLATION_PROVIDER={provider!r}")

    async def generate_amharic_script(self, video_id: str) -> Dict[str, Any]:
        """
        Generate a high-retention Amharic recap script.
        
        This is NOT a literal translation - it's a better recap
        optimized for Amharic audience retention.
        
        Args:
            video_id: YouTube video ID
        
        Returns:
            Dict with script components and quality score
        """
        # Get transcript from database
        transcript_data = self.db.get_transcript(video_id)
        
        if not transcript_data or not transcript_data.get("cleaned_transcript"):
            raise Exception(f"No transcript found for video {video_id}")
        
        transcript = transcript_data["cleaned_transcript"]
        timestamps = transcript_data.get("timestamps", [])
        
        # Get video metadata
        video_data = self.db.get_video(video_id)
        video_title = video_data.get("title", "") if video_data else ""
        
        # Generate script components
        hook_text = await self._generate_hook(transcript, video_title)
        main_segments = await self._generate_main_recap(transcript, timestamps, video_title=video_title)
        payoff_text = await self._generate_payoff(transcript)
        cta_text = await self._generate_cta()
        
        # Combine into full script
        full_script = self._combine_script(hook_text, main_segments, payoff_text, cta_text)
        
        # Quality check
        quality_score = await self._check_quality(full_script)
        
        # Save to database
        script_data = {
            "hook_text": hook_text,
            "main_recap_segments": main_segments,
            "payoff_text": payoff_text,
            "cta_text": cta_text,
            "full_script": full_script,
            "quality_score": quality_score
        }
        
        script_id = self.db.save_script(video_id, script_data)
        self.db.update_video_status(video_id, "scripted")
        
        return {
            "script_id": script_id,
            "hook_text": hook_text,
            "segments_count": len(main_segments),
            "full_script_length": len(full_script),
            "quality_score": quality_score
        }
    
    async def _generate_hook(self, transcript: str, video_title: str) -> str:
        """Generate attention-grabbing Amharic hook (0-15 seconds)."""
        if not self.model:
            return self._fallback_hook()
        
        prompt = f"""You are an expert Amharic scriptwriter for YouTube movie recap videos.

Create a powerful HOOK in Amharic (Ethiopian language using Ge'ez script) for a movie recap video.

The hook should:
1. Be 2-3 sentences (15 seconds when spoken)
2. Create curiosity and stakes
3. Use dramatic, cinematic language
4. Make viewers NEED to watch the rest
5. Be written in natural, fluent Amharic

Original video title: {video_title}

Transcript excerpt (first 500 chars):
{transcript[:500]}

Write ONLY the Amharic hook text, nothing else. Use Ge'ez script (ፊደል)."""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Hook generation error: {e}")
            return self._fallback_hook()
    
    async def _generate_main_recap(
        self,
        transcript: str,
        timestamps: List[Dict],
        video_title: str = ""
    ) -> List[Dict[str, Any]]:
        """Generate main recap segments in Amharic."""
        if not self.model:
            return self._fallback_segments()

        # Optional pipeline: English recap beats -> Translate -> Persona rewrite.
        # This is useful when you want a strict translation step and then apply style/emotion separately.
        translator = self._get_translator()
        if translator is not None:
            return await self._generate_main_recap_translate_style(
                transcript,
                timestamps,
                video_title=video_title,
                translator=translator,
            )

        # Split transcript into chunks for processing
        chunk_size = 3000
        chunks = [transcript[i:i+chunk_size] for i in range(0, len(transcript), chunk_size)]
        
        segments = []
        
        for i, chunk in enumerate(chunks[:10]):  # Limit to 10 chunks
            prompt = f"""You are an expert Amharic scriptwriter for YouTube movie recap videos.

Convert this English movie recap segment into an engaging Amharic narration.

IMPORTANT RULES:
1. Do NOT translate literally - create a BETTER recap in Amharic
2. Use short, punchy sentences for high retention
3. Add dramatic pauses and emphasis where appropriate
4. Keep the story clear and easy to follow
5. Use natural, conversational Amharic
6. Write in Ge'ez script (ፊደል)

English segment {i+1}:
{chunk}

Write the Amharic recap segment. Include [PAUSE] markers where dramatic pauses should go."""

            try:
                response = self.model.generate_content(prompt)
                segment_text = response.text.strip()
                
                # Estimate timing based on text length
                # Amharic typically spoken at ~100-120 words per minute
                word_count = len(segment_text.split())
                estimated_duration = (word_count / 110) * 60  # seconds
                
                segments.append({
                    "segment_number": i + 1,
                    "text": segment_text,
                    "estimated_duration": estimated_duration,
                    "start_time": sum(s.get("estimated_duration", 0) for s in segments)
                })
                
            except Exception as e:
                print(f"Segment {i+1} generation error: {e}")
                continue
        
        return segments

    @dataclass
    class _Beat:
        start: float
        end: float
        text: str

    def _beats_from_timestamps(self, timestamps: List[Dict[str, Any]]) -> List["_Beat"]:
        # Timestamps can come from YouTube captions or Whisper.
        # Expected keys: start, end(optional), text.
        items = []
        for t in timestamps or []:
            try:
                start = float(t.get("start", 0.0))
            except Exception:
                continue
            end = t.get("end", None)
            try:
                end_f = float(end) if end is not None else None
            except Exception:
                end_f = None
            text = (t.get("text") or "").strip()
            if not text:
                continue
            items.append((start, end_f, text))
        items.sort(key=lambda x: x[0])

        beats: List[ScriptGenerator._Beat] = []
        if not items:
            return beats

        cur_start = items[0][0]
        cur_end = items[0][1] if items[0][1] is not None else cur_start
        buf: List[str] = []

        def flush():
            nonlocal cur_start, cur_end, buf
            merged = " ".join(buf).strip()
            if merged:
                beats.append(ScriptGenerator._Beat(start=cur_start, end=cur_end, text=merged))
            buf = []

        for i, (start, end, text) in enumerate(items):
            if not buf:
                cur_start = start
                cur_end = end if end is not None else start
            else:
                # Advance end.
                if end is not None:
                    cur_end = max(cur_end, end)
                else:
                    cur_end = max(cur_end, start)

            buf.append(text)

            # If we don't have explicit end times, approximate using next start.
            next_start = items[i + 1][0] if i + 1 < len(items) else None
            approx_end = cur_end
            if next_start is not None and (end is None):
                approx_end = max(approx_end, next_start)

            if (approx_end - cur_start) >= self.beat_seconds or len(" ".join(buf)) >= 900:
                # Use approx_end for better windowing.
                cur_end = approx_end
                flush()

        flush()
        return beats[: self.max_beats]

    def _beats_from_text(self, transcript: str) -> List["_Beat"]:
        # Fallback when timestamps are missing.
        chunk_size = 1200
        chunks = [transcript[i : i + chunk_size] for i in range(0, len(transcript), chunk_size)]
        beats: List[ScriptGenerator._Beat] = []
        t = 0.0
        for c in chunks[: self.max_beats]:
            beats.append(ScriptGenerator._Beat(start=t, end=t + self.beat_seconds, text=c))
            t += self.beat_seconds
        return beats

    async def _en_recap_with_emotion(self, beat_text: str, video_title: str) -> Dict[str, str]:
        """
        Produce a short English recap line plus emotion + reaction tag.
        """
        if not self.model_fast:
            # Minimal fallback without LLM.
            return {
                "recap_en": beat_text[:280],
                "emotion": "tense",
                "reaction_en": "Stay sharp.",
            }

        prompt = f"""You are writing beat-by-beat recap notes for a YouTube movie recap.

Input is a raw transcript excerpt (may be messy). Output STRICT JSON with keys:
- recap_en: 1-2 short sentences describing what happens (English).
- emotion: 1-3 words (e.g., fear, suspense, shock, triumph, mystery).
- reaction_en: 1 short sentence spoken by a narrator persona reacting to the beat.

Title/context: {video_title}

Transcript beat:
{beat_text[:1400]}
"""
        resp = self.model_fast.generate_content(prompt)
        txt = (resp.text or "").strip()
        # Best-effort JSON extraction.
        try:
            obj = json.loads(txt)
        except Exception:
            # Try to locate the first {...}
            start = txt.find("{")
            end = txt.rfind("}")
            if start != -1 and end != -1 and end > start:
                obj = json.loads(txt[start : end + 1])
            else:
                obj = {"recap_en": txt[:400], "emotion": "tense", "reaction_en": "Stay sharp."}

        recap_en = (obj.get("recap_en") or "").strip()
        emotion = (obj.get("emotion") or "tense").strip()
        reaction_en = (obj.get("reaction_en") or "").strip()
        if not reaction_en:
            reaction_en = "Stay sharp."
        return {"recap_en": recap_en, "emotion": emotion, "reaction_en": reaction_en}

    async def _stylize_amharic(self, translated_am: str, emotion: str) -> str:
        if not self.model:
            return translated_am

        prompt = f"""You are an Amharic narrator writing a high-retention movie recap voiceover.

Narrator persona: {self.narrator_persona}
Target: Ethiopian Amharic in Ge'ez script (ፊደል).

Rules:
1) Keep meaning but rewrite for retention and clarity (not literal).
2) Add cinematic emotion appropriate to: {emotion}
3) Use short punchy sentences.
4) Insert [PAUSE] markers for dramatic timing (1-2 per beat).
5) Do not add celebrity/real-person identity details.

Source (already translated to Amharic):
{translated_am[:900]}

Return ONLY the final Amharic narration for this beat.
"""
        resp = self.model.generate_content(prompt)
        return (resp.text or "").strip()

    async def _generate_main_recap_translate_style(
        self,
        transcript: str,
        timestamps: List[Dict[str, Any]],
        video_title: str = "",
        translator=None,
    ) -> List[Dict[str, Any]]:
        if translator is None:
            raise RuntimeError("internal: translator is required")

        beats = self._beats_from_timestamps(timestamps)
        if not beats:
            beats = self._beats_from_text(transcript)

        segments: List[Dict[str, Any]] = []

        for i, beat in enumerate(beats):
            en = await self._en_recap_with_emotion(beat.text, video_title=video_title)
            en_combined = f"EMOTION: {en['emotion']}. RECAP: {en['recap_en']} REACTION: {en['reaction_en']}"

            tr = await translator.translate_batch([en_combined], target="am", source="en")
            base_am = tr[0].translated_text if tr else ""
            final_am = await self._stylize_amharic(base_am, emotion=en["emotion"])

            # Estimate duration based on text length (same as old behavior).
            word_count = len(final_am.split())
            estimated_duration = (word_count / 110) * 60  # seconds

            segments.append(
                {
                    "segment_number": i + 1,
                    "start_time": beat.start,
                    "end_time": beat.end,
                    "emotion": en["emotion"],
                    "recap_en": en["recap_en"],
                    "reaction_en": en["reaction_en"],
                    "translated_am": base_am,
                    "text": final_am,
                    "estimated_duration": estimated_duration,
                    "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
                    "mode": "translate_then_style",
                }
            )

        return segments

    async def _generate_payoff(self, transcript: str) -> str:
        """Generate the ending/payoff in Amharic."""
        if not self.model:
            return self._fallback_payoff()
        
        # Get the last portion of transcript for the ending
        ending_portion = transcript[-2000:] if len(transcript) > 2000 else transcript
        
        prompt = f"""You are an expert Amharic scriptwriter for YouTube movie recap videos.

Create a powerful ENDING/PAYOFF in Amharic for this movie recap.

The payoff should:
1. Summarize the movie's conclusion dramatically
2. Leave viewers satisfied but wanting more
3. Be 2-3 sentences
4. Use Ge'ez script (ፊደል)

Transcript ending:
{ending_portion}

Write ONLY the Amharic payoff text, nothing else."""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Payoff generation error: {e}")
            return self._fallback_payoff()
    
    async def _generate_cta(self) -> str:
        """Generate call-to-action in Amharic."""
        if not self.model:
            return self._fallback_cta()
        
        prompt = """Create a short, engaging call-to-action in Amharic for a YouTube movie recap channel.

The CTA should:
1. Ask viewers to subscribe
2. Ask them to like the video
3. Mention they can watch more recaps
4. Be friendly and natural
5. Use Ge'ez script (ፊደል)

Write ONLY the Amharic CTA text (2-3 sentences), nothing else."""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"CTA generation error: {e}")
            return self._fallback_cta()
    
    def _combine_script(
        self,
        hook: str,
        segments: List[Dict],
        payoff: str,
        cta: str
    ) -> str:
        """Combine all script components into full script."""
        parts = [hook, ""]
        
        for segment in segments:
            parts.append(segment.get("text", ""))
            parts.append("")
        
        parts.extend([payoff, "", cta])
        
        return "\n\n".join(parts)
    
    async def _check_quality(self, script: str) -> float:
        """Check Amharic script quality using LLM self-critique."""
        if not self.model:
            return 0.7  # Default score without LLM
        
        prompt = f"""You are an Amharic language expert. Rate this Amharic script on a scale of 0-100.

Evaluate:
1. Grammar correctness (25 points)
2. Natural flow and readability (25 points)
3. Engagement and retention potential (25 points)
4. Proper use of Amharic expressions (25 points)

Script:
{script[:3000]}

Return ONLY a number between 0 and 100, nothing else."""

        try:
            response = self.model.generate_content(prompt)
            score_text = response.text.strip()
            
            # Extract number from response
            import re
            numbers = re.findall(r'\d+', score_text)
            if numbers:
                score = min(100, max(0, int(numbers[0])))
                return score / 100.0
            
            return 0.7
            
        except Exception as e:
            print(f"Quality check error: {e}")
            return 0.7
    
    def _fallback_hook(self) -> str:
        """Fallback hook if LLM is unavailable."""
        return "ይህን ፊልም ማየት አለባችሁ! አስደናቂ ታሪክ ነው። እስኪ እንይ..."
    
    def _fallback_segments(self) -> List[Dict[str, Any]]:
        """Fallback segments if LLM is unavailable."""
        return [{
            "segment_number": 1,
            "text": "ታሪኩ እንዲህ ይጀምራል...",
            "estimated_duration": 30,
            "start_time": 0
        }]
    
    def _fallback_payoff(self) -> str:
        """Fallback payoff if LLM is unavailable."""
        return "እና ታሪኩ በዚህ መልኩ ያበቃል። አስደናቂ ፊልም ነበር!"
    
    def _fallback_cta(self) -> str:
        """Fallback CTA if LLM is unavailable."""
        return "ይህን ቻናል ሰብስክራይብ ያድርጉ እና ላይክ ይስጡ! ተጨማሪ ፊልም ሪካፕ ለማየት ይጠብቁን።"
    
    async def compress_script(self, script: str, target_duration: float) -> str:
        """Compress script to fit target duration if too long."""
        if not self.model:
            return script
        
        prompt = f"""You are an Amharic editor. This script is too long.

Compress it to fit approximately {target_duration} seconds when spoken (about {int(target_duration * 2)} words in Amharic).

Keep the most important story points.
Maintain dramatic impact.
Use Ge'ez script.

Original script:
{script}

Write the compressed Amharic script, nothing else."""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Compression error: {e}")
            return script
