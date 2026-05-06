#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALUES_FILE="$ROOT_DIR/infra/gitops/environments/prod/values.yaml"
RENDER_FILE="${RENDER_FILE:-/tmp/biowatch-prod-render.yaml}"
IMAGE_REPOSITORY="ghcr.io/mbaimuratov/biowatch"

cd "$ROOT_DIR"

tag="$(python3 - <<'PY'
from pathlib import Path
import re

text = Path("infra/gitops/environments/prod/values.yaml").read_text()
match = re.search(r"(?m)^  tag: ([0-9a-f]{40})$", text)
if not match:
    raise SystemExit("prod image.tag must be a full 40-character commit SHA")
print(match.group(1))
PY
)"

docker buildx imagetools inspect "$IMAGE_REPOSITORY:$tag" > /tmp/biowatch-prod-image.txt
grep -q "Platform:    linux/amd64" /tmp/biowatch-prod-image.txt
grep -q "Platform:    linux/arm64" /tmp/biowatch-prod-image.txt

helm template biowatch infra/helm/biowatch \
  --namespace biowatch-prod \
  -f "$VALUES_FILE" \
  > "$RENDER_FILE"

scripts/validate-helm-serviceaccounts.sh "$RENDER_FILE"

expected="image: \"$IMAGE_REPOSITORY:$tag\""
rendered_images="$(grep -Eo 'image: "ghcr\.io/mbaimuratov/biowatch:[^"]+"' "$RENDER_FILE" || true)"
unexpected_images="$(printf '%s\n' "$rendered_images" | grep -vFx "$expected" || true)"
if [ -n "$unexpected_images" ]; then
  echo "rendered prod manifests contain an unexpected BioWatch image tag" >&2
  printf '%s\n' "$unexpected_images" >&2
  exit 1
fi

image_count="$(printf '%s\n' "$rendered_images" | grep -cFx "$expected" || true)"
if [ "$image_count" -lt 6 ]; then
  echo "expected every BioWatch workload to render the promoted image tag" >&2
  exit 1
fi
