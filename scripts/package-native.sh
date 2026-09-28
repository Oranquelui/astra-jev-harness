#!/bin/sh
# Package an already-tested binary; artifacts must be outside the checkout.
set -eu
root=$(CDPATH= cd -P -- "$(dirname -- "$0")/.." && pwd -P)
cd "$root"
if [ "$#" -ne 2 ]; then
  printf '%s\n' 'Usage: scripts/package-native.sh <outside-output-dir> <os-arch>' >&2
  exit 2
fi
out=$1
platform=$2
case "$platform" in darwin-arm64|darwin-amd64|linux-amd64|linux-arm64) ;; *) exit 2 ;; esac
mkdir -p "$out"
out=$(CDPATH= cd -P -- "$out" && pwd -P)
case "$out/" in "$root/"*) printf '%s\n' 'Use an external artifact directory' >&2; exit 2 ;; esac
actual_platform=$(bin/astra-jev platform)
if [ "$actual_platform" != "$platform" ]; then
  printf '%s\n' "Binary platform mismatch: $actual_platform" >&2
  exit 2
fi
version=$(cat VERSION)
name="astra-jev-$version-$platform"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
mkdir -p "$stage/$name/bin" "$stage/$name/Codex Desktop/skills" "$stage/$name/Claude Code/skills"
cp bin/astra-jev "$stage/$name/bin/"
cp -R 'Codex Desktop/skills/astra-jev-coding' "$stage/$name/Codex Desktop/skills/"
cp -R 'Claude Code/skills/claude-jev-coding' "$stage/$name/Claude Code/skills/"
# These are migration references, never shipped as runtime dependencies.
find "$stage" -type f -name '*.py' -delete
find "$stage" -type d -name '__pycache__' -prune -exec rm -rf {} +
cp -R docs licenses "$stage/$name/"
cp README.md README-ja.md LICENSE VERSION CHANGELOG.md "$stage/$name/"
cp 'Codex Desktop/README.md' "$stage/$name/Codex Desktop/"
cp 'Claude Code/README.md' 'Claude Code/README-ja.md' "$stage/$name/Claude Code/"
tar -czf "$out/$name.tar.gz" -C "$stage" "$name"
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$out" && sha256sum "$name.tar.gz" > "$name.sha256")
else
  (cd "$out" && shasum -a 256 "$name.tar.gz" > "$name.sha256")
fi
printf '%s\n' "$out/$name.tar.gz"
