"""
Part E: Timing & Scene Matching Module
Aligns narration to scene cuts and renders final video.
"""

import os
import subprocess
import json
from typing import Dict, Any, List, Optional
from datetime import datetime


class TimingMatcher:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        
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
        await self._render_video(
            source_video,
            narration_file,
            output_file,
            alignment_map
        )
        
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
            "quality_check_passed": quality_passed
        }
        
        render_id = self.db.save_render(video_id, audio_data["id"], render_data)
        self.db.update_video_status(video_id, "rendered")
        
        return {
            "render_id": render_id,
            "output_file": output_file,
            "duration": duration,
            "alignment_score": alignment_score,
            "scene_count": len(scene_cuts),
            "quality_passed": quality_passed
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
        alignment_map: List[Dict]
    ) -> bool:
        """Render final video with narration replacing original audio."""
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
            cmd = [
                "ffmpeg",
                "-i", source_video,
                "-i", narration_audio,
                "-map", "0:v",           # Use video from first input
                "-map", "1:a",           # Use audio from second input (narration)
                "-c:v", "libx264",       # Video codec
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac",           # Audio codec
                "-b:a", "192k",
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
                print(f"Render error: {result.stderr}")
                return False
            
            return os.path.exists(output_file)
            
        except Exception as e:
            print(f"Video render error: {e}")
            return False
    
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
