# Astra＋Jev Coding Harness

主対象はLayerisとUnsolojiです。既存ソースの編集、計画で指定したソース・テストの追加、既存テストの更新を、確認可能な計画・差分・検証結果として作るローカルCLIです。Astraは既存のCodexログイン、Jevは`TYPESAFE_API_KEY`を利用します。CodexのModelメニューやユーザー設定を書き換えません。

## 基本の流れ

CLIの入口は `python3 "Codex cli/main.py"` です。`run`時、環境変数が未設定ならmacOSキーチェーン（service `astra-jev-harness` / account `TYPESAFE_API_KEY`）から補います。`plan` / `verify` / `apply` / ヘルプと明示的な`--mode astra`ではキーチェーンを読みません。`doctor`でキーの有無・取得元だけを確認できます。`keychain_timeout` / `keychain_unavailable`はキーの不在を意味しません。

Desktop版は別方式です。[Desktopの説明](../Codex%20Desktop/README.md)を参照してください。

リポジトリルートで実行します。必要なのはPython 3.10以降、Git、ログイン済みCodex CLIです。現在の実動作検証環境はmacOS・Codex CLI 0.153.2です。

```sh
# task.txtに修正課題を書き、ローカルで対象を確認。API呼び出しなし。
python3 "Codex cli/main.py" plan --repo /absolute/path/to/repo \
  --task-file /absolute/path/to/task.txt --out /absolute/path/to/plan

# PLAN.mdの対象を確認して実行。この段階で対象コードをプロバイダーに送ります。
python3 "Codex cli/main.py" run --plan /absolute/path/to/plan \
  --out /absolute/path/to/run --mode auto \
  --verify-json '["python3", "-B", "-m", "unittest", "discover"]'

# changes.diffと検証結果を確認後、元リポジトリへ適用。
python3 "Codex cli/main.py" apply --run /absolute/path/to/run
```

`--verify-json`は対象プロジェクトに合ったテストコマンドへ変更してください。コマンドは引数配列で受け取り、shell文字列として実行しません。モデルは検証コマンドを決定しません。

## 大きなリポジトリのplan

適格ファイル全体が2,000,000バイトまたは1,500ファイルを超える場合、`plan`は課題文とパス・本文の語の一致を使い、**ローカルで**候補を絞ります。Jevを呼ぶ前の処理です。CLIの絞り込み後の候補は最大350,000バイトに抑え、Astraへ送るプロンプトの500,000バイト上限に余地を残します。`run`は全候補を含む実際のシリアライズ済みプロンプトをJev呼び出し前に検査し、上限超過なら停止します。`--scope-max-calls`はJevの計画上のリクエスト数の上限で、既定4回、指定範囲1〜24回です。`run`時の実行上限とは別です。全体が元の上限内なら従来のplan動作のままで、この新しい絞り込みは行いません。

課題の重要なファイルが分かっている場合は、繰り返し指定できる`--focus-file`で固定します。未追跡ファイルは別途`--include-file`で明示してください。固定指定でも秘密情報・非対応形式・100 KBの単一ファイル上限を迂回できません。

```sh
python3 "Codex cli/main.py" plan --repo /absolute/path/to/repo \
  --task-file /absolute/path/to/task.txt --out /absolute/path/to/plan \
  --focus-file src/pagination.py --focus-file tests/test_pagination.py \
  --scope-max-calls 4
```

`PLAN.md`と`plan.json`の`scope`には、元の適格ファイル数/バイト数、絞り込み対象外の数/バイト数、候補上限、予定Jev呼び出し数が残ります。`scoped_out`は適格だが今回の候補から外れたパスであり、保護規則による`excluded`とも、Jevが「無関係」と判定したファイルとも異なります。AGENTS.md・主要設定・解決できる依存ファイルは候補に残します。語の一致は翻訳しないため、ASCIIのパスや識別子を含まない日本語だけの課題では`--focus-file`が必要になる場合があります。課題とファイルの一致がなく必須パスの明示もない場合、または固定ファイル・必須情報が上限を超える場合は、黙って削らずplanを停止します。課題または`--focus-file`を具体化し、新しいplanを作成してください。対象外ファイルの本文はJev・Astraに送りませんが、CLIはAstraに対象外の名前を最大512件と総件数を渡し、不足ファイルを要求できるようにします。必要ファイルの取りこぼし率とAstraトークン削減量は、この処理だけでは分かりません。

