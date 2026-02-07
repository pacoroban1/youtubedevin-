"""
Part F: Thumbnail Generation Module
Generates superb thumbnails with Amharic hooks.
Gemini-only (Imagen + Gemini Image) with model fallbacks.
"""

import os
import logging
from typing import Dict, Any, List
from PIL import Image, ImageDraw, ImageFont
import numpy as np

from modules.gemini_client import gemini
from modules.gemini_client import GeminiCallFailed, GeminiNotConfigured

# Configure logging
logger = logging.getLogger("thumbnail_generator")
logger.setLevel(logging.INFO)

class ThumbnailGenerator:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")

        # Thumbnail specs
        self.width = 1280
        self.height = 720
    
    async def generate_thumbnails(self, video_id: str) -> Dict[str, Any]:
        """Generate thumbnails (Gemini/Imagen fallback) and pick the best one."""
        # Create output directory
        thumb_dir = os.path.join(self.media_dir, "thumbnails", video_id)
        os.makedirs(thumb_dir, exist_ok=True)
        
        # Get video and script data (best-effort)
        video_data = self.db.get_video(video_id)
        script_data = self.db.get_script(video_id)
        
        video_title = video_data.get("title", "") if video_data else ""
        
        # Handle full script JSON or legacy text for extra prompt conditioning (best-effort).
        hook_text = ""
        if script_data:
            full_script = script_data.get("full_script")
            if isinstance(full_script, dict):
                hook_text = str(full_script.get("hook") or "")
            elif isinstance(full_script, str):
                try:
                    import json
                    obj = json.loads(full_script)
                    hook_text = str(obj.get("hook") or "")
                except Exception:
                    hook_text = str(script_data.get("hook_text") or "")

        if not gemini.is_configured():
            return {
                "status": "error",
                "error": "missing_env",
                "message": "GEMINI_API_KEY is required for thumbnail generation",
                "video_id": video_id,
            }

        # Build a single strong prompt (no overlay text at generation time for reliability).
        prompt = self._build_thumbnail_prompt(video_title=video_title, hook_text=hook_text)

        try:
            images_bytes, model_used, prior_attempts = gemini.generate_images_with_fallback(
                prompt,
                number_of_images=4,
                aspect_ratio="16:9",
                timeout_s=60.0,
                retries_per_model=2,
            )
        except GeminiNotConfigured:
            return {
                "status": "error",
                "error": "missing_env",
                "message": "GEMINI_API_KEY is required for thumbnail generation",
                "video_id": video_id,
            }
        except GeminiCallFailed as e:
            return {
                "status": "error",
                "error": "thumbnail_generation_failed",
                "video_id": video_id,
                "attempts": e.attempts_as_dicts(),
                "hint": "check if Imagen/T2I is enabled for this key/tier",
            }

        thumbnails: List[Dict[str, Any]] = []
        for idx, b in enumerate(images_bytes):
            out_path = os.path.join(thumb_dir, f"thumb_{idx+1:02d}.png")
            with open(out_path, "wb") as f:
                f.write(b)

            # Optional: overlay a short hook if we have one; do not fail generation if overlay fails.
            if hook_text.strip():
                try:
                    await self._add_text_overlay(out_path, hook_text.strip()[:30])
                except Exception:
                    pass

            score = await self._calculate_heuristic_score(out_path)
            thumbnails.append(
                {
                    "id": idx,
                    "path": out_path,
                    "url": f"/api/media/thumbnails/{video_id}/thumb_{idx+1:02d}.png",
                    "score": score,
                }
            )

            # Save metadata (best-effort)
            try:
                self.db.save_thumbnail(
                    video_id,
                    {
                        "thumbnail_path": out_path,
                        "hook_text_amharic": hook_text.strip()[:120],
                        "is_selected": False,
                        "heuristic_score": score,
                        "model_used": model_used,
                    },
                )
            except Exception:
                pass

        if not thumbnails:
            return {
                "status": "error",
                "error": "thumbnail_generation_failed",
                "video_id": video_id,
                "attempts": prior_attempts,
                "hint": "check if Imagen/T2I is enabled for this key/tier",
            }

        # Pick best by score (contrast proxy).
        best_pick_index = max(range(len(thumbnails)), key=lambda i: float(thumbnails[i].get("score") or 0.0))
        selected_path = thumbnails[best_pick_index]["path"]

        try:
            self.db.update_video_status(video_id, "thumbnailed")
        except Exception:
            pass

        # Backward-compatible fields included alongside the required ones.
        return {
            "status": "success",
            "video_id": video_id,
            "images": thumbnails,
            "thumbnails": thumbnails,
            "best_pick_index": int(best_pick_index),
            "selected_path": selected_path,
            "model_used": model_used,
            "attempts": prior_attempts,
        }

    def _build_thumbnail_prompt(self, *, video_title: str, hook_text: str) -> str:
        # Keep prompts policy-safe: no real-person/celebrity identity requests.
        title = (video_title or "").strip()
        hook = (hook_text or "").strip()
        hook_hint = f"Scene vibe hint: {hook}. " if hook else ""

        return (
            "You are generating a high-performing YouTube movie recap thumbnail.\n"
            "Goal: strong single subject, dramatic lighting, high contrast, mobile-readable composition.\n"
            "Constraints: no watermark, no text, no logos, no extra limbs, no gore.\n"
            f"Title/context: {title}\n"
            f"{hook_hint}"
            "Style: cinematic, sharp focus, rim light, bold contrast, centered subject, clear negative space for text.\n"
            "Subject ideas: alien/creature reveal, doorway silhouette, split transformation.\n"
            "Output: a single striking frame."
        )

    # Legacy helper retained for minimal diffs with older code paths.
    async def _generate_gemini_thumbnail(self, video_title: str, hook: str, output_path: str) -> bool:
        prompt = f"Cinematic YouTube thumbnail for movie recap: {video_title}. Dramatic, high contrast, mysterious. No text."
        result_path = gemini.generate_image(prompt, output_path)
        if not result_path:
            return False
        try:
            if hook and hook.strip():
                await self._add_text_overlay(output_path, hook.strip()[:30])
        except Exception:
            pass
        return True

    async def _add_text_overlay(self, image_path: str, text: str) -> bool:
        """Add Amharic text overlay."""
        try:
            img = Image.open(image_path)
            img = img.resize((self.width, self.height), Image.LANCZOS)
            draw = ImageDraw.Draw(img)
            
            # Font handling
            font_size = 90
            font = ImageFont.load_default()
            try:
                # Try to find a font (system dependent)
                # In docker we might need to install one or use default
                # For now using default or checking common paths
                paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
                         "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Bold.ttf"]
                for p in paths:
                    if os.path.exists(p):
                        font = ImageFont.truetype(p, font_size)
                        break
            except:
                pass

            # Text positioning
            # Center bottom
            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = (self.width - w) // 2
            y = self.height - h - 50
            
            # Stroke/Shadow
            draw.text((x+4, y+4), text, font=font, fill="black")
            draw.text((x, y), text, font=font, fill="white")
            
            img.save(image_path)
            return True
        except Exception as e:
            logger.error(f"Text overlay failed: {e}")
            return False

    async def _calculate_heuristic_score(self, thumbnail_path: str) -> float:
        """Simple heuristic score."""
        try:
            img = Image.open(thumbnail_path)
            arr = np.array(img)
            return float(np.std(arr) / 128.0) # Contrast proxy
        except:
            return 0.5
