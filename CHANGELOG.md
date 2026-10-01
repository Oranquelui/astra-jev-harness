# Changelog / 変更履歴

## Unreleased

- Clarify Desktop Skill local continuation for a user-chosen no-Jev workflow, required-scope budget errors, missing credentials, and provider failures. Preserve the choice across in-scope follow-ups without repeated approval. Keep incomplete Jev acceptance distinct from authorized local implementation.
- Document direct local select/check/read for sufficient plans and bounded native reads when plans cannot cover required files. Keep Jev launcher checks, request caps, failure receipts, secret/freshness protection and no automatic retry; do not mislabel local work as Jev-selected. No runtime, version, or published-release change.
- Desktop SkillにJev未検証を明示したローカル継続を追加。必須依存の予算超過と認証・provider障害を分け、同じ許可を聞き直さずに許可済みの調査・実装・テストを継続します。実行コード・版番号・公開済みリリースは変更しません。
- Extend the continuation policy to the installed Claude Code Skill and Codex CLI guidance. Claude's wrapper supports local select/check/read directly; CLI `--mode astra` still requires authorized Codex generation and is not offline. Preserve failure receipts, sufficient-plan checks and verify/apply guards. Remove mandatory routine usage reporting from Claude guidance; keep internal records and request limits.
- Claude Code SkillとCodex CLIの英日ガイドにも継続方針を反映。Claudeは既存wrapperのlocal経路を使い、CLIはJevなしでもCodex生成を行う点を明記。plan不足・失敗記録・検証／適用の制約を維持し、Claude側の使用量の定型報告も削除します。既存の実行経路を使う指示の修正で、runtime変更や自動fallbackは追加しません。

## v0.7.1 — 2026-09-29

- Remove mandatory routine Jev accounting from the Codex Desktop Skill: planned/actual call counts, tokens, cache reuse, cost summaries, and output bytes. Progress and final replies focus on changes, verification, and actionable blockers.
- Keep internal receipts, request caps, validated cache reuse, failure recovery, and explicit measurement tools. Show accounting from saved records only on an explicit user request; never add API calls, benchmarks, or comparisons for reporting. Runtime and Claude Code Skill behavior are unchanged.
- Align Desktop guidance and both READMEs, correct the Japanese README version link, and publish matching v0.7.1 native packages.
- Codex Desktop SkillのJev回数・使用量・cache・費用・出力bytesの定型報告を削除。通常の返信を変更内容と検証結果に絞り、内訳は明示的な依頼時だけ保存済み記録から回答します。内部の上限制御・失敗復旧・cache・任意の計測機能は維持し、報告のための追加APIや比較は実行しません。英日READMEと配布versionを揃え、実行コードとClaude Code Skillの動作は変更しません。

## v0.7.0 — 2026-09-29

- Replace normal Harness execution and Skill installation with a compiled Go runtime: Desktop/Claude context workflows, evidence, optional output selection, saved-receipt comparison and CLI candidate generation/verify/apply. Python remains a source-only development oracle; platform archives do not contain Python entrypoints.
- Preserve Python-compatible canonical Jev request hashes and cache validation, source/host freshness, bounded reads, secret/path guards, explicit call caps, attempt-before-request records, no redirects/retries and unknown-cost accounting. Add native Go package/module dependency closure; conservatively retain Python context on parser uncertainty.
- Preserve configured Codex model/effort, isolated candidates, explicit new-file/test grants, unchanged verified-artifact checks and apply rollback. Add native regression coverage using fake Codex and local HTTP fixtures, with no live generation or recurring timing/A-B measurement.
- Switch both installed Skills to `.sh` launchers that execute the existing binary. Build once or use the platform archive; no compilation or interpreter setup occurs during coding. Keep installer idempotence, foreign-Skill protection and user authentication intact.
- Add independent macOS arm64/Linux amd64 build/test/archive jobs and bundled dependency license notices. Detail runtime requirements, migration limits and rollback in both READMEs. No new measured claim about coding tokens, total model cost or end-to-end speed.

### 日本語

