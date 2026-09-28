# Keelを参考にした計測・予算・選別評価の改善計画

作成日: 2026-09-27

**2026-09-28更新: P1-Aを実装。P1-B/P2/P3は未実装。検証・測定の記録は[今回の結果](IMPROVEMENT-RESULTS-20260928.md)を参照。**

以下の承認範囲は2026-09-27の計画保存時点の記録。2026-09-28の再開依頼でP1-A/J1/J2の実装・検証・ローカルcommitが追加承認された。公開操作は未承認。

計画保存時の承認範囲は、この計画の記録とローカルcommitまで。機能実装、設定変更、性能比較の実行、push、PR、merge、release、Skill更新は含めない。再開用の計画であり、自動実行や予約ではない。

## 目的と確認時点

Astraの消費tokenとJevを含む総費用を減らし、コードの正しさを維持して再読込・手戻り・完了時間を抑える。計測だけで削減したとは扱わず、比較可能な作業結果で判断する。

- 対象: `astra-jev-harness` v0.5.1、確認したmainは `433000718d3c7877979df49953c07909ca51ea02`。
- 参考: Keel `5cef4569e7f850b3a85dc998cc64c64e944c80a0`。本計画は設計上の参考で、コードの移植・依存追加は行わない。
- 方式: Pythonの既存CLI／Desktop／Claude Codeの分離を維持。Desktopから別のCodex CLIを起動しない。利用中のモデル・推論強度を勝手に変えない。
- 現在の評価: 過去の限定的なCLI試験は存在するが、Desktop／Claude Code会話全体の節約率は未測定。bytes、モデルtoken、API単価換算、実請求額、契約枠を区別する。

## 確認済みの現状と不足

| 項目 | 実装済み | 改善候補 |
|---|---|---|
| 使用量 | `measure.py`がCLI／選別記録を集計し、欠測・失敗・cache read/writeを区別する | 出力選別の`report.json`にある`calls`を取り込めない |
| 判断記録 | ファイル／範囲の確率、保持理由、API試行・失敗、鮮度確認がある | 複数段階の判断を課題全体の追加読込・検証・手戻りへ結び付ける規約がない |
| API上限 | 各コマンドに呼出上限があり、自動retryをしない | 別コマンドや別processにまたがる課題単位の累計制御がない |
| 選別評価 | 保存済み確率で`batch`／`per-file`を比較し、必要ファイルのラベルを渡せる | 失敗事例の蓄積、代表的なファイル発見課題、未使用課題での評価が不足 |

具体的な確認箇所は `measure.py::summarize` と `shared/tool_output.py::select_output`。前者は`completed_jev_calls`／`jev_calls`を読むが、後者は`calls`へ使用量を保存する。この不一致は「出力選別の実使用量を統合集計できない」問題であり、費用をゼロと確定している問題ではない。

Keelには判断記録のexport/reportと、組み込みループ内で共有する呼出予算がある。比較runner・独立した評価集合・自動学習は完成機能として扱わない。当方の既存キャッシュ、鮮度確認、使用量計算、policy比較を再利用する。

## 実施順序

### P1-A: 既存記録の読み取りアダプターを追加する

最初の実装単位。永続ログの書き換えや新しいDBを伴わず、既存の計測処理を修正する。

- 対象: `measure.py`、`tests/test_workflow_improvements.py`の`UsageTests`、必要に応じて`tests/test_context_budget.py`。記録形式の参照元は`shared/tool_output.py`。
- 既存CLI／Desktop／evidence／tool-outputの種別を明示的に判別し、認識済み形式だけを共通の集計入力へ正規化する。任意のJSONの`calls`を無条件にAPI使用量とみなさない。
- tool-outputの`calls`、`attempted_calls`、status、seconds、usageを取り込み、元の記録を変更しない。CLI使用量＋補助処理の集計を維持する。
- 補助段階自身がAstraを呼ばないことと、ラップしたコマンドやDesktop会話全体のAstra使用量が未取得であることを区別する。補助記録だけで会話全体の費用を確定しない。
- 同じ成果物パスの重複は現行どおり除外する。同一request hashでも別の実呼び出しは別消費。cache再利用の過去usageは新規消費に加算しない。

完了条件:

1. 合成したtool-output記録の既知使用量が正しく集計され、既存CLI記録と組み合わせてもCLIの既知使用量を失わない。
2. API失敗・欠測usage・欠測cache情報・未知の記録形式は完全な費用見積にならず、既知の部分集計と不明分を区別できる。
3. provider失敗、途中完了、Jev未呼出、重複入力、cache再利用、複数provider単価の回帰確認が通る。
4. 既存形式を継続して読める。集計のためのAPI呼び出し・キー取得・元ログへの書き込みは発生しない。

