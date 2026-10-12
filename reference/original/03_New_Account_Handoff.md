# New ChatGPT Account — Portable Handoff

## How to begin
1. Upload the complete ZIP bundle and, if available, the original full static audit Markdown/HTML to the new ChatGPT conversation. The audit is not embedded in full here.
2. Ask the assistant to read 01_Master_Phased_Engineering_Plan.md, 02_Codex_Prompt_Playbook.md and this handoff before proposing code.
3. Connect GitHub/Codex to the new account under the user's own authorization. Confirm repository access and pinned SHA, especially retrivo_bot's missing SHA.
4. Use prompt 00 in the playbook to initialize the new conversation; then prompt 01 for the P0 evidence gate; after P0 approval, prompt 02 for P1.
5. Keep one main architecture/governance chat and one dedicated chat per implementation phase; store decision logs and milestone handoff files in the new repo once authorized.

## The product in one paragraph
A single multi-tenant platform powers self-service or admin-managed website-chatbot onboarding with safe automated crawling, multilingual grounded RAG, per-tenant bot and dashboard, embeddable widget, subscriptions and platform administration. It shares canonical tenant identity and optional authorized AI knowledge with the independently subscribable ManyOsirisChat Meta messaging product, which keeps its own operational responsibilities. A single durable provisioning engine handles both onboarding modes. New SaaS foundation is preferred over merging existing monolith databases.

## What is approved and what is not
Approved: architecture, phase order and planning documentation. Not automatically approved: code edits, repo creation, commits, branch creation, billing charges, deployment, secret rotation, production DB access or migration. Each change requires explicit scope authorization. P0 investigation is read-only until owner approves remediation.

## Evidence limitations
The prior audit reports 628 tracked files and no runtime test execution. Some files received structural scans rather than deep semantic review. Current deployment state is unknown. Exact retrivo_bot commit SHA must be copied from original audit. Do not treat estimates, security impact or proposed schema as verified implementation facts.

## Required conversation behavior
Act as principal architect, security reviewer and engineering delivery manager. Before every Codex task, identify scope, file paths, non-goals, dependencies, test targets, acceptance criteria, migration/rollback and security. Prefer minimal, reviewable PRs. Avoid speculative refactors. Cite repo files/commit SHAs for source claims. Maintain a decisions register, risk register, dependency map, phase checklist and CHANGELOG. Never execute destructive tests against non-disposable DBs. Never echo secret contents.

## Milestone reporting template
Phase / ticket ID; pinned source SHAs; files changed; verified behaviors; tests and exact results; migrations and data impact; unresolved risks; next dependency; approval needed. Distinguish planned, in progress, implemented, tested, reviewed, deployed.

## Repository links
https://github.com/Youssefelsayed148/ManyOsirisChat
https://github.com/Youssefelsayed148/retrivo_bot
https://github.com/Youssefelsayed148/rabbit_hole_chatbot
