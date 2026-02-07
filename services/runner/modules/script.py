"""
Part C: Amharic Script Generation Module
Generates high-retention Amharic recap scripts using Gemini.
"""

import os
import json
import logging
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
        self.narrator_persona = (os.getenv("NARRATOR_PERSONA") or "futuristic captain").strip()
        self.beat_seconds = int(os.getenv("SCRIPT_BEAT_SECONDS") or "20")
        self.max_beats = int(os.getenv("SCRIPT_MAX_BEATS") or "60")

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

        prompt = f"""
You are an expert Amharic scriptwriter for YouTube movie recaps.
Your persona is: {self.narrator_persona}.

Task: Write a full movie recap script in Amharic (Ge'ez script).
Video Title: {video_title}
Transcript Source:
{transcript_context}

Requirements:
1. HOOK: 15-second intro that grabs attention immediately.
2. BEATS: Break the story into segments. For each beat:
   - Narration: The Amharic voiceover (engaging, not literal translation).
   - Visual Prompt: Description for a thumbnail/scene generator (in English).
   - On Screen Text: Short Amharic text to show on screen (optional).
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
            # We use the generate_json method from our client
            script_obj = gemini.generate_json(prompt, FullScript)
            
            if not script_obj:
                raise RuntimeError("Empty response from Gemini")
            
            # Convert Pydantic model to dict if needed, or if generate_json returned a dict/object
            # generate_json returns the Pydantic instance if schema is provided
            if isinstance(script_obj, BaseModel):
                script_data = script_obj.model_dump()
            else:
                script_data = script_obj

            # Legacy compatibility: VoiceGenerator expects "full_script" key
            # We store the structured data as a JSON string in this key
            script_data["full_script"] = json.dumps(script_data)

            # Save to DB
            self.db.save_script(video_id, script_data)
            self.db.update_video_status(video_id, "scripted")
            
            return script_data

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
