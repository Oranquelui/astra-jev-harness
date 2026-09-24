"""Versioned full-coverage source ranges and conservative Jev request planning.

UTF-8 JSON bytes plus reserve are a token-budget *estimate*, not Jev tokenization.
Never silently truncate a file or label an uncovered range irrelevant.
"""
import hashlib
import json
from bisect import bisect_right
from itertools import accumulate
from shared.jev import ProtocolError, jev_request

FORMAT = 'fragments-v1'
STATE_QUESTION_BUDGET = 30000  # Headroom below the official 32k token limit.
REQUEST_BUDGET = 60000       # Headroom below the official 64k token limit.
RESERVE = 1024
FRAGMENT_BYTES = 12000


def encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False).encode('utf-8'))


def request_bounds(payload):
    return {'method': 'serialized_utf8_bytes_plus_reserve_not_exact_tokens',
            'state_and_longest_question': encoded_size(payload['state']) +
                max((encoded_size(q) for q in payload['questions'].values()), default=0) + RESERVE,
            'total': encoded_size(payload) + RESERVE}


def fits(payload):
    bound = request_bounds(payload)
    return (bound['state_and_longest_question'] <= STATE_QUESTION_BUDGET
            and bound['total'] <= REQUEST_BUDGET)


def split_text(text):
    """Keep exact text, prefer line boundaries, split very long lines losslessly."""
    if not text:
        return ['']
    result, start = [], 0
    while start < len(text):
        low, high = start + 1, min(len(text), start + FRAGMENT_BYTES)
        while low <= high:
            middle = (low + high) // 2
            if encoded_size(text[start:middle]) <= FRAGMENT_BYTES:
                low = middle + 1
            else:
                high = middle - 1
        end = high
        if end < len(text):
            newline = text.rfind('\n', start, end)
            if newline >= start:
                end = newline + 1
        if end <= start:
            raise ProtocolError('Source range cannot fit fragment budget')
        result.append(text[start:end])
        start = end
    return result


def units(plan):
    result = {}
    for path, record in sorted(plan['files'].items()):
        parts = split_text(record['content'])
        # Match Desktop bounded reads, including CRLF and Unicode separators.
        line_ends = list(accumulate(len(line.encode()) for line in record['content'].splitlines(keepends=True)))
        offset = 0
        for index, text in enumerate(parts):
            key = path if len(parts) == 1 else '@span/' + hashlib.sha256(path.encode()).hexdigest() + '/' + str(index)
            while key in result or (len(parts) > 1 and key in plan['files']):
                key = '@' + key
            end = offset + len(text.encode())
            result[key] = {'path': path, 'start_byte': offset, 'end_byte': end,
                           'start_line': bisect_right(line_ends, offset) + 1,
                           'end_line': bisect_right(line_ends, max(offset, end - 1)) + 1,
                           'complete_file': len(parts) == 1, 'text': text}
            offset = end
    return result


def case(plan, batch, catalog=None):
    catalog = units(plan) if catalog is None else catalog
    if not set(batch) <= set(catalog):
        raise ProtocolError('Unknown source range')
    return {'task': plan['task'], 'files': batch,
            'source_ranges': {key: {k: v for k, v in catalog[key].items() if k != 'text'}
                              for key in batch}}


def batches(plan):
    catalog = units(plan)
    result, current = [], {}
    for key, unit in catalog.items():
        proposed = {**current, key: unit['text']}
        if current and (len(proposed) > 32 or not fits(jev_request(case(plan, proposed, catalog)))):
            result.append(current)
            proposed = {key: unit['text']}
        if not fits(jev_request(case(plan, proposed, catalog))):
            raise ProtocolError('Task, path metadata and source range exceed Jev planning budget')
        current = proposed
    if current:
        result.append(current)
    return result


def summary(plan):
    work = batches(plan)
    catalog = units(plan)
    bounds = [request_bounds(jev_request(case(plan, batch, catalog))) for batch in work]
    return {'format': FORMAT, 'planned_calls': len(work), 'source_fragments': len(catalog),
            'budget_method': 'serialized_utf8_bytes_plus_1024_reserve_not_exact_tokens',
            'state_and_longest_question_budget': STATE_QUESTION_BUDGET,
            'request_budget': REQUEST_BUDGET,
            'max_estimated_state_and_question': max((b['state_and_longest_question'] for b in bounds), default=0),
            'max_estimated_request': max((b['total'] for b in bounds), default=0)}
