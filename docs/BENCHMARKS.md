# Measurements, not a savings promise / 比較結果

## v0.3.0 upgrade check — 2026-09-24

This selection-only comparison ran the released `v0.2.0` code against the same synthetic repository, task and file hashes as the saved v0.3.0 candidate check from earlier that day. Both used the default conservative `batch` policy and explicitly focused `main.py`. There was one live selection per arm, with no retries or Astra child generation. These observations are not interleaved trials or a timing benchmark.

| Selection metric | v0.2.0 | v0.3.0 candidate |
|---|---:|---:|
| Candidate / retained files | 2 / 2 | 2 / 1 |
| Fully judged / unjudged files | 1 / 1 | 2 / 0 |
| Retained source bytes | 27,353 | 75 |
| Live Jev requests | 1 | 2 |
| Jev input / output tokens | 392 / 21 | 6,784 / 76 |
| Estimated Jev USD | 0.000016464 | 0.000284928 |
| Selection seconds, one observation only | 0.891 | 2.696 |
| Astra input and total-task cost | Not measured | Not measured |

The 27,278-byte gardening document was unrelated to the multiplication task. The old 22 KB allowance left it unjudged and retained; complete-range judging omitted it. Retained source bytes fell **99.73%**, while Jev input **increased by 6,392 tokens**. This intentionally easy fixture diagnoses the old bypass; it does not represent a realistic mix of relevant/irrelevant code. The necessary file was pinned, so its retention does not demonstrate model recall. No generated fix or coding acceptance result was measured.

