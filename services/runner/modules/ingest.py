"""
Part B: Video Ingest Module
Downloads videos and extracts/generates transcripts.
"""

import os
import subprocess
import json
from typing import Dict, Any, Optional
from datetime import datetime
import httpx


class VideoIngest:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
    
    async def process_video(self, video_id: str) -> Dict[str, Any]:
        """
        Download video and extract/generate transcript.
        
        Args:
            video_id: YouTube video ID
        
        Returns:
            Dict with transcript data and metadata
        """
        # Create video directory
        video_dir = os.path.join(self.media_dir, "videos", video_id)
        os.makedirs(video_dir, exist_ok=True)
        
        # Step 1: Download video with yt-dlp
        video_path = await self._download_video(video_id, video_dir)
        
        if not video_path:
            raise Exception(f"Failed to download video {video_id}")
        
        # Step 2: Try to get YouTube captions first
        transcript_data = await self._get_youtube_captions(video_id)
        
        # Step 3: If no captions, transcribe with Whisper or Gemini
        if not transcript_data or not transcript_data.get("raw_transcript"):
            audio_path = await self._extract_audio(video_path, video_dir)
            transcript_data = await self._transcribe_audio(audio_path, video_id)
        
        # Step 4: Clean transcript
        if transcript_data.get("raw_transcript"):
            transcript_data["cleaned_transcript"] = await self._clean_transcript(
                transcript_data["raw_transcript"]
            )
        
        # Step 5: Detect language
        transcript_data["language_detected"] = await self._detect_language(
            transcript_data.get("cleaned_transcript", transcript_data.get("raw_transcript", ""))
        )
        
        # Save to database
        self.db.save_transcript(video_id, transcript_data)
        self.db.update_video_status(video_id, "ingested")
        
        return {
            "video_id": video_id,
            "video_path": video_path,
            "source": transcript_data.get("source", "unknown"),
            "language": transcript_data.get("language_detected", "unknown"),
            "transcript_length": len(transcript_data.get("cleaned_transcript", ""))
        }
    
    async def _download_video(self, video_id: str, output_dir: str) -> Optional[str]:
        """Download video using yt-dlp."""
        output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
        
        cmd = [
            "yt-dlp",
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--no-playlist",
            f"https://www.youtube.com/watch?v={video_id}"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode != 0:
                print(f"yt-dlp error: {result.stderr}")
                return None
            
            # Find the downloaded file
            for ext in ["mp4", "mkv", "webm"]:
                video_path = os.path.join(output_dir, f"{video_id}.{ext}")
                if os.path.exists(video_path):
                    return video_path
            
            return None
            
        except subprocess.TimeoutExpired:
            print(f"Download timeout for video {video_id}")
            return None
        except Exception as e:
            print(f"Download error: {e}")
            return None
    
    async def _get_youtube_captions(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Try to get captions from YouTube."""
        try:
            # Use yt-dlp to get subtitles
            cmd = [
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--skip-download",
                "--sub-format", "json3",
                "-o", f"/tmp/{video_id}",
                f"https://www.youtube.com/watch?v={video_id}"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Check for subtitle file
            sub_file = f"/tmp/{video_id}.en.json3"
            if os.path.exists(sub_file):
                with open(sub_file, "r") as f:
                    captions_data = json.load(f)
                
                # Parse captions
                transcript_parts = []
                timestamps = []
                
                for event in captions_data.get("events", []):
                    if "segs" in event:
                        start_time = event.get("tStartMs", 0) / 1000
                        text = "".join(seg.get("utf8", "") for seg in event["segs"])
                        if text.strip():
                            transcript_parts.append(text)
                            timestamps.append({
                                "start": start_time,
                                "text": text.strip()
                            })
                
                raw_transcript = " ".join(transcript_parts)
                
                # Clean up temp file
                os.remove(sub_file)
                
                if raw_transcript:
                    return {
                        "raw_transcript": raw_transcript,
                        "timestamps": timestamps,
                        "source": "youtube_captions"
                    }
            
            return None
            
        except Exception as e:
            print(f"Error getting YouTube captions: {e}")
            return None
    
    async def _extract_audio(self, video_path: str, output_dir: str) -> str:
        """Extract audio from video for transcription."""
        audio_path = os.path.join(output_dir, "audio.wav")
        
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            audio_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=300)
            return audio_path
        except Exception as e:
            print(f"Audio extraction error: {e}")
            return video_path  # Return video path as fallback
    
    async def _transcribe_audio(self, audio_path: str, video_id: str) -> Dict[str, Any]:
        """Transcribe audio using Whisper or Gemini."""
        # Try Whisper first (local)
        try:
            import whisper
            
            model = whisper.load_model("base")
            result = model.transcribe(audio_path)
            
            timestamps = []
            for segment in result.get("segments", []):
                timestamps.append({
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"]
                })
            
            return {
                "raw_transcript": result["text"],
                "timestamps": timestamps,
                "source": "whisper"
            }
            
        except Exception as e:
            print(f"Whisper transcription failed: {e}")
        
        # Fallback to Gemini if available
        if self.gemini_api_key:
            try:
                return await self._transcribe_with_gemini(audio_path)
            except Exception as e:
                print(f"Gemini transcription failed: {e}")
        
        return {
            "raw_transcript": "",
            "timestamps": [],
            "source": "failed"
        }
    
    async def _transcribe_with_gemini(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe audio using Google Gemini."""
        import google.generativeai as genai
        
        genai.configure(api_key=self.gemini_api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # Upload audio file
        audio_file = genai.upload_file(audio_path)
        
        prompt = """Transcribe this audio file. 
        Return the transcription as plain text.
        Include timestamps in the format [MM:SS] at the start of each major section or topic change."""
        
        response = model.generate_content([prompt, audio_file])
        
        return {
            "raw_transcript": response.text,
            "timestamps": [],  # Parse timestamps from response if needed
            "source": "gemini"
        }
    
    async def _clean_transcript(self, raw_transcript: str) -> str:
        """Clean and format the transcript."""
        if not raw_transcript:
            return ""
        
        # Basic cleaning
        cleaned = raw_transcript
        
        # Remove multiple spaces
        import re
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Remove common filler words/sounds
        fillers = ["um", "uh", "like", "you know", "basically", "actually"]
        for filler in fillers:
            cleaned = re.sub(rf'\b{filler}\b', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up punctuation
        cleaned = re.sub(r'\s+([.,!?])', r'\1', cleaned)
        cleaned = re.sub(r'([.,!?])\s*([.,!?])+', r'\1', cleaned)
        
        # Remove extra whitespace again
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # If Gemini is available, use it for better cleaning
        if self.gemini_api_key:
            try:
                cleaned = await self._clean_with_gemini(cleaned)
            except Exception as e:
                print(f"Gemini cleaning failed: {e}")
        
        return cleaned
    
    async def _clean_with_gemini(self, transcript: str) -> str:
        """Use Gemini to clean and improve transcript."""
        import google.generativeai as genai
        
        genai.configure(api_key=self.gemini_api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt = f"""Clean up this transcript by:
1. Fixing grammar and punctuation
2. Removing filler words and repetitions
3. Breaking into proper sentences and paragraphs
4. Keeping the meaning exactly the same

Transcript:
{transcript[:10000]}  # Limit to avoid token limits

Return only the cleaned transcript, nothing else."""
        
        response = model.generate_content(prompt)
        return response.text
    
    async def _detect_language(self, text: str) -> str:
        """Detect the language of the transcript."""
        if not text:
            return "unknown"
        
        # Simple heuristic for common languages
        # In production, use a proper language detection library
        
        # Check for Amharic characters (Ethiopic script)
        if any('\u1200' <= char <= '\u137F' for char in text):
            return "am"
        
        # Check for Arabic characters
        if any('\u0600' <= char <= '\u06FF' for char in text):
            return "ar"
        
        # Default to English
        return "en"
