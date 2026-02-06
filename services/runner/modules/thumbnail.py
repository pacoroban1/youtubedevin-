"""
Part F: Thumbnail Generation Module
Generates superb thumbnails with Amharic hooks.
Supports ZThumb local engine when ZTHUMB_URL is set.
"""

import os
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

import httpx


class ThumbnailGenerator:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        # ZThumb local engine URL (if set, use local generation)
        self.zthumb_url = os.getenv("ZTHUMB_URL")
        
        # Thumbnail specs
        self.width = 1280
        self.height = 720
    
    async def generate_thumbnails(self, video_id: str) -> Dict[str, Any]:
        """
        Generate 3 thumbnail concepts with Amharic hooks.
        
        Args:
            video_id: YouTube video ID
        
        Returns:
            Dict with thumbnail paths and selection
        """
        # Create output directory
        thumb_dir = os.path.join(self.media_dir, "thumbnails", video_id)
        os.makedirs(thumb_dir, exist_ok=True)
        
        # Get video and script data
        video_data = self.db.get_video(video_id)
        script_data = self.db.get_script(video_id)
        
        video_title = video_data.get("title", "") if video_data else ""
        hook_text = script_data.get("hook_text", "") if script_data else ""
        
        # Generate Amharic hook texts for thumbnails
        hook_texts = await self._generate_thumbnail_hooks(video_title, hook_text)
        
        # Extract key frames from video
        video_dir = os.path.join(self.media_dir, "videos", video_id)
        source_video = await self._find_source_video(video_dir)
        
        key_frames = []
        if source_video:
            key_frames = await self._extract_key_frames(source_video, thumb_dir)
        
        # Generate thumbnails
        thumbnails = []
        
        for i, hook in enumerate(hook_texts[:3]):
            thumb_path = os.path.join(thumb_dir, f"thumbnail_{i+1}.png")
            
            if key_frames and i < len(key_frames):
                # Use extracted frame as base
                base_image = key_frames[i]
                await self._create_thumbnail_with_text(base_image, hook, thumb_path)
            else:
                # Generate thumbnail using AI (prefer ZThumb if available)
                if self.zthumb_url:
                    await self._generate_zthumb_thumbnail(video_title, hook, thumb_path)
                else:
                    await self._generate_ai_thumbnail(video_title, hook, thumb_path)
            
            # Calculate heuristic score
            score = await self._calculate_heuristic_score(thumb_path)
            
            thumbnail_data = {
                "thumbnail_path": thumb_path,
                "hook_text_amharic": hook,
                "is_selected": False,
                "heuristic_score": score
            }
            
            thumb_id = self.db.save_thumbnail(video_id, thumbnail_data)
            thumbnails.append({
                "id": thumb_id,
                "path": thumb_path,
                "hook": hook,
                "score": score
            })
        
        # Select best thumbnail
        if thumbnails:
            best_thumb = max(thumbnails, key=lambda t: t["score"])
            best_thumb["is_selected"] = True
            
            # Update database
            with self.db.get_session() as session:
                from sqlalchemy import text
                session.execute(text("""
                    UPDATE thumbnails SET is_selected = TRUE WHERE id = :id
                """), {"id": best_thumb["id"]})
                session.commit()
        
        self.db.update_video_status(video_id, "thumbnailed")
        
        return {
            "thumbnails": thumbnails,
            "selected": best_thumb["path"] if thumbnails else None,
            "selected_hook": best_thumb["hook"] if thumbnails else None
        }
    
    async def _generate_thumbnail_hooks(
        self,
        video_title: str,
        script_hook: str
    ) -> List[str]:
        """Generate 3 Amharic hook texts for thumbnails."""
        if not self.gemini_api_key:
            return self._fallback_hooks()
        
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            prompt = f"""Generate 3 short, attention-grabbing Amharic text hooks for YouTube thumbnails.

Video title: {video_title}
Script hook: {script_hook[:200]}

Requirements:
1. Each hook should be 2-4 words maximum
2. Use Ge'ez script (ፊደል)
3. Create curiosity and urgency
4. Be dramatic and emotional
5. Easy to read on mobile

Return ONLY 3 hooks, one per line, nothing else."""

            response = model.generate_content(prompt)
            hooks = response.text.strip().split('\n')
            
            # Clean and filter
            hooks = [h.strip() for h in hooks if h.strip()]
            
            return hooks[:3] if len(hooks) >= 3 else hooks + self._fallback_hooks()[:3-len(hooks)]
            
        except Exception as e:
            print(f"Hook generation error: {e}")
            return self._fallback_hooks()
    
    def _fallback_hooks(self) -> List[str]:
        """Fallback Amharic hooks."""
        return [
            "አስደናቂ ፊልም!",
            "ይህን ተመልከቱ!",
            "እውነተኛ ታሪክ"
        ]
    
    async def _find_source_video(self, video_dir: str) -> Optional[str]:
        """Find the source video file."""
        if not os.path.exists(video_dir):
            return None
            
        for ext in ["mp4", "mkv", "webm"]:
            for filename in os.listdir(video_dir):
                if filename.endswith(f".{ext}"):
                    return os.path.join(video_dir, filename)
        return None
    
    async def _extract_key_frames(
        self,
        video_path: str,
        output_dir: str,
        num_frames: int = 3
    ) -> List[str]:
        """Extract visually interesting frames from video."""
        frames = []
        
        try:
            # Get video duration
            cmd_duration = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(cmd_duration, capture_output=True, text=True, timeout=30)
            duration = float(result.stdout.strip())
            
            # Extract frames at different points
            timestamps = [
                duration * 0.1,   # 10% - usually intro/hook
                duration * 0.4,   # 40% - rising action
                duration * 0.7    # 70% - climax
            ]
            
            for i, ts in enumerate(timestamps[:num_frames]):
                frame_path = os.path.join(output_dir, f"frame_{i+1}.png")
                
                cmd = [
                    "ffmpeg",
                    "-ss", str(ts),
                    "-i", video_path,
                    "-vframes", "1",
                    "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2",
                    "-y",
                    frame_path
                ]
                
                subprocess.run(cmd, capture_output=True, timeout=60)
                
                if os.path.exists(frame_path):
                    frames.append(frame_path)
            
            return frames
            
        except Exception as e:
            print(f"Frame extraction error: {e}")
            return []
    
    async def _create_thumbnail_with_text(
        self,
        base_image: str,
        text: str,
        output_path: str
    ) -> bool:
        """Create thumbnail by adding text overlay to base image."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # Open base image
            img = Image.open(base_image)
            img = img.resize((self.width, self.height), Image.LANCZOS)
            
            # Create drawing context
            draw = ImageDraw.Draw(img)
            
            # Try to load a font that supports Amharic
            font_size = 72
            try:
                # Try common fonts that support Ethiopic
                font_paths = [
                    "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
                ]
                
                font = None
                for font_path in font_paths:
                    if os.path.exists(font_path):
                        font = ImageFont.truetype(font_path, font_size)
                        break
                
                if not font:
                    font = ImageFont.load_default()
                    
            except Exception:
                font = ImageFont.load_default()
            
            # Calculate text position (bottom center with padding)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (self.width - text_width) // 2
            y = self.height - text_height - 50  # 50px from bottom
            
            # Draw text shadow
            shadow_offset = 3
            draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill="black")
            
            # Draw main text
            draw.text((x, y), text, font=font, fill="white")
            
            # Add slight vignette/gradient at bottom for text readability
            # (simplified - just darken bottom portion)
            
            # Save
            img.save(output_path, "PNG", quality=95)
            return True
            
        except Exception as e:
            print(f"Thumbnail creation error: {e}")
            # Copy base image as fallback
            import shutil
            shutil.copy(base_image, output_path)
            return False
    
    async def _generate_zthumb_thumbnail(
        self,
        video_title: str,
        hook_text: str,
        output_path: str
    ) -> bool:
        """
        Generate thumbnail using ZThumb local engine.
        Falls back to OpenAI if ZThumb is unavailable.
        """
        if not self.zthumb_url:
            return await self._generate_ai_thumbnail(video_title, hook_text, output_path)
        
        try:
            # Build prompt for cinematic thumbnail
            prompt = f"cinematic movie poster, dramatic scene, {video_title}, high contrast lighting, volumetric fog, 8k, photorealistic, movie quality"
            
            payload = {
                "prompt": prompt,
                "negative_prompt": "text, watermark, logo, blurry, low quality, cartoon, anime, deformed hands",
                "width": self.width,
                "height": self.height,
                "batch": 3,  # Generate 3 variants
                "steps": 35,
                "cfg": 4.5,
                "variant": "auto",
                "upscale": True,
                "face_detail": True,
                "safe_mode": True,
                "style_preset": "alien_reveal"
            }
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.zthumb_url}/generate",
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("warnings"):
                    print(f"ZThumb warnings: {result['warnings']}")
                
                images = result.get("images", [])
                if not images:
                    print("ZThumb returned no images, falling back to OpenAI")
                    return await self._generate_ai_thumbnail(video_title, hook_text, output_path)
                
                # Get the first image (best one based on ZThumb scoring)
                best_image = images[0].replace("file://", "")
                
                # Copy to output path and add text overlay
                import shutil
                shutil.copy(best_image, output_path)
                
                # Add Amharic text overlay
                await self._add_text_overlay(output_path, hook_text)
                
                return True
                
        except httpx.ConnectError:
            print(f"ZThumb server not available at {self.zthumb_url}, falling back to OpenAI")
            return await self._generate_ai_thumbnail(video_title, hook_text, output_path)
        except Exception as e:
            print(f"ZThumb generation error: {e}, falling back to OpenAI")
            return await self._generate_ai_thumbnail(video_title, hook_text, output_path)
    
    async def _generate_ai_thumbnail(
        self,
        video_title: str,
        hook_text: str,
        output_path: str
    ) -> bool:
        """Generate thumbnail using AI image generation (OpenAI DALL-E)."""
        if not self.openai_api_key:
            return await self._create_placeholder_thumbnail(hook_text, output_path)
        
        try:
            import openai
            
            client = openai.OpenAI(api_key=self.openai_api_key)
            
            prompt = f"""Create a dramatic YouTube thumbnail for a movie recap video.
            
