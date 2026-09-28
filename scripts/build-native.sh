#!/bin/sh
# Build once; normal coding never compiles or downloads a runtime.
set -eu
root=$(CDPATH= cd -P -- "$(dirname -- "$0")/.." && pwd -P)
cd "$root"
mkdir -p bin
version=$(cat VERSION)
revision=$(git rev-parse HEAD)
"${GO:-go}" build -trimpath -ldflags "-X github.com/Oranquelui/astra-jev-harness/internal/harness.Version=$version -X github.com/Oranquelui/astra-jev-harness/internal/harness.Revision=$revision" -o bin/astra-jev ./cmd/astra-jev
