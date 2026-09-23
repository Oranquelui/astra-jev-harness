# Changelog / 変更履歴

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
