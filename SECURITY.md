# Credentials and source data

Each user supplies their own `TYPESAFE_API_KEY` and their own Codex authentication. This repository ships neither. Never submit real keys, tokens, cookies, `auth.json`, session exports, or private source files in issues or pull requests.

- `install.py` links the Desktop Skill to the user's clone. It does not read, copy, or configure login data and refuses to overwrite a different Skill.
- Key resolution: existing environment first; on macOS, optional login Keychain service `astra-jev-harness`, account `TYPESAFE_API_KEY`. Keychain values are captured in memory. No `.env` discovery or copying from another project.
- TypeSafe requests use the official HTTPS origin. Redirects are refused. Provider error bodies and headers are not logged. `doctor` shows availability and source only.
- CLI Astra generation uses the user's existing Codex login and strips `TYPESAFE_API_KEY`, `OPENAI_API_KEY`, and `CODEX_API_KEY` from its child environment. This is not an export of the login. Codex still reads its own locally managed authentication as normal.
- Plans, candidates, and selections contain source text. Keep them outside the target repository and outside commits. The ignore rules cover common credential and artifact locations; they do not prevent intentional `git add -f` or every possible secret filename.
- Source screening is pattern-based, not a guarantee. Review the plan before sending proprietary code. Model relevance scores do not make file contents trusted instructions.

A failed or timed-out provider request may have been processed and billed. Inspect saved attempts before starting another selection. There are no hidden service retries. Local tests and historical comparison do not need live credentials.

For a vulnerability, use GitHub's private vulnerability reporting if enabled; do not post secrets publicly. If a credential is exposed, revoke/rotate it at its provider. Do not attach the old credential to a report.

## 日本語

利用者自身のJevキーとCodexログインを使用します。installerはSkillのリンクだけを作り、ログインやキーをコピーしません。実キー・認証ファイル・Cookie・私有ソースをissueやPRへ送らないでください。planやrunにはソース本文が入るためGitへ追加せず、外部送信前に対象を確認してください。秘密情報検出は完全ではなく、関連性スコアは安全性を保証しません。応答のないAPI試行でも課金される可能性があります。
