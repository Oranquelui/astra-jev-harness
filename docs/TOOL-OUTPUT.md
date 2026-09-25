# Experimental command-output selection / コマンド出力選別

This opt-in wrapper extends file selection to **routine progress logs produced during a task**. It executes a command once, keeps an exact local stdout archive, and lets Jev judge eligible progress chunks before the result reaches the coding model. It does not summarize, modify conversation history, install hooks, or launch another coding agent. The selected coding model and login remain unchanged.

## Use from Codex Desktop or a normal Codex CLI session

Write an explicit task brief (UTF-8, up to 4,000 bytes) containing the outcome, constraints and facts that must survive. The wrapper does not read the conversation transcript. It cannot protect a requirement absent from the brief; use `--keep-text` for mandatory literals, or ordinary execution when completeness matters.

```sh
# From the harness checkout; use absolute paths when working elsewhere.
python3 output.py --task-file /absolute/task.txt \
  --out /absolute/new-directory-outside-git --max-calls 2 \
  --keep-text release-target -- npm run build

# Through an installed Desktop Skill symlink:
python3 ~/.codex/skills/astra-jev-coding/scripts/output.py \
  --task-file /absolute/task.txt --out /absolute/new-directory-outside-git \
  -- npm run build
```

The command runs with the caller's cwd and environment, except `TYPESAFE_API_KEY` is removed from the child environment. Keychain credentials are loaded only after the command finishes, in the wrapper process. No implicit shell expansion is performed. Stdin is closed: use the ordinary terminal for interactive commands, servers, live streaming or commands needing the TypeSafe key. Do not pipe selected output into a parser or another program. This is a human/model-facing log view.

The CLI harness's isolated `codex exec` generation does **not** automatically use this wrapper. It is available for explicitly routed commands in normal CLI sessions and Desktop. No Claude hook or Claude-specific launcher is installed by this change.

## Retention, bounds and recovery

- `auto` skips outputs under 12,000 UTF-8 bytes. `local` is the unchanged, no-Jev baseline. `jev` explicitly bypasses the small-output gate. These are byte heuristics, not model token counts.
- Only lines starting with recognized progress prefixes (`progress`, `downloading`, `fetching`, `compiling`, `building`, `checking`, `cache hit`) are candidates. Unknown lines and recognized structured/source-like lines stay. This initial scope deliberately does not prune search matches or general documents.
- First/last lines, diagnostics, test/result summaries, artifact/rollback references, required literals and adjacent lines stay. Recognition is heuristic, not a guarantee for every language or format. Uncertain meaning stays in the model judgment as well.
- Each request includes the complete task brief, all protected context and the complete candidate chunks being judged. No question refers to a hidden or truncated candidate. Protected context over 8,000 bytes skips selection. Requests use a conservative 28,000 serialized-UTF-8-byte-plus-reserve bound, not an exact tokenizer.
- A chunk is omitted only with Noul probability at most `0.1`. This threshold is experimental, not a measured error guarantee. Missing judgments and chunks beyond the call cap stay. Default cap: two requests; maximum: four; no automatic retries.
- Nonzero command exits preserve stdout and bypass Jev. Original stderr and exit status are preserved; a receipt notice may be added to stderr. API failure restores the entire original stdout, including after an earlier successful request. Selection never re-executes the command.
- Outputs beyond 2,000,000 bytes switch to unchanged streaming. Invalid UTF-8, control characters and detected credential-like content skip archiving and inference. Secret detection is heuristic: only wrap output authorized for TypeSafe. Content is not redacted before sending.
- For eligible output, `stdout.txt` is saved **before** inference in the explicitly chosen new directory outside every Git repository, with private directory/file permissions. Failure to archive prevents inference. Retained text is copied verbatim and omissions are marked. A footer gives the archive path for recovery. If the footer and markers remove the byte advantage, the original output is returned.

Read the archive directly when facts are missing; do not repeat a side-effecting command to recover output. Archives persist until explicitly deleted. Do not add them to Git. No credentials, task brief, raw output or provider response body are included in `report.json`; the report contains hashes, byte counts, ranges, decisions, provider usage and bounded failure metadata. The private archive does contain the original output.