Prices use actual reported input multiplied by $0.042 / 1,000,000, with free output, verified against the [official TypeSafe model page](https://docs.typesafe.ai/models) on 2026-09-24. The extra Jev estimate is **$0.000268464**. Net savings would require a measured decrease in Astra cost greater than that increase, accounting for output, retries and cache changes:

`net saving = (Astra cost before − Astra cost after) − (Jev cost after − Jev cost before)`

Astra cost is unknown for these runs. OpenAI's [prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) distinguishes ordinary input, cache reads and cache writes; shorter text alone cannot establish the price difference. API estimates are also different from Codex subscription quota consumption. No formula here establishes a Desktop percentage saving.

A separate local check on the 75-byte `main.py` fixture retained all source with zero Jev calls using v0.3.0 `--mode auto`. The threshold is 12,000 source bytes, not tokens. The command default is still `jev`; the updated Skill recommends `auto`. Repeating the larger candidate's identical request used the existing Jev response cache with zero new calls; that capability predates v0.3.0 and is not counted as an upgrade gain.

[Public aggregate, input hashes and caveats](../benchmarks/context-selection-v0.3.0.json). Raw provider records and snapshots remain outside Git, so the original traces cannot be independently audited from this package. Local regression tests cover full Unicode/long-line coverage, missing-range retention, request-budget refusal before calls, bounded/fresh reads, bypass behavior and cache accounting; **114 tests passed**. Real-task holdouts and repeated three-arm comparisons (ordinary Codex, local scope only, local scope + Jev) remain necessary for a savings claim.

### 日本語：今回わかったこと

同じ合成入力で旧版と新版を比較し、旧版が22 KB超で未判定保持した資料を、新版は全範囲判定して除外できました。本文27,353→75 bytes（99.73%減）は選別の改善です。一方、Jev入力は392→6,784 token、費用見積は$0.000016464→$0.000284928に増えました。Astra側の削減がこの差額を上回るかは未測定です。

必要な`main.py`は明示固定済みで、簡単な合成1例・各1回です。実装結果・必要ファイルの判断精度・速度差・総費用の優位性は示しません。過去の「Astra入力1.2%減」と今回の更新効果も別に扱います。75 bytesの別例では`auto`でJev 0回を確認しましたが、Desktop会話全体のtokenや契約枠の節約率には換算しません。

## Historical Astra generation measurement

On 2026-09-22, three synthetic Python repair tasks (pagination, retry configuration, and expiry) were run once per arm in a controlled rerun. Astra was `gpt-6-astra`, reasoning `low`, accessed through the experimenter's own Codex CLI 0.153.2 login. Jev was `jev-1.13.0`. Both arms passed the same 22 behavior checks. Hidden checks and reference fixes were kept out of model inputs; generation was constrained to no tool calls.

| Three-task total | Astra only | Astra + Jev |
|---|---:|---:|
| Candidate files delivered | 28 | 4 |
| Harness-written prompt characters | 4,309 | 2,581 |
| Astra-reported input tokens | 42,714 | 42,199 |
| Astra-reported output tokens | 175 | 175 |
| Elapsed seconds | 18.51 | 21.53 |
| Jev input tokens | 0 | 4,094 |
| Jev API seconds, included in elapsed time | 0 | 1.62 |
| Passed behavior checks | 22 / 22 | 22 / 22 |

Reduction is `(baseline - hybrid) / baseline`: files **85.7%**, harness prompt characters **40.1%**, Astra input tokens **1.2%**. Elapsed time increased **16.3%**. The 515-token difference in Astra input is the measured result; do not advertise the file-count reduction as a token saving.

The small input reduction despite a shorter custom prompt is consistent with shared runtime instructions, tools, and other context dominating these small tasks. That is an interpretation, not a decomposition of all internal input.

## Controls and evidence limits

- An initial run had uneven Skill-catalog warnings and was not used to claim savings. In the rerun, plugin, app, memory, and hook features were disabled for the comparison process, and the Skill-context budget was set to 1,000. All six generation calls still emitted the catalog warning. Inputs were not perfectly fixed; time, caching, startup, and provider variability remain confounders.
- The initial run plus rerun made 12 Astra calls and 6 Jev calls. The table is the rerun only (6 Astra, 3 Jev). Different provider tokens are not interchangeable billing units.
- These are maintainer-reported historical measurements made before the package split and later features. They are **not a fresh release-wide performance benchmark**. Aggregate values are published in [JSON](../benchmarks/results-2026-09-22.json). Raw session artifacts, credentials, and private local paths are intentionally not published; identical original traces cannot be independently audited from this repository.
- Three small tasks and one trial per arm do not establish real-project quality or a reliable speed difference. Dollar cost, subscription-limit consumption, and end-to-end Desktop tokens were not measured.

## Later context-only observations

| Experiment | Observed result | What it does not prove |
|---|---|---|
| Native Desktop handoff, four copied implementation files | One Jev request; 4,207 input / 72 output tokens; about 0.72 s; all four files retained | No context reduction or complete Desktop cost comparison |
| Conservative batch versus per-file replay on 15 tracked files | Same two recorded Jev replies; 34,852 → 34,634 source bytes (218 bytes / 0.63%); 15 → 14 files; no new API calls | No token/cost saving or correctness proof; required-file labels were not supplied |

The latter live selection used 13,548 Jev input and 263 output tokens, about 1.42 seconds in total. Untracked implementation files were reviewed locally and were not part of those 15 candidates. The default policy remains `batch`.

## Reproduce a new run

Offline validation needs no API key or Codex login:

```sh
python3 -m unittest -v
python3 harness.py --help
```

With your own Codex login/model access and `TYPESAFE_API_KEY` in the environment:

```sh
# --out is a root under which a new timestamped run is written.
python3 harness.py compare --case pagination --out /absolute/benchmark-results
# Omit --case to compare all three fixture tasks.
```

One selected fixture comparison uses up to two Astra calls and one Jev call. All three use up to six Astra calls and three Jev calls. Check the command's local help for current options. The benchmark entrypoint reads the key from the environment, not the optional Keychain helper. No automatic provider retries.

For Desktop selection policy evaluation, use `desktop/context.py compare --selection ...` against saved output. This reuses the same probabilities without a provider call. Repeated `--required-file PATH` labels must come from an independent assessment of what the task needs; labels inferred from the chosen output would make recall meaningless. A comparison never edits the original selection or claims it is fresh.

For a convincing real-project study, use representative tasks, hold required files and behavior checks out of selection, repeat each arm, record cold/warm conditions, include all Jev overhead, and report failures alongside successes. Measure the whole completed task rather than only the first prompt.

## 日本語での読み方

3課題の合計で、候補ファイルは85.7%減、自作プロンプト文字数は40.1%減でした。一方、Astraが報告した入力トークンは42,714→42,199で**1.2%減**だけです。実行時間は18.51→21.53秒で16.3%増え、Jev入力4,094トークンが別途発生しました。ファイル数の削減率をトークンや料金の削減率として扱えません。

両方式の22件の動作確認は成功しましたが、小さな合成3課題・各1試行です。費用、Codex週次上限、Desktop会話全体の節約率は未測定です。表は配布構成へ分離する前の過去測定で、現在版の全機能の実測ではありません。生の会話・実行ログは公開していないため、ここから元のtraceを完全再監査することはできません。利用者自身の認証で、新しい測定を再実行できます。

Desktopの後続比較は本文34,852→34,634 bytes、差218 bytes（0.63%）のみでした。保存済み判断を再利用したため追加API呼び出しは0回ですが、必要ファイルの正解ラベルはなく、実装品質の改善を示すものではありません。
