"""Pure, byte-bounded source presentation; no inference, writes or retention changes."""
import json

from shared.jev import ProtocolError
from shared.repo_context import digest, is_instruction


def output_size(value):
    return len(json.dumps(value, ensure_ascii=False).encode('utf-8')) + 1


def bounds(max_bytes, offset, lines):
    if (type(max_bytes) is not int or not 1024 <= max_bytes <= 24000
            or type(offset) is not int or offset < 0
            or type(lines) is not int or not 1 <= lines <= 200):
        raise ProtocolError('Use 1024..24000 output bytes, a nonnegative offset and 1..200 lines')


def excerpt(path, text, start, count, **metadata):
    lines = text.splitlines(keepends=True)
    start = min(start, max(1, len(lines)))
    end = min(start - 1 + count, len(lines))
    missing = []
    if start > 1:
        missing.append([1, start - 1])
    if end < len(lines):
        missing.append([end + 1, len(lines)])
    return {'path': path, 'source_sha256': digest(text.encode()),
            'start_line': start, 'end_line': end, 'total_lines': len(lines),
            'text': ''.join(lines[start-1:end]), 'unpresented_ranges': missing, **metadata}


def page(base, candidates, offset, max_bytes):
    """Fit whole entries/lines. An oversized line becomes an explicit reading lead."""
    if offset > len(candidates):
        raise ProtocolError('Offset is outside the view')
    result = {**base, 'items': [], 'offset': offset, 'total_items': len(candidates),
              'next_offset': None, 'output_limit_bytes': max_bytes, 'provider_calls': 0}
    for index in range(offset, len(candidates)):
        item = candidates[index]()
        next_offset = index + 1 if index + 1 < len(candidates) else None
        while True:
            trial = {**result, 'items': result['items'] + [item], 'next_offset': next_offset}
            if output_size(trial) <= max_bytes:
                result = trial
                break
            if result['items']:
                result['next_offset'] = index
                return result
            # Reduce only complete source lines, never cut UTF-8 or invent a summary.
            if item.get('text'):
                lines = item['text'].splitlines(keepends=True)
                item = dict(item, text=''.join(lines[:-1]), end_line=item['end_line']-1)
                missing = ([[1, item['start_line']-1]] if item['start_line'] > 1 else [])
                if item['end_line'] < item['total_lines']:
                    missing.append([item['end_line']+1, item['total_lines']])
                item['unpresented_ranges'] = missing
                if not item['text']:
                    item['reason'] = 'source_line_exceeds_output_budget_use_read'
            else:
                raise ProtocolError('Metadata exceeds output budget; increase --max-bytes')
    if output_size(result) > max_bytes:
        raise ProtocolError('Metadata exceeds output budget')
    return result


def presentation(plan, record, context, max_bytes, offset, lines_per_file):
    bounds(max_bytes, offset, lines_per_file)
    decisions = record.get('decisions', {})
    focus = set(plan.get('focus_paths', []))
    def score(path):
        d = decisions.get(path, {})
        p = d.get('max_fragment_probability', d.get('probability'))
        return p if isinstance(p, (float, int)) else -1
    paths = sorted(record['paths'], key=lambda p: (not is_instruction(p), p not in focus, -score(p), p))
    def item(path):
        fragments = [f for f in record.get('fragment_decisions', {}).values() if f['path'] == path]
        # Start at the strongest saved source range; probabilities never generate text.
        fragment = max(fragments, key=lambda f: f.get('probability') if f.get('probability') is not None else -1,
                       default={})
        start = 1 if is_instruction(path) or path in focus else fragment.get('start_line', 1)
        return excerpt(path, context['files'][path], start, lines_per_file,
                       reasons=decisions.get(path, {}).get('reasons', []))
    return page({'status': 'presentation', 'retained_files': len(paths),
                 'retained_source_bytes': sum(len(t.encode()) for t in context['files'].values()),
                 'scoped_out_files': len(plan.get('scoped_out', {})),
                 'coverage': 'excerpts_only_full_sources_remain_in_context',
                 'reading_leads': 'Use read for unpresented_ranges; next_offset visits further retained files.'},
                [lambda p=p: item(p) for p in paths], offset, max_bytes)
