"""Load a scoped process environment without printing or persisting credential values."""
import os
import subprocess
import sys


def execution_environment():
    env = os.environ.copy()
    if env.get('TYPESAFE_API_KEY'):
        return env, 'environment'
    if sys.platform == 'darwin':
        try:
            result = subprocess.run(
                ['/usr/bin/security', 'find-generic-password', '-s', 'astra-jev-harness', '-a', 'TYPESAFE_API_KEY', '-w'],
                capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and result.stdout.strip():
                env['TYPESAFE_API_KEY'] = result.stdout.strip()
                return env, 'keychain'
            if result.returncode != 44:
                return env, 'keychain_unavailable'
        except subprocess.TimeoutExpired:
            return env, 'keychain_timeout'
        except OSError:
            return env, 'keychain_unavailable'
    return env, 'absent'
