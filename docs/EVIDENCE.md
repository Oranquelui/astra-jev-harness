# Evidence selection and measurement / 評価資料の選別と計測

## English

The harness can now select **original excerpts** from explicitly supplied evaluation logs, specifications, and diffs. Jev answers independent Noul questions about relevance, counterevidence, and the need for further review. Python selects the original text; Astra investigates and implements. Jev does not summarize, decide test exit status, grant permission, or certify completion.

### Prepare and inspect

All artifact directories and caches must be outside source repositories. Use your own configured TypeSafe key. Planning, freshness checks, and measurement are local.

```sh
python3 evidence.py plan --task-file /absolute/task.txt \
  --source /absolute/evaluation-review.md \
  --source /absolute/changes.diff \
  --pin-source /absolute/status-and-budget.json \
  --out /absolute/evidence-plan
```

Review `PLAN.md` and `plan.json`. **Pin all failure/status, budget, and authorization records**: pinned sources are always retained and never sent for classification. Pinning is explicit; this tool cannot discover every important constraint in arbitrary prose. The experimental selector is not a complete failure or secret detector. Sources are explicit UTF-8 `.txt`, `.md`, `.json`, `.jsonl`, `.log`, or `.diff` files: at most 100 sources, 500 KB each, 2 MB total. Known credential filenames/patterns are refused. Lines above 4 KB are refused rather than silently truncated; provide a readable, explicitly prepared source instead.

### Select and consume

```sh
python3 evidence.py select --plan /absolute/evidence-plan \
  --out /absolute/evidence-selection --max-calls 4 \
  --cache-dir /absolute/private-jev-cache
python3 evidence.py check --selection /absolute/evidence-selection
```

Selection uses up to the reviewed request count, with no automatic retry. `selection.json` records attempted live calls, cached responses, usage, probabilities, time and safe failure diagnostics. `packet.json` contains verbatim excerpts, original absolute paths, source SHA-256 and one-based start/end lines. Selection transmits the task and excerpt data to TypeSafe, not the local absolute source paths. Artifacts contain source text: never commit them.

The policy keeps pinned and unjudged excerpts and any excerpt whose relevance, counterevidence or review probability exceeds 0.2. This is an experimental conservative threshold, not a calibrated accuracy guarantee. Adjacent excerpts from the same source are retained for context. If nothing would survive, everything is kept. A failed selection produces no usable packet. Changes to the source, plan or packet invalidate `check`.

Use the **same task file** for the repository plan and evidence plan. Then either surface can attach a fresh packet:

```sh
python3 desktop/context.py select --plan /absolute/repo-plan \
  --out /absolute/context-selection --max-calls 4 \
  --evidence /absolute/evidence-selection

python3 cli/main.py run --plan /absolute/cli-plan \
  --out /absolute/cli-run --mode jev \
  --evidence /absolute/evidence-selection \
  --verify-json '["python3", "-m", "unittest", "discover"]'
```

Desktop still uses the current conversation for implementation; no child Codex is started. CLI attaches the packet to its isolated generation input. Freshness is checked before and after consumption; apply/reverification also check attached evidence. No source is modified by evidence selection.

### Reuse exact judgments

`--cache-dir` is optional for evidence selection, Desktop selection and CLI `run`. It stores validated response probabilities and historical usage, not request source text or credentials. A cache hit requires the entire request hash (task, model, questions/criteria, and batch state) to match; unchanged individual files alone are insufficient. Corrupt entries are rejected. Changed prompts, task, model or batch content require a new judgment. A hit has `reused: true`, current `usage: null`, and no provider call; its old usage is never counted as new usage.

Limits apply to planned **cache misses**. A new output directory is still required. The cache is not a global financial ledger or permission to repeat failed calls: call caps remain per invocation. Keep previous failed/unknown usage in the task's budget when approving another invocation. There is no automatic continuation or service retry. Concurrent processes are not deduplicated by the cache.

### Include work in progress

Both repository `plan` entrypoints accept repeated `--include-file relative/path.py`. This adds a specifically reviewed untracked file without staging it; protected, ignored, missing, symlinked or credential-like files are refused. All ordinary freshness and content checks still apply. Default collection remains tracked files only.

