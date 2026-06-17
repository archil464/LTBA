#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 output.zip"
  exit 2
fi

OUT="$1"

if command -v git >/dev/null 2>&1; then
  echo "Creating review zip using git archive -> $OUT"
  git archive --format=zip --output="$OUT" HEAD
  echo "Done. $OUT created (git archive)"
  exit 0
fi

echo "git not available; creating zip via find (excluding .git and caches) -> $OUT"
TMPDIR=$(mktemp -d)
cd "$(dirname "$0")/.." || exit 2

# Build list of exclusions
EXCLUDES=(".git" "__pycache__" ".pytest_cache" "build" "dist" "*.egg-info")

ZIPLIST="$TMPDIR/files.lst"
find . -path ./\.git -prune -o -path ./__pycache__ -prune -o -path ./\.pytest_cache -prune -o -path ./build -prune -o -path ./dist -prune -o -name "*.egg-info" -prune -o -type f -print > "$ZIPLIST"

zip -@ "$OUT" < "$ZIPLIST"
rm -rf "$TMPDIR"
echo "Done. $OUT created (find+zip)"
