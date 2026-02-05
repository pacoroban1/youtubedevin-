"""
Part C: Amharic Script Generation Module
Generates high-retention Amharic recap scripts (not literal translation).
"""

import os
import json
from typing import Dict, Any, List, Optional
import google.generativeai as genai


class ScriptGenerator:
    def __init__(self, db):
        self.db = db
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel("gemini-1.5-pro")
        else:
            self.model = None
    
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
        main_segments = await self._generate_main_recap(transcript, timestamps)
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
        timestamps: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Generate main recap segments in Amharic."""
        if not self.model:
            return self._fallback_segments()
        
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
