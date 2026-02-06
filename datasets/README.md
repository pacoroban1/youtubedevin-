# Datasets

This repo supports LoRA fine-tuning for recap thumbnail style via `training/`.

## Dataset Layout (Thumbs)

Manual curated mode (MODE A):

- `datasets/thumbs/images/`
  - PNG/JPG/WebP images
  - Recommended: 1280x720 (or larger, same aspect)
- `datasets/thumbs/captions/`
  - One `.txt` per image, same basename
  - Example:
    - `datasets/thumbs/images/000123.png`
    - `datasets/thumbs/captions/000123.txt`
- `datasets/thumbs/masks/` (optional)
  - Same basename mask images if you want subject-area masks

Auto-bootstrap mode (MODE B):

- Import your historic winners into any folder
- Run `training/prepare_dataset.py --mode bootstrap --import-dir <folder>`
- The script copies images into `datasets/thumbs/images/` and generates editable captions into `datasets/thumbs/captions/`.

## Caption Format (Required)

Captions MUST include:

- A style preset tag:
  - `[alien_reveal]` or `[doorway_silhouette]` or `[split_transformation]`
- Subject + composition + quality tags

Example caption:

```text
[alien_reveal] subject: alien creature close-up; composition: centered subject, rim light, high contrast, minimal empty area for text; quality: cinematic, sharp focus, clean, no watermark, no extra limbs
```

## Notes

- Avoid celebrity/real-person identity prompts. This fine-tune is for style/composition only.
- Keep images consistent with your target output: high-contrast, mobile-readable, single clear subject.

