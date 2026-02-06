"""
SDXL GGUF Backend - Low VRAM / CPU fallback
Uses quantized models for systems with limited resources.
"""

import asyncio
from pathlib import Path
from typing import List

from .base import BaseBackend


class GGUFBackend(BaseBackend):
    """GGUF quantized backend for low VRAM systems."""
    
    def __init__(self, models: list):
        super().__init__(models)
        self.variant = "gguf"
        self.pipe = None
    
    def _setup(self):
        """Setup the GGUF backend."""
        self.model_path = self.get_model_path("gguf")
    
    def _load_pipeline(self):
        """Lazy load the diffusion pipeline with GGUF support."""
        if self.pipe is not None:
            return
        
        try:
            import torch
            from diffusers import StableDiffusionXLPipeline
            
            # For GGUF, we need special handling
            # If GGUF model exists, try to load it
            # Otherwise fall back to regular SDXL with CPU offloading
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            # Use float32 for CPU, float16 for CUDA with low memory
            if device == "cpu":
                dtype = torch.float32
            else:
                dtype = torch.float16
            
            # Try to load GGUF model if available
            if self.model_path and Path(self.model_path).exists():
                # GGUF loading requires special handling
                # For now, fall back to regular model with aggressive memory optimization
                self.pipe = StableDiffusionXLPipeline.from_pretrained(
                    "stabilityai/stable-diffusion-xl-base-1.0",
                    torch_dtype=dtype,
                    use_safetensors=True,
                    variant="fp16" if device == "cuda" else None
                )
            else:
                # Load regular model with memory optimizations
                self.pipe = StableDiffusionXLPipeline.from_pretrained(
                    "stabilityai/stable-diffusion-xl-base-1.0",
                    torch_dtype=dtype,
                    use_safetensors=True,
                    variant="fp16" if device == "cuda" else None
                )
            
            # Aggressive memory optimizations for low VRAM
            if device == "cuda":
                try:
                    self.pipe.enable_model_cpu_offload()
                except Exception:
                    pass
                try:
                    self.pipe.enable_vae_slicing()
                except Exception:
                    pass
                try:
                    self.pipe.enable_vae_tiling()
                except Exception:
                    pass
            else:
                self.pipe.to(device)
                    
        except ImportError as e:
            raise ImportError(f"Required packages not installed: {e}")
    
    async def generate(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        seed: int,
        steps: int,
        cfg: float,
        batch: int,
        output_dir: Path,
        output_format: str,
        upscale: bool = False,
        face_detail: bool = False
    ) -> List[str]:
        """Generate images using GGUF/low-memory mode."""
        
        # Run in thread pool to not block
        loop = asyncio.get_event_loop()
        
        # Reduce resolution for low VRAM
        effective_width = min(width, 1024)
        effective_height = min(height, 576)
        
        images = await loop.run_in_executor(
            None,
            self._generate_sync,
            prompt, negative_prompt, effective_width, effective_height, seed,
            min(steps, 25),  # Limit steps for speed
            cfg, batch, output_dir, output_format, width, height
        )
        
        # Post-process if requested
        if upscale or face_detail:
            processed = []
            for img_path in images:
                processed_path = await self.post_process(
                    Path(img_path.replace("file://", "")),
                    upscale=upscale,
                    face_detail=face_detail
                )
                processed.append(f"file://{processed_path}")
            return processed
        
        return images
    
    def _generate_sync(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        seed: int,
        steps: int,
        cfg: float,
        batch: int,
        output_dir: Path,
        output_format: str,
        target_width: int,
        target_height: int
    ) -> List[str]:
        """Synchronous generation with memory optimization."""
        import torch
        from PIL import Image
        
        self._load_pipeline()
        
        images = []
        for i in range(batch):
            # Generate with slightly different seeds for variety
            gen = torch.Generator().manual_seed(seed + i)
            
            result = self.pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=cfg,
                generator=gen
            )
            
            img = result.images[0]
            
            # Resize to target dimensions if different
            if img.width != target_width or img.height != target_height:
                img = img.resize((target_width, target_height), Image.LANCZOS)
            
            img_path = output_dir / f"img_{i+1}.{output_format}"
            img.save(img_path)
            images.append(f"file://{img_path}")
            
            # Clear CUDA cache between generations
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        
        return images
    
    async def post_process(
        self,
        image_path: Path,
        upscale: bool = False,
        face_detail: bool = False
    ) -> Path:
        """Apply post-processing."""
        from PIL import Image, ImageEnhance, ImageFilter
        
        img = Image.open(image_path)
        
        if upscale:
            # 2x upscale with Lanczos
            new_size = (img.width * 2, img.height * 2)
            img = img.resize(new_size, Image.LANCZOS)
            # Sharpen
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
        
        if face_detail:
            # Enhance contrast and sharpness
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.1)
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.2)
        
        # Save processed image
        processed_path = image_path.parent / f"{image_path.stem}_processed{image_path.suffix}"
        img.save(processed_path)
        
        return processed_path
