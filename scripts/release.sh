#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TAG="${TAG:-${1:-}}"

if [[ -z "${TAG}" ]]; then
  echo "ERROR: TAG is required (example: TAG=v1.0.0 make release)" >&2
  exit 2
fi

if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  echo "ERROR: tag already exists: ${TAG}" >&2
  exit 1
fi

# Release gate: require a full pipeline run when tagging a release.
REQUIRE_PIPELINE=1 bash scripts/gate_local.sh

if ! git diff --quiet; then
  echo "ERROR: working tree has unstaged changes (commit/stash before release):" >&2
  git status --porcelain=v1 >&2
  exit 1
fi

if [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
  echo "ERROR: untracked files present (commit/stash before release):" >&2
  git status --porcelain=v1 >&2
  exit 1
fi

if ! git diff --cached --quiet; then
  git commit -m "chore(release): ${TAG}"
fi

if [[ -n "$(git status --porcelain=v1)" ]]; then
  echo "ERROR: working tree must be clean to tag a release:" >&2
  git status --porcelain=v1 >&2
  exit 1
fi

git tag -a "${TAG}" -m "${TAG}"

# Push the commit (if any) and the tag.
git push origin HEAD
git push origin "${TAG}"

echo "ok: released ${TAG}"

