#!/usr/bin/env python3
"""
GPU Detection Script
Detects GPU type and VRAM to recommend the best backend.
"""

import subprocess
import sys
import json


def get_gpu_info():
    """Detect GPU and VRAM information."""
    info = {
        "gpu": False,
        "cuda_available": False,
        "vram_mb": 0,
        "gpu_name": "None",
        "recommended_backend": "gguf"
    }
    
    # Try nvidia-smi first
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines and lines[0]:
                parts = lines[0].split(", ")
                info["gpu"] = True
                info["gpu_name"] = parts[0] if len(parts) > 0 else "Unknown"
                info["vram_mb"] = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        pass
    
    # Check CUDA availability via torch
    try:
        import torch
        info["cuda_available"] = torch.cuda.is_available()
        if info["cuda_available"] and not info["gpu"]:
            info["gpu"] = True
            info["vram_mb"] = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
            info["gpu_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    
    # Determine recommended backend
    if info["vram_mb"] >= 12000:
        info["recommended_backend"] = "full"
    elif info["vram_mb"] >= 8000:
        info["recommended_backend"] = "turbo"
    else:
        info["recommended_backend"] = "gguf"
    
    return info


def main():
    info = get_gpu_info()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        print(json.dumps(info, indent=2))
    else:
        print(f"GPU Detected: {info['gpu']}")
        print(f"GPU Name: {info['gpu_name']}")
        print(f"VRAM: {info['vram_mb']} MB")
        print(f"CUDA Available: {info['cuda_available']}")
        print(f"Recommended Backend: {info['recommended_backend']}")


if __name__ == "__main__":
    main()
