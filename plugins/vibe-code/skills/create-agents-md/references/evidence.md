# Why these rules: evidence base (researched 2026-08-07)

Read this when the user challenges a rule, asks why the file is so small, or wants sources. Tags: [doc] official vendor documentation, [emp] controlled study, [comm] named community figure.

## The core empirical result

Instruction files are not a correctness lever; they are a consistency and efficiency lever.

- ETH Zürich SRI (Gloaguen, Mündler, Müller, Raychev, Vechev), arXiv:2602.11988 (v2 2026-06): across LLMs and agents, context files "do not generally improve task success rates, while increasing inference cost by over 20% on average". But: "instructions in the context files are well followed", and "repository overviews, although popular and recommended by model providers, are not helpful". [emp]
- Lulla et al., arXiv:2601.20404 (v2 2026-03): 10 repos, 124 PRs, with/without AGENTS.md — median runtime −28.6%, output tokens −16.6%, "comparable task completion behavior". A good file reduces exploratory wandering. [emp]
- Khatri, arXiv:2607.27250 (2026-07): 291 runs, Claude Code + Codex CLI — no measurable correctness movement from context files in either direction; failures were implementation-skill, not missing repo knowledge. [emp]

Consequence: every line must earn its context cost. Commands and explicit conventions are the only content class all three streams support. Overview prose is the worst class — cost, no measured benefit — and it is exactly what auto-generators emit, so a generated draft is a starting point to prune, never a deliverable.

## Size and adherence

- Anthropic: "target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence"; CLAUDE.md is delivered as a user message after the system prompt, so it is context, not enforced configuration. [doc]
- HumanLayer: frontier models follow roughly 150–200 instructions with consistency and the product's own system prompt consumes a large share; their production CLAUDE.md is under 60 lines. [comm]
- This skill's 150-line target sits inside both envelopes.

## Commands first, verified only

- Anthropic: give Claude a check it can run on its own work, such as a test suite, a build exit code or a linter. [doc]
- Anthropic: "Run `npm test` before committing" not "Test your changes" — instructions "concrete enough to verify". [doc]
- Chris Reddington (GitHub DevRel, 2026-08): "Keep validation commands executable. 'Write good tests' leaves room for interpretation; `pnpm test` gives the agent and reviewer an observable result." [comm]
- CI workflows are ground truth in conflicts: they are the commands that must actually pass.

## What to omit

- Linter-enforced style: VS Code docs say skip "conventions that standard linters or formatters already enforce"; HumanLayer: don't use the model as "an expensive linter". [doc/comm]
- Derivable content: Claude Code's /doctor trim cuts "content Claude can derive from the codebase, such as directory layouts, dependency lists, and architecture overviews, and keeps pitfalls, rationale, and conventions that differ from tool defaults" — the same dividing line this skill uses. [doc]
- Personas and vague demands: Anthropic says instructions work best when "concrete enough to verify"; "You are a helpful coding assistant" personas are a documented anti-pattern (Matt Nigh, GitHub, 2,500-repo analysis). [doc/comm]

## How Claude Code reads AGENTS.md

- Since v2.1.277 Claude Code reads `AGENTS.md` directly, but only when no `CLAUDE.md` or `CLAUDE.local.md` exists in the working directory or any directory above it. With one present, Claude reads the `CLAUDE.md` files only. [doc]
- An `@AGENTS.md` import in a `CLAUDE.md` keeps `AGENTS.md` as the one file every tool shares, and Claude does not read it twice. A symlink also works; the import is the choice on Windows and when Claude-specific rules are needed. [doc]
- Adding a `CLAUDE.local.md` to a project that relies on `AGENTS.md` stops Claude reading `AGENTS.md`. [doc]
- Single source of truth, "duplication is a source of drift" (Reddington); one canonical `AGENTS.md` plus thin per-tool files is the cross-tool pattern (Vaughan, 2026-05). [comm]

## Boundaries section

- Three-tier boundary structure (always / ask first / never) from Nigh's 2,500-repo analysis — the highest-signal structure observed in real files. [comm]
- Real-world census (arXiv:2511.12884): only 14.5% of context files carry any security/boundary specification — the most commonly missing high-value section. [emp]

## Key sources

1. VS Code Docs, custom instructions: code.visualstudio.com/docs/agent-customization/custom-instructions
2. Claude Code Docs, memory: code.claude.com/docs/en/memory
3. Gloaguen et al., arXiv:2602.11988 · Lulla et al., arXiv:2601.20404 · Khatri, arXiv:2607.27250 · Chatlatanagulchai et al., arXiv:2511.12884
4. Nigh (github.blog agents-md, 2025-11) · Reddington (chrisreddington.com, upd. 2026-08) · Vaughan (codex.danielvaughan.com, upd. 2026-07) · HumanLayer (humanlayer.dev, writing-a-good-claude-md)
