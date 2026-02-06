"""
Z-Image Thumbnail Engine - Backend Abstraction
Supports multiple backends: Full (SDXL), Turbo (SDXL-Turbo), GGUF (quantized)
"""

from .base import BaseBackend
from .turbo import TurboBackend
from .full import FullBackend
from .gguf import GGUFBackend
from .auto import AutoBackend


def get_backend(variant: str, models: list) -> BaseBackend:
    """Get the appropriate backend instance."""
    backends = {
        "turbo": TurboBackend,
        "full": FullBackend,
        "gguf": GGUFBackend,
        "auto": AutoBackend
    }
    
    backend_class = backends.get(variant, TurboBackend)
    return backend_class(models)


__all__ = [
    "BaseBackend",
    "TurboBackend", 
    "FullBackend",
    "GGUFBackend",
    "AutoBackend",
    "get_backend"
]
