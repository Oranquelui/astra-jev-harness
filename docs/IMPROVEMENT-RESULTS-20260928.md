# 2026-09-28 改善実装・検証の記録

起点: `codex/keel-improvement-plan` / `f0caf8424f99e43c757221a75217f525a161155b`。指定worktreeで実施し、古い標準checkoutは編集していない。開始時の差分なし。

## 実装

- **P1-A**: `measure.py`で既存CLI/host/evidence/tool-outputを明示的に識別し、tool-output version 1の`calls`を統合。未知形式、失敗・途中完了、欠測、cache再利用、別実呼出し、重複artifactを区別する。元記録は読み取りのみ。
- **J1**: `present`で保持と提示を分離。全文保持は維持し、原文hash・行番号・未提示範囲・次ページをJSON出力予算内に返す。Jev必須guard・surface・鮮度を維持。
- **J2初版**: `discover`で候補外のディレクトリ→短い原文→focus再計画→Jev select/checkへ進める。複数の枝を全ページに残す。操作型探索であり、自動の意味検索ではない。
- **Python依存**: 全入口とinstallerの依存を調査し、[同梱CPython配布案](PYTHON-DISTRIBUTION-PROPOSAL.md)を作成。実行構成の変更は提案への承認待ち。現状はPythonが必要。

P1-B/P2（永続的な結果関連付け・共有API予算）は未実装。J3–J5は、追加質問・構文単位・retry・batch/cache変更が必要と判断できる実測がないため保留。既定のbatch選別を変更していない。

## 開発時のJev使用

明示指定されたDesktop Skillのplan/select/checkを実行。会話モデルは実行メタデータで`gpt-6-astra` / `high`と確認。別のCodex CLIで生成していない。

| 項目 | 結果 |
|---|---:|
| 適格ファイル | 79 |
| Jev送信候補 | 37 |
| ローカル候補外（未評価） | 42 |
| 実API試行 / 完了 | 12 / 12 |
| cache再利用 | 0 |
| Jev入力 / 出力token | 83,571 / 813 |
| 判定済み範囲 | 45 |
| 保持ファイル | 37 / 37 |
| 保持原文bytes | 267,517 / 267,517 |
| Astra child生成 | 0 |

Jev前のローカル絞り込みは発見率の証明ではない。全保持されたためJev選別による原文削減は0%。キー・snapshot・API応答・実行ログはGitへ追加していない。

## J1の保存済み記録によるローカル評価

同じ選別記録を用いた**歴史的な表示再生**。変更後のrepoへ古いcontextを適用する許可ではない。追加APIは0回。

- 全文保持267,517 bytesを変更しない。
- `max_bytes=8192`、各ファイル12行で、初回ページは7ファイル、原文3,459 bytes、JSON全体（末尾改行込み）5,750 bytes。
- 未提示のファイル・行範囲にはreading leadが残る。初回ページだけで実装に十分かは未測定。
- Astra会話token、Jevを含む総費用削減、実請求額、再読込、総作業時間、受入品質は未測定。

## 検証

`python3 -m unittest -v`: **198 tests passed**（183既存 + 15追加）。fixtureは合成repoと偽providerを使用。

追加検証はtool-output＋CLI統合、未知形式、失敗・usage欠測、cache欠測、同一requestの別実呼出し、cache履歴の非加算、重複path、モデル別単価、原記録の非変更を含む。J1/J2はUnicode/CRLF原文一致、長行の明示的未提示、出力全体の上限、ページ網羅、2つの探索枝、発見ファイルの再計画と既存focus維持、秘密除外、鮮度、artifact改変、surface誤用、local-only拒否、コマンド実行を含む。

この検証は回帰・機構の確認。独立した未使用課題でのcoding品質、Astra token、総費用の比較ではない。CI・Preview・本番・release・ユーザー受入は未実施。

## 次の判断

Python配布方式の承認後、固定runtime assetとhashを決め、配布実装とPythonなし環境の検証へ進める。J2の自動化や選別policy調整は、必要ファイルを独立にラベル付けした反復課題で発見率・再読込・正解・総費用を測ってから判断する。
