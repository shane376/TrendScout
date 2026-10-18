# Repository workflow

- Preserve the V1–V1.3.2 contracts, CLI commands, export schemas and offline tests unless a task explicitly requires a compatible change.
- Inspect Git state before changing branches. Preserve user changes; do not reset, discard, rebase or force-push them.
- For implementation milestones, fetch `origin/main` and work on the requested feature branch. Never modify `main` directly.
- Codex may commit, push a feature branch and open a pull request when authorized by the current task. Include validation and material limitations in the PR.
- Never merge a PR or enable auto-merge without explicit human approval. Opening a PR does not authorize merging it.
- Run the complete suite with `.\.venv\Scripts\python.exe -m pytest -q` before marking a PR ready. If verification fails or is incomplete, keep the PR draft and report the issue.
- Keep tests offline and use explicit synthetic fixtures. Never silently replace live data with fixtures.
- Keep `.env`, credentials, live metadata, derived per-video reports and raw API responses out of Git. Do not read or print secrets for debugging.
- Do not perform live provider requests unless explicitly authorized. API-key access is distinct from authorization for derived analytics or retention; preserve the source-specific safeguards.