- 通常のHarness・両Skill・installerをGo実行版へ移行。コンテキスト、資料、任意ログ選別、保存済み使用量比較、CLI候補生成／検証／適用を移植。Pythonはソースrepoの開発用に残し、配布archiveから除外します。
- 互換JSON／request hash、cache検証、鮮度・host・path・秘密情報の保護、呼び出し上限、試行記録、retryなしの動作を維持。Go依存解析を追加し、Python解析の不確実性では保持します。
- ユーザーのCodex設定、隔離候補、明示の変更許可、検証済みhash、apply復旧を維持。疑似CodexとローカルHTTPを使う回帰検証を追加し、実モデルの比較や常時計測は導入しません。
- Skill入口をビルド済みバイナリへ切替。通常CodingでPython／Go／自動ビルドは不要。installerは別Skillや認証を上書きしません。
- macOS arm64／Linux amd64の検証・配布archive、依存ライセンス、英日READMEを整備。Coding token・総費用・課題完了速度の改善率は未計測です。

## v0.6.0 — 2026-09-28

- Add `present` to Desktop and Claude Code: bounded original-source pages with hashes, line numbers, unpresented ranges and continuation offsets. The entire JSON output has an explicit byte cap; retained full sources are unchanged. Valid Jev judgments, freshness and host checks remain required.
- Add operator-guided `discover`: browse every scoped-out directory/file page, inspect short original previews, then create a fresh plan preserving focus/includes before Jev selection. Unjudged files remain distinct from irrelevant files. No automatic provider calls, retries or new selection defaults.
- Fix `measure.py` to normalize recognized version-1 tool-output `calls` alongside CLI, host and evidence receipts. Preserve known subtotals, unknown attempts/usage/cache details, separate live requests and reused judgments, and duplicate-path suppression. Unknown receipt schemas cannot contribute run duration. Auxiliary receipts do not establish complete conversation costs.
- Expand English/Japanese README with before/after behavior, commands, compatibility, measured presentation bytes and explicit unmeasured outcomes. Python 3.10+ remains required; bundled Python is a proposal only.
- Validation: 199 offline tests passed. Implementation context selection: 12 live attempts/completions, 0 cache reuses, 83,571 input / 813 output tokens, all 37 candidate files retained. Historical presentation replay kept 267,517 source bytes and returned 5,750 JSON bytes on the first page (3,459 source bytes); replay made no API calls. No new Astra-token, total-cost or coding-quality improvement is established.

### 日本語

- Desktop／Claude Codeに`present`を追加。保持済み全文を変えず、原文・hash・行番号・未提示範囲・次ページをJSON応答全体の上限内で返します。Jev判定・鮮度・host一致を確認します。
- `discover`で候補外のディレクトリと短い原文を段階的に確認できます。ページを辿って複数の枝を残し、既存focus/includeを維持した新しいplanとJev選別へ戻ります。未判定を無関係とみなさず、自動API・retry・既定policy変更は行いません。
- `measure.py`がtool-output v1の`calls`を統合集計します。既知の部分集計、試行・usage・cacheの欠測、実呼び出しと再利用、重複pathを区別し、補助記録だけで会話全体の費用を確定しません。
- 英日READMEに改善前後、使い方、互換性、表示bytes実測と限界を追記。Python 3.10以上は必要で、同梱配布は提案段階です。
- 検証199件成功。実装時Jevは12回試行／完了・再利用0回、入力83,571／出力813 tokenで37候補を全保持。保存済み選別の原文267,517 bytesを保持し、初回提示はJSON5,750 bytes（原文3,459 bytes）。再生の追加APIは0回で、Astra token・総費用・coding品質の改善実測ではありません。

## v0.5.1 — 2026-09-27

