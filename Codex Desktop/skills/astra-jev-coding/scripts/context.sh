#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd -P)
root=$(CDPATH= cd -P -- "$script_dir/../../../.." && pwd -P)
if [ ! -x "$root/bin/astra-jev" ]; then
  printf '%s\n' 'Native Harness binary missing. Build once with scripts/build-native.sh; normal coding does not compile.' >&2
  exit 1
fi
case "${1-}" in
  select|check|read) set -- "$@" --require-jev ;;
esac
exec "$root/bin/astra-jev" --harness-root "$root" desktop "$@"
