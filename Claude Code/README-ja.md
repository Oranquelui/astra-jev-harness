# Claude Code用エージェントスキル

[English](README.md) · [リポジトリ全体の説明](../README-ja.md)

[`claude-jev-coding`](skills/claude-jev-coding/SKILL.md)は、Claude Codeで使うエージェントスキルです。現在のClaude Codeセッションが通常のツールで実装・レビュー・変更に応じた検証を行い、Jevはファイルの関連性だけを判定します。`Claude Code/context.py`は、Codex Desktop版と共通の選別処理（`shared/host_context.py`）を呼び出すツールです。Codex・Astra・別のコーディングエージェントを起動することはありません。

Python 3.10以上とGitが必要です。追加のPythonパッケージは不要です。

## インストールと確認

cloneしたハーネスのリポジトリルートで実行します。

```sh
# インストール予定の内容だけを表示。書き込みは行いません。
python3 install.py --target claude-code --check

# ~/.claude/skills/claude-jev-coding にリンクを作成します。
python3 install.py --target claude-code

# 特定プロジェクトだけで使う場合は、代わりに配置先を指定します。
python3 install.py --target claude-code --skills-dir "/absolute/project/.claude/skills"
```

インストーラーは、このcloneを指すシンボリックリンクを１つ作成します。再実行時は`already-installed`と表示します。同名の別ファイル・ディレクトリ・シンボリックリンクがある場合は、リンク切れであっても上書きしません。Claude CodeやTypeSafeの認証情報を読み取ったりコピーしたりせず、設定・モデル・権限も変更しません。

リンク先となるcloneは移動・削除せず保持してください。アンインストールする場合は、作成されたリンクだけを削除します。`--target`を付けずに`python3 install.py`を実行した場合は、従来どおりCodex Desktop用Skillをインストールします。

個人用ディレクトリにインストールした場合は、次で確認できます。

```sh
python3 ~/.claude/skills/claude-jev-coding/scripts/context.py doctor
```

`doctor`は`"surface": "claude-code"`、リンク先のcheckout、APIキーを利用できるかを表示します。キーの値は表示せず、プロバイダーAPIも呼び出しません。

## 呼び出し方とモデル設定

Claude CodeはSkillの説明に応じて自動的に読み込めます。明示的に呼び出す場合は、対象プロジェクトのClaude Codeセッションで次のように指示します。

```text
/claude-jev-coding このcheckoutのページングを、公開APIを変えずに修正してください。
```

Skillは、**現在のClaude Codeセッションで選択しているモデルと推論強度をそのまま使います**。モデル・effortの上書き、ツールの事前承認、contextのfork、シェル出力の自動挿入は行いません。各helperコマンドにはClaude Codeの通常の権限確認が適用されます。

## コマンド

`plan`、`select`（`--mode auto|jev|local`、`--policy batch|per-file`、`--max-calls`、`--cache-dir`、`--evidence`）、`check`、`read`、`compare`、`doctor`の動作は、[Codex Desktop版のhelper](../Codex%20Desktop/README.md)と共通です。異なる点は次のとおりです。

- 新しいplan・選別結果にはsurface `claude-code`を記録します。Claude Code版はDesktop・CLI版のplanや選別結果を受け付けず、Desktop・CLI版もClaude Code版の成果物を受け付けません。
- Jevを呼ばない経路は`local`と記録します。子プロセスによる生成回数の項目は`astra_child_calls`ではなく、`child_generation_calls: 0`です。

## 認証情報と制限

helperは利用者自身の環境変数`TYPESAFE_API_KEY`を使います。macOSでは、login Keychainに設定済みのservice `astra-jev-harness`、account `TYPESAFE_API_KEY`の項目も利用できます。取得したキーはhelperのプロセス内だけで使用します。

Jevの使用量は`selection.json`に記録します。Claude Codeの会話全体の使用量とは別であり、helperから会話全体の使用量を測ることはできません。

会話の圧縮、hooks、MCPサーバーは実装していません。**Claude Codeでのtoken・費用削減効果は未測定です。** 公開済みベンチマークの対象はCodex CLI版だけです。

## 検証済みの範囲

2026年９月24日にClaude Code 2.1.281を使い、隔離した合成Gitリポジトリで、プロジェクトにインストールしたSkillの検出・呼び出しを確認しました。リンク先のhelperでplan作成・local選別・鮮度確認・行範囲の読み取りを行い、Claude Code自身のツールでテスト用コードを編集しました。テストの期待値を維持したまま、３件の受け入れテストがすべて成功しています。

保存した選別結果では、Jevの試行・完了回数と子プロセスによる生成回数はすべて０回です。これはlocalモードでのSkill動作確認であり、Claude Codeから実際にJevを呼んだベンチマークではありません。Jevとの連携処理は、プロバイダー応答を模擬したオフラインテストで確認しています。同時点で`claude plugin validate "Claude Code/skills"`とハーネスのオフラインテスト141件が成功しました。
