"""Synthetic Japanese coding exercises. Gold answers never enter model prompts."""

NOISE = {
    "display.py": "def display_count(count):\n    return str(count)\n",
    "stats.py": "def average(values):\n    return sum(values) / max(1, len(values))\n",
    "limits.py": "UPLOAD_LIMIT = 10000000\nMAX_USERS = 100\n",
    "sort_order.py": "def ordered(values):\n    return sorted(values)\n",
    "cart.py": "def cart_total(prices):\n    return sum(prices)\n",
    "progress.py": "def progress(done, total):\n    return min(1, done / max(1, total))\n",
    "geometry.py": "def area(width, height):\n    return width * height\n",
    "feature_flags.py": "FEATURE_SEARCH = True\nFEATURE_EXPORT = False\n",
}

CASES = [
    {
        "id": "pagination", "function": "page_slice",
        "task": "一覧ページが1ページ目から先頭のデータを飛ばす不具合を修正してください。ページ番号は1始まりです。pageとsizeが1未満なら、それぞれ1として扱います。範囲外は空リストを返します。既存の関数名と引数は維持してください。",
        "files": {**NOISE, "pagination.py": "def page_slice(items, page, size):\n    return items[page * size:(page + 1) * size]\n"},
        "required": ["pagination.py"],
        "solution": {"pagination.py": "def page_slice(items, page, size):\n    page = max(1, page)\n    size = max(1, size)\n    return items[(page - 1) * size:page * size]\n"},
        "tests": [([list(range(7)), 1, 3], [0, 1, 2]), ([list(range(7)), 2, 3], [3, 4, 5]),
                  ([list(range(7)), 3, 3], [6]), ([[], 1, 3], []), ([[8, 9], 0, 0], [8]),
                  ([[8, 9], -2, 1], [8]), ([[8, 9], 5, 2], [])],
    },
    {
        "id": "retry", "function": "retry_delay",
        "task": "リトライ待ち時間の計算を修正してください。attemptは0始まりで、初回は設定されたBASE_MS、以降は2倍になります。負のattemptは0扱い、待ち時間はCAP_MSを超えないこと。別ファイルの既存設定値を使用し、設定値自体は変更しないでください。全ファイルは同じ名前空間に読み込まれます。",
        "files": {**NOISE, "retry_policy.py": "BASE_MS = 200\nCAP_MS = 5000\n",
                  "retry.py": "def retry_delay(attempt):\n    return BASE_MS * (2 ** (attempt + 1))\n"},
        "required": ["retry.py", "retry_policy.py"],
        "solution": {"retry.py": "def retry_delay(attempt):\n    return min(CAP_MS, BASE_MS * (2 ** max(0, attempt)))\n"},
        "tests": [([0], 200), ([1], 400), ([3], 1600), ([5], 5000), ([-1], 200), ([8], 5000)],
    },
    {
        "id": "expiry", "function": "is_active",
        "task": "利用権の期限ちょうどの時刻でも有効になってしまう不具合を修正してください。有効条件は、revokedがFalseであり、expires_atがNone（無期限）またはnowがexpires_atより小さいことです。0も有効な期限値なのでNoneと区別してください。引数は整数時刻、None、boolだけです。",
        "files": {**NOISE, "access.py": "def is_active(now, expires_at, revoked):\n    return not revoked and (not expires_at or now <= expires_at)\n"},
        "required": ["access.py"],
        "solution": {"access.py": "def is_active(now, expires_at, revoked):\n    return not revoked and (expires_at is None or now < expires_at)\n"},
        "tests": [([10, 10, False], False), ([9, 10, False], True), ([11, 10, False], False),
                  ([100, None, False], True), ([0, 0, False], False), ([-1, 0, False], True),
                  ([1, None, True], False), ([9, 10, True], False)],
    },
]
