#!/usr/bin/env python3
"""CLI entrypoint with optional Keychain credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared.credentials import execution_environment




def main():
    args = sys.argv[1:]
    if args == ['doctor']:
        env, source = execution_environment()
        print(json.dumps({'harness_root': str(ROOT), 'entrypoint_exists': (ROOT / 'cli/coding.py').is_file(),
                          'typesafe_key_present': bool(env.get('TYPESAFE_API_KEY')), 'key_source': source}))
        return 0 if env.get('TYPESAFE_API_KEY') else 1
    # Local inspection, help, re-verification, and apply do not need to unlock the Keychain.
    env = os.environ.copy()
    if args and args[0] == 'run' and not any(a in ('-h', '--help') for a in args):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--mode', default='auto')
        options, _ = parser.parse_known_args(args[1:])
        if options.mode != 'astra':
            env, _ = execution_environment()
    os.execve(sys.executable, [sys.executable, str(ROOT / 'cli/coding.py'), *args], env)


if __name__ == '__main__':
    raise SystemExit(main())
