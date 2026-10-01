# Claude Code用エージェントスキル

[English](README.md) · [リポジトリ全体の説明](../README-ja.md)

[`claude-jev-coding`](skills/claude-jev-coding/SKILL.md)は、Claude Codeで使うエージェントスキルです。現在のClaude Codeセッションが通常のツールで実装・レビュー・変更に応じた検証を行い、Jevはファイルの関連性だけを判定します。インストール済みのwrapperは`bin/astra-jev claude-code`を実行し、Desktopと共通のnative処理を使います。Codex・Astra・別のコーディングエージェントを起動することはありません。

ビルド済みの`bin/astra-jev`とGitが必要です。Harnessの実行にPythonは不要です。

## インストールと確認

cloneしたハーネスのリポジトリルートで実行します。

```sh
# インストール予定の内容だけを表示。書き込みは行いません。
bin/astra-jev install --target claude-code --check

# ~/.claude/skills/claude-jev-coding にリンクを作成します。
bin/astra-jev install --target claude-code

# 特定プロジェクトだけで使う場合は、代わりに配置先を指定します。
bin/astra-jev install --target claude-code --skills-dir "/absolute/project/.claude/skills"
```

インストーラーは、このcloneを指すシンボリックリンクを１つ作成します。再実行時は`already-installed`と表示します。同名の別ファイル・ディレクトリ・シンボリックリンクがある場合は、リンク切れであっても上書きしません。Claude CodeやTypeSafeの認証情報を読み取ったりコピーしたりせず、設定・モデル・権限も変更しません。

リンク先となるcloneは移動・削除せず保持してください。アンインストールする場合は、作成されたリンクだけを削除します。`--target`を付けずに`bin/astra-jev install`を実行した場合は、従来どおりCodex Desktop用Skillをインストールします。

個人用ディレクトリにインストールした場合は、次で確認できます。

```sh
~/.claude/skills/claude-jev-coding/scripts/context.sh doctor
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

## ローカル継続

ユーザーがJevなしを選んだ場合、必須ファイルの予算超過、認証情報の利用不可、Jevの障害では、原因と「Jev未検証 — ローカルで継続」を一度伝え、現在のセッションで許可済みの作業を続けます。同じ課題と範囲内の継続作業では選択を引き継ぎ、許可を聞き直しません。Jevの成功自体が明示的な完了条件なら、その項目は未完了として残します。

新鮮で十分なClaude用planがあれば、インストール済みの`scripts/context.sh`で`select --mode local`・`check`・`read`を実行できます。Desktop用の`--require-jev`は付加しません。localはplan内の候補を未判定として保持し、`scoped_out`は復元しません。`present`には引き続きJev判定が必要です。十分なplanがなければ、実際に必要なファイルを通常ツールで範囲読み取りし、鮮度・秘密情報・既存差分・許可範囲を守ります。失敗記録を残し、自動再試行や、planを成功させるための必須依存の削除・上限の反復引き上げはしません。[手順と制約](skills/claude-jev-coding/references/workflow.md#local-continuation)。

通常の返信は変更・検証・対処が必要な問題に絞ります。使用量は明示的な依頼時だけ保存済み記録から回答し、報告のためのAPI呼び出しやベンチマークは追加しません。

## 認証情報と制限

helperは利用者自身の環境変数`TYPESAFE_API_KEY`を使います。macOSでは、login Keychainに設定済みのservice `astra-jev-harness`、account `TYPESAFE_API_KEY`の項目も利用できます。取得したキーはhelperのプロセス内だけで使用します。

Jevの使用量は`selection.json`に記録します。Claude Codeの会話全体の使用量とは別であり、helperから会話全体の使用量を測ることはできません。

会話の圧縮、hooks、MCPサーバーは実装していません。**Claude Codeでのtoken・費用削減効果は未測定です。** 公開済みベンチマークの対象はCodex CLI版だけです。

## 検証済みの範囲

2026年９月24日にClaude Code 2.1.281を使い、隔離した合成Gitリポジトリで、プロジェクトにインストールしたSkillの検出・呼び出しを確認しました。リンク先のhelperでplan作成・local選別・鮮度確認・行範囲の読み取りを行い、Claude Code自身のツールでテスト用コードを編集しました。テストの期待値を維持したまま、３件の受け入れテストがすべて成功しています。

保存した選別結果では、Jevの試行・完了回数と子プロセスによる生成回数はすべて０回です。これはlocalモードでのSkill動作確認であり、Claude Codeから実際にJevを呼んだベンチマークではありません。Jevとの連携処理は、プロバイダー応答を模擬したオフラインテストで確認しています。同時点で`claude plugin validate "Claude Code/skills"`とハーネスのオフラインテスト141件が成功しました。