- Require valid Jev judgments through the Codex Desktop Skill's `select`, `check`, and `read` entrypoints. Reject local/auto bypasses before credentials or transmission, preserve matching cached judgments, and distinguish reuse from new API calls. Direct native-helper baselines remain available for explicit no-Jev requests; no silent fallback or automatic retry. Optional output selection and Claude Code behavior are unchanged. This fix makes no new token or cost-saving claim.
- Codex Desktop Skillの`select`・`check`・`read`でJev判定を必須にし、localや小さい入力のautoによる省略を認証・送信前に拒否します。同一リクエストの有効な判定再利用は維持し、実API呼び出しと区別します。明示的なJevなしの依頼にはhelper直接実行を使えますが、黙った切替・自動再試行はしません。任意の出力選別とClaude Codeの動作は変更せず、新たなtoken・費用削減は主張しません。

- Validation / 検証: 183 offline tests passed. A synthetic three-file check through the installed Desktop Skill completed plan/select/check/read with one live Jev call (960 input / 55 output tokens); exact-request reuse completed with zero additional calls. Local and small-auto bypasses and old local handoffs were rejected. These are integration checks, not savings measurements.

## v0.5.0 — 2026-09-25

- Add an opt-in, dependency-free Python wrapper for Desktop and normal Codex CLI sessions. Archive eligible stdout outside Git, retain verbatim required/uncertain/unjudged content, cap requests and preserve command failures, exit status and signals. No transcript scraping, auto-hooks or credential forwarding to the wrapped command.
- Synthetic smoke check: stdout 19,885 → 7,601 bytes (61.8% less); required facts 5/5; exact original archived; Jev 2 calls / 7,172 input / 195 output tokens. This does not establish Astra usage, total-cost or coding-speed savings.
- Desktop・通常のCodex CLI向けに任意の進捗ログ選別を追加。原文をGit外へ保存し、必要・不確実・未判定の情報、失敗時出力、終了コード・シグナルを保持します。会話履歴の収集・自動フック・子コマンドへのJevキー転送は行いません。
- 合成ログ1件のstdoutは61.8%減、必須情報5/5を保持。Astra全体・総費用・実装速度の削減とは分けて記録します。

- CLI generation now resolves the configured model/effort through Codex before Jev selection and forwards only those settings into the isolated generation process. Missing settings use Codex defaults; configuration errors and unsupported custom providers/profiles fail closed. Requested settings are distinct from unknown serving-model identity, preventing cost attribution to a hardcoded Astra model. Historical benchmark settings/results are unchanged.
- CLI生成のモデル・推論強度をCodex設定から継承します。設定はJev選別前に確認し、取得失敗・未対応の独自プロバイダー/profileでは停止します。実応答モデルを確認できない場合の費用は不明とし、過去の測定結果と区別します。

- Validation: 171 offline tests passed; installed Desktop Skill entrypoints and existing Keychain credential availability verified. Live synthetic output selection: 2 Jev calls, no extra coding agent.
- 検証：オフライン171件成功。インストール済みDesktop Skillの起動と既存Keychain認証の有効性を確認。合成ログの実Jev選別は2回で、別のCoding Agentは起動していません。

## v0.4.0 — 2026-09-24

- Add the `claude-jev-coding` Claude Code Skill (`Claude Code/`) and `install.py --target claude-code` (default `~/.claude/skills`; `--skills-dir` for project scope). The Desktop helper logic moved to the host-neutral `shared/host_context.py`. Desktop imports, artifacts and the default install behavior are unchanged. Claude Code artifacts record surface `claude-code` and are rejected by the other hosts, and the reverse also holds. Claude Code token and cost savings are not yet measured.
- Claude Code用`claude-jev-coding` Skillと`install.py --target claude-code`を追加しました。Desktopの処理はホスト非依存の`shared/host_context.py`へ移し、既存の動作は維持しています。Claude Codeでの削減効果は未測定です。

- Validation: 141 offline tests passed. Claude Code 2.1.281 discovered and invoked the Skill, completed plan/select/check/read and a native fixture edit, and passed three fixture tests. This acceptance check used local selection with zero Jev calls; no live-Jev or Claude savings benchmark is claimed.
- 検証：オフライン141件成功。Claude Code 2.1.281によるSkill検出・起動、選別・鮮度確認・範囲読込・編集・テスト３件成功を確認しました。local選別（Jev呼び出し０回）の確認であり、Claudeでの実Jev接続・削減効果の測定ではありません。

