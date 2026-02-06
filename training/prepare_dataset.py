#!/usr/bin/env python3
"""
Dataset builder for ZThumb LoRA.

Modes:
  - manual: validate that images have matching caption .txt files
  - bootstrap: import images from a folder and optionally auto-caption
"""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def iter_images(folder: Path) -> Iterable[Path]:
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            yield p


def caption_skeleton(style_tag: str, subject: str = "mysterious creature") -> str:
    # Keep format consistent and editable.
    return (
        f"[{style_tag}] "
        f"subject: {subject}; "
        "composition: close-up, centered subject, rim light, high contrast, minimal empty area for text; "
        "quality: cinematic, sharp focus, clean, no watermark, no extra limbs"
    )


def blip_caption(image_path: Path, model_name: str) -> str:
    try:
        from PIL import Image
        import torch
        from transformers import BlipProcessor, BlipForConditionalGeneration
    except Exception as e:
        raise RuntimeError(
            "Auto-caption requires pillow, torch, transformers. "
            "Run inside the training container or install deps."
        ) from e

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = BlipProcessor.from_pretrained(model_name)
    model = BlipForConditionalGeneration.from_pretrained(model_name).to(device)
    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt").to(device)
    out = model.generate(**inputs, max_new_tokens=40)
    text = processor.decode(out[0], skip_special_tokens=True).strip()
    return text


@dataclass
class Paths:
    root: Path
    images: Path
    captions: Path
    masks: Path


def resolve_dataset(root: Path) -> Paths:
    return Paths(
        root=root,
        images=root / "images",
        captions=root / "captions",
        masks=root / "masks",
    )


def ensure_dirs(p: Paths) -> None:
    p.images.mkdir(parents=True, exist_ok=True)
    p.captions.mkdir(parents=True, exist_ok=True)
    p.masks.mkdir(parents=True, exist_ok=True)


def validate_manual(ds: Paths, allow_missing: bool, default_style: str) -> None:
    missing = []
    for img in iter_images(ds.images):
        cap = ds.captions / (img.stem + ".txt")
        if not cap.exists():
            missing.append((img, cap))

    if missing and not allow_missing:
        print("ERROR: Missing captions:")
        for img, cap in missing:
            print(f"  - {img} -> expected {cap}")
        raise SystemExit(2)

    if missing and allow_missing:
        for img, cap in missing:
            cap.write_text(caption_skeleton(default_style), encoding="utf-8")
        print(f"OK: Wrote {len(missing)} placeholder caption(s).")

    print("OK: Manual dataset validated.")


def import_bootstrap(
    ds: Paths,
    import_dir: Path,
    max_images: Optional[int],
    style_tag: str,
    auto_caption: bool,
    caption_model: str,
) -> None:
    if not import_dir.exists():
        raise SystemExit(f"ERROR: import dir does not exist: {import_dir}")

    imgs = list(iter_images(import_dir))
    if max_images is not None:
        imgs = imgs[:max_images]

    if not imgs:
        raise SystemExit(f"ERROR: no images found under {import_dir}")

    for idx, src in enumerate(imgs):
        dst_name = f"{idx:06d}{src.suffix.lower()}"
        dst_img = ds.images / dst_name
        shutil.copy2(src, dst_img)

        dst_cap = ds.captions / f"{Path(dst_name).stem}.txt"
        if auto_caption:
            raw = blip_caption(dst_img, caption_model)
            cap = caption_skeleton(style_tag, subject=raw)
        else:
            cap = caption_skeleton(style_tag)
        dst_cap.write_text(cap, encoding="utf-8")

    print(f"OK: Imported {len(imgs)} image(s) into {ds.images}")
    print(f"OK: Captions written to {ds.captions}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="datasets/thumbs", help="Dataset root (images/, captions/, masks/)")
    ap.add_argument("--mode", choices=["manual", "bootstrap"], required=True)
    ap.add_argument("--allow-missing-captions", action="store_true", help="Create placeholder captions if missing")

    # Bootstrap options
    ap.add_argument("--import-dir", help="Folder containing images to import (bootstrap mode)")
    ap.add_argument("--max-images", type=int, default=None)
    ap.add_argument("--style-tag", default="alien_reveal", help="Style tag name (without brackets)")
    ap.add_argument("--auto-caption", action="store_true", help="Use a caption model for bootstrap mode")
    ap.add_argument("--caption-model", default="Salesforce/blip-image-captioning-base")

    args = ap.parse_args()

    ds = resolve_dataset(Path(args.dataset))
    ensure_dirs(ds)

    if args.mode == "manual":
        validate_manual(ds, allow_missing=args.allow_missing_captions, default_style=args.style_tag)
        return

    if args.mode == "bootstrap":
        if not args.import_dir:
            raise SystemExit("ERROR: --import-dir is required for bootstrap mode")
        import_bootstrap(
            ds,
            import_dir=Path(args.import_dir),
            max_images=args.max_images,
            style_tag=args.style_tag,
            auto_caption=args.auto_caption,
            caption_model=args.caption_model,
        )
        return


if __name__ == "__main__":
    main()

