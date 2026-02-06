"""
Ambient Content Generator Engine
Automated walking tour and driving video creation.
High RPM ($20-30) with minimal effort.
"""

import os
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import subprocess


class AmbientContentGenerator:
    """
    Generates ambient content like walking tours and driving videos.
    
    Features:
    - Walking tour video automation
    - Driving/road trip video creation
    - City exploration content
    - 4K quality processing
    - Background music integration
    - Automatic chapter markers
    """
    
    # City presets with metadata
    CITY_PRESETS = {
        "tokyo": {
            "country": "Japan",
            "timezone": "Asia/Tokyo",
            "best_times": ["sunrise", "night"],
            "popular_areas": ["Shibuya", "Shinjuku", "Akihabara", "Ginza"],
            "rpm_estimate": 25
        },
        "paris": {
            "country": "France",
            "timezone": "Europe/Paris",
            "best_times": ["golden_hour", "night"],
            "popular_areas": ["Champs-Élysées", "Montmartre", "Le Marais", "Latin Quarter"],
            "rpm_estimate": 22
        },
        "new_york": {
            "country": "USA",
            "timezone": "America/New_York",
            "best_times": ["sunrise", "night"],
            "popular_areas": ["Times Square", "Central Park", "Brooklyn Bridge", "SoHo"],
            "rpm_estimate": 20
        },
        "london": {
            "country": "UK",
            "timezone": "Europe/London",
            "best_times": ["morning", "evening"],
            "popular_areas": ["Westminster", "Covent Garden", "Camden", "Notting Hill"],
            "rpm_estimate": 23
        },
        "dubai": {
            "country": "UAE",
            "timezone": "Asia/Dubai",
            "best_times": ["sunset", "night"],
            "popular_areas": ["Downtown", "Marina", "Old Dubai", "Palm Jumeirah"],
            "rpm_estimate": 28
        },
        "singapore": {
            "country": "Singapore",
            "timezone": "Asia/Singapore",
            "best_times": ["evening", "night"],
            "popular_areas": ["Marina Bay", "Orchard Road", "Chinatown", "Little India"],
            "rpm_estimate": 24
        },
        "addis_ababa": {
            "country": "Ethiopia",
            "timezone": "Africa/Addis_Ababa",
            "best_times": ["morning", "golden_hour"],
            "popular_areas": ["Piazza", "Bole", "Merkato", "Entoto"],
            "rpm_estimate": 15
        },
    }
    
    # Driving route presets
    DRIVING_PRESETS = {
        "pacific_coast": {
            "country": "USA",
            "duration_hours": 4,
            "scenery": ["ocean", "cliffs", "beaches"],
            "rpm_estimate": 22
        },
        "swiss_alps": {
            "country": "Switzerland",
            "duration_hours": 3,
            "scenery": ["mountains", "lakes", "villages"],
            "rpm_estimate": 28
        },
        "amalfi_coast": {
            "country": "Italy",
            "duration_hours": 2,
            "scenery": ["coastal", "cliffs", "towns"],
            "rpm_estimate": 25
        },
        "scottish_highlands": {
            "country": "UK",
            "duration_hours": 5,
            "scenery": ["mountains", "lochs", "castles"],
            "rpm_estimate": 24
        },
        "norwegian_fjords": {
            "country": "Norway",
            "duration_hours": 4,
            "scenery": ["fjords", "waterfalls", "mountains"],
            "rpm_estimate": 26
        },
    }
    
    def __init__(self, db):
        self.db = db
        self.output_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.ambient_dir = os.path.join(self.output_dir, "ambient")
        os.makedirs(self.ambient_dir, exist_ok=True)
        
        # Quality settings
        self.default_resolution = "3840x2160"  # 4K
        self.default_fps = 60
        self.default_bitrate = "50M"
        
        # Music library path
        self.music_dir = os.path.join(self.output_dir, "music")
        os.makedirs(self.music_dir, exist_ok=True)
        
    async def process_walking_video(
        self,
        input_path: str,
        city: str,
        area: str,
        time_of_day: str = "day",
        add_music: bool = True,
        add_chapters: bool = True
    ) -> Dict[str, Any]:
        """
        Process raw walking footage into polished video.
        
        Args:
            input_path: Path to raw footage
            city: City name
            area: Specific area/neighborhood
            time_of_day: Time of day (sunrise, day, golden_hour, night)
            add_music: Add background music
            add_chapters: Add chapter markers
            
        Returns:
            Processed video info
        """
        city_config = self.CITY_PRESETS.get(city.lower(), {})
        
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"walk_{city}_{area}_{time_of_day}_{timestamp}.mp4"
        output_path = os.path.join(self.ambient_dir, output_filename)
        
        # Step 1: Stabilize footage
        stabilized_path = await self._stabilize_video(input_path)
        
        # Step 2: Color grade based on time of day
        graded_path = await self._color_grade(stabilized_path, time_of_day)
        
        # Step 3: Add ambient sound enhancement
        enhanced_path = await self._enhance_audio(graded_path)
        
        # Step 4: Add background music if requested
        if add_music:
            music_path = await self._select_music(time_of_day, "walking")
            if music_path:
                enhanced_path = await self._mix_audio(enhanced_path, music_path)
                
        # Step 5: Add intro/outro
        final_path = await self._add_intro_outro(
            enhanced_path,
            city,
            area,
            time_of_day,
            output_path
        )
        
        # Step 6: Generate chapters if requested
        chapters = []
        if add_chapters:
            chapters = await self._generate_chapters(final_path)
            
        # Generate metadata
        metadata = await self._generate_walking_metadata(city, area, time_of_day)
        
        # Save to database
        video_id = await self.db.fetchval("""
            INSERT INTO ambient_videos 
            (type, city, area, time_of_day, video_path, chapters, metadata, created_at)
            VALUES ('walking', $1, $2, $3, $4, $5, $6, NOW())
            RETURNING id
        """, city, area, time_of_day, final_path, json.dumps(chapters), json.dumps(metadata))
        
        return {
            "video_id": video_id,
            "type": "walking",
            "city": city,
            "area": area,
            "time_of_day": time_of_day,
            "video_path": final_path,
            "chapters": chapters,
            "metadata": metadata,
            "rpm_estimate": city_config.get("rpm_estimate", 20)
        }
        
    async def process_driving_video(
        self,
        input_path: str,
        route: str,
        add_music: bool = True,
        add_speedometer: bool = False
    ) -> Dict[str, Any]:
        """
        Process raw driving footage into polished video.
        
        Args:
            input_path: Path to raw footage
            route: Route name/preset
            add_music: Add background music
            add_speedometer: Add speedometer overlay
            
        Returns:
            Processed video info
        """
        route_config = self.DRIVING_PRESETS.get(route.lower(), {})
        
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"drive_{route}_{timestamp}.mp4"
        output_path = os.path.join(self.ambient_dir, output_filename)
        
        # Step 1: Stabilize footage
        stabilized_path = await self._stabilize_video(input_path)
        
        # Step 2: Color grade for scenic driving
        graded_path = await self._color_grade(stabilized_path, "scenic")
        
        # Step 3: Add speedometer overlay if requested
        if add_speedometer:
            graded_path = await self._add_speedometer(graded_path)
            
        # Step 4: Enhance engine/road sounds
        enhanced_path = await self._enhance_driving_audio(graded_path)
        
        # Step 5: Add background music if requested
        if add_music:
            music_path = await self._select_music("day", "driving")
            if music_path:
                enhanced_path = await self._mix_audio(enhanced_path, music_path, music_volume=0.3)
                
        # Step 6: Add intro/outro
        final_path = await self._add_driving_intro_outro(
            enhanced_path,
            route,
            output_path
        )
        
        # Generate chapters based on scenery changes
        chapters = await self._generate_driving_chapters(final_path, route_config.get("scenery", []))
        
        # Generate metadata
        metadata = await self._generate_driving_metadata(route)
        
        # Save to database
        video_id = await self.db.fetchval("""
            INSERT INTO ambient_videos 
            (type, route, video_path, chapters, metadata, created_at)
            VALUES ('driving', $1, $2, $3, $4, NOW())
            RETURNING id
        """, route, final_path, json.dumps(chapters), json.dumps(metadata))
        
        return {
            "video_id": video_id,
            "type": "driving",
            "route": route,
            "video_path": final_path,
            "chapters": chapters,
            "metadata": metadata,
            "rpm_estimate": route_config.get("rpm_estimate", 22)
        }
        
    async def _stabilize_video(self, input_path: str) -> str:
        """Stabilize shaky footage using ffmpeg vidstab."""
        output_path = input_path.replace(".mp4", "_stabilized.mp4")
        
        # Two-pass stabilization
        # Pass 1: Analyze
        analyze_cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", "vidstabdetect=stepsize=6:shakiness=8:accuracy=9:result=/tmp/transforms.trf",
            "-f", "null", "-"
        ]
        
        process = await asyncio.create_subprocess_exec(
            *analyze_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        # Pass 2: Apply
        apply_cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", "vidstabtransform=input=/tmp/transforms.trf:smoothing=30:interpol=bicubic",
            "-c:a", "copy",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *apply_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        return output_path if os.path.exists(output_path) else input_path
        
    async def _color_grade(self, input_path: str, style: str) -> str:
        """Apply color grading based on style."""
        output_path = input_path.replace(".mp4", "_graded.mp4")
        
        # Color grading presets
        grades = {
            "sunrise": "curves=r='0/0 0.3/0.35 1/1':g='0/0 0.3/0.3 1/1':b='0/0 0.3/0.25 1/0.95',eq=saturation=1.2:contrast=1.1",
            "day": "eq=saturation=1.1:contrast=1.05:brightness=0.02",
            "golden_hour": "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.45 1/0.95':b='0/0 0.5/0.35 1/0.85',eq=saturation=1.3",
            "night": "curves=r='0/0 0.5/0.45 1/0.9':g='0/0 0.5/0.5 1/0.95':b='0/0 0.5/0.55 1/1',eq=contrast=1.15",
            "scenic": "eq=saturation=1.15:contrast=1.08:brightness=0.01,unsharp=5:5:0.8:3:3:0.4",
        }
        
        grade_filter = grades.get(style, grades["day"])
        
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", grade_filter,
            "-c:a", "copy",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        return output_path if os.path.exists(output_path) else input_path
        
    async def _enhance_audio(self, input_path: str) -> str:
        """Enhance ambient audio (footsteps, city sounds)."""
        output_path = input_path.replace(".mp4", "_audio_enhanced.mp4")
        
        # Audio enhancement: normalize, slight compression, high-pass filter
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-af", "highpass=f=80,lowpass=f=12000,compand=attacks=0.3:decays=0.8:points=-80/-80|-45/-45|-27/-25|0/-10:soft-knee=6,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v", "copy",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        return output_path if os.path.exists(output_path) else input_path
        
    async def _enhance_driving_audio(self, input_path: str) -> str:
        """Enhance driving audio (engine, road sounds)."""
        output_path = input_path.replace(".mp4", "_drive_audio.mp4")
        
        # Driving audio: emphasize low frequencies (engine), reduce wind noise
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-af", "highpass=f=40,lowpass=f=8000,equalizer=f=100:t=q:w=2:g=3,compand=attacks=0.2:decays=0.5:points=-80/-80|-45/-45|-27/-25|0/-8:soft-knee=6",
            "-c:v", "copy",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        return output_path if os.path.exists(output_path) else input_path
        
    async def _select_music(self, time_of_day: str, content_type: str) -> Optional[str]:
        """Select appropriate background music."""
        # Music selection based on mood
        mood_map = {
            ("sunrise", "walking"): "peaceful",
            ("day", "walking"): "upbeat",
            ("golden_hour", "walking"): "warm",
            ("night", "walking"): "chill",
            ("day", "driving"): "energetic",
            ("scenic", "driving"): "epic",
        }
        
        mood = mood_map.get((time_of_day, content_type), "ambient")
        
        # Look for music file
        music_file = os.path.join(self.music_dir, f"{mood}.mp3")
        
        if os.path.exists(music_file):
            return music_file
            
        return None
        
    async def _mix_audio(
        self,
        video_path: str,
        music_path: str,
        music_volume: float = 0.2
    ) -> str:
        """Mix background music with video audio."""
        output_path = video_path.replace(".mp4", "_with_music.mp4")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-filter_complex", f"[1:a]volume={music_volume}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=3[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        return output_path if os.path.exists(output_path) else video_path
        
    async def _add_intro_outro(
        self,
        video_path: str,
        city: str,
        area: str,
        time_of_day: str,
        output_path: str
    ) -> str:
        """Add intro and outro with text overlays."""
        # Create intro text
        intro_text = f"{city.upper()} - {area}"
        subtitle_text = f"{time_of_day.replace('_', ' ').title()} Walk"
        
        # Add text overlay at the beginning
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"drawtext=text='{intro_text}':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,5)':shadowcolor=black:shadowx=2:shadowy=2,drawtext=text='{subtitle_text}':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h+text_h)/2+20:enable='between(t,0,5)':shadowcolor=black:shadowx=2:shadowy=2",
            "-c:a", "copy",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        return output_path if os.path.exists(output_path) else video_path
        
    async def _add_driving_intro_outro(
        self,
        video_path: str,
        route: str,
        output_path: str
    ) -> str:
        """Add intro and outro for driving videos."""
        route_config = self.DRIVING_PRESETS.get(route.lower(), {})
        country = route_config.get("country", "")
        
        intro_text = route.replace("_", " ").title()
        subtitle_text = f"{country} - 4K Scenic Drive"
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"drawtext=text='{intro_text}':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,5)':shadowcolor=black:shadowx=2:shadowy=2,drawtext=text='{subtitle_text}':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h+text_h)/2+20:enable='between(t,0,5)':shadowcolor=black:shadowx=2:shadowy=2",
            "-c:a", "copy",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        return output_path if os.path.exists(output_path) else video_path
        
    async def _add_speedometer(self, video_path: str) -> str:
        """Add speedometer overlay to driving video."""
        # This would require GPS data or speed estimation
        # For now, return unchanged
        return video_path
        
    async def _generate_chapters(self, video_path: str) -> List[Dict[str, Any]]:
        """Generate chapter markers based on scene changes."""
        chapters = []
        
        # Use ffmpeg scene detection
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "frame=pts_time",
            "-select_streams", "v",
            "-of", "json",
            "-f", "lavfi",
            f"movie={video_path},select='gt(scene,0.3)'"
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await process.communicate()
            
            data = json.loads(stdout.decode())
            frames = data.get("frames", [])
            
            for i, frame in enumerate(frames[:10]):  # Max 10 chapters
                time = float(frame.get("pts_time", 0))
                chapters.append({
                    "index": i + 1,
                    "time": time,
                    "title": f"Scene {i + 1}"
                })
                
        except Exception:
            pass
            
        return chapters
        
    async def _generate_driving_chapters(
        self,
        video_path: str,
        scenery: List[str]
    ) -> List[Dict[str, Any]]:
        """Generate chapters for driving video based on scenery."""
        # Get video duration
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await process.communicate()
            
            data = json.loads(stdout.decode())
            duration = float(data.get("format", {}).get("duration", 0))
            
            # Create chapters based on scenery
            chapters = []
            if scenery and duration > 0:
                segment_duration = duration / len(scenery)
                for i, scene in enumerate(scenery):
                    chapters.append({
                        "index": i + 1,
                        "time": i * segment_duration,
                        "title": scene.title()
                    })
                    
            return chapters
            
        except Exception:
            return []
            
    async def _generate_walking_metadata(
        self,
        city: str,
        area: str,
        time_of_day: str
    ) -> Dict[str, Any]:
        """Generate YouTube metadata for walking video."""
        city_config = self.CITY_PRESETS.get(city.lower(), {})
        country = city_config.get("country", "")
        
        title = f"Walking in {city.title()} - {area} [{time_of_day.replace('_', ' ').title()}] 4K"
        
        description = f"""Experience the streets of {city.title()}, {country} in stunning 4K resolution.

This {time_of_day.replace('_', ' ')} walk takes you through {area}, one of the most iconic areas of {city.title()}.

Perfect for:
- Virtual travel
- Relaxation
- Background ambiance
- Treadmill walking

Filmed with professional stabilization equipment.

#walking #4k #{city.lower()} #{country.lower().replace(' ', '')} #virtualwalk #citywalk"""

        tags = [
            f"{city} walk",
            f"{city} 4k",
            "walking tour",
            "city walk",
            "virtual walk",
            f"{country} travel",
            "4k walking",
            "ambient walk",
            f"{area} {city}",
            "relaxing walk"
        ]
        
        return {
            "title": title,
            "description": description,
            "tags": tags,
            "category": "Travel & Events",
            "language": "en"
        }
        
    async def _generate_driving_metadata(self, route: str) -> Dict[str, Any]:
        """Generate YouTube metadata for driving video."""
        route_config = self.DRIVING_PRESETS.get(route.lower(), {})
        country = route_config.get("country", "")
        scenery = route_config.get("scenery", [])
        
        route_name = route.replace("_", " ").title()
        
        title = f"Driving {route_name} - {country} 4K Scenic Drive"
        
        description = f"""Experience the breathtaking {route_name} in {country} from the driver's seat.

This scenic drive features:
{chr(10).join(f'- {s.title()}' for s in scenery)}

Perfect for:
- Virtual road trip
- Relaxation
- Background scenery
- Driving simulation

Filmed in stunning 4K resolution.

#{route.lower().replace('_', '')} #{country.lower().replace(' ', '')} #roadtrip #scenicdriving #4k"""

        tags = [
            f"{route_name} drive",
            "scenic drive",
            "4k driving",
            f"{country} road trip",
            "virtual drive",
            "relaxing drive",
            "car pov",
            "driving video"
        ]
        
        return {
            "title": title,
            "description": description,
            "tags": tags,
            "category": "Travel & Events",
            "language": "en"
        }
        
    def get_available_cities(self) -> List[Dict[str, Any]]:
        """Get list of available city presets."""
        return [
            {
                "code": code,
                "name": code.replace("_", " ").title(),
                **config
            }
            for code, config in self.CITY_PRESETS.items()
        ]
        
    def get_available_routes(self) -> List[Dict[str, Any]]:
        """Get list of available driving route presets."""
        return [
            {
                "code": code,
                "name": code.replace("_", " ").title(),
                **config
            }
            for code, config in self.DRIVING_PRESETS.items()
        ]
