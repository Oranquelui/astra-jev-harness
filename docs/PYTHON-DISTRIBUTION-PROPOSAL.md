# Pythonを別途準備しない配布方式の提案

2026-09-28。**Proposed: 方式承認前。配布物・installerの変更は未実装。**

目的は利用者がHarnessのインストールと実行のためにPythonを別途導入しなくて済むこと。内部からPythonをなくすことや、対象プロジェクトの言語環境を提供することは含まない。

## Current / Implemented

- `install.py`自体がPython 3.10+を使い、clone内のSkillへsymlinkを作る。異なる既存Skillを上書きしない。
- Desktop/Claude CodeのSkill launcherとhelper、CLI入口、evidence/output/measureがPythonで動く。追加pipライブラリは不要。
- Skill launcherとCLI入口は`sys.executable`を再実行する。単純にPyInstallerで凍結すると「Pythonとして自身を再起動する」という前提が崩れるため、起動dispatcherの変更と検証が必要。
- 現行はPython 3.10/3.14のCI設定。実動作文書はmacOSを基準にする。Gitとホスト（Desktop/Claude Code/CLI）は別依存。
- 認証は環境変数優先、macOS Keychainを補完利用。配布物へ認証・source snapshot・usageログを同梱しない。

## 選択肢

| 案 | 利用者の準備 | 互換・運用・費用 |
|---|---|---|
| **専用CPythonを同梱したディレクトリ配布（推奨）** | Python/uvの準備不要。archive展開と付属installer実行 | Pythonコード、sys.executable、surface分離を維持しやすい。OS/CPU別ビルドとruntimeの脆弱性更新、容量・配信費が増える |
| uv bootstrapで専用Pythonを取得 | Python不要。installerがuv/Pythonを取得する | 小さい配布だが初回ネットワーク・追加取得元に依存。uvの版、download先、整合性、失敗復旧の管理が必要 |
| PyInstaller onedir | Python不要 | interpreterを同梱できるがexecve、動的import、Skill・docsのresource配置を作り直す。OSごとのビルドが必要 |
| Rust/Go等へ全面移植 | Python不要 | 契約・秘密除外・Git鮮度・cache・usage・各host連携の再実装が必要。今回の小さな配布改善としては検証負担が大きい |

推奨は既存実行モデルを保つ同梱方式。Pythonの実行時downloadや暗黙のsystem Python fallbackは行わない。Git・ログイン済みホスト・対象repoのテスト用runtimeは引き続き必要と明記する。

## 提案する具体的な構成

1. リリースごとにOS/CPUを固定し、`astra-jev/<version>/app/`へ現行コード/Skill、`runtime/`へprivate CPython、`bin/`へshell launcherを置く。初期対応はmacOS arm64/x86_64。Linux/Windowsを対応済みと表示しない。
2. `bin/astra-jev install|desktop|claude-code|cli|evidence|output|measure`が、相対位置から同梱Pythonと現在の各入口を呼ぶ。引数と終了コードを保持する。surfaceを一つのartifact形式へ統合しない。
3. `install`も同梱runtimeで動く。配布版Skillの実行例は付属launcherを使う。既存clone向けPython入口とSkillは引き続き提供する。
4. ビルド時にpython-build-standaloneの**固定リリース・asset URL・SHA-256**をmanifestへ記録し、検証後に同梱する。版/URL/hash/ライセンス一覧は最初のbuild PRで具体値をレビューする。`latest`解決を利用者の端末で行わない。
5. 完成archiveにもSHA-256とライセンス通知、ビルド元commitを添える。秘密・run artifact・ユーザーHOMEをbuild入力にしない。TLS証明書の解決を実機で検証し、独自の証明書検証無効化はしない。
6. 展開は新しいversionディレクトリへ行い、起動チェック成功後に明示的にリンクを切り替える。同一製品の既知リンクだけを対象とし、他Skill・認証・シェル設定は変更しない。破損/未対応CPU/runtime欠落時は停止する。
7. macOS配布の署名・notarizationは別の公開判断。ローカルbuild成功を配布・release完了と呼ばない。

## 移行・戻し方

- source版`python3 install.py`と現在のAPI/成果物形式を維持する。既存のログ・cache・planを自動migrationしない。
- 更新前に既存Skillのlink先を確認。ユーザー変更や別cloneを見つけたら上書きしない。更新対象リンクと戻し先を表示する。
- 旧配布ディレクトリを残し、同製品リンクを元のversion/cloneに戻せばrollbackできる。ランタイムとコードを別々に更新しない。
- uninstallはこの配布のリンク・ディレクトリだけ。Keychain、cache、run logs、Codex/Claudeの認証を消さない。

## 承認後の実装と検証

- ランチャー、配布manifest、buildスクリプト、配布用Skill、installerのリンク移行だけを実装する。provider API/選別policy/課金設定は変更しない。
- PythonがPATHにないクリーン環境でinstall/check/plan/select/check/read/present/discover、evidence/output/measureを確認する。まず偽provider、live checkは別途回数を限定する。
- 空白/日本語パス、symlink経由、別cwd、引数と終了コード、両surfaceの誤受け渡し、Jev必須guard、認証非出力を確認する。
- hash不一致、破損archive、runtime欠落、未対応CPU、既存の別Skill、権限不足、更新途中失敗、旧versionへのrollbackを確認する。
- CLIのgeneration経路は偽Codexで検証し、Desktop/Claudeから別Codexを起動しない。利用者repoのPythonテスト環境を同梱runtimeで暗黙に置換しない。
- 全unittestとmacOS両CPUの実配布smokeが完了条件。片方未検証なら、そのCPUは未検証と記す。release/pushは本依頼の承認外。

## 判断点

**上記の同梱CPython・macOS arm64/x86_64ディレクトリ配布で実装へ進むか。**

適用方針はユーザー環境の`/Users/louistoyozaki/.codex/policies/architecture-continuity.md`。
「architecture変更はこの提案への承認後に実装」に該当するため、現段階は提案まで。既存方式を保つP1-A/J1/J2の実装・テスト・ローカルcommitは独立して進める。

## 一次資料（2026-09-28確認）

- [uv Python versions](https://docs.astral.sh/uv/concepts/python-versions/): managed Pythonはpython-build-standaloneを使う。
- [python-build-standaloneの実行資料](https://github.com/astral-sh/python-build-standalone/blob/main/docs/running.rst): 配布と実行の制約。実装前に採用assetの制約を確認する。
- [PyInstallerの動作](https://pyinstaller.org/en/stable/operating-mode.html)と[OS別build](https://www.pyinstaller.org/en/stable/usage.html): interpreter同梱とプラットフォーム別配布。
