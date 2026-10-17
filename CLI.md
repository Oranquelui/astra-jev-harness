# Codex CLI版

手順と制限は[Codex cli/README.md](Codex%20cli/README.md)へ移しました。

現行版の入口は `bin/astra-jev cli`。v0.7.3は新しいJev要求を`jev-1.14.0`へ固定し、生成用Codexのモデル設定は変更しません。Pythonは実行時に不要で、rootの `coding.py` はソースcheckoutに残した開発・互換検証用の入口です。英語の[CLIガイド](docs/CLI.md)と、別方式の[Codex Desktopガイド](Codex%20Desktop/README.md)も参照してください。
