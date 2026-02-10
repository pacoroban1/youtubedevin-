#!/usr/bin/env python3
"""
Evaluation for ZThumb LoRA: generate fixed prompt set with fixed seeds,
save before/after images and simple grids, and write TRAINING_REPORT.md.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image


DEFAULT_PROMPTS = [
    "[alien_reveal] cinematic movie poster, alien creature close-up, rim light, high contrast, volumetric fog, sharp focus, dramatic lighting",
    "[doorway_silhouette] mysterious silhouette in doorway, backlit, rim lighting, horror movie poster composition, high contrast",
    "[split_transformation] split face transformation, before and after, dramatic lighting, cinematic composition, sharp focus",
    "cinematic monster reveal, centered subject, high contrast, dramatic lighting, sharp focus",
    "fearful face close-up, dark background, rim light, intense expression, cinematic, high contrast",
    "mysterious creature emerging from shadows, close-up, volumetric fog, movie poster, dramatic lighting",
    "doorway silhouette, backlit subject, high contrast, cinematic, sharp focus",
    "transformation scene, split composition, dramatic lighting, cinematic, sharp focus",
    "single subject close-up, centered, rim light, high contrast, clean background",
    "movie recap thumbnail, dramatic lighting, sharp focus, high contrast, single subject",
]


def img_score(path: Path) -> dict:
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img).astype(np.float32) / 255.0
    gray = arr.mean(axis=2)
    contrast = float(gray.std())

    # Simple edge density (Sobel-ish via finite diffs)
    dx = np.abs(gray[:, 1:] - gray[:, :-1])
    dy = np.abs(gray[1:, :] - gray[:-1, :])
    edge = float((dx.mean() + dy.mean()) / 2.0)

    return {"contrast": contrast, "edge_density": edge}


def make_grid(paths: list[Path], cols: int, out_path: Path) -> None:
    imgs = [Image.open(p).convert("RGB") for p in paths]
    if not imgs:
        return
    w, h = imgs[0].size
    rows = math.ceil(len(imgs) / cols)
    grid = Image.new("RGB", (cols * w, rows * h), color=(0, 0, 0))
    for i, im in enumerate(imgs):
        x = (i % cols) * w
        y = (i // cols) * h
        grid.paste(im, (x, y))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    grid.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-model", default=None)
    ap.add_argument("--lora", default="outputs/lora/zthumb_lora")
    ap.add_argument("--lora-scale", type=float, default=0.8)
    ap.add_argument("--out", default="outputs/eval")
    ap.add_argument("--seeds", default="111,222")
    ap.add_argument("--steps", type=int, default=35)
    ap.add_argument("--cfg", type=float, default=4.5)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    args = ap.parse_args()

    out_root = Path(args.out)
    before_dir = out_root / "before"
    after_dir = out_root / "after"
    before_dir.mkdir(parents=True, exist_ok=True)
    after_dir.mkdir(parents=True, exist_ok=True)

    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]

    base_model = args.base_model
    if base_model is None:
        local = Path("models/sd_xl_base_1.0.safetensors")
        base_model = str(local) if local.exists() else "stabilityai/stable-diffusion-xl-base-1.0"

    import torch
    from diffusers import StableDiffusionXLPipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    def load_pipe():
        if Path(str(base_model)).exists():
            p = StableDiffusionXLPipeline.from_single_file(str(base_model), torch_dtype=dtype, use_safetensors=True)
        else:
            p = StableDiffusionXLPipeline.from_pretrained(
                str(base_model),
                torch_dtype=dtype,
                use_safetensors=True,
                variant="fp16" if device == "cuda" else None,
            )
        p.to(device)
        return p

    base_pipe = load_pipe()
    tuned_pipe = load_pipe()
    tuned_pipe.load_lora_weights(args.lora)
    if hasattr(tuned_pipe, "set_adapters"):
        try:
            tuned_pipe.set_adapters(["default"], adapter_weights=[args.lora_scale])
        except Exception:
            pass
    if hasattr(tuned_pipe, "fuse_lora"):
        try:
            tuned_pipe.fuse_lora(lora_scale=args.lora_scale)
        except TypeError:
            tuned_pipe.fuse_lora()

    results = []
    before_paths: list[Path] = []
    after_paths: list[Path] = []

    for prompt_i, prompt in enumerate(DEFAULT_PROMPTS):
        for seed in seeds:
            gen = torch.Generator(device=device).manual_seed(seed)
            b_img = base_pipe(prompt, width=args.width, height=args.height, num_inference_steps=args.steps, guidance_scale=args.cfg, generator=gen).images[0]
            b_path = before_dir / f"p{prompt_i:02d}_s{seed}_before.png"
            b_img.save(b_path)
            before_paths.append(b_path)

            gen = torch.Generator(device=device).manual_seed(seed)
            a_img = tuned_pipe(prompt, width=args.width, height=args.height, num_inference_steps=args.steps, guidance_scale=args.cfg, generator=gen).images[0]
            a_path = after_dir / f"p{prompt_i:02d}_s{seed}_after.png"
            a_img.save(a_path)
            after_paths.append(a_path)

            b_score = img_score(b_path)
            a_score = img_score(a_path)
            results.append(
                {
                    "prompt": prompt,
                    "seed": seed,
                    "before": {"path": str(b_path), **b_score},
                    "after": {"path": str(a_path), **a_score},
                }
            )

    # Grids
    make_grid(before_paths[:12], cols=4, out_path=out_root / "before_grid.png")
    make_grid(after_paths[:12], cols=4, out_path=out_root / "after_grid.png")

    (out_root / "eval_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Report (appendable, but deterministic section)
    report_path = Path("TRAINING_REPORT.md")
    now = datetime.now().isoformat(timespec="seconds")
    lines = []
    lines.append(f"# TRAINING_REPORT\n")
    lines.append(f"\n## Latest Eval\n")
    lines.append(f"- Timestamp: `{now}`\n")
    lines.append(f"- Base model: `{base_model}`\n")
    lines.append(f"- LoRA path: `{args.lora}`\n")
    lines.append(f"- Output: `{out_root}`\n")
    lines.append(f"\n### Samples\n")
    lines.append(f"- Before grid: `{out_root / 'before_grid.png'}`\n")
    lines.append(f"- After grid: `{out_root / 'after_grid.png'}`\n")
    lines.append(f"\n### Heuristic Summary\n")
    b_con = np.mean([r['before']['contrast'] for r in results])
    a_con = np.mean([r['after']['contrast'] for r in results])
    b_edge = np.mean([r['before']['edge_density'] for r in results])
    a_edge = np.mean([r['after']['edge_density'] for r in results])
    lines.append(f"- Contrast (avg): before={b_con:.4f} after={a_con:.4f}\n")
    lines.append(f"- Edge density (avg): before={b_edge:.4f} after={a_edge:.4f}\n")
    lines.append(f"\n### Notes\n")
    lines.append(f"- These are simple heuristics (contrast + edge density). Add face/subject detectors later if needed.\n")
    report_path.write_text("".join(lines), encoding="utf-8")

    print("OK: eval complete")
    print(f"Wrote: {report_path}")


if __name__ == "__main__":
    main()