## 新規ファイルと既存テストの変更計画

追加先と更新するテストは、plan時にrepoルートからの相対パスで指定します。各オプションは繰り返し指定できます。

```sh
python3 "Codex cli/main.py" plan --repo /absolute/path/to/repo \
  --task-file /absolute/path/to/task.txt --out /absolute/path/to/plan \
  --allow-create src/helper.py \
  --allow-create tests/test_helper.py \
  --allow-test-edit tests/test_existing.py
```

- `--allow-create`は存在しないファイルだけを許可します。必要な親ディレクトリは作成します。既存・未追跡・ignoredファイルへの上書き、symlink、パスの脱出、重複・大小文字だけが異なる追加先、保護対象は拒否します。
- `--allow-test-edit`はスナップショットに含まれる既存テストだけを許可します。`test` / `tests` / `__tests__`配下、`test_*`、`*_test.py`、`.test.` / `.spec.`を含むファイルと`conftest.py`をテストとして扱います。
- 指定がなければ従来どおり既存ソースだけを編集します。指定パスは許可範囲であり、すべてを変更する義務ではありません。AGENTS.md・policiesは変更できません。
- 許可内容は`PLAN.md`と`plan.json`に保存し、生成スキーマとローカル検査の両方に使います。許可を追加する場合は新しいplanを作成してください。追加権限を持つplanはversion 2で保存し、旧CLIでは実行できません。version 1の既存planは引き続き読み込めます。
- `changes.diff`には新規・空ファイルも表示します。新規ファイルのモードは0644です。既存ファイルのモードは保持します。

検証コマンドには既存回帰テストと課題の受入条件を含めてください。テスト編集後の終了コード0だけでは、既存の検査を弱めていないことまで保証できません。テスト差分と実装差分の両方をレビューします。

## ルーティング

- `auto`: 対象コードが12KB未満ならAstra単独、それ以上ならJevを使用。12KBは運用上の仮置きで、費用対効果を保証する閾値ではありません。
- `astra`: 全候補をAstraへ渡します。Jevキー不要。
- `jev`: Jevによる選別を必ず実行します。

Jevはファイル本文をバッチで読み、確率が0.8以上を採用、0.2以下を除外します。曖昧なバッチは全件を保持。全体で対象が見つからなければ全件に戻します。大きな単独ファイルは途中で切らず保持します。AGENTS.md・policy・主要設定と、静的に解決できるPython・相対JSインポートを追加で保持します。パスエイリアスや動的importを完全に追跡する解析器ではありません。

Astraがplan内の不足ファイルを指定した場合は、同じスナップショットから追加して1回だけ再生成できます。`scoped_out`のファイルが必要な場合は、`--focus-file`を指定して新しいplanを作成します。Astraのツール使用は検知して失敗扱いにします。

## 状態と復旧

| 状態 | 意味 |
|---|---|
| `unverified` | 差分を作成したがテストコマンド未指定。適用不可 |
| `verification_failed` | テストまたは実行環境で失敗。適用不可 |
| `verified` | 指定テストが成功。レビュー後に適用可能 |
| `applied` | 明示的なapplyで元ファイルへ適用済み。コミット・pushはしていない |
| `failed` / `cancelled` / `apply_failed` | 失敗・中断。詳細はresult.json |

テスト環境の問題を直した後は、モデルを再呼び出さず検証だけを再実行できます。

```sh
python3 "Codex cli/main.py" verify --run /absolute/path/to/run
```

元ファイル、Git状態、計画、候補コード（追加ファイルを含む）が変わっていれば適用を拒否します。新規ファイルは宛先が存在しない場合だけ原子的に追加し、適用中に現れたファイルを上書きしません。

適用中の通常の書き込みエラーでは、他者に変更されていない適用済みファイルを戻し、今回追加したファイルと空の親ディレクトリを取り除きます。他者の変更や復旧時のエラーで戻せないファイルは`result.json`の`recovery_incomplete`へ記録します。プロセス強制終了や電源断、同時に親ディレクトリが置換される場合などに対する完全なトランザクション保証はありません。