## What the measurements establish

`report.json` distinguishes attempted/completed calls, returned usage, unknown usage after failure, protected/unjudged ranges, output bytes and archive hashes. `astra_tokens_saved` and `combined_cost_saved` remain null. The host can further truncate the returned output, and the receipt/footer also use context. A shorter stdout is not automatically a reduction in total input tokens, cached input cost, task duration or retries.

For adoption, compare identical completed coding tasks with the same model/reasoning settings, initial files and acceptance checks. Count ordinary and cached model input separately, output tokens, Jev usage/cost, recovery reads, retries and elapsed time. The initial synthetic check is an information-retention smoke test, not that end-to-end benchmark.

## 日本語

既存のファイル選別に加え、**作業中に出る進捗ログ**を選別する任意のラッパーです。コマンドは1回だけ実行し、原文stdoutをGit外へ保存してからJevが候補を判定します。履歴圧縮・自動フック・別のCoding Agentの起動は行いません。モデルとログインは変えません。

上のコマンドをDesktopまたは通常のCodex CLIセッションから明示的に使います。課題・制約・必要な値を4,000 bytes以内の課題ファイルに書き、必須文字列は`--keep-text`で指定します。会話履歴は収集しないため、課題文にない過去の要件は判断できません。CLIハーネス内の隔離された`codex exec`への自動適用や、Claude用フックの追加はありません。

- `auto`は12,000 bytes未満を素通し、`local`はJevを使わない比較用、`jev`は小さい出力も明示的に判定します。バイト数はtoken数ではありません。
- 対象は認識できた進捗行のみ。未知の行、認識できた構造化データ・コード、先頭/末尾、診断・結果・必須文字列とその前後を保持します。検索結果や一般文書の削減は今回の対象外です。形式判定はヒューリスティックです。
- Jevには課題文・保護部分・判定対象のチャンク全文を渡します。見えていない内容を削除しません。保護部分が8,000 bytes超なら選別を省略します。1リクエストの保守的な上限はJSONのUTF-8 bytes＋余裕分で28,000です。
- Noulが0.1以下の進捗チャンクだけ省略候補とし、不確実・未判定は保持します。既定2回、最大4回、自動再試行なし。閾値は実験値です。
- 非ゼロ終了・API失敗・上限超過時は原文を返します。コマンド再実行はしません。stderr・終了コードを維持し、stderrに記録の保存先を追加する場合があります。2 MB超はそのままストリームへ切り替えます。
- 新しいGit外ディレクトリへ原文を先に保存し、復元先を返します。保存に失敗したらAPIを呼びません。原文は自動削除されません。機密らしい内容は保存・送信を避けますが、検知は完全ではないため、TypeSafeへの送信が許可された出力だけに使います。
- 子コマンドには`TYPESAFE_API_KEY`を渡しません。Keychainはコマンド終了後にラッパー内で読みます。標準入力は閉じるため、対話コマンド・常駐プロセス・パーサーへの入力には通常の実行経路を使います。

`report.json`は実行回数・使用量・判定・原文hash・bytesを記録します。Astra全体のtoken・費用削減は未測定としてnullを維持します。採用判断には、同じ課題・設定・合格条件で、キャッシュ込みのモデル使用量、Jev費用、再読込・再作業、完了時間を比較してください。

## References / 参考

- [jev-pruner](https://github.com/tamaratran/jev-pruner): command wrapper, verbatim excerpts and recoverable originals informed this design. No upstream source or plugin is bundled. This version uses the existing Python transport and an explicit brief, not transcript scraping.
- [fast-jev-compaction issue #52](https://github.com/tamaratran/fast-jev-compaction/issues/52): a reported case of scoring missing candidate content informed the full-candidate coverage invariant; the report is not our own reproduction.
- [TypeSafe Noul](https://docs.typesafe.ai/primitives/noul), [API](https://docs.typesafe.ai/api), [Codex hooks](https://learn.chatgpt.com/docs/hooks).
