# Codex Desktop用Agent Skill

[`astra-jev-coding`](skills/astra-jev-coding/SKILL.md)はCodex Desktopで使うCodex Agent Skillです。現在の会話モデル（Astraを選択した場合はAstra）が実装・レビュー・検証を行い、Jevをコンテキスト選別に使います。`desktop/context.py`は選別用のローカルツールです。別のCodex CLIを起動してコード生成する方式は[cli/](../cli/README.md)へ分離しました。

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

適格ファイル全体が2,000,000バイト・1,500ファイル・予定呼出数のいずれかの上限を超えるrepoでは、`plan`が課題文とファイルの語の一致で候補をローカルに絞り、最大2,000,000バイトのplanにします。`--focus-file`は重要と分かっている適格ファイルを固定し、繰り返し指定できます。`--scope-max-calls`は候補全体の**予定**Jevリクエスト数を制限し、既定4回、指定範囲1〜24回です。すべての上限内なら全文候補を維持します。

```sh
python3 desktop/context.py plan --repo /absolute/target/repo \
  --task-file /absolute/task.txt --out /absolute/context-plan \
  --focus-file src/pagination.py --focus-file tests/test_pagination.py \
  --scope-max-calls 4
```

`PLAN.md`には元の適格ファイル数/バイト数、絞り込み対象外のパス/バイト数、予定呼び出し数を記録します。`plan.json`の`scope`が集計、`scoped_out`が対象外の適格ファイルです。これらは保護規則で除いた`excluded`や、Jevが無関係と判定したファイルとは別です。AGENTS.md、主要設定、解決できる依存は候補に残します。語の一致は翻訳しないため、ASCIIのパスや識別子を含まない日本語だけの課題では`--focus-file`が必要になる場合があります。課題とファイルの一致がなく必須パスの明示もないとき、または固定ファイル・必須情報が上限を超えるときはplanが停止するため、課題または`--focus-file`を具体化して作り直してください。固定指定は適格性や100 KBの単一ファイル上限を迂回しません。未追跡ファイルは別途`--include-file`で明示します。

`select`だけがJevを呼びます。実行上限`--max-calls`は既定4回、指定可能範囲1〜24回で、plan時の`--scope-max-calls`とは別です。必要な回数が上限を超える場合は送信前に拒否します。各呼び出しの直前・完了後に`selection.json`を更新し、自動再試行はしません。失敗時も完了分の応答・使用量と試行回数が残ります。応答を受け取れなかった試行も課金された可能性があり、再実行前に記録を確認します。同じ出力ディレクトリへの再実行は拒否します。

`context.json`は全文保管用です。会話へ全体を展開せず、`read --selection /absolute/selection --path src/main.py --start-line 1 --end-line 80`で必要行だけ取得してください。`selected`は選別完了だけを表します。会話は`check`で鮮度を確かめてから本文を読み、許可済みの実装と検証を通常のツールで進めます。コード変更後に再選別するなら新しいplanを作成してください。

`check`はHEAD・branch・Git status・収録ファイルの本文/モード・plan/contextのハッシュを照合します。継続的ロックではないため、会話側も編集直前の状態を確認します。planは編集権限を付与しません。run/verify/applyコマンドはCLI版だけのものです。

## Skillと資格情報

`desktop/skills/astra-jev-coding`をユーザーのSkillディレクトリから参照します。インストール済みSkillの`python3 ~/.codex/skills/astra-jev-coding/scripts/context.py doctor`（`CODEX_HOME`を変更した場合は対応するパス）はsymlinkを解決して、このcheckoutの入口を使います。checkoutを削除・移動する際は参照も更新してください。

`TYPESAFE_API_KEY`を優先し、未設定のmacOS環境ではlogin Keychainのservice `astra-jev-harness` / account `TYPESAFE_API_KEY`から取得します。キー値を出力せず、helperプロセス内だけで使います。`doctor`は外部APIを呼びません。plan/check/ヘルプはKeychainを読みません。

## 選別の限界

絞り込み後の候補も最大2 MB・1500ファイル・1ファイル100 KBです。秘密情報のパターン、lockfile、生成物、データ、未対応拡張子は除外します。新規planは大きいファイルの全範囲を分割して判定します。未判定・不確実な範囲があれば全文を保持します。旧planは従来のバッチ動作を再現します。選別結果は実呼び出し数と区別してください。ローカル絞り込みの必要ファイル保持率は、独立に必要ファイルを特定しなければ不明です。

各バッチ内の独立したNoul質問をまとめて送ります。中間の確率は保守的に保持し、解決できる依存ファイルとAGENTS.md/policiesを補います。閾値は実験値です。未解決のimportや除外ファイルの影響は会話側でも確認します。

会話履歴の自動圧縮やDesktop全体の使用量計測は行いません。ファイル数削減だけで費用・速度改善を保証できません。保存物はソースを含み、対象リポジトリ外に置いてGitへ追加しません。

## 判定理由とオフライン比較

`selection.json`の`decisions`はファイルの関連/無関係/不確実/未判定・保持理由を示します。分割されたファイルの`probability`はnullで、範囲ごとの確率は`fragment_decisions`にあります。`unjudged_paths`に載るファイルには、Jevの判定がない範囲が残っています。`metrics`は候補/選択/判定/未判定/除外の件数と本文バイト数を記録します。除外はplan作成時の別枠であり、無関係と判定されたことを意味しません。関連性の判定は安全性の検査ではありません。

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

`compare`は過去のplanハッシュと保存済み応答を使う歴史的比較です。現在のrepoが変更済みでも動きますが、古いcontextの消費許可は付与しません。失敗/途中の記録も比較でき、未判定は保持します。`--required-file`にはplan内または`scoped_out`に載る、独立に特定した必要パスを指定できます。`scope_required_recall`と`missing_in_scope`はローカル絞り込みの保持率と欠落、`required_recall`はJev選別後まで含む保持率です。ラベルがなければこれらは不明で、ラベルがあっても実装正解率ではありません。CLI版は共有診断を記録しますが、生成経路の既定選別方式を変更していません。

## 評価資料・再利用・失敗診断

`--evidence`、`--cache-dir`、安全な失敗記録と計測の使い方は[共通ガイド](../docs/EVIDENCE.md)を参照してください。

## 本文の読み方と呼び出し省略

本文を会話へ出す前にplan/selectを実行します。`select --mode auto`は12,000本文bytes未満なら全候補を保持してJevを省略、`--mode local`は明示的に省略します。既定は`jev`です。`read`は鮮度確認後に80行既定・最大200行/24 KBを返し、APIを呼びません。通常入力・cache read/write・料金見積の区別と分割の仕様は[共通ガイド](../docs/CONTEXT-BUDGETS.md)を参照してください。
