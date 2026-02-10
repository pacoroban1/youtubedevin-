#!/usr/bin/env python3
"""
LoRA training for ZThumb (SDXL) using Diffusers attention-processor LoRA.

Output is compatible with Diffusers `pipe.load_lora_weights()` and ZThumb’s
inference loader (env: Z_LORA_PATH / Z_LORA_SCALE).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
import numpy as np


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def iter_images(folder: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            out.append(p)
    return out


class CaptionedImageDataset(Dataset):
    def __init__(self, images_dir: Path, captions_dir: Path, width: int, height: int, random_flip: bool):
        self.images = iter_images(images_dir)
        if not self.images:
            raise RuntimeError(f"No images found in {images_dir}")
        self.captions_dir = captions_dir
        self.width = width
        self.height = height
        self.random_flip = random_flip

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, idx: int):
        img_path = self.images[idx]
        cap_path = self.captions_dir / f"{img_path.stem}.txt"
        if not cap_path.exists():
            raise RuntimeError(f"Missing caption: {cap_path}")

        caption = cap_path.read_text(encoding="utf-8").strip()

        img = Image.open(img_path).convert("RGB")
        img = img.resize((self.width, self.height), Image.BICUBIC)
        if self.random_flip and torch.rand(1).item() < 0.5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)

        # [0,1] float32 CHW
        pixel_values = torch.from_numpy(np.array(img)).permute(2, 0, 1).to(dtype=torch.float32) / 255.0
        # [-1,1]
        pixel_values = pixel_values * 2.0 - 1.0

        return {"pixel_values": pixel_values, "caption": caption}


@dataclass
class Tier:
    width: int
    height: int
    batch_size: int
    grad_accum: int
    mixed_precision: str  # "no" | "fp16" | "bf16"
    gradient_checkpointing: bool


TIERS: dict[str, Tier] = {
    "24gb": Tier(width=1024, height=576, batch_size=1, grad_accum=1, mixed_precision="bf16", gradient_checkpointing=True),
    "16gb": Tier(width=960, height=540, batch_size=1, grad_accum=1, mixed_precision="fp16", gradient_checkpointing=True),
    "12gb": Tier(width=768, height=432, batch_size=1, grad_accum=1, mixed_precision="fp16", gradient_checkpointing=True),
    "8gb": Tier(width=640, height=360, batch_size=1, grad_accum=2, mixed_precision="fp16", gradient_checkpointing=True),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="datasets/thumbs")
    ap.add_argument("--output", default="outputs/lora/zthumb_lora")
    ap.add_argument("--base-model", default=None, help="HF model id or local path. Default: SDXL base on HF.")
    ap.add_argument("--tier", choices=sorted(TIERS.keys()), default="12gb")
    ap.add_argument("--steps", type=int, default=1500)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--random-flip", action="store_true")
    ap.add_argument("--save-every", type=int, default=500)
    args = ap.parse_args()

    torch.manual_seed(args.seed)

    tier = TIERS[args.tier]
    ds_root = Path(args.dataset)
    images_dir = ds_root / "images"
    captions_dir = ds_root / "captions"
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device != "cuda" and tier.mixed_precision in ("fp16", "bf16"):
        tier = Tier(**{**tier.__dict__, "mixed_precision": "no"})

    base_model = args.base_model
    if base_model is None:
        local = Path("models/sd_xl_base_1.0.safetensors")
        if local.exists():
            base_model = str(local)
        else:
            base_model = "stabilityai/stable-diffusion-xl-base-1.0"

    from diffusers import StableDiffusionXLPipeline, DDPMScheduler
    from diffusers.loaders import AttnProcsLayers
    from diffusers.models.attention_processor import LoRAAttnProcessor2_0

    dtype = torch.float32
    if tier.mixed_precision == "fp16":
        dtype = torch.float16
    elif tier.mixed_precision == "bf16":
        dtype = torch.bfloat16

    # Load pipeline
    if Path(str(base_model)).exists():
        pipe = StableDiffusionXLPipeline.from_single_file(str(base_model), torch_dtype=dtype, use_safetensors=True)
    else:
        pipe = StableDiffusionXLPipeline.from_pretrained(
            str(base_model),
            torch_dtype=dtype,
            use_safetensors=True,
            variant="fp16" if (device == "cuda" and dtype == torch.float16) else None,
        )

    pipe.to(device)
    pipe.scheduler = DDPMScheduler.from_config(pipe.scheduler.config)

    # Freeze base weights
    pipe.vae.requires_grad_(False)
    pipe.text_encoder.requires_grad_(False)
    pipe.text_encoder_2.requires_grad_(False)
    pipe.unet.requires_grad_(False)

    if tier.gradient_checkpointing:
        try:
            pipe.unet.enable_gradient_checkpointing()
        except Exception:
            pass

    # Inject LoRA into UNet attention processors
    lora_attn_procs = {}
    for name, proc in pipe.unet.attn_processors.items():
        cross_attention_dim = None if name.endswith("attn1.processor") else pipe.unet.config.cross_attention_dim
        if name.startswith("mid_block"):
            hidden_size = pipe.unet.config.block_out_channels[-1]
        elif name.startswith("up_blocks"):
            block_id = int(name.split(".")[1])
            hidden_size = list(reversed(pipe.unet.config.block_out_channels))[block_id]
        elif name.startswith("down_blocks"):
            block_id = int(name.split(".")[1])
            hidden_size = pipe.unet.config.block_out_channels[block_id]
        else:
            hidden_size = pipe.unet.config.block_out_channels[0]
        lora_attn_procs[name] = LoRAAttnProcessor2_0(
            hidden_size=hidden_size,
            cross_attention_dim=cross_attention_dim,
            rank=args.rank,
        )
    pipe.unet.set_attn_processor(lora_attn_procs)

    lora_layers = AttnProcsLayers(pipe.unet.attn_processors)
    lora_layers.to(device)

    optimizer = torch.optim.AdamW(lora_layers.parameters(), lr=args.lr)
    scaler = torch.cuda.amp.GradScaler(enabled=(device == "cuda" and tier.mixed_precision == "fp16"))

    dataset = CaptionedImageDataset(
        images_dir=images_dir,
        captions_dir=captions_dir,
        width=tier.width,
        height=tier.height,
        random_flip=args.random_flip,
    )
    dl = DataLoader(dataset, batch_size=tier.batch_size, shuffle=True, num_workers=2, drop_last=True)

    # Precompute some SDXL “time ids” conditioning values for 16:9 target
    def add_time_ids(batch: int):
        # original_size, crop coords, target_size
        original_size = (tier.height, tier.width)
        crop = (0, 0)
        target = (tier.height, tier.width)
        return pipe._get_add_time_ids(original_size, crop, target, dtype=dtype).to(device).repeat(batch, 1)

    noise_scheduler = pipe.scheduler

    log_path = out_dir / "train.log"
    loss_path = out_dir / "loss.jsonl"
    report_meta_path = out_dir / "training_meta.json"

    start = time.time()
    step = 0
    losses: list[float] = []

    pipe.unet.train()
    lora_layers.train()

    while step < args.steps:
        for batch in dl:
            if step >= args.steps:
                break

            pixel_values = batch["pixel_values"].to(device=device, dtype=dtype)
            captions = batch["caption"]

            with torch.no_grad():
                latents = pipe.vae.encode(pixel_values).latent_dist.sample()
                latents = latents * pipe.vae.config.scaling_factor

            noise = torch.randn_like(latents)
            bsz = latents.shape[0]
            timesteps = torch.randint(
                0, noise_scheduler.config.num_train_timesteps, (bsz,), device=device
            ).long()
            noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)

            # Encode text
            enc = pipe.encode_prompt(
                captions,
                device=device,
                num_images_per_prompt=1,
                do_classifier_free_guidance=False,
            )
            if isinstance(enc, tuple) and len(enc) == 4:
                prompt_embeds, _, pooled_prompt_embeds, _ = enc
            elif isinstance(enc, tuple) and len(enc) == 2:
                prompt_embeds, pooled_prompt_embeds = enc
            else:
                raise RuntimeError(f"Unexpected encode_prompt return type/shape: {type(enc)}")
            time_ids = add_time_ids(bsz)

            with torch.cuda.amp.autocast(enabled=(device == "cuda" and tier.mixed_precision in ("fp16", "bf16")), dtype=dtype):
                model_pred = pipe.unet(
                    noisy_latents,
                    timesteps,
                    encoder_hidden_states=prompt_embeds,
                    added_cond_kwargs={"text_embeds": pooled_prompt_embeds, "time_ids": time_ids},
                ).sample
                loss = torch.nn.functional.mse_loss(model_pred.float(), noise.float(), reduction="mean")

            loss_val = float(loss.detach().cpu().item())
            losses.append(loss_val)

            loss = loss / tier.grad_accum
            if scaler.is_enabled():
                scaler.scale(loss).backward()
            else:
                loss.backward()

            if (step + 1) % tier.grad_accum == 0:
                if scaler.is_enabled():
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    optimizer.step()
                optimizer.zero_grad(set_to_none=True)

            if step % 25 == 0:
                msg = f"step={step} loss={loss_val:.6f}"
                print(msg)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
                with open(loss_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"step": step, "loss": loss_val}) + "\n")

            if args.save_every and step > 0 and step % args.save_every == 0:
                ckpt = out_dir / f"checkpoint-{step}"
                ckpt.mkdir(parents=True, exist_ok=True)
                pipe.save_lora_weights(save_directory=str(ckpt), unet_lora_layers=lora_layers)

            step += 1

    # Save final adapter
    pipe.save_lora_weights(save_directory=str(out_dir), unet_lora_layers=lora_layers)

    meta = {
        "base_model": base_model,
        "tier": args.tier,
        "width": tier.width,
        "height": tier.height,
        "rank": args.rank,
        "lr": args.lr,
        "steps": args.steps,
        "mixed_precision": tier.mixed_precision,
        "device": device,
        "time_seconds": time.time() - start,
        "loss_last": losses[-1] if losses else None,
    }
    report_meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("OK: training complete")
    print(f"LoRA adapter saved to: {out_dir}")


if __name__ == "__main__":
    main()