### P1-B: 課題と作業結果を関連付ける

P1-Aの後。既存記録を変換して読む方式を優先し、旧記録から特定できない関連は推測しない。

- 候補: task/run IDと段階を明示したmanifest、または同等の小さな関連付け記録。正確な形式・IDの発行元・保存場所・更新主体は提案段階。
- 対象候補: `measure.py`、`shared/host_context.py`、`shared/evidence.py`、`shared/tool_output.py`、`Codex cli/coding.py`。すべてを一度に変更せず、読み取り側から最小範囲を選ぶ。
- 最小結果項目: 選別結果、追加context要求、検証コマンドの終了結果、再作業回数、実際の開始／終了時刻、独立した受入・品質評価とその出典。取得できないものはnull／unknown。
- 検証成功、ユーザー受入、品質、完了状態を別々に扱う。モデルの「完了」という文章だけで受入済みにしない。並行処理の所要時間を単純に加算して壁時計時間と呼ばない。

完了条件: 同じ課題の複数段階を追跡でき、未知の関連・未記録の結果・重複を説明できる。元receiptとそれを参照するmanifest／集約記録を両方入力しても同一呼び出しを二重計上しない。同じrequest hashの別実行は別消費として維持する。privateログ・ソース・キーをGitへ入れず、Desktop全体の使用量を推測で補わない。

### P2: 課題全体でJevの呼出予算を共有する

P1の集計を土台に設計する。Keelのin-processカウンタをそのまま移植せず、当方の複数コマンド／processの実行方式に合わせる。

- 対象候補: `shared/jev.py`、`shared/host_context.py`、`shared/evidence.py`、`shared/tool_output.py`、`Codex cli/coding.py`、各入口。必要なら共通予算モジュールを新設する。
- 初期案は課題単位の**実API試行回数**。各helperの既存上限も維持し、両方を満たした場合だけ呼び出す。回数上限をtoken／USDの厳密な上限として表示しない。
- API送信前に予算を原子的に予約する。並行process、再起動、timeout、異常終了で上限が復活しないようにする。送信有無が不明な予約を自動返却しない。
- 有効なcache hitは新規API予算を消費しない。予算不足時もJev必須経路をlocalへ黙って切り替えない。outputは元の出力を保持し、ラップしたコマンドを再実行しない。

実装前に決める事項:

1. 保存方式、lock／transaction、課題IDと予算の作成・共有・終了規約。既存OS対応と追加依存を比較する。
2. crash後の未確定予約の扱いと、利用者が明示的に予算を追加する操作。既存ログや他課題の予算を変更しない。
3. 未指定時の互換動作と導入範囲。既定で新しい予算を自動作成するかは、この計画では決定しない。

完了条件: 同時実行、上限到達、providerエラー、cache hit、強制終了／再開、破損・利用不能な予算記録を合成環境で確認する。記録を安全に更新できない場合、新しいAPI呼び出しを許可しない。既存のno-retryと出力復旧を維持する。

### P3: 失敗事例から選別方法を評価する

P1の計測・結果を使い、既存の`shared/repo_context.py::resolve_selection`と`shared/host_context.py::compare`を再利用する。最初は追加APIなしの保存済み判定の比較とする。

- 対象候補: 既存比較処理、`tests/test_selection_policy.py`、`tests/test_staged_scope.py`、`benchmarks/`の公開可能な合成ケースと評価ツール。
- ケースに課題、入力revision、必要ファイル／範囲、期待する保持／省略／保留、期待される結果を明示する。未ラベルと「必要ファイルなし／保留が正解」を混同しない。
- 全保持、必要ファイルの誤除外、無関係ファイルの誤保持、shortlist外の必要ファイル、依存・指示ファイル、不完全な範囲、古い入力、provider失敗を含める。
- 対象ファイルを最初から固定した例だけにせず、必要ファイルを発見する課題も用意する。調整用と未使用の評価用課題を分離する。
- 既存`batch`／`per-file`と閾値を、必要情報の保持率、追加読込、検証結果、再作業、費用、総時間で比較する。policyや質問を変更する場合は同じ記録の再利用が妥当か確認する。
- 検証結果・再作業・費用・総時間は、そのpolicyに対応する実行記録がある場合だけ比較する。元runの成功や費用を、別policyのoffline replay結果へ付け替えない。

