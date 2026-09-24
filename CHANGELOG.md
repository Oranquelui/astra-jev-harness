# Changelog / 変更履歴

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