Dependency preservation now covers conventional Python `src/` roots, local TypeScript `paths`/`baseUrl`, relative JSONC tsconfig inheritance, `.mts`/`.cts`, and conservatively keeps matching local workspace packages. Unreadable/unsupported inherited TS configuration retains local scope. This is still static, partial analysis: arbitrary Python package-dir configuration, dynamically constructed imports, package-manager resolution and external tsconfig packages are not fully resolved.

### Compare complete recorded runs

```sh
python3 measure.py --baseline /absolute/astra-only/result.json \
  --candidate /absolute/hybrid/result.json \
  --candidate /absolute/evidence-selection/selection.json
```

Repeat flags to include every run in an arm. The report separates providers, cache hits, known tokens, missing usage and summed run durations. Missing usage remains unknown. Desktop records do not measure the active conversation, so complete Astra usage remains unknown. Evidence records are auxiliary Jev-only stages; combine them with the associated CLI generation records when measuring a CLI workflow. Evidence records alone never establish complete Astra usage. Input reduction is shown only when both arms have complete recorded Astra usage; comparable tasks and acceptance criteria must still be checked independently. Summed durations are not parallel wall-clock time. Dollar savings and semantic quality are not inferred. Use independent required-evidence labels, existing regression tests and repeated representative tasks before claiming savings.

## 日本語

今回の追加は、**評価資料から修正に必要な原文を選び、出典付きでAstraへ渡す機能**です。Jevは「関連するか・反証か・追加確認が必要か」を判断し、Pythonが原文を抜き出します。Astraが説明・設計・実装を担当します。

- `plan`で資料を明示指定し、失敗状態・予算・権限に関する記録は必ず`--pin-source`で固定してください。固定資料は省略もモデル判定もしません。
- `select`だけが外部APIを呼び、`check`は出典と成果物の改変・古さを確認します。原文・行番号・SHA-256が残り、生成した要約に置き換えません。
- 同じtask fileを使い、CLI/Desktopの`--evidence`で受け渡せます。Desktopは現在の会話が実装します。
- `--cache-dir`はリクエスト全体が一致した応答のみ再利用します。キャッシュ使用を新規Jev実行や新しいtoken消費として数えません。複数runをまたぐ予算上限の強制や並行呼出しの重複防止は含みません。
- repoの`plan --include-file`で、確認した未追跡ファイルをstageせず追加できます。Pythonの通常の`src/`配置、TypeScriptの別名と`.mts`等も補完対象になりました。動的importや任意のビルド設定の完全解決はしません。
- `measure.py`は失敗を含む保存済みrunを集計します。Desktop会話全体のtokenは取得できないため不明のままです。ファイル数やbytesをtoken削減率として報告しません。

英語のコマンド例をそのまま使えます。いずれも自動retry、commit、push、配信を行いません。現在の閾値は実験値で、品質や費用削減の保証ではありません。

## Official design references

- [System One](https://docs.typesafe.ai/concepts/system-one): typed judgments; generation stays with an LLM; individual answers can be wrong.
- [Jev with coding agents](https://docs.typesafe.ai/introduction/coding-agents): Jev is not a replacement for the coding model or a model-menu setting.
- [HTTP API](https://docs.typesafe.ai/api): request/response and Noul schema.
- [Classifying RAG passages](https://docs.typesafe.ai/cookbooks/classifying_rag_passages): retain useful evidence and conflicting information.
- [Fan-out](https://docs.typesafe.ai/patterns/fan-out): independent questions over shared state.

Reviewed 2026-09-23. No headline provider benchmark is a measured harness saving.

## 2026-09-23 validation

One live Jev 1.13.0 request on fictional code-debugging evidence succeeded: 971 input / 112 output tokens, approximately 0.34 seconds for the API call. The required failure excerpt and pinned status record were retained. An unrelated excerpt was also retained because its review probability was 0.30; the conservative threshold kept it. Original excerpt bytes remained 444 → 444 (0% reduction). This is a functionality check, not an accuracy or Astra-token-saving benchmark. The identical second selection used the validated cache with **zero additional provider calls**. No Astra child generation or real-project evaluation API was run.

架空資料の実Jev検証は1回成功し、再利用は追加API 0回でした。ただし本文削減は0%で、Astraのtoken節約は未実証です。無関係な資料の誤保持も含めて、次の評価セットで閾値・質問を検証する必要があります。
