"""
YouTube Shorts Auto-Generator Module
Automatically creates 60-second vertical clips from long videos.
Detects key moments, crops to 9:16, adds captions/overlays.
"""

import os
import subprocess
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import tempfile
import random


class ShortsGenerator:
    """
    Generates YouTube Shorts from long-form videos.
    
    Features:
    - Scene detection to find key moments
    - Audio peak detection for engaging segments
    - Vertical cropping (9:16 aspect ratio)
    - Text overlays with hooks
    - Automatic caption burning
    - Multiple shorts per video (3-5)
    """
    
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.shorts_dir = os.path.join(self.media_dir, "shorts")
        os.makedirs(self.shorts_dir, exist_ok=True)
        
        # Shorts specs (YouTube Shorts requirements)
        self.width = 1080
        self.height = 1920
        self.max_duration = 60  # seconds
        self.min_duration = 15  # seconds
        self.target_duration = 45  # optimal duration
        
        # Detection thresholds
        self.scene_threshold = 0.3
        self.audio_peak_threshold = 0.7
        
        # Font settings for overlays
        self.font_path = os.getenv("AMHARIC_FONT_PATH", "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Regular.ttf")
        self.hook_font_size = 72
        self.caption_font_size = 48
        
    async def generate_shorts(
        self,
        video_id: str,
        source_video_path: str,
        transcript: Optional[str] = None,
        hooks: Optional[List[str]] = None,
        num_shorts: int = 5
    ) -> Dict[str, Any]:
        """
        Generate multiple YouTube Shorts from a long video.
        
        Args:
            video_id: Database video ID
            source_video_path: Path to the source video file
            transcript: Optional transcript for caption generation
            hooks: Optional list of Amharic hook texts for overlays
            num_shorts: Number of shorts to generate (default 5)
            
        Returns:
            Dict with generated shorts info and paths
        """
        result = {
            "video_id": video_id,
            "shorts": [],
            "errors": [],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if not os.path.exists(source_video_path):
            result["errors"].append(f"Source video not found: {source_video_path}")
            return result
            
        try:
            # Step 1: Analyze video for key moments
            video_info = await self._get_video_info(source_video_path)
            duration = video_info.get("duration", 0)
            
            if duration < self.min_duration:
                result["errors"].append(f"Video too short: {duration}s < {self.min_duration}s minimum")
                return result
                
            # Step 2: Detect scenes and audio peaks
            key_moments = await self._detect_key_moments(source_video_path, duration)
            
            # Step 3: Select best segments for shorts
            segments = self._select_segments(key_moments, duration, num_shorts)
            
            # Step 4: Generate each short
            for i, segment in enumerate(segments):
                try:
                    short_info = await self._create_short(
                        video_id=video_id,
                        source_path=source_video_path,
                        segment=segment,
                        index=i + 1,
                        hook=hooks[i] if hooks and i < len(hooks) else None,
                        transcript=transcript
                    )
                    result["shorts"].append(short_info)
                except Exception as e:
                    result["errors"].append(f"Short {i+1} failed: {str(e)}")
                    
            # Step 5: Save to database
            await self._save_shorts_to_db(video_id, result["shorts"])
            
        except Exception as e:
            result["errors"].append(f"Generation failed: {str(e)}")
            
        return result
        
    async def _get_video_info(self, video_path: str) -> Dict[str, Any]:
        """Get video metadata using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        
        info = json.loads(stdout.decode())
        
        # Extract relevant info
        duration = float(info.get("format", {}).get("duration", 0))
        
        video_stream = None
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break
                
        return {
            "duration": duration,
            "width": video_stream.get("width", 1920) if video_stream else 1920,
            "height": video_stream.get("height", 1080) if video_stream else 1080,
            "fps": eval(video_stream.get("r_frame_rate", "30/1")) if video_stream else 30
        }
        
    async def _detect_key_moments(
        self,
        video_path: str,
        duration: float
    ) -> List[Dict[str, Any]]:
        """
        Detect key moments using scene detection and audio analysis.
        Returns list of timestamps with scores.
        """
        moments = []
        
        # Scene detection using ffmpeg
        scene_changes = await self._detect_scene_changes(video_path)
        for timestamp in scene_changes:
            moments.append({
                "timestamp": timestamp,
                "type": "scene_change",
                "score": 0.7
            })
            
        # Audio peak detection
        audio_peaks = await self._detect_audio_peaks(video_path)
        for timestamp in audio_peaks:
            # Check if near existing moment
            existing = next((m for m in moments if abs(m["timestamp"] - timestamp) < 2), None)
            if existing:
                existing["score"] = min(1.0, existing["score"] + 0.3)
                existing["type"] = "scene_and_audio"
            else:
                moments.append({
                    "timestamp": timestamp,
                    "type": "audio_peak",
                    "score": 0.6
                })
                
        # Sort by score
        moments.sort(key=lambda x: x["score"], reverse=True)
        
        return moments
        
    async def _detect_scene_changes(self, video_path: str) -> List[float]:
        """Detect scene changes using ffmpeg."""
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-filter:v", f"select='gt(scene,{self.scene_threshold})',showinfo",
            "-f", "null",
            "-"
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        
        # Parse timestamps from ffmpeg output
        timestamps = []
        for line in stderr.decode().split("\n"):
            if "pts_time:" in line:
                try:
                    pts_part = line.split("pts_time:")[1].split()[0]
                    timestamps.append(float(pts_part))
                except (IndexError, ValueError):
                    continue
                    
        return timestamps
        
    async def _detect_audio_peaks(self, video_path: str) -> List[float]:
        """Detect audio peaks/loud moments."""
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-af", "silencedetect=noise=-30dB:d=0.5",
            "-f", "null",
            "-"
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        
        # Parse silence end times (these are where audio gets loud)
        timestamps = []
        for line in stderr.decode().split("\n"):
            if "silence_end:" in line:
                try:
                    time_part = line.split("silence_end:")[1].split()[0]
                    timestamps.append(float(time_part))
                except (IndexError, ValueError):
                    continue
                    
        return timestamps
        
    def _select_segments(
        self,
        moments: List[Dict[str, Any]],
        total_duration: float,
        num_shorts: int
    ) -> List[Dict[str, Any]]:
        """
        Select best non-overlapping segments for shorts.
        """
        segments = []
        used_ranges = []
        
        # Add evenly spaced fallback moments if not enough detected
        if len(moments) < num_shorts * 2:
            interval = total_duration / (num_shorts + 1)
            for i in range(1, num_shorts + 1):
                moments.append({
                    "timestamp": interval * i,
                    "type": "interval",
                    "score": 0.3
                })
            moments.sort(key=lambda x: x["score"], reverse=True)
            
        for moment in moments:
            if len(segments) >= num_shorts:
                break
                
            start = max(0, moment["timestamp"] - 5)  # Start 5s before moment
            end = min(total_duration, start + self.target_duration)
            
            # Adjust if too close to end
            if end - start < self.min_duration:
                start = max(0, end - self.target_duration)
                
            # Check for overlap with existing segments
            overlaps = False
            for used_start, used_end in used_ranges:
                if not (end <= used_start or start >= used_end):
                    overlaps = True
                    break
                    
            if not overlaps:
                segments.append({
                    "start": start,
                    "end": end,
                    "duration": end - start,
                    "moment": moment
                })
                used_ranges.append((start, end))
                
        return segments
        
    async def _create_short(
        self,
        video_id: str,
        source_path: str,
        segment: Dict[str, Any],
        index: int,
        hook: Optional[str] = None,
        transcript: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a single YouTube Short from a segment.
        """
        output_dir = os.path.join(self.shorts_dir, video_id)
        os.makedirs(output_dir, exist_ok=True)
        
        output_path = os.path.join(output_dir, f"short_{index}.mp4")
        
        # Build ffmpeg filter chain
        filters = []
        
        # 1. Crop to vertical (center crop for 9:16)
        filters.append(
            "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2"
        )
        
        # 2. Add hook text overlay if provided
        if hook:
            # Escape special characters for ffmpeg
            escaped_hook = hook.replace("'", "'\\''").replace(":", "\\:")
            filters.append(
                f"drawtext=fontfile={self.font_path}:"
                f"text='{escaped_hook}':"
                f"fontsize={self.hook_font_size}:"
                "fontcolor=white:"
                "borderw=3:"
                "bordercolor=black:"
                f"x=(w-text_w)/2:"
                f"y=h*0.15:"
                "enable='between(t,0,5)'"
            )
            
        # 3. Add subtle zoom effect for engagement
        filters.append(
            "zoompan=z='min(zoom+0.0005,1.1)':"
            f"d={int(segment['duration'] * 30)}:"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"s={self.width}x{self.height}"
        )
        
        filter_complex = ",".join(filters)
        
        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(segment["start"]),
            "-i", source_path,
            "-t", str(segment["duration"]),
            "-vf", filter_complex,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            output_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise Exception(f"FFmpeg failed: {stderr.decode()[:500]}")
            
        # Generate thumbnail for the short
        thumb_path = os.path.join(output_dir, f"short_{index}_thumb.jpg")
        await self._generate_thumbnail(output_path, thumb_path)
        
        return {
            "index": index,
            "path": output_path,
            "thumbnail": thumb_path,
            "start": segment["start"],
            "end": segment["end"],
            "duration": segment["duration"],
            "hook": hook,
            "moment_type": segment["moment"]["type"],
            "moment_score": segment["moment"]["score"]
        }
        
    async def _generate_thumbnail(self, video_path: str, output_path: str):
        """Generate thumbnail from middle of short."""
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vf", "select='eq(n,45)',scale=1080:1920",
            "-vframes", "1",
            output_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
    async def _save_shorts_to_db(self, video_id: str, shorts: List[Dict[str, Any]]):
        """Save generated shorts info to database."""
        query = """
            INSERT INTO shorts (video_id, index, path, thumbnail, start_time, end_time, 
                              duration, hook, moment_type, moment_score, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            ON CONFLICT (video_id, index) DO UPDATE SET
                path = EXCLUDED.path,
                thumbnail = EXCLUDED.thumbnail,
                start_time = EXCLUDED.start_time,
                end_time = EXCLUDED.end_time,
                duration = EXCLUDED.duration,
                hook = EXCLUDED.hook,
                moment_type = EXCLUDED.moment_type,
                moment_score = EXCLUDED.moment_score
        """
        
        for short in shorts:
            await self.db.execute(
                query,
                video_id,
                short["index"],
                short["path"],
                short["thumbnail"],
                short["start"],
                short["end"],
                short["duration"],
                short.get("hook"),
                short["moment_type"],
                short["moment_score"]
            )
            
    async def add_captions_to_short(
        self,
        short_path: str,
        captions: List[Dict[str, Any]],
        output_path: Optional[str] = None
    ) -> str:
        """
        Burn captions/subtitles into a short video.
        
        Args:
            short_path: Path to the short video
            captions: List of caption dicts with 'start', 'end', 'text' keys
            output_path: Optional output path (defaults to replacing original)
            
        Returns:
            Path to the captioned video
        """
        if output_path is None:
            output_path = short_path.replace(".mp4", "_captioned.mp4")
            
        # Create ASS subtitle file
        ass_path = short_path.replace(".mp4", ".ass")
        self._create_ass_file(captions, ass_path)
        
        # Burn subtitles using ffmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-i", short_path,
            "-vf", f"ass={ass_path}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "copy",
            output_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        return output_path
        
    def _create_ass_file(self, captions: List[Dict[str, Any]], output_path: str):
        """Create ASS subtitle file with styled captions."""
        header = """[Script Info]
Title: YouTube Short Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans Ethiopic,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,2,2,50,50,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        events = []
        for cap in captions:
            start = self._seconds_to_ass_time(cap["start"])
            end = self._seconds_to_ass_time(cap["end"])
            text = cap["text"].replace("\n", "\\N")
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(events))
            
    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Convert seconds to ASS time format (H:MM:SS.CC)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"
        
    async def upload_short_to_youtube(
        self,
        short_info: Dict[str, Any],
        title: str,
        description: str,
        tags: List[str]
    ) -> Dict[str, Any]:
        """
        Upload a generated short to YouTube.
        Uses the existing upload module.
        """
        # This will be integrated with the upload module
        # For now, return the prepared metadata
        return {
            "path": short_info["path"],
            "title": title[:100],  # YouTube title limit
            "description": description,
            "tags": tags,
            "shorts": True,
            "thumbnail": short_info.get("thumbnail")
        }
        
    async def generate_short_metadata(
        self,
        video_title: str,
        short_index: int,
        hook: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate optimized metadata for a YouTube Short.
        """
        # Create engaging title
        title_templates = [
            f"{video_title} - Part {short_index} #shorts",
            f"Wait for it... {video_title} #shorts",
            f"You won't believe this! {video_title} #shorts",
            f"{video_title} | Must Watch #shorts",
            f"This is INSANE! {video_title} #shorts"
        ]
        
        title = random.choice(title_templates)
        
        # Create description
        description = f"""
{hook if hook else video_title}

Watch the full video on our channel!

#shorts #viral #trending #amharic #ethiopian #recap
        """.strip()
        
        # Tags optimized for Shorts discovery
        tags = [
            "shorts",
            "viral",
            "trending",
            "amharic",
            "ethiopian",
            "recap",
            "movie recap",
            "film recap"
        ]
        
        return {
            "title": title,
            "description": description,
            "tags": tags
        }
