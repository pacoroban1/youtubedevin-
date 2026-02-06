"""
Auto-Subtitles Module
Generates and burns Amharic subtitles into videos.
Supports multiple subtitle styles and positioning.
"""

import os
import subprocess
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import tempfile
import re


class SubtitleGenerator:
    """
    Generates and burns subtitles into videos.
    
    Features:
    - Generate subtitles from transcript/audio
    - Multiple style presets (modern, classic, minimal)
    - Amharic font support
    - Word-by-word highlighting
    - Position customization
    - Burn subtitles into video
    """
    
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.subtitles_dir = os.path.join(self.media_dir, "subtitles")
        os.makedirs(self.subtitles_dir, exist_ok=True)
        
        # Font settings
        self.font_path = os.getenv(
            "AMHARIC_FONT_PATH", 
            "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Regular.ttf"
        )
        self.font_bold_path = os.getenv(
            "AMHARIC_FONT_BOLD_PATH",
            "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Bold.ttf"
        )
        
        # Style presets
        self.style_presets = {
            "modern": {
                "font_size": 48,
                "primary_color": "&H00FFFFFF",  # White
                "outline_color": "&H00000000",  # Black
                "back_color": "&H80000000",     # Semi-transparent black
                "outline": 3,
                "shadow": 2,
                "margin_v": 80,
                "alignment": 2,  # Bottom center
                "bold": True
            },
            "classic": {
                "font_size": 42,
                "primary_color": "&H00FFFF00",  # Yellow
                "outline_color": "&H00000000",
                "back_color": "&H00000000",
                "outline": 2,
                "shadow": 1,
                "margin_v": 60,
                "alignment": 2,
                "bold": False
            },
            "minimal": {
                "font_size": 36,
                "primary_color": "&H00FFFFFF",
                "outline_color": "&H00000000",
                "back_color": "&H00000000",
                "outline": 1,
                "shadow": 0,
                "margin_v": 50,
                "alignment": 2,
                "bold": False
            },
            "cinematic": {
                "font_size": 52,
                "primary_color": "&H00FFFFFF",
                "outline_color": "&H00000000",
                "back_color": "&HAA000000",
                "outline": 4,
                "shadow": 3,
                "margin_v": 100,
                "alignment": 2,
                "bold": True
            },
            "top": {
                "font_size": 44,
                "primary_color": "&H00FFFFFF",
                "outline_color": "&H00000000",
                "back_color": "&H80000000",
                "outline": 3,
                "shadow": 2,
                "margin_v": 80,
                "alignment": 8,  # Top center
                "bold": True
            }
        }
        
    async def generate_subtitles(
        self,
        video_id: str,
        transcript: str,
        timestamps: Optional[List[Dict[str, Any]]] = None,
        style: str = "modern"
    ) -> Dict[str, Any]:
        """
        Generate subtitle files from transcript.
        
        Args:
            video_id: Database video ID
            transcript: Full transcript text
            timestamps: Optional list of word/segment timestamps
            style: Style preset name
            
        Returns:
            Dict with subtitle file paths and metadata
        """
        result = {
            "video_id": video_id,
            "srt_path": None,
            "ass_path": None,
            "vtt_path": None,
            "style": style,
            "segment_count": 0,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        output_dir = os.path.join(self.subtitles_dir, video_id)
        os.makedirs(output_dir, exist_ok=True)
        
        # Parse transcript into segments
        if timestamps:
            segments = self._timestamps_to_segments(timestamps)
        else:
            segments = self._text_to_segments(transcript)
            
        result["segment_count"] = len(segments)
        
        # Generate SRT file
        srt_path = os.path.join(output_dir, "subtitles.srt")
        self._write_srt(segments, srt_path)
        result["srt_path"] = srt_path
        
        # Generate ASS file with styling
        ass_path = os.path.join(output_dir, "subtitles.ass")
        self._write_ass(segments, ass_path, style)
        result["ass_path"] = ass_path
        
        # Generate VTT file (for web players)
        vtt_path = os.path.join(output_dir, "subtitles.vtt")
        self._write_vtt(segments, vtt_path)
        result["vtt_path"] = vtt_path
        
        # Save to database
        await self._save_subtitles_to_db(video_id, result)
        
        return result
        
    def _timestamps_to_segments(
        self,
        timestamps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert word timestamps to subtitle segments."""
        segments = []
        current_segment = {
            "start": 0,
            "end": 0,
            "text": ""
        }
        
        words_in_segment = 0
        max_words_per_segment = 8
        max_duration = 4.0  # seconds
        
        for ts in timestamps:
            word = ts.get("word", ts.get("text", ""))
            start = ts.get("start", 0)
            end = ts.get("end", start + 0.5)
            
            if not current_segment["text"]:
                current_segment["start"] = start
                
            current_segment["text"] += " " + word if current_segment["text"] else word
            current_segment["end"] = end
            words_in_segment += 1
            
            # Check if segment should end
            duration = current_segment["end"] - current_segment["start"]
            if words_in_segment >= max_words_per_segment or duration >= max_duration:
                segments.append(current_segment.copy())
                current_segment = {"start": 0, "end": 0, "text": ""}
                words_in_segment = 0
                
        # Add remaining segment
        if current_segment["text"]:
            segments.append(current_segment)
            
        return segments
        
    def _text_to_segments(
        self,
        text: str,
        words_per_segment: int = 6,
        duration_per_word: float = 0.4
    ) -> List[Dict[str, Any]]:
        """Convert plain text to timed segments (estimated timing)."""
        segments = []
        
        # Split into sentences first
        sentences = re.split(r'[።.!?]+', text)
        
        current_time = 0.0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            words = sentence.split()
            
            # Split sentence into chunks
            for i in range(0, len(words), words_per_segment):
                chunk_words = words[i:i + words_per_segment]
                chunk_text = " ".join(chunk_words)
                
                duration = len(chunk_words) * duration_per_word
                
                segments.append({
                    "start": current_time,
                    "end": current_time + duration,
                    "text": chunk_text
                })
                
                current_time += duration + 0.1  # Small gap between segments
                
        return segments
        
    def _write_srt(self, segments: List[Dict[str, Any]], output_path: str):
        """Write SRT subtitle file."""
        with open(output_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                start = self._seconds_to_srt_time(seg["start"])
                end = self._seconds_to_srt_time(seg["end"])
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{seg['text']}\n\n")
                
    def _write_vtt(self, segments: List[Dict[str, Any]], output_path: str):
        """Write WebVTT subtitle file."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for i, seg in enumerate(segments, 1):
                start = self._seconds_to_vtt_time(seg["start"])
                end = self._seconds_to_vtt_time(seg["end"])
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{seg['text']}\n\n")
                
    def _write_ass(
        self,
        segments: List[Dict[str, Any]],
        output_path: str,
        style: str = "modern"
    ):
        """Write ASS subtitle file with styling."""
        preset = self.style_presets.get(style, self.style_presets["modern"])
        
        # Determine font name from path
        font_name = "Noto Sans Ethiopic"
        
        header = f"""[Script Info]
Title: Amharic Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{preset['font_size']},{preset['primary_color']},&H000000FF,{preset['outline_color']},{preset['back_color']},{1 if preset['bold'] else 0},0,0,0,100,100,0,0,1,{preset['outline']},{preset['shadow']},{preset['alignment']},50,50,{preset['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        events = []
        for seg in segments:
            start = self._seconds_to_ass_time(seg["start"])
            end = self._seconds_to_ass_time(seg["end"])
            text = seg["text"].replace("\n", "\\N")
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(events))
            
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        
    def _seconds_to_vtt_time(self, seconds: float) -> str:
        """Convert seconds to VTT time format (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
        
    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Convert seconds to ASS time format (H:MM:SS.CC)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"
        
    async def burn_subtitles(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: Optional[str] = None,
        style: str = "modern"
    ) -> str:
        """
        Burn subtitles into video using ffmpeg.
        
        Args:
            video_path: Path to input video
            subtitle_path: Path to subtitle file (SRT or ASS)
            output_path: Optional output path
            style: Style preset (only used if subtitle_path is SRT)
            
        Returns:
            Path to output video with burned subtitles
        """
        if output_path is None:
            base, ext = os.path.splitext(video_path)
            output_path = f"{base}_subtitled{ext}"
            
        # Determine subtitle filter based on file type
        if subtitle_path.endswith(".ass"):
            # ASS has styling built-in
            sub_filter = f"ass={subtitle_path}"
        else:
            # SRT needs styling applied
            preset = self.style_presets.get(style, self.style_presets["modern"])
            sub_filter = (
                f"subtitles={subtitle_path}:"
                f"force_style='FontName=Noto Sans Ethiopic,"
                f"FontSize={preset['font_size']},"
                f"PrimaryColour={preset['primary_color']},"
                f"OutlineColour={preset['outline_color']},"
                f"BackColour={preset['back_color']},"
                f"Outline={preset['outline']},"
                f"Shadow={preset['shadow']},"
                f"MarginV={preset['margin_v']},"
                f"Alignment={preset['alignment']},"
                f"Bold={1 if preset['bold'] else 0}'"
            )
            
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vf", sub_filter,
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
        _, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise Exception(f"FFmpeg failed: {stderr.decode()[:500]}")
            
        return output_path
        
    async def generate_word_highlight_subtitles(
        self,
        video_id: str,
        timestamps: List[Dict[str, Any]],
        highlight_color: str = "&H0000FFFF",  # Yellow
        style: str = "modern"
    ) -> str:
        """
        Generate karaoke-style word-by-word highlighting subtitles.
        
        Args:
            video_id: Database video ID
            timestamps: Word-level timestamps
            highlight_color: Color for highlighted word
            style: Base style preset
            
        Returns:
            Path to ASS file with word highlighting
        """
        output_dir = os.path.join(self.subtitles_dir, video_id)
        os.makedirs(output_dir, exist_ok=True)
        
        ass_path = os.path.join(output_dir, "subtitles_highlight.ass")
        
        preset = self.style_presets.get(style, self.style_presets["modern"])
        font_name = "Noto Sans Ethiopic"
        
        header = f"""[Script Info]
Title: Amharic Subtitles with Word Highlighting
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{preset['font_size']},{preset['primary_color']},&H000000FF,{preset['outline_color']},{preset['back_color']},{1 if preset['bold'] else 0},0,0,0,100,100,0,0,1,{preset['outline']},{preset['shadow']},{preset['alignment']},50,50,{preset['margin_v']},1
Style: Highlight,{font_name},{preset['font_size']},{highlight_color},&H000000FF,{preset['outline_color']},{preset['back_color']},1,0,0,0,100,100,0,0,1,{preset['outline']},{preset['shadow']},{preset['alignment']},50,50,{preset['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # Group words into segments
        segments = self._timestamps_to_segments(timestamps)
        
        events = []
        for seg in segments:
            start = self._seconds_to_ass_time(seg["start"])
            end = self._seconds_to_ass_time(seg["end"])
            
            # Find words in this segment
            seg_words = []
            for ts in timestamps:
                word_start = ts.get("start", 0)
                if seg["start"] <= word_start < seg["end"]:
                    seg_words.append(ts)
                    
            if seg_words:
                # Create karaoke effect
                text_parts = []
                for i, word_ts in enumerate(seg_words):
                    word = word_ts.get("word", word_ts.get("text", ""))
                    word_start = word_ts.get("start", 0)
                    word_end = word_ts.get("end", word_start + 0.3)
                    
                    # Calculate timing relative to segment start
                    rel_start = int((word_start - seg["start"]) * 100)
                    duration = int((word_end - word_start) * 100)
                    
                    # Add karaoke tag
                    text_parts.append(f"{{\\k{duration}}}{word}")
                    
                text = " ".join([w.get("word", w.get("text", "")) for w in seg_words])
                karaoke_text = "{\\kf0}" + "".join(text_parts)
                
                events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,karaoke,{karaoke_text}")
            else:
                text = seg["text"].replace("\n", "\\N")
                events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
                
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(events))
            
        return ass_path
        
    async def _save_subtitles_to_db(self, video_id: str, result: Dict[str, Any]):
        """Save subtitle info to database."""
        query = """
            INSERT INTO subtitles (video_id, srt_path, ass_path, vtt_path, style, 
                                  segment_count, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (video_id) DO UPDATE SET
                srt_path = EXCLUDED.srt_path,
                ass_path = EXCLUDED.ass_path,
                vtt_path = EXCLUDED.vtt_path,
                style = EXCLUDED.style,
                segment_count = EXCLUDED.segment_count
        """
        
        await self.db.execute(
            query,
            video_id,
            result["srt_path"],
            result["ass_path"],
            result["vtt_path"],
            result["style"],
            result["segment_count"]
        )
        
    async def extract_subtitles_from_video(
        self,
        video_path: str,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Extract embedded subtitles from video if present.
        
        Args:
            video_path: Path to video file
            output_path: Optional output path for SRT
            
        Returns:
            Path to extracted SRT or None if no subtitles found
        """
        if output_path is None:
            base, _ = os.path.splitext(video_path)
            output_path = f"{base}_extracted.srt"
            
        # Check for subtitle streams
        probe_cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "s",
            video_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *probe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        
        info = json.loads(stdout.decode())
        streams = info.get("streams", [])
        
        if not streams:
            return None
            
        # Extract first subtitle stream
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-map", "0:s:0",
            output_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
            
        return None
