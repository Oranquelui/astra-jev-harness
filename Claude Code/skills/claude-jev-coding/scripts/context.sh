#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd -P)
root=$(CDPATH= cd -P -- "$script_dir/../../../.." && pwd -P)
if [ ! -x "$root/bin/astra-jev" ]; then
  printf '%s\n' 'Native Harness binary missing. Build once with scripts/build-native.sh.' >&2
  exit 1
fi
exec "$root/bin/astra-jev" --harness-root "$root" claude-code "$@"
