#!/usr/bin/env python3
"""
Z-Image Thumbnail Engine - Python Client & CLI
Usage:
  python zthumb_client.py generate "cinematic alien reveal" --batch 4
  python zthumb_client.py health
  python zthumb_client.py models
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

try:
    import httpx
except ImportError:
    print("Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)


DEFAULT_SERVER_URL = "http://localhost:8100"


@dataclass
class ThumbnailConcept:
    """Thumbnail generation concept."""
    prompt: str
    negative_prompt: str = "text, watermark, logo, blurry, low quality, cartoon, anime, deformed hands"
    width: int = 1280
    height: int = 720
    seed: Optional[int] = None
    steps: int = 35
    cfg: float = 4.0
    batch: int = 4
    style_preset: Optional[str] = None
    subject: Optional[str] = None


class ZThumbClient:
    """Client for Z-Image Thumbnail Engine API."""
    
    def __init__(self, server_url: str = DEFAULT_SERVER_URL, timeout: float = 300.0):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
    
    def health(self) -> Dict[str, Any]:
        """Check server health."""
        response = self.client.get(f"{self.server_url}/health")
        response.raise_for_status()
        return response.json()
    
    def models(self) -> Dict[str, Any]:
        """List available models."""
        response = self.client.get(f"{self.server_url}/models")
        response.raise_for_status()
        return response.json()
    
    def generate(
        self,
        prompt: str,
        negative_prompt: str = "text, watermark, logo, blurry, low quality",
        width: int = 1280,
        height: int = 720,
        seed: Optional[int] = None,
        steps: int = 35,
        cfg: float = 4.0,
        sampler: str = "euler",
        variant: str = "auto",
        batch: int = 4,
        output_format: str = "png",
        upscale: bool = True,
        face_detail: bool = True,
        safe_mode: bool = True,
        style_preset: Optional[str] = None,
        subject: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate thumbnail images."""
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "sampler": sampler,
            "variant": variant,
            "batch": batch,
            "output_format": output_format,
            "upscale": upscale,
            "face_detail": face_detail,
            "safe_mode": safe_mode
        }
        
        if seed is not None:
            payload["seed"] = seed
        if style_preset:
            payload["style_preset"] = style_preset
        if subject:
            payload["subject"] = subject
        
        response = self.client.post(
            f"{self.server_url}/generate",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    def generate_from_concept(self, concept: ThumbnailConcept) -> Dict[str, Any]:
        """Generate from a ThumbnailConcept object."""
        return self.generate(
            prompt=concept.prompt,
            negative_prompt=concept.negative_prompt,
            width=concept.width,
            height=concept.height,
            seed=concept.seed,
            steps=concept.steps,
            cfg=concept.cfg,
            batch=concept.batch,
            style_preset=concept.style_preset,
            subject=concept.subject
        )
    
    def close(self):
        """Close the client."""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


def generate_thumbnail(concept: Dict[str, Any], server_url: str = DEFAULT_SERVER_URL) -> List[str]:
    """
    Convenience function to generate thumbnails.
    
    Args:
        concept: Dictionary with prompt, negative_prompt, etc.
        server_url: Server URL
    
    Returns:
        List of image file paths
    """
    with ZThumbClient(server_url) as client:
        result = client.generate(**concept)
        return result.get("images", [])


def two_pass_generate(
    prompt: str,
    subject: Optional[str] = None,
    style_preset: Optional[str] = None,
    server_url: str = DEFAULT_SERVER_URL
) -> Dict[str, Any]:
    """
    Two-pass thumbnail generation strategy:
    1. Generate 6 Turbo drafts (fast)
    2. Score them using heuristics
    3. Re-render top 2 with Full quality
    
    Args:
        prompt: Main prompt
        subject: Subject for preset templates
        style_preset: Style preset name
        server_url: Server URL
    
    Returns:
        Dictionary with best images and metadata
    """
    with ZThumbClient(server_url) as client:
        # Check available backends
        models_info = client.models()
        has_full = any(m["variant"] == "full" and m["available"] for m in models_info.get("models", []))
        
        # Pass 1: Generate 6 Turbo drafts
        print("Pass 1: Generating 6 Turbo drafts...")
        drafts = client.generate(
            prompt=prompt,
            variant="turbo",
            batch=6,
            steps=4,
            upscale=False,
            face_detail=False,
            style_preset=style_preset,
            subject=subject
        )
        
        draft_images = drafts.get("images", [])
        print(f"  Generated {len(draft_images)} drafts")
        
        # Score drafts (simple heuristics)
        scores = score_thumbnails(draft_images)
        
        # Get top 2 indices
        sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        top_2_indices = sorted_indices[:2]
        
        print(f"  Top 2 drafts: indices {top_2_indices}")
        
        # Pass 2: Re-render top 2 with Full quality (if available)
        if has_full:
            print("Pass 2: Re-rendering top 2 with Full quality...")
            # Use the same seeds as the top drafts
            seed = drafts.get("meta", {}).get("seed", 12345)
            
            finals = []
            for idx in top_2_indices:
                result = client.generate(
                    prompt=prompt,
                    variant="full",
                    batch=1,
                    seed=seed + idx,
                    steps=35,
                    upscale=True,
                    face_detail=True,
                    style_preset=style_preset,
                    subject=subject
                )
                finals.extend(result.get("images", []))
            
            return {
                "images": finals,
                "drafts": draft_images,
                "scores": scores,
                "meta": {
                    "strategy": "two_pass",
                    "draft_count": len(draft_images),
                    "final_count": len(finals)
                }
            }
        else:
            # No Full backend, return best drafts with upscaling
            print("Pass 2: Full backend not available, upscaling best drafts...")
            return {
                "images": [draft_images[i] for i in top_2_indices],
                "drafts": draft_images,
                "scores": scores,
                "meta": {
                    "strategy": "turbo_only",
                    "draft_count": len(draft_images),
                    "final_count": 2
                }
            }


def score_thumbnails(image_paths: List[str]) -> List[float]:
    """
    Score thumbnails using simple heuristics.
    
    Scoring criteria:
    - Subject size/center
    - Contrast
    - Face clarity (if face present)
    
    Returns list of scores (0-100).
    """
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        # Return equal scores if PIL not available
        return [50.0] * len(image_paths)
    
    scores = []
    
    for path in image_paths:
        try:
            # Remove file:// prefix if present
            clean_path = path.replace("file://", "")
            img = Image.open(clean_path).convert("RGB")
            arr = np.array(img)
            
            score = 0.0
            
            # Contrast score (std of luminance)
            luminance = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
            contrast = np.std(luminance) / 128.0 * 30  # Max 30 points
            score += min(contrast, 30)
            
            # Center brightness (subject likely in center)
            h, w = luminance.shape
            center = luminance[h//4:3*h//4, w//4:3*w//4]
            center_brightness = np.mean(center) / 255.0 * 20  # Max 20 points
            score += center_brightness
            
            # Edge sharpness (Laplacian variance)
            from PIL import ImageFilter
            edges = img.filter(ImageFilter.FIND_EDGES)
            edge_arr = np.array(edges.convert("L"))
            sharpness = np.var(edge_arr) / 1000 * 30  # Max 30 points
            score += min(sharpness, 30)
            
            # Color variety
            color_std = np.std(arr) / 128.0 * 20  # Max 20 points
            score += min(color_std, 20)
            
            scores.append(min(score, 100))
            
        except Exception as e:
            print(f"  Warning: Could not score {path}: {e}")
            scores.append(50.0)
    
    return scores


def main():
    parser = argparse.ArgumentParser(
        description="Z-Image Thumbnail Engine CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s health
  %(prog)s models
  %(prog)s generate "cinematic alien creature reveal"
  %(prog)s generate "mysterious figure" --preset doorway_silhouette
  %(prog)s two-pass "epic transformation scene" --subject "werewolf"
        """
    )
    
    parser.add_argument("--server", default=DEFAULT_SERVER_URL,
                        help=f"Server URL (default: {DEFAULT_SERVER_URL})")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # Health command
    subparsers.add_parser("health", help="Check server health")
    
    # Models command
    subparsers.add_parser("models", help="List available models")
    
    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate thumbnails")
    gen_parser.add_argument("prompt", help="Generation prompt")
    gen_parser.add_argument("--negative", default="text, watermark, logo, blurry, low quality",
                           help="Negative prompt")
    gen_parser.add_argument("--width", type=int, default=1280)
    gen_parser.add_argument("--height", type=int, default=720)
    gen_parser.add_argument("--seed", type=int, default=None)
    gen_parser.add_argument("--steps", type=int, default=35)
    gen_parser.add_argument("--cfg", type=float, default=4.0)
    gen_parser.add_argument("--variant", choices=["auto", "turbo", "full", "gguf"], default="auto")
    gen_parser.add_argument("--batch", type=int, default=4)
    gen_parser.add_argument("--preset", choices=["alien_reveal", "doorway_silhouette", "split_transformation"])
    gen_parser.add_argument("--subject", help="Subject for preset templates")
    gen_parser.add_argument("--no-upscale", action="store_true")
    gen_parser.add_argument("--no-face-detail", action="store_true")
    gen_parser.add_argument("--unsafe", action="store_true", help="Disable safe mode")
    
    # Two-pass command
    two_parser = subparsers.add_parser("two-pass", help="Two-pass generation (drafts + quality)")
    two_parser.add_argument("prompt", help="Generation prompt")
    two_parser.add_argument("--preset", choices=["alien_reveal", "doorway_silhouette", "split_transformation"])
    two_parser.add_argument("--subject", help="Subject for preset templates")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        with ZThumbClient(args.server) as client:
            if args.command == "health":
                result = client.health()
            
            elif args.command == "models":
                result = client.models()
            
            elif args.command == "generate":
                result = client.generate(
                    prompt=args.prompt,
                    negative_prompt=args.negative,
                    width=args.width,
                    height=args.height,
                    seed=args.seed,
                    steps=args.steps,
                    cfg=args.cfg,
                    variant=args.variant,
                    batch=args.batch,
                    upscale=not args.no_upscale,
                    face_detail=not args.no_face_detail,
                    safe_mode=not args.unsafe,
                    style_preset=args.preset,
                    subject=args.subject
                )
            
            elif args.command == "two-pass":
                result = two_pass_generate(
                    prompt=args.prompt,
                    style_preset=args.preset,
                    subject=args.subject,
                    server_url=args.server
                )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if args.command == "health":
                print(f"Status: {result['status']}")
                print(f"Backend: {result['backend']}")
                print(f"GPU: {result['gpu']}")
                print(f"VRAM: {result['vram_mb']} MB")
                print(f"CUDA: {result['cuda_available']}")
                print(f"Models: {', '.join(result['models_available']) or 'None'}")
            
            elif args.command == "models":
                print(f"Recommended: {result['recommended']}")
                print(f"VRAM: {result['vram_mb']} MB")
                print("\nAvailable models:")
                for m in result['models']:
                    status = "OK" if m['available'] else "NOT INSTALLED"
                    print(f"  - {m['name']} ({m['variant']}): {status}")
                    print(f"    VRAM required: {m['vram_required']} MB")
            
            elif args.command in ["generate", "two-pass"]:
                if result.get("warnings"):
                    print("Warnings:")
                    for w in result["warnings"]:
                        print(f"  - {w}")
                
                print(f"\nGenerated {len(result['images'])} images:")
                for img in result["images"]:
                    print(f"  {img}")
                
                if "meta" in result:
                    print(f"\nMetadata:")
                    print(f"  Seed: {result['meta'].get('seed')}")
                    print(f"  Backend: {result['meta'].get('backend')}")
                    if "timings" in result["meta"]:
                        print(f"  Time: {result['meta']['timings'].get('total', 0):.2f}s")
    
    except httpx.ConnectError:
        print(f"Error: Could not connect to server at {args.server}")
        print("Make sure the Z-Image server is running: ./run_zthumb.sh")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: {e.response.status_code} - {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