## 範囲と制限

- Git管理されたUTF-8テキストを対象にします。作業中の追跡済み変更はその内容をスナップショットします。未追跡ファイルは対象外です。
- `.env`、鍵・DBファイル、生成物、ルートのdata/uploads、credentialパターンを含むファイルなどを除外し、理由をPLAN.mdへ記録します。パターン検査は秘密情報の完全検出を保証しません。送信前に対象を確認してください。
- 元リポジトリへの書き込みはapplyのみです。実行用コピーには採用されなかったファイルも含め、テストに必要な全スナップショットを配置します。
- ファイル削除、AGENTS.md・policiesの変更、マイグレーション適用、デプロイ、Model登録は扱いません。
- スナップショットと生成後の候補は最大2MB・1500ファイル、各ファイル100KB。大きなrepoの自動絞り込みでは、CLI用planの本文をさらに350,000バイト以内に抑えます。追加予定ファイルも件数に含めます。Jev最大24リクエスト、Astra最大2回。Astraのプロンプト上限は別に500,000バイトで、元の上限内にあるrepoも含め、超過時は停止します。
- 依存パッケージの自動インストールはしません。node_modulesやvenvはコピーしません。依存関係のあるプロジェクトでは、隔離コピーで動く検証環境を先に用意する必要があります。
- 検証はCodexの`:read-only`プロファイルで実行し、環境変数は必要最小限にします。macOSで候補への書き込みとネットワークの拒否を実測済みです。ユーザーのHOME等の読み取りを完全隔離する仕組みではなく、敵対的な任意コード用サンドボックスではありません。
- 検証コマンドの終了コード0だけで品質を完全に保証しません。適切なテストを指定し、差分をレビューしてください。

## 再現用サンプル

```sh
python3 make_demo.py /absolute/path/to/new-demo-repo
```

53個の対象ファイルを持つ合成リポジトリを作成します。ページ番号を1始まりにし、size=Noneなら既存設定、size<1なら1を使う修正課題で検証できます。テストコマンドは上記unittestです。初期状態では6つの境界値が失敗します。

自動テストは`python3 -m unittest -v`で実行できます。旧3課題ベンチマークは`harness.py`としてそのまま残しています。

## 選別の診断

Jev利用時の`result.json` → `selection`には、ファイルごとの判定・保持理由、未判定パス、候補と選択後のバイト数を記録します。CLIの既定は従来のバッチ単位の保守的保持です。Desktopの実験用per-file方式をCLI生成へ自動適用しません。

## モデル設定

通常の`run`は、Codex CLIのユーザー設定・信頼済みプロジェクト設定にある`model`と`model_reasoning_effort`を引き継ぎます。Astra・Mediumへの固定指定はありません。未設定の項目はCodexの既定に委ねます。Desktop会話やCLI対話セッションだけで一時的に選んだモデルは引き継ぎません。

ローカルの`config/read`で生成前に読み取り、２項目だけを隔離した生成プロセスに渡します。MCP・プラグイン・権限など他の設定はコピーしません。設定取得に失敗した場合はJev呼び出し前に停止します。独自プロバイダーと旧形式のprofile指定は未対応のため拒否します。`--profile`の選択にも対応していません。

記録の`requested_model`・`requested_reasoning`は指定値です。実際に応答したモデル・推論強度がCLIイベントから確認できないため、`model`・`reasoning`はnullとし、モデル別費用も不明として扱います。過去のベンチマーク設定・測定結果は変更しません。[詳細](../docs/CLI.md#model-verification-and-limits)。

## Optional command-output selection / 任意のコマンド出力選別

The root [`output.py`](../output.py) wrapper is available for explicitly routed commands in a normal Codex CLI session. It preserves the selected model/login and retains recoverable original logs. It is not automatically invoked by this harness's isolated generation process. See [usage, limits and measurements](../docs/TOOL-OUTPUT.md).

通常のCodex CLIセッションで長い進捗ログを扱う場合は、rootの`output.py`を明示的に使えます。モデルとログインを維持し、原文を後から復元できます。このハーネス内の隔離された生成プロセスには自動適用しません。
