# Context budgets and cache accounting / 文脈予算とキャッシュ計測

## Implemented behavior

New plans use `context_format: fragments-v1`. Eligible sources are split losslessly into bounded ranges, preferring line boundaries. Long lines split at Unicode character boundaries. Each range records its original path, byte offsets and line numbers; the ranges cover the complete file, including its tail. One independent Noul question judges each range. Several questions share one request's state. Nothing is silently truncated, and crossing the old 22 KB batch size no longer makes a new-plan file automatically unjudged.

The official Jev 1.13 limits are **32k tokens for state plus the longest question** and **64k tokens for the whole request**. This dependency-free harness does not have an official Jev tokenizer. It uses serialized UTF-8 JSON bytes plus a 1,024-unit reserve as a conservative **estimate**, capped at 30,000 / 60,000 respectively. Questions, paths, metadata and JSON escaping count too. Fragments target at most 12,000 serialized bytes and requests contain at most 32 questions. These are local planning budgets, not provider limits or exact token counts. `plan.json.inference` exposes the method and largest estimated request; the API response supplies actual usage. A provider rejection stops without retry.

`--scope-max-calls` now also triggers local candidate scoping when the request budget is exceeded even below 2 MB. All ranges of each retained file count toward that budget. Mandatory files and their dependencies must fit, or planning fails before credentials or provider calls. Check locally scoped-out files for missing task context.

The default conservative batch policy is unchanged. A relevant/uncertain range, an unjudged range, or dependency/focus protection retains the complete file. A split file can be omitted only after every range was judged irrelevant and no retention rule applies. `fragment_decisions` preserves original range scores. A split file's `probability` is null: `max_fragment_probability` is a selection signal, **not a calibrated whole-file probability**. `unjudged_bytes` includes the full size of any file with incomplete coverage. Empty overall selection still retains all files. Old plans without `context_format` retain their old batching and replay semantics.

## Desktop: select before reading bodies

Inspect repository instructions, status, file names and a focused task first. Let the local planner read bodies outside the conversation. Inspect plan/selection metadata without dumping `plan.json` or `context.json`. Then read only the selected ranges needed for the next implementation step:

```sh
python3 "Codex Desktop/context.py" select --plan /absolute/plan --out /absolute/selection \
  --max-calls 4 --mode auto
python3 "Codex Desktop/context.py" read --selection /absolute/selection --path src/main.py \
  --start-line 10 --end-line 60
```

`read` checks artifact hashes and repository freshness. It defaults to 80 lines, allows at most 200 lines and refuses excerpts over 24 KB. An oversized single line requires deliberate local inspection. It never calls Jev or starts another Codex. `context.json` still preserves full selected files for compatibility; the helper does not rewrite Desktop history. After edits, use native source reads for the changed files; refresh the plan only if another selection is needed.

`--mode auto` skips Jev below 12,000 source bytes and retains all candidates. This is an overhead-avoidance heuristic, not evidence that every file is necessary or that Astra will be cheaper. `--mode local` explicitly retains the complete local shortlist without Jev. `--mode jev` remains the compatibility default and forces the requested evaluation. Zero-call modes need no API key. A run's `route: astra` means the local bypass path, not a child Astra call. Exact-request Jev cache reuse remains separate from OpenAI prompt caching.

## Measurement

`measure.py` separates ordinary input, cached reads and cache writes when the provider actually reports them. It accepts API `input_tokens_details.cached_tokens` / `cache_write_tokens` and CLI `cached_input_tokens` / `cache_write_input_tokens`. Conflicting aliases stay unknown. Missing write counts remain unknown; they are not invented as zero. Invalid counts, unreturned usage and failed attempts prevent complete cost claims. Known subtotals are explicitly partial. Jev has no OpenAI cache-accounting requirement: valid reported input remains known ordinary input without those cache fields; missing provider usage still prevents a complete total.

Optional `--prices /absolute/prices.json` accepts USD-per-million rates keyed by exact returned model ID. For example, a file containing only the verified Jev rate is:

```json
{"jev-1.13.0": {"input": 0.042, "output": 0}}
```

Add verified `input`, `output`, `cache_read` and `cache_write` rates for the specific Astra model to estimate its cost. Rates are not guessed or fetched by the script. Each input token belongs to exactly one price category; cache-write cost is not added on top of ordinary-input cost. Missing model/rate/usage/cache details leave that provider's estimate incomplete. All-provider `dollar_cost` stays null until both providers are fully accounted for. These estimates are not invoices or Codex subscription quota measurements.

For comparisons, run normal Codex, local selection only, and local selection plus Jev against matched repeated tasks. Include every repair/retry record with repeated baseline/candidate flags. Separately record task acceptance, missing necessary files, rereads and true wall-clock completion time; summed call durations alone do not establish these. Actual Desktop conversation metrics unavailable to the Skill remain unknown.

## 日本語

- 新規planは元ファイル全範囲を行境界優先で分割し、各範囲をNoulで判定します。22 KB超を無条件で未判定保持する処理を改めました。不確実・未判定・focus・依存があれば全文を保持します。断片の最大確率はファイル全体の校正済み確率ではありません。旧planの再現性も維持します。
- 公式上限はstate＋最長質問32k token、全体64k tokenです。公式tokenizerは同梱せず、JSON・質問・メタデータを含むUTF-8 bytes＋1,024の余裕を推定値として30,000/60,000以内に収めます。1断片は12,000 bytes目安、1回最大32質問です。実tokenはAPI応答から記録します。
- 2 MB未満でも予定呼出数を超えればローカルで候補を絞ります。必須資料が収まらなければ送信前に停止します。省略された必要ファイルがないか確認してください。
- Desktopは本文を会話へ出す前にplan/selectを実行し、`read`で必要行だけ取得します。80行既定、最大200行・24 KBで、鮮度を確認します。過去の会話履歴は変更しません。
- `auto`は12,000本文bytes未満なら全候補を保持してJevを省略、`local`は明示的な省略、既定の`jev`は評価を要求します。少量なら省略する基準は節約保証ではありません。
- 使用量は通常入力・cache read・cache writeを分け、欠測は不明とします。`--prices`で正確なモデルIDごとの確認済み単価を渡すと見積できます。請求額やCodex契約枠とは区別します。実測のないDesktop全体の節約は主張しません。

## Official sources checked 2026-09-24

- [TypeSafe models, pricing and request limits](https://docs.typesafe.ai/models)
- [Noul](https://docs.typesafe.ai/primitives/noul) and [API contract](https://docs.typesafe.ai/api)
- [Jev long-state limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13): filter unrelated content first; a larger limit is not a quality guarantee.
- [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching): stable prefixes, append-only conversation growth, model-specific cache accounting. API controls are not automatically exposed through a Desktop Skill. Preserve stable material and measure total cost when changing handoff order or context size.
