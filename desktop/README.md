# Codex Desktop app版

現在の会話モデル（Astraを選択した場合はAstra）が実装・レビュー・検証を行い、Jevをコンテキスト選別に使います。`desktop/context.py`は選別用のローカルツールです。別のCodex CLIを起動してコード生成する方式は[cli/](../cli/README.md)へ分離しました。

Python 3.10以降とGitを使用し、追加Pythonライブラリは不要です。下記はリポジトリルートから実行します。

```sh
python3 desktop/context.py doctor
python3 desktop/context.py plan --repo /absolute/target/repo \
  --task-file /absolute/task.txt --out /absolute/context-plan
python3 desktop/context.py select --plan /absolute/context-plan \
  --out /absolute/context-selection --max-calls 4
python3 desktop/context.py check --selection /absolute/context-selection
```

`plan`はAPIを呼ばず、対象を変更しません。`PLAN.md`に送信候補、除外理由、必要なリクエスト数を示します。対象はGit追跡中の現在のファイル内容です。既存の未コミット変更は含まれ、未追跡ファイルは既定では含まれません。確認したファイルを`--include-file`で明示指定できます。stageは不要です。

`select`だけがJevを呼びます。上限は既定4回、指定可能範囲1〜24回。必要な回数が上限を超える場合は送信前に拒否します。各呼び出しの直前・完了後に`selection.json`を更新し、自動再試行はしません。失敗時も完了分の応答・使用量と試行回数が残ります。応答を受け取れなかった試行も課金された可能性があり、再実行前に記録を確認します。同じ出力ディレクトリへの再実行は拒否します。

`context.json`が会話へ渡す課題・選択ファイル本文です。`selected`は選別完了だけを表します。会話は`check`で鮮度を確かめてから本文を読み、許可済みの実装と検証を通常のツールで進めます。コード変更後に再選別するなら新しいplanを作成してください。

`check`はHEAD・branch・Git status・収録ファイルの本文/モード・plan/contextのハッシュを照合します。継続的ロックではないため、会話側も編集直前の状態を確認します。planは編集権限を付与しません。run/verify/applyコマンドはCLI版だけのものです。

## Skillと資格情報

`desktop/skills/astra-jev-coding`をユーザーのSkillディレクトリから参照します。インストール済みSkillの`python3 ~/.codex/skills/astra-jev-coding/scripts/context.py doctor`（`CODEX_HOME`を変更した場合は対応するパス）はsymlinkを解決して、このcheckoutの入口を使います。checkoutを削除・移動する際は参照も更新してください。

`TYPESAFE_API_KEY`を優先し、未設定のmacOS環境ではlogin Keychainのservice `astra-jev-harness` / account `TYPESAFE_API_KEY`から取得します。キー値を出力せず、helperプロセス内だけで使います。`doctor`は外部APIを呼びません。plan/check/ヘルプはKeychainを読みません。

## 選別の限界

候補は最大2 MB・1500ファイル・1ファイル100 KBです。秘密情報のパターン、lockfile、生成物、データ、未対応拡張子は除外します。22 KBのバッチ許容量を超えるファイルは推論せず保持します。すべてがその条件に該当すればAPI呼び出しは0回です。選別結果は実呼び出し数と区別してください。

各バッチ内の独立したNoul質問をまとめて送ります。中間の確率は保守的に保持し、解決できる依存ファイルとAGENTS.md/policiesを補います。閾値は実験値です。未解決のimportや除外ファイルの影響は会話側でも確認します。

会話履歴の自動圧縮やDesktop全体の使用量計測は行いません。ファイル数削減だけで費用・速度改善を保証できません。保存物はソースを含み、対象リポジトリ外に置いてGitへ追加しません。

## 判定理由とオフライン比較

`selection.json`の`decisions`はファイルごとの確率・関連/無関係/不確実/未判定・保持理由を示します。`unjudged_paths`に載るファイルはJevが判定していません。`metrics`は候補/選択/判定/未判定/除外の件数と本文バイト数を記録します。除外はplan作成時の別枠であり、無関係と判定されたことを意味しません。関連性の判定は安全性の検査ではありません。

既定の`batch`は、1件でも不確実ならそのバッチ全体を保持する従来方式です。追加した`per-file`は、不確実なファイルを保持しつつ、同じバッチの確率0.2以下のファイルを省く実験用オプションです。未判定ファイル・解決できる依存関係・設定・指示ファイルの補完、全件不一致時の全保持を維持します。

```sh
# 同じ保存済み確率で比較。API・Keychainへのアクセスも書き込みも行いません。
python3 desktop/context.py compare --selection /absolute/context-selection

# 課題の必要ファイルを独立に特定済みなら、取りこぼしも比較できます。
python3 desktop/context.py compare --selection /absolute/context-selection \
  --required-file src/main.py --required-file tests/test_main.py

# 比較で省略内容を確認してから、新規selectで明示的に採用します。
python3 desktop/context.py select --plan /absolute/context-plan \
  --out /absolute/new-selection --max-calls 4 --policy per-file
```

`compare`は過去のplanハッシュと保存済み応答を使う歴史的比較です。現在のrepoが変更済みでも動きますが、古いcontextの消費許可は付与しません。失敗/途中の記録も比較でき、未判定は保持します。必要ファイルのラベルがなければ`required_recall`はnullです。ラベルがある場合も、そのラベルに対する保持率であり実装正解率ではありません。CLI版は共有診断を記録しますが、生成経路の既定選別方式を変更していません。

## 評価資料・再利用・失敗診断

`--evidence`、`--cache-dir`、安全な失敗記録と計測の使い方は[共通ガイド](../docs/EVIDENCE.md)を参照してください。
