# Astra + Jev Coding Harness

- Develop a local coding harness for feature work, fixes, refactoring and tests. Keep implemented behavior distinct from experiments.
- CLI generates through the user's Codex login. Desktop uses the active conversation and must not spawn a second Codex CLI for generation.
- Jev uses the user's TYPESAFE_API_KEY. Never commit credentials, authentication files, session exports, run outputs or repository snapshots.
- Preserve existing changes. Use synthetic fixtures for harness tests rather than modifying someone's real project.
- Run python3 -m unittest -v for behavioral changes. Live-provider checks must have explicit scope and call limits; report usage honestly.
- Record measured token effects separately from source bytes, cost and subscription limits. Do not promote experimental selection policies from byte savings alone.
- Keep the English README.md and Japanese README-ja.md consistent. Installation must never overwrite another Skill or copy user authentication.
