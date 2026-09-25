#!/usr/bin/env python3
"""Run one explicit noninteractive command with optional Jev progress-log selection."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys

from shared.evidence import require_external
from shared.jev import ProtocolError
from shared.tool_output import MAX_OUTPUT_BYTES, select_output, sensitive, validate_options


def run(command, task, out, *, keep=(), max_calls=2, mode='auto'):
    # Validate everything before executing a potentially side-effecting command.
    validate_options(task, keep, max_calls)
    if not command or mode not in ('auto', 'jev', 'local'):
        raise ProtocolError('Expected a command and valid selection mode')
    require_external(out)
    if Path(out).exists():
        raise ProtocolError('Use a new output directory')
    env = os.environ.copy()
    env.pop('TYPESAFE_API_KEY', None)
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=None, env=env, start_new_session=True)
    interrupted = []
    previous = {}
    def forward(signum, _frame):
        interrupted.append(signum)
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass
    buffer = bytearray()
    streamed = False
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, forward)
        while True:
            data = child.stdout.read1(65536)
            if not data:
                break
            if streamed:
                sys.stdout.buffer.write(data)
            elif len(buffer) + len(data) > MAX_OUTPUT_BYTES:
                sys.stdout.buffer.write(buffer)
                sys.stdout.buffer.write(data)
                buffer.clear()
                streamed = True
            else:
                buffer.extend(data)
        code = child.wait()
        if not streamed:
            raw = bytes(buffer)
            visible = raw
            if not code and not interrupted and not sensitive(' '.join(command)):
                try:
                    visible, report = select_output(raw, task, out, keep=keep,
                        max_calls=max_calls, mode=mode, cancelled=lambda: bool(interrupted))
                    if report.get('archive'):
                        print(f'[Jev output receipt: {Path(out).resolve() / "report.json"}]', file=sys.stderr)
                except Exception:
                    # Never leak command text, credentials or provider responses.
                    print('[Jev selection unavailable; original stdout preserved]', file=sys.stderr)
            sys.stdout.buffer.write(visible)
        sys.stdout.buffer.flush()
        return 128 + interrupted[-1] if interrupted else 128 - code if code < 0 else code
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        child.stdout.close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-file', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='new directory outside any Git repository')
    parser.add_argument('--keep-text', action='append', default=[], help='required literal; repeat as needed')
    parser.add_argument('--max-calls', type=int, choices=range(1, 5), default=2)
    parser.add_argument('--mode', choices=('auto', 'jev', 'local'), default='auto')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='-- executable arguments (no implicit shell)')
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    try:
        if args.task_file.stat().st_size > 4000:
            raise ProtocolError('Task file exceeds 4000 bytes')
        return run(command, args.task_file.read_text(encoding='utf-8'), args.out, keep=args.keep_text,
                   max_calls=args.max_calls, mode=args.mode)
    except (OSError, ValueError):
        print('Output wrapper could not start; check command, task and new external output path.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
