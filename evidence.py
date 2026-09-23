#!/usr/bin/env python3
"""Select original evaluation excerpts for CLI or Desktop; never generates code."""
import argparse
import json
from pathlib import Path
import sys
from shared import evidence
from shared.jev import ProtocolError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--task-file', required=True)
    p.add_argument('--source', action='append', default=[])
    p.add_argument('--pin-source', action='append', default=[])
    p.add_argument('--out', required=True)
    p = sub.add_parser('select')
    p.add_argument('--plan', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--max-calls', type=int, default=4)
    p.add_argument('--cache-dir')
    p = sub.add_parser('check')
    p.add_argument('--selection', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            plan = evidence.make_plan(Path(args.task_file).read_text(), args.source, args.pin_source, args.out)
            result = {'status': 'planned', 'calls': plan['planned_calls'], 'fragments': len(plan['fragments'])}
        elif args.command == 'select':
            record = evidence.select(args.plan, args.out, args.max_calls, args.cache_dir)
            result = {k: record[k] for k in ('status', 'attempted_calls', 'candidate_bytes', 'selected_bytes')}
        else:
            packet = evidence.check(args.selection)
            result = {'status': 'fresh', 'fragments': len(packet['fragments'])}
        print(json.dumps(result))
        return 0
    except (ProtocolError, OSError, ValueError, KeyError, TypeError):
        print('Evidence operation failed; inspect the plan and safe selection failure record.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
