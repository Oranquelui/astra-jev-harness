# Measurements, not a savings promise / 比較結果

## What was measured

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
