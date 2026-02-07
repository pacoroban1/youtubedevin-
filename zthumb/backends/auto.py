"""
Auto Backend - Automatically selects best backend based on VRAM
"""

import subprocess
from pathlib import Path
from typing import List

from .base import BaseBackend
from .turbo import TurboBackend
from .full import FullBackend
from .gguf import GGUFBackend


class AutoBackend(BaseBackend):
    """Auto-selecting backend based on VRAM availability."""
    
    def __init__(self, models: list):
        super().__init__(models)
        self.variant = "auto"
        self.selected_backend = None
        self._select_backend()
    
    def _get_vram_mb(self) -> int:
        """Get available VRAM in MB."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split("\n")[0])
        except Exception:
            pass
        
        try:
            import torch
            if torch.cuda.is_available():
                return torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
        except ImportError:
            pass
        
        return 0
    
    def _select_backend(self):
        """Select the best backend based on VRAM."""
        vram_mb = self._get_vram_mb()
        available_variants = {m["variant"] for m in self.models if m["available"]}
        
        if vram_mb >= 12000 and "full" in available_variants:
            self.selected_backend = FullBackend(self.models)
            self.variant = "full"
        elif vram_mb >= 8000 and "turbo" in available_variants:
            self.selected_backend = TurboBackend(self.models)
            self.variant = "turbo"
        elif "gguf" in available_variants:
            self.selected_backend = GGUFBackend(self.models)
            self.variant = "gguf"
        elif "turbo" in available_variants:
            self.selected_backend = TurboBackend(self.models)
            self.variant = "turbo"
        else:
            # Fallback to GGUF even if not available (will use memory optimizations)
            self.selected_backend = GGUFBackend(self.models)
            self.variant = "gguf"
    
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
        lora_path=None,
        lora_scale=None
    ) -> List[str]:
        """Generate images using auto-selected backend."""
        return await self.selected_backend.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            steps=steps,
            cfg=cfg,
            batch=batch,
            output_dir=output_dir,
            output_format=output_format,
            upscale=upscale,
            face_detail=face_detail,
            lora_path=lora_path,
            lora_scale=lora_scale
        )