## v0.3.1 — 2026-09-24

- Rename the workflow directories to `Codex Desktop/` and `Codex cli/`; update launchers, quoted shell commands, and English/Japanese documentation links.
- Keep existing Python imports and root compatibility scripts working. Re-running `install.py` atomically migrates only this clone's old Desktop Skill symlink; unrelated Skills and existing legacy content are preserved.
- This is a packaging and naming update, with no new token/cost benchmark or model-setting change. Validation: 122 offline tests passed, including entrypoints from another working directory, Skill-link migration and failure recovery. No live provider calls.
- 方式別ディレクトリを`Codex Desktop/`と`Codex cli/`に変更し、起動パス・空白を含むコマンド・英日ドキュメントを更新しました。
- Python importとrootの互換入口は維持。`install.py`再実行で、このcloneを指す旧Skillリンクだけを移行します。他のSkillや既存の旧パス内容は保持します。新たなtoken・費用削減やモデル設定変更はありません。

## v0.3.0 — 2026-09-24

- New CLI/Desktop plans judge complete source ranges instead of bypassing files over 22 KB. Request budgeting includes serialized questions and metadata; old plans remain reproducible.
- Desktop supports bounded `read` and explicit `auto`/`local` bypass modes; the installed Skill selects before loading file bodies.
- Usage separates ordinary input and provider cache reads/writes. Optional exact-model prices report known partial subtotals; complete totals require full accounting. Efficiency claims require completed-task measurements.
- 新規planの大きいファイルを全範囲判定し、旧plan互換を維持。Desktopに範囲読込とJev省略モード、計測にcache内訳と任意単価の見積を追加。節約率の実証は別途必要です。
- Validation: 119 offline tests passed. On one identical two-file synthetic fixture, v0.2.0 → v0.3.0 fully judged files increased 1 → 2 and retained source bytes fell 27,353 → 75. Jev input increased 392 → 6,784 tokens; its API price estimate increased $0.000016464 → $0.000284928. This is a selection check, not an Astra savings result.
- 検証は119テスト成功。同じ合成入力で全体を判定できたファイルは1→2、保持本文は27,353→75 bytes。Jev入力・費用見積は増えました。この選別比較だけではAstra全体・総費用の削減を判断できません。README英日版に旧版比較と限界を追記しました。
- Completed v0.3.0 CLI coding checks used Extra High and Medium separately, one synthetic task per setting and one trial per mode. All four generations produced the same fix and passed six held-out checks. Extra High: Astra input 19,198 → 14,011 (27.0% fewer), combined Standard API-equivalent $0.201630 → $0.146695 (27.2% lower), elapsed 12.78 → 11.85 s (7.3% shorter). Medium: input 27.0% fewer and equivalent cost 26.4% lower, but elapsed time 34.6% longer. No general speedup, Desktop saving or subscription reduction is established; the distributed CLI default is still Medium.
- CLI `cache_write_input_tokens` is now recognized; conflicting fields remain unknown. Jev input totals no longer require inapplicable cache details. Fragment line numbers use the same CR/Unicode separator rules as Desktop reads.
- 実修正の比較はExtra HighとMediumを分離し、全4回とも同じ修正と6件の確認に成功。Extra Highは入力27.0%減・API換算27.2%減・時間7.3%減。Mediumは入力27.0%減・換算26.4%減でしたが時間34.6%増。各1試行のため高速化は断定せず、Desktop・実請求・契約枠への効果とも分けて掲載しました。配布CLIの既定はMediumのままです。
- CLI cache書込tokenの別名対応、Jev入力の表示、CR・Unicode改行時の行番号も修正しました。
- [Completed coding method / 実修正の比較条件](docs/BENCHMARKS.md#completed-cli-coding-check--2026-09-24) · [Extra High data / 集計値](benchmarks/cli-coding-xhigh-v0.3.0.json) · [Medium data / 集計値](benchmarks/cli-coding-v0.3.0.json)
- [Version comparison and method / バージョン比較と方法](docs/BENCHMARKS.md#v030-upgrade-check--2026-09-24) · [Aggregate data / 集計値](benchmarks/context-selection-v0.3.0.json)

## v0.2.0 — 2026-09-23

- Repositories above 2,000,000 eligible source bytes or 1,500 eligible files now get a local task-aware shortlist before Jev. Reviewed `--focus-file` paths, repository guidance, configuration and resolvable dependencies are retained; `--scope-max-calls` bounds the planned requests.
- Plans record eligible and locally scoped-out paths/bytes separately from Jev judgments. Desktop freshness checks cover omitted files, and labeled `compare` results expose local-scope misses as well as end-to-end required-file recall.
- CLI bounds large-repository candidates more tightly and checks the serialized worst-case Astra prompt before making a Jev request. An omitted file needed by Astra requires a fresh focused plan.
- Validation: 101 local tests passed. A synthetic 4.12 MB repository produced a five-file plan from 235 eligible files and completed one live Jev selection (807 input / 89 output tokens). This is a functionality check, not evidence of Astra-token savings or coding quality.

### 日本語

- 適格な本文が2,000,000バイトまたは1,500ファイルを超えるrepoでは、Jevの前に課題に基づくローカル候補絞り込みを行います。`--focus-file`、repo指示・設定・解決可能な依存を保持し、`--scope-max-calls`で予定呼び出し数を制限します。
- 絞り込み対象外とJevの判定を分けて記録します。Desktopの鮮度確認は対象外ファイルにも及び、独立した必要ファイルのラベルがあれば両段階の取りこぼしを比較できます。
- CLIは大規模repoの候補をさらに絞り、Astraへ渡すシリアライズ済み入力の上限をJev呼び出し前に検査します。対象外ファイルが必要ならfocus指定でplanを作り直します。
- 101件のローカルテストが成功しました。約4.12 MBの合成repoでは235ファイルから5ファイルのplanを作り、Jevの実呼び出し1回が成功しました（入力807 / 出力89 token）。Astra token削減や実装品質の証明ではありません。

## v0.1.0 — 2026-09-23

First tagged experimental release, upgrading the unversioned public baseline.

- CLI and Desktop can attach original evaluation excerpts with source hashes and line numbers. Explicitly pinned failure, status, budget and authorization records stay in the evidence packet; freshness checks reject changed sources.
- Jev can reuse validated responses only when the full request matches. Cache hits are reported separately from live calls and do not count old usage as new usage.
- Repository planning can include specifically reviewed untracked files without staging. Dependency retention now covers conventional Python `src/` roots and more local TypeScript alias, workspace and module-extension cases.
- Multi-run measurement separates known provider usage, cache hits and missing usage. The Desktop conversation's complete Astra usage remains unknown.
- No token or cost reduction is claimed for these additions. The earlier three-task synthetic result is historical: 1.2% fewer Astra input tokens, with longer elapsed time.

## 日本語

未バージョンの公開版を更新した、最初のタグ付き実験版です。

- CLIとDesktopに、出典hash・行番号付きの評価資料原文を渡せます。失敗・状態・予算・権限の記録は明示的に固定し、資料が変われば鮮度確認で拒否します。
- Jev応答はリクエスト全体が一致する場合だけ再利用します。キャッシュと実API呼び出し、過去と今回の使用量を区別します。
- 確認済みの未追跡ファイルをstageせずplanへ追加できます。Pythonの`src/`配置やTypeScriptの別名・workspace・拡張子の一部に対応しました。
- 複数runの計測はプロバイダー別の既知使用量・キャッシュ・不明分を分けます。Desktop会話全体のAstra使用量はまだ測定できません。
- 今回の機能によるtoken・費用削減は主張しません。過去の合成3課題ではAstra入力tokenが1.2%減り、所要時間は増えました。

[Details and limitations / 詳細と制限](docs/EVIDENCE.md) · [Historical measurements / 過去の測定](docs/BENCHMARKS.md)
