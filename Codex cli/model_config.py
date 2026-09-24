"""Read model settings through Codex's config parser without starting a model turn.

Only the two allowlisted settings leave this module. Raw configuration, which may
contain credentials or MCP definitions, is never printed or written to artifacts.
"""
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time

from shared.jev import ProtocolError
from cli.benchmark import RUNTIME_ARGS


def model_settings(config):
    if not isinstance(config, dict):
        raise ProtocolError('Codex configuration response is invalid')
    # The generator uses the existing first-party login, not custom provider auth.
    if config.get('model_provider') not in (None, 'openai'):
        raise ProtocolError('Custom Codex model providers are not supported by this harness')
    if config.get('profile'):
        raise ProtocolError('Codex profile selection is not supported; use base model settings')
    model, effort = config.get('model'), config.get('model_reasoning_effort')
    if model is not None and (not isinstance(model, str) or
                             not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}', model)):
        raise ProtocolError('Invalid configured Codex model identifier')
    if effort not in (None, 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'):
        raise ProtocolError('Invalid configured Codex reasoning effort')
    return {'model': model, 'reasoning': effort}


def model_arguments(settings):
    argv = []
    if settings['model'] is not None:
        argv += ['--model', settings['model']]
    if settings['reasoning'] is not None:
        argv += ['-c', 'model_reasoning_effort=' + json.dumps(settings['reasoning'])]
    return argv


def read_model_settings(repo, timeout=15):
    """Resolve user/trusted-project config with the installed CLI; fail closed."""
    env = os.environ.copy()
    for key in ('TYPESAFE_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY'):
        env.pop(key, None)
    messages = queue.Queue(maxsize=64)
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryDirectory(prefix='codex-config-') as cwd:
        try:
            process = subprocess.Popen(['codex', 'app-server', '--stdio', *RUNTIME_ARGS],
                                       cwd=cwd, env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       text=True, encoding='utf-8')
        except OSError:
            raise ProtocolError('Cannot start Codex configuration reader') from None

        def receive():
            try:
                while True:
                    line = process.stdout.readline(2_000_001)
                    if not line or len(line) > 2_000_000:
                        messages.put_nowait(None)
                        return
                    messages.put_nowait(json.loads(line))
            except (OSError, ValueError, queue.Full):
                try:
                    messages.put_nowait(None)
                except queue.Full:
                    pass

        reader = threading.Thread(target=receive, daemon=True)
        reader.start()

        def send(value):
            process.stdin.write(json.dumps(value) + '\n')
            process.stdin.flush()

        def response(request_id):
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProtocolError('Codex configuration read timed out; no model call made')
                try:
                    value = messages.get(timeout=remaining)
                except queue.Empty:
                    raise ProtocolError('Codex configuration read timed out; no model call made') from None
                if not isinstance(value, dict):
                    raise ProtocolError('Codex configuration reader returned invalid output')
                if value.get('id') == request_id:
                    if 'error' in value or not isinstance(value.get('result'), dict):
                        raise ProtocolError('Codex configuration read failed; no model call made')
                    return value['result']

        try:
            send({'id': 1, 'method': 'initialize', 'params': {
                'clientInfo': {'name': 'astra_jev_config', 'version': '1'}}})
            response(1)
            send({'method': 'initialized', 'params': {}})
            send({'id': 2, 'method': 'config/read', 'params': {
                'includeLayers': False, 'cwd': str(Path(repo).resolve())}})
            return model_settings(response(2).get('config'))
        except ProtocolError:
            raise
        except (OSError, ValueError):
            raise ProtocolError('Codex configuration read failed; no model call made') from None
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            reader.join(timeout=2)
            process.stdin.close()
            process.stdout.close()