完了条件: 再評価は決定的でAPIを呼ばず、ラベル欠損・入力不足・不正値を隠さない。offline replayの結果から実際のAstra token・費用・コード品質を推定しない。既定policyの変更は評価基準を事前に決め、根拠と戻し先をレビューしてから行う。

続く実作業の比較は別段階とする。通常Codex／ローカル絞り込みのみ／ローカル絞り込み＋Jevを、同じモデル・推論強度・source revision・完了条件で反復し、cold／warm cacheを区別する。必要な実provider呼び出し数・費用範囲を具体化してから実行し、失敗試行も集計する。

## 検証・文書・互換性

- P1-Aは既存の計測テストへ振る舞いを確認するケースを追加し、まず影響範囲を検証する。behavioral changeの最終確認はrepo方針の`python3 -m unittest -v`。同じ状態の検証を無目的に繰り返さない。
- P2は予算・課金・永続化に触れるため、並行実行、拒否、欠測、復旧を含める。実Projectを書き換えず、synthetic fixtureと偽providerで確認する。
- 実装した範囲に合わせて`docs/CONTEXT-BUDGETS.md`、`docs/EVIDENCE.md`、`docs/TOOL-OUTPUT.md`を更新する。利用者に見える変更は英日READMEを揃える。
- 当初の計画保存段階ではVERSION、CHANGELOG、インストール済みSkillを変更しなかった。その後の実装・検証とユーザーの公開指示を受け、v0.6.0公開準備でVERSION、CHANGELOG、英日READMEを更新している。Python同梱配布は引き続き提案段階。
- 既存成果物の読み取り互換を維持する。新しい関連付け・予算は既存記録と分離し、導入を取り消せるようにする。ログ削除・自動migration・資格情報の移動を行わない。

## 今回の対象外と次回の開始位置

KeelのmacOS UI、Laya導入、モデルの自動切替、Codex Desktop内部のtool bundle制御、自動学習・自動policy昇格は対象外。Keelの組み込みDeepSeek向け制御を、外部Codexの内部ループでも使えるものとして扱わない。

P1-Bの結果記録とP2の共有予算は永続化・実行方式の設計を含む。この計画の保存・commitは方式選択の承認ではない。実装時に具体案、互換性、復旧、検証を示し、architecture変更は承認範囲を確認する。既存処理を維持するP1-Aの通常修正に、不要な承認工程を追加しない。

次回は以下から再開する。

1. この計画のローカルcommitと対象checkout、branch、HEAD、差分を確認する。以後の変更で前提が変わっていれば計画を更新する。
2. 利用者の再開指示の範囲でP1-Aから実装する。`astra-jev-coding`の新しいplan/select/checkを作り、過去の選別を現在の編集許可として使わない。
3. P1-A完了後、その結果を確認してP1-B／P2の未決定事項を具体化する。push・merge・releaseは今回の承認から推定しない。

未知の必要ファイルを探す段階的探索、保持と提示の分離、部分結果の扱いは[jevgrepを参考にした追加計画](JEVGREP-ADOPTION-PLAN.md)に記録した。P1-AとP3を計測基盤として使い、両計画の費用・品質評価を一つの比較にまとめる。

## 参考資料

- [Keelの判断記録とreport](https://github.com/codejunkie99/keel/blob/5cef4569e7f850b3a85dc998cc64c64e944c80a0/crates/engine/src/decision_log.rs)
- [KeelのDecisionEvent](https://github.com/codejunkie99/keel/blob/5cef4569e7f850b3a85dc998cc64c64e944c80a0/crates/proto/src/entities.rs)
- [KeelのDecisionBudget](https://github.com/codejunkie99/keel/blob/5cef4569e7f850b3a85dc998cc64c64e944c80a0/crates/jev-core/src/lib.rs)
- [Keelの制御範囲](https://github.com/codejunkie99/keel/blob/5cef4569e7f850b3a85dc998cc64c64e944c80a0/docs/decision-architecture.md)
- [Keelの改善ループ案](https://github.com/codejunkie99/keel/blob/5cef4569e7f850b3a85dc998cc64c64e944c80a0/docs/proposals/improvement-loop.md)
- [TypeSafe: Confidence](https://docs.typesafe.ai/confidence)／[Re-ranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe)／[Speculative fan-out](https://docs.typesafe.ai/patterns/fan-out)

参照先は調査時点の根拠。次回のAPI／SDK変更時には公式仕様を再確認する。参考コードを実際に複製する場合は、該当ファイルと第三者部分のライセンス・通知を確認して保持する。
