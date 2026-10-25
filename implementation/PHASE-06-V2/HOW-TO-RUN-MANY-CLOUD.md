# Running the Many side as a Claude Code cloud session

Verified against the Claude Code docs on 2026-10-26: `--cloud` is the current flag (`--remote` still works as a deprecated alias). A cloud session clones the GitHub remote at your CURRENT BRANCH, not your local checkout, so everything it needs must be committed and pushed first. The cloud VM has PostgreSQL 16 and Redis 7 installed (not running), Ubuntu 24.04.

## One-time prerequisites
1. Rotate the Meta token inside `popeye access token.txt` (it is tracked in the repo, so the cloud VM will have a copy of the file). Purging it from git history can wait, but the token must be dead before the session starts.
2. `claude auth login` with your claude.ai account (not an API key, not Bedrock/Vertex).
3. Give cloud sessions access to the private repo: install the Claude GitHub App on `Youssefelsayed148/ManyOsirisChat`, or run `/web-setup` inside a local `claude` session (sends your `gh` token).
4. At claude.ai/code, open Settings > environment: keep the Default environment (Trusted network) or create one named `many-dev`. Network must allow pip/PyPI; the Trusted defaults do. Add NO real Meta or OpenAI keys. Optional env vars: `APP_ENV=test`.

## Prepare and push the work branch (PowerShell)
```powershell
cd "D:\Projects\Work Projects\The Osiris Labs\ManyOsirisChat"
git switch main; git pull --ff-only
git switch -c feature/saas-delegation
$pack = "D:\Projects\Work Projects\The Osiris Labs\SAAS-chats-ai-phase6\implementation\PHASE-06-V2\many-pack"
New-Item -ItemType Directory docs\saas-delegation | Out-Null
Copy-Item "$pack\TASK.md","$pack\CONTRACT-V1.md","$pack\CONTRACT-V1.1-DELTA.md" docs\saas-delegation\
Copy-Item "$pack\CLAUDE.md" .\CLAUDE.md
git add CLAUDE.md docs/saas-delegation
git commit -m "docs: SaaS delegation task, contract v1.1 and agent rules"
git push -u origin feature/saas-delegation
```

## Start the session (same folder, branch checked out)
```powershell
claude --cloud "Read CLAUDE.md and docs/saas-delegation/TASK.md, then do ticket M-00 only (read-only) and report. Follow the rules in CLAUDE.md exactly."
```
The CLI prints a session URL. Open it on claude.ai/code (or the phone app). Answer "continue" there to move to M-01, M-02, and so on; one ticket per turn. Follow-up from the terminal: `claude -p "continue" --cloud <session-id>`.

## Getting the work back
- The session pushes commits to `feature/saas-delegation`; review the diff in the session's Changes card or on GitHub. Do not merge yet.
- To continue locally: from the Many folder, `claude --teleport <session-id>` (needs a clean working tree).
- Instagram: M-02 stops before the Instagram branch and waits for your confirmation. Review that diff yourself.

## Limits and gotchas
- Cloud usage counts against your plan limits; one session is enough (tickets are sequential).
- Idle sessions expire; reopen from claude.ai/code and the conversation is restored, but running services (Postgres/Redis) are not: ask Claude to restart them.
- The session cannot run docker-based Many stacks or reach Meta; contract tests use a fake SaaS server only.
