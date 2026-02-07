#!/usr/bin/env python3
"""
Evaluate a ZThumb LoRA by generating before/after images *through the ZThumb API*.

This is intentionally "end-to-end": it validates that ZThumb can load and apply
the adapter (lora_path + lora_scale) and that outputs improve on simple
thumbnail heuristics.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import json
import math
import os
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import urllib.request


# Keep prompts aligned with thumbnail goals: single subject, high contrast, mobile readability.
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _utc_now_slug() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")


def _json_loads_bytes(b: bytes) -> dict:
    txt = b.decode("utf-8", errors="replace")
    return json.loads(txt) if txt.strip() else {}


def _post_json(url: str, payload: dict, timeout_s: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
    return _json_loads_bytes(body)


def _get_json(url: str, timeout_s: float) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read()
    return _json_loads_bytes(body)


def _host_path_from_zthumb_uri(root_dir: Path, uri: str) -> Path:
    # ZThumb returns `file:///outputs/...` paths (container paths). Host has ./outputs mounted to /outputs.
    p = uri.replace("file://", "")
    if p.startswith("/outputs/"):
        return root_dir / "outputs" / p[len("/outputs/") :]
    return Path(p)


def _parse_style_tag(prompt: str) -> Tuple[Optional[str], str]:
    s = prompt.strip()
    if s.startswith("[") and "]" in s:
        tag = s[1 : s.index("]")]
        rest = s[s.index("]") + 1 :].strip()
        if tag in ("alien_reveal", "doorway_silhouette", "split_transformation"):
            return tag, rest
    return None, prompt


def _require_pillow() -> Any:
    try:
        from PIL import Image, ImageFilter  # type: ignore

        return Image, ImageFilter
    except Exception as e:
        raise SystemExit(
            "ERROR: Pillow is required for scoring/report images.\n"
            "Install it (in your current python): pip install Pillow\n"
            f"Details: {e}"
        )


@dataclasses.dataclass
class Metrics:
    contrast: float
    edge_density: float
    center_edge_density: float
    subject_clarity: float


def _img_metrics(path: Path) -> Metrics:
    Image, ImageFilter = _require_pillow()

    img = Image.open(path).convert("L")
    w, h = img.size
    px = list(img.getdata())
    n = max(1, len(px))
    mean = sum(px) / n
    mean_sq = sum((v - mean) ** 2 for v in px) / n
    contrast = math.sqrt(mean_sq) / 255.0

    edges = img.filter(ImageFilter.FIND_EDGES)
    epx = list(edges.getdata())
    edge_density = (sum(epx) / max(1, len(epx))) / 255.0

    # Center crop: captures "single subject" readability heuristically.
    cx0 = int(w * 0.25)
    cx1 = int(w * 0.75)
    cy0 = int(h * 0.20)
    cy1 = int(h * 0.80)
    center = edges.crop((cx0, cy0, cx1, cy1))
    cpx = list(center.getdata())
    center_edge_density = (sum(cpx) / max(1, len(cpx))) / 255.0

    # Ratio > 1 tends to indicate more structure in the center vs the whole frame.
    subject_clarity = center_edge_density / (edge_density + 1e-6)

    return Metrics(
        contrast=float(contrast),
        edge_density=float(edge_density),
        center_edge_density=float(center_edge_density),
        subject_clarity=float(subject_clarity),
    )


def _side_by_side(before: Path, after: Path, out_path: Path) -> None:
    Image, _ = _require_pillow()
    b = Image.open(before).convert("RGB")
    a = Image.open(after).convert("RGB")
    if b.size != a.size:
        a = a.resize(b.size)
    w, h = b.size
    canvas = Image.new("RGB", (w * 2, h), color=(0, 0, 0))
    canvas.paste(b, (0, 0))
    canvas.paste(a, (w, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def _grid(images: List[Path], cols: int, out_path: Path) -> None:
    Image, _ = _require_pillow()
    if not images:
        return
    ims = [Image.open(p).convert("RGB") for p in images]
    w, h = ims[0].size
    rows = int(math.ceil(len(ims) / float(cols)))
    canvas = Image.new("RGB", (cols * w, rows * h), color=(0, 0, 0))
    for i, im in enumerate(ims):
        x = (i % cols) * w
        y = (i // cols) * h
        canvas.paste(im, (x, y))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zthumb-url", default=os.getenv("ZTHUMB_URL", "http://localhost:8100").rstrip("/"))
    ap.add_argument("--lora-path", default=None, help="LoRA path inside the ZThumb container (e.g. /models/lora/my_lora)")
    ap.add_argument("--lora-scale", type=float, default=0.8, help="After scale (before is always 0)")
    ap.add_argument("--variant", default="full", help="ZThumb variant: full|turbo|gguf|auto")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--steps", type=int, default=35)
    ap.add_argument("--cfg", type=float, default=4.5)
    ap.add_argument("--seeds", default="111,222")
    ap.add_argument("--prompts", default=None, help="Optional path to a text file with one prompt per line.")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--out", default=None, help="Output directory (default outputs/lora_eval/<utc>)")
    args = ap.parse_args()

    root = _repo_root()
    out_dir = Path(args.out) if args.out else (root / "outputs" / "lora_eval" / _utc_now_slug())
    out_dir.mkdir(parents=True, exist_ok=True)
    before_dir = out_dir / "before"
    after_dir = out_dir / "after"
    pairs_dir = out_dir / "pairs"
    before_dir.mkdir(parents=True, exist_ok=True)
    after_dir.mkdir(parents=True, exist_ok=True)
    pairs_dir.mkdir(parents=True, exist_ok=True)

    lora_path = args.lora_path or os.getenv("Z_LORA_PATH") or os.getenv("ZTHUMB_LORA_PATH")
    if not lora_path:
        raise SystemExit("ERROR: missing --lora-path (or Z_LORA_PATH/ZTHUMB_LORA_PATH env var)")

    seeds = [int(s.strip()) for s in str(args.seeds).split(",") if s.strip()]
    if not seeds:
        raise SystemExit("ERROR: no seeds provided")

    prompts: List[str]
    if args.prompts:
        p = Path(args.prompts)
        if not p.exists():
            raise SystemExit(f"ERROR: prompts file not found: {p}")
        prompts = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    else:
        prompts = list(DEFAULT_PROMPTS)

    # Pre-flight: confirm server is up and show model status.
    health = _get_json(f"{args.zthumb_url}/health", timeout_s=min(args.timeout, 20.0))
    models = _get_json(f"{args.zthumb_url}/models", timeout_s=min(args.timeout, 20.0))

    results: List[Dict[str, Any]] = []
    pair_images: List[Path] = []
    warnings_accum: List[str] = []

    for prompt_i, raw_prompt in enumerate(prompts):
        style_tag, prompt = _parse_style_tag(raw_prompt)
        for seed in seeds:
            base_payload: Dict[str, Any] = {
                "prompt": prompt,
                "negative_prompt": "text, watermark, logo, blurry, low quality, cartoon, anime, deformed hands",
                "width": int(args.width),
                "height": int(args.height),
                "seed": int(seed),
                "steps": int(args.steps),
                "cfg": float(args.cfg),
                "batch": 1,
                "variant": str(args.variant),
                "safe_mode": True,
                # Force LoRA path so "before" uses scale=0 with adapter loaded.
                "lora_path": str(lora_path),
            }
            if style_tag:
                base_payload["style_preset"] = style_tag

            before_payload = dict(base_payload)
            before_payload["lora_scale"] = 0.0
            after_payload = dict(base_payload)
            after_payload["lora_scale"] = float(args.lora_scale)

            before_resp = _post_json(f"{args.zthumb_url}/generate", before_payload, timeout_s=float(args.timeout))
            after_resp = _post_json(f"{args.zthumb_url}/generate", after_payload, timeout_s=float(args.timeout))

            for w in (before_resp.get("warnings") or []):
                warnings_accum.append(str(w))
            for w in (after_resp.get("warnings") or []):
                warnings_accum.append(str(w))

            before_imgs = before_resp.get("images") or []
            after_imgs = after_resp.get("images") or []
            if not before_imgs or not after_imgs:
                raise SystemExit(
                    "ERROR: ZThumb returned no images.\n"
                    f"before.warnings={before_resp.get('warnings')}\n"
                    f"after.warnings={after_resp.get('warnings')}\n"
                    f"backend={before_resp.get('meta', {}).get('backend')}"
                )

            before_host = _host_path_from_zthumb_uri(root, before_imgs[0])
            after_host = _host_path_from_zthumb_uri(root, after_imgs[0])
            if not before_host.exists():
                raise SystemExit(f"ERROR: missing generated file on host: {before_host}")
            if not after_host.exists():
                raise SystemExit(f"ERROR: missing generated file on host: {after_host}")

            before_dst = before_dir / f"p{prompt_i:02d}_s{seed}_before.png"
            after_dst = after_dir / f"p{prompt_i:02d}_s{seed}_after.png"
            shutil.copy2(before_host, before_dst)
            shutil.copy2(after_host, after_dst)

            pair_dst = pairs_dir / f"p{prompt_i:02d}_s{seed}_pair.png"
            _side_by_side(before_dst, after_dst, pair_dst)
            pair_images.append(pair_dst)

            bm = _img_metrics(before_dst)
            am = _img_metrics(after_dst)
            results.append(
                {
                    "prompt_raw": raw_prompt,
                    "prompt": prompt,
                    "style_preset": style_tag,
                    "seed": seed,
                    "before": {**dataclasses.asdict(bm), "path": str(before_dst)},
                    "after": {**dataclasses.asdict(am), "path": str(after_dst)},
                }
            )

    # Output artifacts
    (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    if pair_images:
        _grid(pair_images[:12], cols=2, out_path=out_dir / "pairs_grid.png")

    # Summary stats
    def avg(path: str, which: str) -> float:
        vals = [float(r[which][path]) for r in results]
        return sum(vals) / max(1, len(vals))

    summary = {
        "count": len(results),
        "before": {
            "contrast_avg": avg("contrast", "before"),
            "edge_density_avg": avg("edge_density", "before"),
            "center_edge_density_avg": avg("center_edge_density", "before"),
            "subject_clarity_avg": avg("subject_clarity", "before"),
        },
        "after": {
            "contrast_avg": avg("contrast", "after"),
            "edge_density_avg": avg("edge_density", "after"),
            "center_edge_density_avg": avg("center_edge_density", "after"),
            "subject_clarity_avg": avg("subject_clarity", "after"),
        },
    }
    summary["delta"] = {
        k: summary["after"][k] - summary["before"][k] for k in summary["before"].keys()
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Report markdown
    report_path = out_dir / "report.md"
    now = _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    wuniq = []
    seen = set()
    for w in warnings_accum:
        if w not in seen:
            wuniq.append(w)
            seen.add(w)

    lines = []
    lines.append("# LoRA Eval Report (ZThumb API)\n\n")
    lines.append("## Run Info\n\n")
    lines.append(f"- Timestamp (UTC): `{now}`\n")
    lines.append(f"- ZThumb URL: `{args.zthumb_url}`\n")
    lines.append(f"- Variant: `{args.variant}`\n")
    lines.append(f"- LoRA path: `{lora_path}`\n")
    lines.append(f"- Scales: before=`0.0` after=`{float(args.lora_scale)}`\n")
    lines.append(f"- Output dir: `{out_dir}`\n")
    lines.append("\n")
    lines.append("## Server State\n\n")
    lines.append(f"- /health: `{json.dumps(health)}`\n")
    lines.append(f"- /models: `{json.dumps(models)}`\n")
    lines.append("\n")

    lines.append("## Heuristic Summary\n\n")
    for k in summary["before"].keys():
        b = summary["before"][k]
        a = summary["after"][k]
        d = summary["delta"][k]
        lines.append(f"- `{k}`: before={b:.4f} after={a:.4f} delta={d:+.4f}\n")
    lines.append("\n")
    lines.append("## Side-by-Side Visuals\n\n")
    if (out_dir / "pairs_grid.png").exists():
        lines.append(f"- Grid (first 12 pairs): `{out_dir / 'pairs_grid.png'}`\n")
    lines.append(f"- Pairs dir: `{pairs_dir}`\n")
    lines.append("\n")

    if wuniq:
        lines.append("## Warnings\n\n")
        for w in wuniq[:40]:
            lines.append(f"- {w}\n")
        lines.append("\n")

    lines.append("## Per-Prompt Metrics\n\n")
    lines.append("| i | seed | style | contrast Δ | edge Δ | clarity Δ | pair |\n")
    lines.append("|---:|---:|---|---:|---:|---:|---|\n")
    for i, r in enumerate(results):
        b = r["before"]
        a = r["after"]
        d_con = float(a["contrast"]) - float(b["contrast"])
        d_edge = float(a["edge_density"]) - float(b["edge_density"])
        d_cla = float(a["subject_clarity"]) - float(b["subject_clarity"])
        pair = pairs_dir / f"p{i // len(seeds):02d}_s{r['seed']}_pair.png"
        lines.append(
            f"| {i} | {r['seed']} | {r.get('style_preset') or ''} | {d_con:+.4f} | {d_edge:+.4f} | {d_cla:+.4f} | `{pair}` |\n"
        )
    lines.append("\n")
    lines.append("## Notes\n\n")
    lines.append(
        textwrap.dedent(
            """\
            - These scores are simple heuristics (contrast + edge-based "subject clarity").
              Use the side-by-side images as the real truth.
            - If you see no difference, confirm:
              1) `lora_path` exists inside the ZThumb container, and
              2) ZThumb is using the expected base model variant (usually `full` for SDXL base).
            """
        )
    )
    report_path.write_text("".join(lines), encoding="utf-8")

    print("OK: wrote report:", report_path)
    print("OK: output dir:", out_dir)


if __name__ == "__main__":
    main()

