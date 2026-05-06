#!/usr/bin/env bash
set -euo pipefail

rendered_manifest="${1:-}"
if [[ -z "$rendered_manifest" ]]; then
  echo "Usage: $0 <rendered-helm-manifest.yaml>"
  exit 2
fi

if [[ ! -f "$rendered_manifest" ]]; then
  echo "Rendered manifest not found: $rendered_manifest"
  exit 2
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

service_accounts_file="$tmp_dir/serviceaccounts.txt"
references_file="$tmp_dir/references.txt"

awk '
  /^kind: ServiceAccount$/ {
    in_service_account = 1
    in_metadata = 0
    next
  }
  in_service_account && /^metadata:$/ {
    in_metadata = 1
    next
  }
  in_service_account && in_metadata && /^  name:/ {
    print $2
    in_service_account = 0
    in_metadata = 0
  }
' "$rendered_manifest" | sort -u >"$service_accounts_file"

awk '
  /serviceAccountName:/ {
    print $2
  }
' "$rendered_manifest" | sort -u >"$references_file"

missing="$(comm -13 "$service_accounts_file" "$references_file")"
if [[ -n "$missing" ]]; then
  echo "Missing ServiceAccount manifests for serviceAccountName references:"
  echo "$missing"
  exit 1
fi

echo "All rendered serviceAccountName references have matching ServiceAccount manifests."
