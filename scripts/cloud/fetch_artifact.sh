#!/usr/bin/env bash
set -euo pipefail

# Fetch a packaged LoRA artifact (created by scripts/cloud/runpod_train.sh)
# and extract it into ./models/lora on your local machine.
#
# Required env:
#   RUN_NAME=...                          # name used during finetune
#   FETCH_METHOD=rclone|gsutil|scp
#   RCLONE_SRC=remote:bucket/path         # if rclone (folder containing <RUN_NAME>.tar.gz)
#   GSUTIL_SRC=gs://bucket/path           # if gsutil (folder containing <RUN_NAME>.tar.gz)
#   SCP_SRC=user@host:/path               # if scp (folder containing <RUN_NAME>.tar.gz)
#
# Optional env:
#   DEST_DIR=models/lora                  # default

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RUN_NAME="${RUN_NAME:-}"
FETCH_METHOD="${FETCH_METHOD:-}"
RCLONE_SRC="${RCLONE_SRC:-}"
GSUTIL_SRC="${GSUTIL_SRC:-}"
SCP_SRC="${SCP_SRC:-}"
DEST_DIR="${DEST_DIR:-models/lora}"

if [ -z "$RUN_NAME" ]; then
  echo "ERROR: missing RUN_NAME" >&2
  exit 2
fi
if [ -z "$FETCH_METHOD" ]; then
  echo "ERROR: missing FETCH_METHOD=rclone|gsutil|scp" >&2
  exit 2
fi

mkdir -p "$DEST_DIR" "outputs/finetune_z/downloads"
TARBALL_LOCAL="outputs/finetune_z/downloads/${RUN_NAME}.tar.gz"

case "$FETCH_METHOD" in
  rclone)
    if [ -z "$RCLONE_SRC" ]; then
      echo "ERROR: FETCH_METHOD=rclone requires RCLONE_SRC" >&2
      exit 2
    fi
    if ! command -v rclone >/dev/null 2>&1; then
      echo "ERROR: rclone not found." >&2
      exit 2
    fi
    echo "[fetch] rclone copy $RCLONE_SRC/${RUN_NAME}.tar.gz -> $TARBALL_LOCAL"
    rclone copy "$RCLONE_SRC" "outputs/finetune_z/downloads" --include "${RUN_NAME}.tar.gz"
    ;;
  gsutil)
    if [ -z "$GSUTIL_SRC" ]; then
      echo "ERROR: FETCH_METHOD=gsutil requires GSUTIL_SRC" >&2
      exit 2
    fi
    if ! command -v gsutil >/dev/null 2>&1; then
      echo "ERROR: gsutil not found." >&2
      exit 2
    fi
    echo "[fetch] gsutil cp $GSUTIL_SRC/${RUN_NAME}.tar.gz -> $TARBALL_LOCAL"
    gsutil cp "$GSUTIL_SRC/${RUN_NAME}.tar.gz" "$TARBALL_LOCAL"
    ;;
  scp)
    if [ -z "$SCP_SRC" ]; then
      echo "ERROR: FETCH_METHOD=scp requires SCP_SRC" >&2
      exit 2
    fi
    if ! command -v scp >/dev/null 2>&1; then
      echo "ERROR: scp not found." >&2
      exit 2
    fi
    echo "[fetch] scp $SCP_SRC/${RUN_NAME}.tar.gz -> $TARBALL_LOCAL"
    scp "$SCP_SRC/${RUN_NAME}.tar.gz" "$TARBALL_LOCAL"
    ;;
  *)
    echo "ERROR: unknown FETCH_METHOD=$FETCH_METHOD (use rclone|gsutil|scp)" >&2
    exit 2
    ;;
esac

if [ ! -f "$TARBALL_LOCAL" ]; then
  echo "ERROR: expected tarball not found: $TARBALL_LOCAL" >&2
  exit 2
fi

echo "[fetch] extracting -> $DEST_DIR"
tar -xzf "$TARBALL_LOCAL" -C "$DEST_DIR"

echo ""
echo "OK: extracted LoRA adapter to $DEST_DIR/$RUN_NAME"
echo "Use with ZThumb:"
echo "  export Z_LORA_PATH=/models/lora/$RUN_NAME"
echo "  export Z_LORA_SCALE=0.8"
