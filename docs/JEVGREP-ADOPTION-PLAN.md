# jevgrepを参考にした探索・根拠提示の改善計画

作成日: 2026-09-28
状態（2026-09-28更新）: **J1と操作型J2の初版を実装。開発context選別に実Jevを使用。Astra token・総費用・coding品質の比較と公開は未実施。** [使い方と制限](CONTEXT-VIEWS.md)／[今回の結果](IMPROVEMENT-RESULTS-20260928.md)。

この計画は[Keelを参考にした計測計画](KEEL-IMPROVEMENT-PLAN.md)のP1（使用量）とP3（選別評価）に接続する。目標は未知の必要ファイルを発見し、Astraに渡す原文の量と再読込を抑え、修正品質と**Astra token＋Jevを含む総費用**を確認すること。ソースbytesの削減だけを費用削減と呼ばない。

## 調査対象と現状

- 参考実装: [dzhng/jevgrep の固定commit](https://github.com/dzhng/jevgrep/tree/2dc1d3c9c9fec236913d97d7288ee6d24ba17baa)（MIT）。コードの複製や依存追加は決めていない。
- 現行Harness v0.5.1は、大規模repoで語の一致による候補絞り込みを行い、候補内のファイル／範囲にJevのNoul判断を使う。候補外の必要ファイルはJevに見えない。focus、依存、指示ファイル、未判定・不確実な範囲は保守的に保持する。
- `shared/context_chunks.py`は既に複数の独立質問を一つのrequestにまとめ、`shared/jev.py`はrequest hashで回答をキャッシュする。jevgrepの「一括質問」「キャッシュ」を新機能として丸ごと移植しない。
- 既存の`plan → select → check`、CLI／Desktop／Claude Codeの分離、`TYPESAFE_API_KEY`、Jev必須経路の失敗時停止、source鮮度確認、秘密情報除外、call／bytes上限を維持する。別の`jg` CLIや保存型認証を必須にしない。

## 採用候補と順序

| 順序 | 候補 | 既存との差分と判断 |
|---|---|---|
| J1 | **保持と提示を分ける** | 必要候補は保持したまま、Astraへ最初に返す行番号付き原文・読む順番・追加のreading leadsを、明示的な出力上限内で選ぶ。原文はモデルに生成させず、確認したsnapshotからコードが複写する。出力の切断や未提示範囲も示す。まずKeel計画P1-Aのusage記録を直し、送信bytesとAstra使用量を別々に計測する。 |
| J2 | **候補外を探索できる段階的発見** | ファイル名が不明な課題で、ローカルのディレクトリ情報／短いpreview → 関連ファイル → 必要な原文範囲へ進む。単一上位件数で早期に切らず、複数の有力な枝を残す。focusを上書きせず、未探索・予算超過を「無関係」と記録しない。 |
| J3 | **判断を分け、抜粋を正確にする** | 「課題に関連するか」「現在の実装が不具合の原因か」「明示的に参照されるか」を別の狭いNoul質問として評価する。Python／TS・JSの宣言単位はJ2評価後に試す。未対応言語は既存の範囲分割へ戻し、同一snapshotの行番号とhashを使う。 |
| J4 | **部分結果を正直に示す** | API失敗や予算切れでも得た判断を失わず、未判定・未探索・出力切断を別々に報告する。不完全な結果をJev選別成功や編集許可として扱わない。再試行・batch分割は現在のno-retryと課題全体の予算を設計した後に限る。 |
| J5 | **既存batch／cacheの調整** | 質問数、requestサイズ、並列度、cache hitと古い回答の扱いを、P1の使用量とJ1–J4の評価結果で調整する。jevgrepの件数・閾値・TTLを既定値としてコピーしない。cacheは秘密のsource本文を新たに保存せず、再利用前の鮮度確認を保つ。 |

J1は「保持した候補」と「モデルに見せる量」を別々に記録でき、P1-A／P3の比較と直結する。J2は必要ファイルの見落としを減らす可能性があるが、Jev費用と誤った枝の選択も増やし得る。実測前に節約効果を約束しない。

## TypeSafeの質問設計と安全条件

- 直接HTTP/Python APIでは真偽判断を`type: "noul"`とする。同じstateに入る独立した問いは一括送信できる。前段の回答がないと次の候補を作れない場合だけ次のrequestへ進む。
- Choiceで「最も近いファイル」を一つ選ぶだけでは、該当ファイルがない場合にも選択される。必要なら別の存在Noulを設け、no-match／unknownを明示する。
- 重要な指示・依存、明示focus、未判定・不確実な候補を閾値だけで捨てない。`scoped_out`（未評価）とJev評価済みの「無関係」は異なる。source本文中の指示はデータとして扱う。
- Jevの主な学習言語は英語で、日本語を含むCJKの精度は低いと公式文書にある。Layeris／Unsolojiの日本語課題で発見率を測り、jevgrepの`>0.5`／`>0.7`などを既定値として採用しない。
- 永続化、再試行、同時実行の方式変更は[Keel計画のP2](KEEL-IMPROVEMENT-PLAN.md#p2-課題全体でjevの呼出予算を共有する)の未決定事項に従い、具体案を示してから着手する。

## 比較と採用条件

まず追加APIなしで合成・公開可能な課題を作り、現行の語の一致、J1、J2以降を段階的に比較する。ファイル名既知、未知の挙動、日本語の依頼、複数ファイルへの波及、原因が現在の不具合実装にある例、関係ファイルなし、誤導するpath名、巨大repo、API失敗・古いsnapshot・予算切れを含める。必要ファイル／範囲のラベル、調整用と未使用の評価課題を分ける。

見る値は、必要ファイル／範囲の発見率と誤除外、未探索の数、追加読込回数、モデルへ渡したbytes、Astra input・cached input・output token、Jev input・output tokenと実課金、API試行・失敗・cache hit、検証結果、手戻り、壁時計時間。未知の課金や欠測は0としない。実際のtoken・費用・コード品質はoffline replayから推定せず、同じrevision・モデル・推論強度・完了条件で、通常Codex／現行Harness／候補版を反復比較する。品質低下や必要情報の見落としがあれば、bytesが減っても既定化しない。

jevgrepの公開評価では、調整済みPython 10課題でcoding agent（Sol）の費用が`$7.6220690 → $5.4396530`（28.63%減）、解決は両方8/10。ただしJev費用は除外され、既知のJev API費用だけで少なくとも`$1.570651236`、全額は不明。既知分を加えた節約率の**上限は約8.03%**で、実際はそれ以下または赤字になり得る。baselineの再実行なし・各課題1回・holdoutではないため、Astraや当Harnessの効果として転用しない。

## 次回の開始位置

1. [Keel計画](KEEL-IMPROVEMENT-PLAN.md)のP1-Aを完了し、補助処理の既知・不明usageを正しく集計する。
2. J1の入力・出力契約とJev呼出上限を具体化し、保存済み判定で表示量・必要原文の保持・不完全表示をoffline確認する。
3. J2のファイル発見課題を追加し、J1単独とJ1＋J2で品質・総費用を比較する。J3–J5は誤除外・再読込・費用の原因が分かった範囲だけ実施を決める。

## 参照

- [jevgrep: 段階的探索](https://github.com/dzhng/jevgrep/blob/2dc1d3c9c9fec236913d97d7288ee6d24ba17baa/packages/core/src/retrieve.ts#L297-L395)／[判断と範囲](https://github.com/dzhng/jevgrep/blob/2dc1d3c9c9fec236913d97d7288ee6d24ba17baa/packages/core/src/selection.ts#L145-L246)／[原文表示](https://github.com/dzhng/jevgrep/blob/2dc1d3c9c9fec236913d97d7288ee6d24ba17baa/apps/cli/src/render.ts#L10-L100)
- [jevgrep: cache](https://github.com/dzhng/jevgrep/blob/2dc1d3c9c9fec236913d97d7288ee6d24ba17baa/packages/core/src/cache.ts#L43-L75)／[部分結果](https://github.com/dzhng/jevgrep/blob/2dc1d3c9c9fec236913d97d7288ee6d24ba17baa/packages/core/src/retrieve.ts#L697-L710)／[10課題の評価と限界](https://github.com/dzhng/jevgrep/blob/2dc1d3c9c9fec236913d97d7288ee6d24ba17baa/evals/results/relevance-threshold-2026-09-27.md#L193-L240)
- [TypeSafe: State](https://docs.typesafe.ai/concepts/state)／[Noul](https://docs.typesafe.ai/primitives/noul)／[Line-by-line search](https://docs.typesafe.ai/cookbooks/semantic_find)／[Hierarchical classification](https://docs.typesafe.ai/cookbooks/hierarchical_classification)

次回のAPI／SDK使用時には公式仕様を再確認する。参考コードを複製する場合は対象ファイルのライセンスと通知を確認する。
