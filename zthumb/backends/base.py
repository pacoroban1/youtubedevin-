"""
Base Backend Abstract Class
"""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional


class BaseBackend(ABC):
    """Abstract base class for image generation backends."""
    
    def __init__(self, models: list):
        self.models = models
        self.model_path = None
        self._setup()
    
    def _setup(self):
        """Setup the backend with available models."""
        pass
    
    @abstractmethod
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
        lora_scale: Optional[float] = None
    ) -> List[str]:
        """Generate images and return list of file paths."""
        pass
    
    def get_model_path(self, variant: str) -> Optional[str]:
        """Get path to model file for given variant."""
        for model in self.models:
            if model["variant"] == variant and model["available"]:
                return model["path"]
        return None

    def _env_lora_path(self) -> Optional[str]:
        # Preferred env vars per project spec
        return os.getenv("Z_LORA_PATH") or os.getenv("ZTHUMB_LORA_PATH")

    def _env_lora_scale(self) -> Optional[float]:
        raw = os.getenv("Z_LORA_SCALE") or os.getenv("ZTHUMB_LORA_SCALE")
        if raw is None or raw == "":
            return None
        try:
            return float(raw)
        except ValueError as e:
            raise RuntimeError("Invalid Z_LORA_SCALE/ZTHUMB_LORA_SCALE (must be float)") from e

    def apply_lora(self, pipe, lora_scale: Optional[float] = None) -> bool:
        """
        Optionally apply an SDXL LoRA (fine-tune) at inference time.

        This is intentionally env-driven so it works in Docker without adding
        new API surface area.

        Env vars:
          - Z_LORA_PATH (preferred) or ZTHUMB_LORA_PATH: path to LoRA weights (e.g. /outputs/lora/my_style_lora)
          - Z_LORA_SCALE (preferred) or ZTHUMB_LORA_SCALE: float scale (default 1.0)

        Returns:
          True if a LoRA path was provided and loading was attempted, else False.
        """
        lora_path = self._env_lora_path()
        if not lora_path:
            return False

        scale = lora_scale
        if scale is None:
            env_scale = self._env_lora_scale()
            scale = env_scale if env_scale is not None else 1.0

        # Diffusers APIs vary by version. Prefer adapter-based flow when available.
        try:
            if not hasattr(pipe, "load_lora_weights"):
                raise RuntimeError("Pipeline does not support LoRA (missing load_lora_weights)")

            loaded_path = getattr(pipe, "_zthumb_lora_loaded_path", None)
            if loaded_path != lora_path:
                # adapter_name support exists on newer diffusers; best-effort.
                try:
                    pipe.load_lora_weights(lora_path, adapter_name="zthumb")
                except TypeError:
                    pipe.load_lora_weights(lora_path)
                setattr(pipe, "_zthumb_lora_loaded_path", lora_path)

            # If adapters can be set, prefer that for per-request scaling.
            if hasattr(pipe, "set_adapters"):
                try:
                    pipe.set_adapters(["zthumb"], adapter_weights=[scale])
                except TypeError:
                    # Some versions use a different signature.
                    pass
                # When adapter weights can be set, avoid fusing so lora_scale overrides work.
                return True

            # Fallback path: fuse LoRA if the pipeline doesn't support adapters.
            if hasattr(pipe, "fuse_lora"):
                fused_path = getattr(pipe, "_zthumb_lora_fused_path", None)
                fused_scale = getattr(pipe, "_zthumb_lora_fused_scale", None)
                if fused_path == lora_path and fused_scale == scale:
                    return True

                # If already fused with some other scale/path, try to unfuse first.
                if hasattr(pipe, "unfuse_lora"):
                    try:
                        pipe.unfuse_lora()
                    except Exception:
                        pass

                try:
                    pipe.fuse_lora(lora_scale=scale)
                except TypeError:
                    pipe.fuse_lora()
                setattr(pipe, "_zthumb_lora_fused_path", lora_path)
                setattr(pipe, "_zthumb_lora_fused_scale", scale)
        except Exception as e:
            raise RuntimeError(f"Failed to load/apply LoRA from Z_LORA_PATH/ZTHUMB_LORA_PATH={lora_path}: {e}") from e

        return True
    
    async def post_process(
        self,
        image_path: Path,
        upscale: bool = False,
        face_detail: bool = False
    ) -> Path:
        """Apply post-processing to generated image."""
        # Default implementation - no processing
        return image_path
