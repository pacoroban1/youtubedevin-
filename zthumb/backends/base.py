"""
Base Backend Abstract Class
"""

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
        face_detail: bool = False
    ) -> List[str]:
        """Generate images and return list of file paths."""
        pass
    
    def get_model_path(self, variant: str) -> Optional[str]:
        """Get path to model file for given variant."""
        for model in self.models:
            if model["variant"] == variant and model["available"]:
                return model["path"]
        return None
    
    async def post_process(
        self,
        image_path: Path,
        upscale: bool = False,
        face_detail: bool = False
    ) -> Path:
        """Apply post-processing to generated image."""
        # Default implementation - no processing
        return image_path