Style: Cinematic, high contrast, dramatic lighting
Subject: A dramatic scene related to: {video_title}
Mood: Intense, mysterious, engaging
Colors: Rich, saturated, eye-catching
Composition: Rule of thirds, clear focal point

DO NOT include any text in the image."""

            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1792x1024",
                quality="standard",
                n=1
            )
            
            # Download image
            image_url = response.data[0].url
            
            import httpx
            async with httpx.AsyncClient() as http_client:
                img_response = await http_client.get(image_url)
                
                # Save and resize
                temp_path = output_path + ".temp.png"
                with open(temp_path, "wb") as f:
                    f.write(img_response.content)
                
                # Resize to YouTube specs and add text
                from PIL import Image
                img = Image.open(temp_path)
                img = img.resize((self.width, self.height), Image.LANCZOS)
                img.save(output_path, "PNG")
                
                os.remove(temp_path)
                
                # Add text overlay
                await self._add_text_overlay(output_path, hook_text)
                
            return True
            
        except Exception as e:
            print(f"AI thumbnail generation error: {e}")
            return await self._create_placeholder_thumbnail(hook_text, output_path)
    
    async def _create_placeholder_thumbnail(
        self,
        hook_text: str,
        output_path: str
    ) -> bool:
        """Create a simple placeholder thumbnail."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # Create gradient background
            img = Image.new('RGB', (self.width, self.height))
            draw = ImageDraw.Draw(img)
            
            # Draw gradient (dark blue to black)
            for y in range(self.height):
                r = int(20 * (1 - y / self.height))
                g = int(40 * (1 - y / self.height))
                b = int(80 * (1 - y / self.height))
                draw.line([(0, y), (self.width, y)], fill=(r, g, b))
            
            # Add text
            font_size = 72
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
            
            bbox = draw.textbbox((0, 0), hook_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (self.width - text_width) // 2
            y = (self.height - text_height) // 2
            
            draw.text((x + 3, y + 3), hook_text, font=font, fill="black")
            draw.text((x, y), hook_text, font=font, fill="white")
            
            img.save(output_path, "PNG")
            return True
            
        except Exception as e:
            print(f"Placeholder thumbnail error: {e}")
            return False
    
    async def _add_text_overlay(self, image_path: str, text: str) -> bool:
        """Add text overlay to existing image."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            img = Image.open(image_path)
            draw = ImageDraw.Draw(img)
            
            font_size = 72
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
            
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (self.width - text_width) // 2
            y = self.height - text_height - 50
            
            # Shadow
            draw.text((x + 3, y + 3), text, font=font, fill="black")
            # Main text
            draw.text((x, y), text, font=font, fill="white")
            
            img.save(image_path, "PNG")
            return True
            
        except Exception as e:
            print(f"Text overlay error: {e}")
            return False
    
    async def _calculate_heuristic_score(self, thumbnail_path: str) -> float:
        """Calculate thumbnail quality score using heuristics."""
        if not os.path.exists(thumbnail_path):
            return 0.0
        
        try:
            from PIL import Image
            import numpy as np
            
            img = Image.open(thumbnail_path)
            img_array = np.array(img)
            
            # Score components
            scores = []
            
            # 1. Contrast score (higher is better)
            if len(img_array.shape) == 3:
                gray = np.mean(img_array, axis=2)
            else:
                gray = img_array
            contrast = np.std(gray) / 128.0  # Normalize to 0-1 range
            scores.append(min(1.0, contrast))
            
            # 2. Brightness score (not too dark, not too bright)
            brightness = np.mean(gray) / 255.0
            brightness_score = 1.0 - abs(brightness - 0.5) * 2  # Peak at 0.5
            scores.append(brightness_score)
            
            # 3. Color saturation (more saturated = more eye-catching)
            if len(img_array.shape) == 3:
                hsv = self._rgb_to_hsv(img_array)
                saturation = np.mean(hsv[:, :, 1])
                scores.append(saturation)
            else:
                scores.append(0.5)
            
            # 4. File size score (larger usually means more detail)
            file_size = os.path.getsize(thumbnail_path)
            size_score = min(1.0, file_size / 500000)  # 500KB = 1.0
            scores.append(size_score)
            
            # Average all scores
            final_score = sum(scores) / len(scores)
            return round(final_score, 2)
            
        except Exception as e:
            print(f"Heuristic score error: {e}")
            return 0.5
    
    def _rgb_to_hsv(self, rgb_array):
        """Convert RGB array to HSV."""
        import numpy as np
        
        rgb = rgb_array.astype(float) / 255.0
        
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        
        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        diff = max_c - min_c
        
        # Hue
        h = np.zeros_like(max_c)
        mask = diff != 0
        
        # Saturation
        s = np.zeros_like(max_c)
        s[max_c != 0] = diff[max_c != 0] / max_c[max_c != 0]
        
        # Value
        v = max_c
        
        return np.stack([h, s, v], axis=2)
