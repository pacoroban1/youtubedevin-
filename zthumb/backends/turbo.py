"""
SDXL-Turbo Backend - Fast draft generation (1-4 steps)
"""

import asyncio
from pathlib import Path
from typing import List

from .base import BaseBackend


class TurboBackend(BaseBackend):
    """SDXL-Turbo backend for fast image generation."""
    
    def __init__(self, models: list):
        super().__init__(models)
        self.variant = "turbo"
        self.pipe = None
    
    def _setup(self):
        """Setup the turbo backend."""
        self.model_path = self.get_model_path("turbo")
    
    def _load_pipeline(self):
        """Lazy load the diffusion pipeline."""
        if self.pipe is not None:
            return
        
        try:
            import torch
            from diffusers import AutoPipelineForText2Image
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            
            if self.model_path and Path(self.model_path).exists():
                # Load from local file
                self.pipe = AutoPipelineForText2Image.from_single_file(
                    self.model_path,
                    torch_dtype=dtype,
                    variant="fp16" if device == "cuda" else None
                )
            else:
                # Load from HuggingFace
                self.pipe = AutoPipelineForText2Image.from_pretrained(
                    "stabilityai/sdxl-turbo",
                    torch_dtype=dtype,
                    variant="fp16" if device == "cuda" else None
                )
            
            self.pipe.to(device)

            # Enable memory optimizations
            if device == "cuda":
                try:
                    self.pipe.enable_xformers_memory_efficient_attention()
                except Exception:
                    pass
                    
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
        face_detail: bool = False,
        lora_scale=None
    ) -> List[str]:
        """Generate images using SDXL-Turbo."""
        
        # Run in thread pool to not block
        loop = asyncio.get_event_loop()
        images = await loop.run_in_executor(
            None,
            self._generate_sync,
            prompt, negative_prompt, width, height, seed,
            min(steps, 4),  # Turbo works best with 1-4 steps
            cfg, batch, output_dir, output_format, lora_scale
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
        lora_scale
    ) -> List[str]:
        """Synchronous generation."""
        import torch
        
        self._load_pipeline()
        self.apply_lora(self.pipe, lora_scale=lora_scale)
        
        generator = torch.Generator(device=self.pipe.device).manual_seed(seed)
        
        images = []
        for i in range(batch):
            # Generate with slightly different seeds for variety
            gen = torch.Generator(device=self.pipe.device).manual_seed(seed + i)
            
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
            img_path = output_dir / f"img_{i+1}.{output_format}"
            img.save(img_path)
            images.append(f"file://{img_path}")
        
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
            # Simple 2x upscale with Lanczos
            new_size = (img.width * 2, img.height * 2)
            img = img.resize(new_size, Image.LANCZOS)
            # Sharpen
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
        
        if face_detail:
            # Enhance contrast slightly for face detail
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.1)
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.2)
        
        # Save processed image
        processed_path = image_path.parent / f"{image_path.stem}_processed{image_path.suffix}"
        img.save(processed_path)
        
        return processed_path
