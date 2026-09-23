# Changelog / 変更履歴

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
