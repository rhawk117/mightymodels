<div align="center">

# mightymodels

**From the first question you ask a model to a merged PR.**<br>
You make the decisions. Cheap workers do the reading. Nothing is called done until it is checked.

[![CI](https://img.shields.io/github/actions/workflow/status/rhawk117/mightymodels/ci.yml?event=pull_request&label=CI&logo=githubactions&logoColor=white)](https://github.com/rhawk117/mightymodels/actions/workflows/ci.yml)
[![Supply chain](https://img.shields.io/github/actions/workflow/status/rhawk117/mightymodels/weekly-security-scan.yml?label=supply%20chain&logo=githubactions&logoColor=white)](https://github.com/rhawk117/mightymodels/actions/workflows/weekly-security-scan.yml)
[![Release](https://img.shields.io/github/v/release/rhawk117/mightymodels?label=release&logo=github)](https://github.com/rhawk117/mightymodels/releases)
[![License](https://img.shields.io/github/license/rhawk117/mightymodels)](LICENSE)

[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757?logo=claude&logoColor=white)](https://code.claude.com/docs/en/plugins)
[![Skills](https://img.shields.io/badge/skills-19-6E56CF)](#skills)
[![Workers](https://img.shields.io/badge/workers-12-6E56CF)](#workers)
[![Hooks](https://img.shields.io/badge/hooks-7-6E56CF)](#under-the-hood)

[![Python 3.14](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/badge/types-ty-261230)](https://github.com/astral-sh/ty)
[![prek](https://img.shields.io/badge/prek-enabled-F5A623)](https://github.com/j178/prek)

[Install](#install) · [Requirements](#requirements) · [How the work moves](#how-the-work-moves) · [Skills](#skills) · [Workers](#workers) · [Under the hood](#under-the-hood) · [Development](#development)

</div>

______________________________________________________________________

Each piece of work gets one `.mightymodels/<slug>/` directory and one `ticket.yml` carrying its scope and model routing. When the work merges, `/prune-ticket` compresses the directory into a 30-line archive and deletes it. The unit of deletion is the unit of work, which is what stops working state from turning into a landfill of stale evidence.

The plugin ships **nineteen skills**, **twelve worker agents**, **seven hooks** and **one MCP server** that holds the state.

<details>
<summary><b>Table of contents</b></summary>

- [The problem it solves](#the-problem-it-solves)
- [The ritual](#the-ritual)
- [Nothing is tracked by git](#nothing-is-tracked-by-git)
- [The names](#the-names)
- [Requirements](#requirements)
- [Install](#install)
- [How the work moves](#how-the-work-moves)
  - [Phase 1: triage](#phase-1-triage)
  - [Phase 2: planning](#phase-2-planning)
  - [Phase 3: execution](#phase-3-execution)
  - [Phase 4: review](#phase-4-review)
- [Walking away: baton-pass](#walking-away-baton-pass)
- [Skills](#skills)
- [Workers](#workers)
- [Under the hood](#under-the-hood)
- [What is not there yet](#what-is-not-there-yet)
- [Development](#development)

</details>

## The problem it solves

mightymodels is built from the failures of spec-driven development. It is oriented around human-in-the-loop decision making, and it is the plugin I cannot live without. It has cut my token consumption, the model gets more of the work right, and it has changed the way I work with AI.

> [!NOTE]
> I have no numbers for any of that yet. I plan to evaluate this release aggressively over the coming days, and what I measure will go here.

Each row is a way agent work goes wrong, and what the loop does about it.

| What goes wrong | What mightymodels does |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A plan written up front goes stale as the code moves. | `plan.md` is a ledger of invariants, tasks, non-goals and risks, deliberately free of code citations. Citations are gathered fresh for each task, at the moment it starts. |
| The agent makes a decision that was yours to make. | Facts go to scouts and decisions go to you. Investigation rounds stop at a gate, the plan needs your approval before any dispatch, and no review finding is fixed unless you picked it. |
| "Done" is a claim nobody checked. | The primary writes what was asked, the implementer writes what it did, and the fact-checker compares the two. A task closes only through the `task` tool, against its recorded commit. |
| An expensive model spends its context reading files. | Scouts do the reading on `haiku`. The primary spends its context on routing and judgment. Each worker refuses the work of the tier above it. |
| You cannot stop without losing what the session knew. | `baton-pass` writes down the facts that live nowhere else and prints the opening prompt for the next session. The rest already lives in the ticket directory and the state database. |
| A failure gets retried blind. | What does not verify is routed: to a residual fix, then to you, then to the architect, then to a debugging protocol that stops after three strikes. |
| Plans, specs and notes pile up in the repository and confuse the next agent. | Nothing under `.mightymodels/` is ever tracked by git, and `/prune-ticket` archives the ticket in 30 lines and deletes the directory when the work merges. |

## The ritual

mightymodels is a ritual, a predictable ceremony by design. Every piece of work goes through the same steps in the same order, and the value comes from that sameness. A step that always happens is one the model cannot skip.

Four ideas sit under it:

1. **You make the design choices**, and the model does not. Scouts bring facts, `cross-examine` puts each decision to you, and the plan is written from your answers.
2. **Risk is established up front and kept small.** `plan.md` lists the risks with the handling you chose for each. The work is cut into small tasks, every one with a clear acceptance criterion, and a task with more than four criteria or more than three owned files is flagged with a pointer to `break-it-down`, which puts the split to you.
3. **Your decisions are recorded so they are never forgotten.** `cross-examine` restates the decisions record after every round, `plan.md` keeps it through a compaction, `BATON.md` carries the settled ones to the next session, and the archive keeps them after the ticket is deleted.
4. **What is non-deterministic should be deterministic.** Which ramp a ticket takes is read from `ticket.yml`. Each worker's model is fixed. A task closes through a tool that checks its commit and the files it touched. And a hook refuses a dispatch where a rule in prose could be ignored.

## Nothing is tracked by git

Nothing under `.mightymodels/` is ever tracked by git, and that is by design.

> [!IMPORTANT]
> Spec-driven development has historically left tons of slop artifacts behind, which litter the repository and confuse the agents that read them later. mightymodels keeps its working files where git cannot see them and deletes them when the work merges.

Nobody runs an ignore step by hand. Whenever the plugin opens the state database, it adds the line `.mightymodels/` to `info/exclude` in git's common directory, so worktrees share it and no commit is needed. The line covers the whole directory, the archives and every `ticket.yml` included.

> [!WARNING]
> There is also a _second_ reason for keeping the exclusion local. `briefs/` and `review/` carry raw command output that can hold secrets, and a local exclusion means a careless `git add -A` cannot ship them. See [SECURITY.md](SECURITY.md#local-working-state).

What reaches git is the work itself: the commits. The review trail goes on the PR.

## The names

Some of the names are silly, and that is by design. Despite how much this plugin delivers, I promise that after a day of running it you will know every skill and subagent by heart, because they are all very memorable.

| You say | What happens |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `lets-investigate` | Scouts go and read, one narrow question each, and you decide when it is enough. |
| `game-plan` | The plan gets written, after `cross-examine` has grilled you about it. |
| `agents-assemble` | The sprint. One task at a time, each one verified before the next starts. |
| `ask-an-adult` | A judgment call goes to `wingman`, the strongest reasoner in the fleet, which has no tools. |
| `whats-broken` | Debugging from evidence, with a three-strike limit. |
| `stick-the-landing` | The push, the PR, and `gitty-up` watching CI. |
| `review-circus` | `uncle-bob` grades the code and `merge-vader` gives the merge verdict. |
| `baton-pass` | You walk away, and the next session picks up where you stopped. |
| `crashout` | You rant, and it writes the rant down verbatim. |

The workers have names too. `terry-toolchain` surveys your environment, the `intern` gets the one-file jobs, and the `architect` is who gets called when the engineer has failed. The full cast is under [Skills](#skills) and [Workers](#workers).

## Requirements

### Required

| Dependency | Why | Install |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **Claude Code** | The host for the skills, workers, hooks and MCP server. | [Set up Claude Code](https://code.claude.com/docs/en/setup) |
| **uv**, on `PATH` | The hooks and the state server both start through `uv run --locked`, against the plugin's own `uv.lock`. | [Install uv](https://docs.astral.sh/uv/getting-started/installation/) |
| **Python 3.14+** | The plugin's packages require it. uv fetches it on first run, so nothing needs installing by hand. | [uv: install Python](https://docs.astral.sh/uv/guides/install-python/) |
| **git** | A ticket's files live in `.mightymodels/` at the git toplevel of the repository you are working in, and the hooks look up the ticket for the checked-out branch. | [Install git](https://git-scm.com/downloads) |
| **A POSIX system** | The hook wrappers are `sh` scripts and `gitty-up` is `bash`. There is no native Windows launcher, so use WSL on Windows. | [Install WSL](https://learn.microsoft.com/windows/wsl/install) |
| **Network access**, on first run | uv downloads Python and the locked dependencies the first time it builds the environment. | |

### Optional

| Dependency | What it unlocks | Without it | Install |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **GitHub CLI** (`gh`), logged in | Issues, pull requests, PR comments, and `gitty-up` watching CI. | `open-ticket` keeps the issue body as a file and shows you the command; `stick-the-landing` shows the command and stops. | [cli.github.com](https://cli.github.com/) |
| **jq** | `gitty-up` parses the check results with it. | `gitty-up` cannot report on CI. | [Download jq](https://jqlang.org/download/) |
| **jira-cli** (`jira`) | Jira tickets, when you pick Jira as a ticket's tracker. | `open-ticket` writes a draft file. | [ankitpokhrel/jira-cli](https://github.com/ankitpokhrel/jira-cli#installation) |

## Install

```text
/plugin marketplace add rhawk117/rygentic-harness
/plugin install mightymodels@rygentic-harness
```

> [!TIP]
> Run `/agents` in a session afterwards. The twelve workers should be listed as `mightymodels:<folder>:<name>`. If they are not, fix the install before debugging the loop, because the ticket routing dispatches workers by those types.

Plugin skills show up as `/mightymodels:agents-assemble`, and the short form `/agents-assemble` works whenever the name is unambiguous in your session.

## How the work moves

One piece of work is split across several short sessions. Each has a narrow job and leaves a written artifact behind, so the next session starts from files and not from somebody's chat history.

The work passes through four phases in order. Inside each phase there is a loop, and every loop has a way out that goes through you.

```mermaid
flowchart TD
    subgraph Triage
        A["lets-investigate\nchat triage with scouts"] --> B["what-we-know\ncited knowns, SWOT"]
        B --> C["open-ticket\ninterview, ticket.yml, issue, branch"]
    end
    subgraph Planning
        C --> D{scope}
        D -->|"sm, no plan"| E["one-shot"]
        D -->|"any other combination"| F["game-plan"]
    end
    subgraph Execution
        E --> G["agents-assemble\nper-task work loop"]
        F --> G
        G --> H["stick-the-landing\nPR and CI via gitty-up"]
    end
    subgraph Review
        H --> I["review-circus\nuncle-bob and merge-vader"]
        I --> J["human review"]
        J --> K["prune-ticket\narchive and delete"]
    end
```

| Phase | The loop inside it | Skills | What it leaves behind |
| --------- | ------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------ |
| Triage | Scout rounds, until you say it is enough | `lets-investigate`, `what-we-know`, `open-ticket` | A ledger of cited facts, then a ticket directory with `ticket.yml` |
| Planning | Question rounds, until the decisions are settled | `one-shot`, `game-plan`, `cross-examine`, `break-it-down` | A task list or an approved `plan.md` |
| Execution | One task at a time, until none are left and CI is green | `agents-assemble`, `stick-the-landing` | Commits, one brief per task, `REPORT.md`, a PR |
| Review | Findings and fixes, until none you picked are left | `review-circus`, `prune-ticket` | Review reports, a PR comment, then a 30-line archive |

Each stage reads `ticket.yml` before doing anything else.

### Phase 1: triage

The problem here is an agent that starts building from a guess. Triage starts in chat, before any ticket exists.

```mermaid
flowchart LR
    Q["your question"] --> S["scouts answer\none narrow question each"]
    S --> L["ledger\nrestated in chat"]
    L --> G{"gate\nyou choose"}
    G -->|"dig further, or redirect"| S
    G -->|"stop"| X["nothing staged"]
    G -->|"consolidate"| W["what-we-know"]
    W --> T["open-ticket"]
```

`lets-investigate` states the target plainly and sends the scouts one narrow question at a time. Scouts retrieve and do not diagnose. Every report is folded into a ledger, and the round ends at a gate where you choose what happens next. When you have enough, `what-we-know` turns the ledger into a table of cited knowns and a list of uncertainties, and resolves each uncertainty by asking you. `open-ticket` then stages the work so a fresh session can start on it.

**What you will usually type:**

- "let's investigate why X happens" to start, with nothing but a question.
- "what do we know" when the scouts have brought back enough and you want it consolidated.
- "cut a ticket for this" once you understand the problem.
- <kbd>/one-shot</kbd> when you already know the task and want to skip triage. It stages the ticket itself.

**When it goes wrong:**

- An investigation heads the wrong way. Every round stops at a gate, so a wrong turn costs one round.
- A judgment call cannot be settled from the facts. `ask-an-adult` takes it to wingman and brings wingman's questions back to you before work resumes.
- `gh` or `jira` is missing. `open-ticket` keeps the body as a file and shows you the command.

**Why it is built this way:** retrieval is cheap-tier work, so the scouts run on the cheapest model. The ledger is saved outside the conversation so a session can end without losing it. And `what-we-know` is the point where the human steers, which is why it asks about each uncertainty.

<details>
<summary><b>Technical details: triage</b></summary>

- code-scout and web-scout run on `haiku`. wingman runs on `fable` and has no tools, so `ask-an-adult` puts the ticket's text into the packet it sends.
- Scout reports separate `VERIFIED` facts from `INFERRED` ones, and anything inferred names what it rests on.
- The ledger is restated in chat every round and saved in the state database. Two hooks, `SubagentStop` on the scouts and `PostToolUse` on `SubagentHandback`, store each scout report for similarity search.
- `what-we-know` cites every known by file:line or URL. It has a second mode, used inside a sprint, that gathers citations for one task and asks nothing.
- `open-ticket` asks for the slug and the tracker (GitHub, Jira, both or none). The `ticket` tool then asks for the scope, the branch, and whether a compaction is expected.
- It creates `.mightymodels/<slug>/` with `ticket.yml`, files the issue with a checked body, cuts and pushes the branch, and validates the ticket into the state database.

</details>

### Phase 2: planning

The problem here is the one spec-driven development has. A plan written before the work is full of code detail that goes stale, and it carries decisions nobody put to you.

```mermaid
flowchart LR
    T["ticket.yml"] --> R{"scope and\nplan-first"}
    R -->|"sm, false"| O["one-shot\ntask list"]
    R -->|"anything else"| V["scouts verify the claims\nterry-toolchain surveys"]
    V --> C["cross-examine\na round of questions"]
    C -->|"decisions still open"| C
    C -->|"settled"| P["plan.md\nyou approve it"]
    O --> S["the sprint"]
    P --> S
```

Which ramp a ticket takes is read from `ticket.yml`. It is never a judgment call. `one-shot` is the fast one: a short interview, a scout check of the claims, and a task list with an acceptance criterion per item. `game-plan` is the full one. Scouts verify the ticket's claims, `cross-examine` interviews you in rounds at the depth you pick, and `plan.md` records what you decided. `game-plan` waits for you to approve the plan before any worker is dispatched.

**What you will usually type:**

- "plan this ticket" for anything that is not small.
- "just send it" or <kbd>/one-shot</kbd> for a small one.
- "grill me" or "stress-test this design" to run `cross-examine` by itself.
- "this task is too big" to run `break-it-down` on one task.

**When it goes wrong:**

- A task is too large. `break-it-down` shows you every piece in one dialog and changes nothing until you answer. You can also keep the task whole.
- A compaction is likely. Saying so in `open-ticket` sends even a small ticket through `game-plan`.
- Nobody will be around when a task blocks. `game-plan` asks who answers a blocked task, and you can tell it to escalate automatically.

**Why it is built this way:**

- `plan.md` carries no code citations, because citations go stale as soon as implementation begins (_another flaw of traditional SDD_), while the plan has to survive compaction.
- Facts in the plan come from scouts and decisions come from you, so the plan records choices you made.

<details>
<summary><b>Technical details: planning</b></summary>

The routing rule:

| scope | plan-first | ramp |
| ---------------- | ---------- | ----------- |
| `sm` | `false` | `one-shot` |
| `sm` | `true` | `game-plan` |
| `med` or `large` | either | `game-plan` |

- An expected compaction sets `plan-first: true`.
- `one-shot` runs by itself at session start when the active ticket says `scope: sm` and `plan-first: false`. An explicit `/one-shot` runs on any scope, after a confirmation on `med` or `large`. It reconfirms the claims at HEAD with two or three scouts, assumes no compaction, and writes no plan or handoff file.
- `game-plan` has terry-toolchain survey the environment once, on `sonnet`, and saves the survey as `toolchain.md` in the ticket directory.
- `cross-examine` has three depths: Skim, Standard and Relentless. It restates a decisions record after every round.
- `plan.md` holds invariants with how each is proved, dependency-ordered tasks each with a size (`tiny`, `sm`, `med` or `large`) and acceptance criteria, non-goals, and risks with the handling you chose.
- Only the answer "escalate automatically" writes `auto-escalate: true` into `ticket.yml`.
- The `task` tool's `task_start` warns about a task with more than four acceptance criteria or more than three owned files and names `break-it-down`. An engineer or architect that returns `too-large` lands there too.

</details>

### Phase 3: execution

The problem here is the implementer that reports success. A model will tell you a task is done, and the only way to know is to check.

```mermaid
flowchart TD
    N["next task"] --> B["primary writes ASKED"]
    B --> D["dispatch\nintern for tiny, engineer otherwise"]
    D --> F["fact-checker\nDONE against ASKED"]
    F --> V{"task verify"}
    V -->|"closed"| N
    V -->|"bounded miss"| R["engineer residual\none attempt"]
    R --> V
    V -->|"failed or blocked"| U["you, then the architect"]
    U -->|"architect fails too"| W["whats-broken\nthree strikes, then you"]
    N -->|"no tasks left"| H["stick-the-landing"]
    H --> I{"CI"}
    I -->|"fail"| X["residual, or whats-broken"]
    X --> H
    I -->|"pass"| Y["review"]
```

`agents-assemble` runs one task at a time. The primary writes what is being asked, an implementer does the work, runs the task's checks and writes what it did, and the fact-checker compares the two halves. Only then does the primary give its verdict, the task close and the next one start. A task's size picks its worker: the intern for a `tiny` one, the engineer for everything else.

The sprint never pushes. `stick-the-landing` does that, and only you can start it. It opens the PR and has gitty-up watch CI, and a failing check goes back into the loop as a task.

**What you will usually type:**

- "start the sprint" or "run the loop" once the plan is approved.
- "pass the baton" when you want to stop. See [Walking away](#walking-away-baton-pass).
- <kbd>/stick-the-landing</kbd> when every task is done.

When it goes wrong, the failure is routed. Nothing is retried blind.

| What happened | Where it goes |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| A bounded miss on a task | An engineer residual, with one attempt |
| The intern's task blocks | The engineer |
| The engineer fails or blocks | You first, then the architect for one pass |
| The architect fails too | `whats-broken`: reproduce, gather evidence, test one hypothesis at a time. After three strikes it escalates to you. There is no fourth patch. |
| An engineer's own fix keeps failing | `agent-debugging`. A fourth failed fix is refused and the engineer reports `blocked`. |
| A CI check fails | If the fix is obvious from the last screen of the log it is an engineer residual, otherwise it is `whats-broken`. |
| The session compacts | A `PreCompact` hook snapshots the ticket. Recovery reads the recorded state, never a conversation. |
| The engineer is dispatched too early | The dispatch hook refuses it until a task is started. |

**Why it is built this way:** the brief has two halves so that neither side's claims are taken on faith. The loop advances only after its evidence is written down, so recovery never depends on what an agent remembers. The architect sits one tier above the engineer that failed and gets one pass. When that fails too, patching stops and `whats-broken` starts again from evidence. And the dispatch hook holds the primary to the loop, because an instruction in prose was not enough.

<details>
<summary><b>Technical details: execution</b></summary>

- The brief is `briefs/task-NN.md`, capped at 80 lines: roughly 15 for ASKED and up to 65 for DONE. ASKED holds the objective, checkable acceptance criteria, the scoped checks to run, the files the task owns and the engineer tier. The implementer appends DONE with the commit hash.
- The `task` tool's `task_verify` closes a task on the primary's verdict and the recorded commit. It refuses on the task's status, its base and its owned set, and reports any change outside the owned files.
- A `tiny` task has one owned file. It goes to the intern on `haiku` for one attempt. The engineer runs on `sonnet` and the architect on `opus`. The primary may bump the engineer one tier for a single hard task, and logs the reason in that task's ASKED stanza.
- Residual fixes run as `R<n>` tasks and failing CI checks as `C<n>` tasks.
- With `auto-escalate: true` in `ticket.yml`, a failed or blocked engineer task goes to the architect without asking you first.
- `agent-debugging` is preloaded into the engineer. Its `failed_fix_record` tool stores three failed fixes per task and refuses a fourth.
- While the checked-out branch has exactly one unclosed ticket, the dispatch hook refuses the main thread's dispatch of the engineer or the architect until a task is started. With several unclosed tickets it warns instead. It refuses a dispatch of the intern unless the task owns exactly one file.
- gitty-up waits for the checks under a time budget: 20 minutes by default, 60 at most.
- The sprint ends with a `REPORT.md` of at most 50 lines: what shipped, what deviated, what remains.

</details>

### Phase 4: review

The problem here is review that happens somewhere reviewers never look, by the same context that wrote the code, followed by fixes nobody asked for.

```mermaid
flowchart LR
    G["one gate\ndepth, emphasis, scope"] --> M["measure the surface"]
    M --> U["uncle-bob"]
    M --> V["merge-vader"]
    U --> F["merged findings\ncomment on the PR"]
    V --> F
    F --> P{"findings\nyou pick"}
    P -->|"some"| X["engineer task\nor residual"]
    X --> G
    P -->|"none left"| H["human review"]
    H --> K["prune-ticket"]
```

`review-circus` asks one question up front for the depth, the emphasis and the scope, then runs two reviewers in parallel. uncle-bob grades maintainability against SOLID, the Clean Code smells catalog and the Clean Architecture component metrics. merge-vader reads the diff for security, regressions, weakened gates and documentation drift, and ends in `BLOCK`, `MERGE WITH CONDITIONS` or `CLEAR`. Their findings are merged, and an abridged comment is always posted to the PR, pass or fail.

You decide each finding by id. Then the fixes are routed by risk first and by source second:

| Finding | Where it goes |
| --------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Critical, or a security finding at High or above | A full engineer task, whichever reviewer found it |
| Any other uncle-bob finding | A full engineer task, because it concerns structure and abstraction |
| A single-concern merge-vader finding with usable Fix and Verify lines | An engineer residual |

After human review and merge, `/prune-ticket` writes the archive, proposes documentation updates as diffs, and deletes the ticket directory on your confirmation.

**What you will usually type:**

- "run the review circus" on a PR with green CI.
- "is this safe to merge" or "uncle-bob this module" for a quick pass by one reviewer.
- <kbd>/prune-ticket</kbd> after the merge.

**When it goes wrong:**

- A fix fails. It climbs to the architect the way a sprint task does.
- There is no PR, or no `gh`. The comment is kept as a file and you get the command.
- Work is still live. `prune-ticket` refuses to delete anything.

**Why it is built this way:** the comment goes on the PR so the review trail is documented where reviewers live. A severity that says "harm now" outranks any statement about who found the defect, which is why risk routes before source. And nothing you did not pick is fixed.

<details>
<summary><b>Technical details: review</b></summary>

- `review-circus` runs on a diff, a branch, a ticket or the whole codebase.
- The reviewers take their model from the review run: `sonnet` for a quick review, `opus` for standard and deep. One run may spend a single override, through `review_override`, that moves its heavier-weighted reviewer to `fable`.
- The `review_metrics` MCP tool measures structure (fan-in, fan-out, cycles, sizes), and the `signals_code_churn`, `signals_change_coupling` and `signals_code_hotspots` tools measure git history. qualitylens, on `haiku`, transcribes the numbers and judges nothing.
- merge-vader may dispatch code-scout, web-scout and qualitylens. uncle-bob may dispatch code-scout and qualitylens.
- Reports land in the run's directory under `.mightymodels/<slug>/review/`. Overlapping findings are severity-unified through the shared table in `skills/agents-assemble/references/contracts.md`.
- Each fix runs under its own `R<n>` task, carrying the finding's Fix and Verify lines.
- `prune-ticket` writes an archive of at most 30 lines at `.mightymodels/archives/<slug>.md`, with a JSON sidecar. It refuses while there are unverified tasks, a live `whats-broken.md`, undecided or unfixed review findings, or unpushed commits.

</details>

## Walking away: baton-pass

This is one of my favorite features. With AI it is hard to walk away from a session cleanly. Stop in the middle and the next session starts cold, or stay and keep working in a context that has grown too long. Either way there is a penalty.

`baton-pass` is how you leave. It works from an active sprint or from a session with no ticket at all. It snapshots the recorded state, runs `what-we-know`, and asks you two things: what the next session should focus on, and what to do with uncommitted work. Then it writes `handoffs/BATON.md` with the facts that live nowhere else (settled decisions, dead ends, working commands, gotchas and parked threads) and prints the opening prompt for the next session.

> [!TIP]
> The loop also offers it at the natural stopping points. `open-ticket` ends by asking whether to plan now, go straight to `one-shot`, or hand off. `stick-the-landing` asks on green whether to review now or hand off. And if a compaction arrives before you get to it, a `PreCompact` hook snapshots the ticket anyway.

<details>
<summary><b>Technical details: baton-pass</b></summary>

- From a session with no ticket, `baton-pass` runs `open-ticket` first, so there is a ticket directory to write into.
- `handoffs/BATON.md` holds only what is recorded nowhere else. The ticket's `context` lines are refreshed alongside it.
- The opening prompt is built from a template that `prompting-subagents` holds.
- The next session starts from `ticket.yml`, the `task` tool and the briefs.

</details>

## Skills

Claude Code picks a skill from your prompt and the skill's description, or you name it with a slash. Three run only when you start them: `stick-the-landing`, `prune-ticket` and `crashout`. Four are never invoked by hand, because a worker or the primary loads them: `agent-debugging`, `becoming-uncle-bob`, `becoming-merge-vader` and `prompting-subagents`. Each skill's full instructions are in `skills/<name>/SKILL.md`.

| Skill | Phase | What it does |
| ---------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `lets-investigate` | Triage | Opens a chat-first investigation before any ticket exists. Scouts get one narrow question each, and every round stops at a gate where you choose to dig further, redirect, stop or consolidate. |
| `what-we-know` | Triage | Consolidates understanding: knowns with file:line or URL citations, the uncertainties, and an analysis shaped by the question. |
| `open-ticket` | Triage | Turns an understood problem into a staged ticket: the directory, the issue or a local draft, the branch, and `ticket.yml` with derived model routing. |
| `one-shot` | Planning | The fast ramp. One dialog, a scout check of the claims at HEAD, a task list with an acceptance criterion per task, then straight into `agents-assemble`. It writes no plan or handoff file. |
| `cross-examine` | Planning | Interviews you about a plan, design or decision at a depth you pick first: Skim, Standard or Relentless. |
| `game-plan` | Planning | The large-scope ramp. Scouts verify the ticket's claims, `terry-toolchain` surveys the environment, `cross-examine` runs, and `plan.md` is written as a compaction-safe ledger. |
| `break-it-down` | Planning | Splits a task that is too large into reviewable pieces. It changes nothing before you answer. |
| `agents-assemble` | Execution | The per-task work loop: citations, the two-half brief, a dispatch, the fact-checker, then verify. It ends in a `REPORT.md` of at most 50 lines and never pushes. |
| `stick-the-landing` | Execution | Closes the sprint: pushes, opens the PR from the repository's template and has `gitty-up` watch CI. |
| `whats-broken` | Execution | The primary's debugging protocol: reproduce, gather evidence, test one falsifiable hypothesis at a time, then fix through a normal engineer dispatch with a regression test. Three strikes and it escalates. |
| `agent-debugging` | Execution | The same protocol for one engineer with nobody to dispatch. A fourth failed fix is refused and the engineer reports `blocked`. |
| `review-circus` | Review | The endgame review. `uncle-bob` and `merge-vader` run in parallel, and an abridged comment is always posted to the PR, pass or fail. Only the findings you pick get fixed. |
| `becoming-uncle-bob` | Review | The `uncle-bob` worker's doctrine: grade a branch or a codebase against SOLID, the Clean Code smells catalog and the Clean Architecture component metrics. |
| `becoming-merge-vader` | Review | The `merge-vader` worker's doctrine: an adversarial pre-merge review that ends in `BLOCK`, `MERGE WITH CONDITIONS` or `CLEAR`. |
| `prune-ticket` | Review | Closes out finished work: a 30-line archive, documentation updates proposed as diffs, then deletion of the ticket directory on your confirmation. It refuses while live work remains. |
| `baton-pass` | Any | Hands a session to the next one: `handoffs/BATON.md` with the facts that live nowhere else, and an opening prompt for the next session. |
| `ask-an-adult` | Any | Takes a judgment call that cannot be decided to `wingman`, and carries its questions to you before work resumes. For reasoning, not for facts a scout can retrieve. |
| `prompting-subagents` | Any | Builds, checks or repairs the dispatch packet for a worker: which worker, which template, which model alias. |
| `crashout` | Any | The pressure valve. On an explicit `/crashout` it journals your rant verbatim, checks whether the failure has happened before, and turns repeated tilt into standing corrective actions. |

## Workers

The twelve workers are subagent files under `agents/`, in three folders: `triage`, `workers` and `review`.

| Folder | Worker | Model | Job |
| --------- | ----------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `triage` | `code-scout` | `haiku` | Repository retrieval: files and symbols, call sites, config values, dependency versions. |
| `triage` | `web-scout` | `haiku` | Documentation retrieval: one official page, changelog or release note, cited by URL and section. |
| `triage` | `wingman` | `fable` | The decision advisor. It has no tools and works only from the packet it is given. |
| `triage` | `terry-toolchain` | `sonnet` | The environment surveyor, dispatched once per `game-plan` run. |
| `workers` | `engineer` | `sonnet` | The default implementer. One task group or one residual fix, inside the files the dispatch owns. |
| `workers` | `architect` | `opus` | The higher-cost recovery implementer, for a task the engineer failed or a reviewer rejected. |
| `workers` | `intern` | `haiku` | The lowest-cost implementer, for a task the plan sizes `tiny`: one owned file. |
| `workers` | `gitty-up` | `haiku` | The CI watcher. It opens or takes a pull request and waits for the checks under a time budget, 20 minutes by default and 60 at most. |
| `review` | `uncle-bob` | by depth | The maintainability reviewer. |
| `review` | `merge-vader` | by depth | The release-readiness reviewer. |
| `review` | `qualitylens` | `haiku` | The measurement worker: code churn, change coupling and hotspots. |
| `review` | `fact-checker` | `haiku` | The task verifier. It checks a brief's DONE half against its ASKED half before the task closes. |

All of them are delegation-only. Half the fleet runs on `haiku`, and what keeps it cheap is that each worker refuses the work of the tier above it.

> [!NOTE]
> The model names are Claude Code aliases, and which model an alias resolves to is Claude Code's decision in your session.

The main conversation dispatches every worker. A worker dispatches only the workers its agent file names, and a hook refuses anything else.

## Under the hood

<details>
<summary><b>Hooks: seven of them, on five events</b></summary>

`hooks/hooks.json` registers seven hooks on five events. Each runs the `mightymodels-hooks` package against the state database and has a timeout of 10 seconds.

| Event | Matcher | What it does |
| -------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SessionStart` | any | Exports the plugin data directory to the session's commands and prunes old session pointers. |
| `PreToolUse` | `Agent` | The dispatch hook. It holds a worker to the workers its agent file allows, and refuses the main thread's dispatch of the engineer or the architect until a task is in progress. |
| `SubagentStop` | the two scouts | Stores the scout's report for similarity search. |
| `PostToolUse` | `SubagentHandback` | Stores a scout report handed back mid-session. |
| `PostToolUse` | `AskUserQuestion` | Records each answered question as a decision in the ledger of the investigation or ticket the session is working on. |
| `PostToolUse` | the `mighty-mcp` tools that name a ticket | Points the session at that ticket or investigation, so later hooks know which ledger it is working in. |
| `PreCompact` | any | Writes a snapshot of the ticket on the checked-out branch before a compaction. |

The hooks record and route. They are not a permission control: they do not run or approve commands, and they do not replace Claude Code's permission prompts. [SECURITY.md](SECURITY.md#what-the-plugins-hooks-do) lists exactly what the dispatch hook refuses, including what happens when the state cannot be read.

</details>

<details>
<summary><b>State: where a ticket lives</b></summary>

The state lives in two places.

A ticket's files (`ticket.yml`, the plan, briefs, snapshots, review runs and archives) are in the target repository's `.mightymodels/` directory, at the git toplevel. None of them is tracked by git; see [Nothing is tracked by git](#nothing-is-tracked-by-git).

The rows (tickets, tasks, review runs, ledgers, crashouts, closings and stored scout reports) are in `state.db`, one SQLite database in the plugin data directory that Claude Code names in `CLAUDE_PLUGIN_DATA`. That file is outside every repository and serves all of them.

`mcp-servers/mighty-mcp.json` declares one stdio server named `mighty-mcp`, started with `uv run --locked --no-dev --package mightymodels-mcp mightymodels-mcp`. The skills call its tools as `mcp__plugin_mightymodels_mighty-mcp__<tool>`, and those tools and `AskUserQuestion` are the only ones a skill's `allowed-tools` pre-approves. No skill pre-approves `Bash`, `Edit` or `Write`. [docs/mighty-mcp-tools.md](docs/mighty-mcp-tools.md) lists all 35 tools by domain.

Contracts shared by every stage live with the skills that own them. The severity table, the verdict vocabularies and the two-half brief schema are in `skills/agents-assemble/references/contracts.md`. The ticket schema and the directory layout are in `skills/open-ticket/references/`. When a skill and a contract disagree, the contract wins and the skill gets fixed.

</details>

<details>
<summary><b>Startup: how the plugin runs</b></summary>

Nothing is installed globally. Both entry points run through `uv run` against the plugin's own `uv.lock`, with `UV_PROJECT` set to the plugin root and the environment kept in the plugin's `.venv`:

```sh
# hooks/lib.sh, sourced by hooks/hook.sh and hooks/dispatch-hook.sh
exec uv run --locked --no-dev --package mightymodels-hooks mightymodels-hooks "$@"
```

`hooks/hook.sh` wraps the recording hooks. When it cannot run, it prints `mightymodels hook did nothing` with the hook's name to standard error and lets the tool call through. `hooks/dispatch-hook.sh` wraps the dispatch hook and fails closed instead: when it cannot run, it refuses any dispatch made by a plugin worker, and any dispatch of the engineer, architect or intern while the project has a `.mightymodels/` directory.

</details>

<details>
<summary><b>Layout: what is in the repository</b></summary>

```text
.claude-plugin/plugin.json  the plugin manifest
mcp-servers/mighty-mcp.json the state server
agents/                     the twelve workers, in triage/, workers/ and review/
skills/                     the nineteen skills
hooks/                      hooks.json (the seven hooks) and the sh wrappers
bin/gitty-up                the CI watcher script
packages/core/              mightymodels_core: the domain, the SQLite store, git access
packages/hooks/             mightymodels_hooks: the hook subcommands
packages/mcp/               mightymodels_mcp: the mighty-mcp server and its tools
docs/                       the MCP tool reference
tests/                      the test suite
pyproject.toml              the mightymodels-plugin project and the uv workspace root
uv.lock                     the pinned dependencies
```

</details>

## What is not there yet

- Nothing measures the token savings or the correctness yet. That is the evaluation planned for the coming days.
- No trigger datasets ship in this repository yet, so nothing measures skill selection. Until they do: a skill that runs when named but never selects itself has a description problem, and a skill the slash menu cannot find has a loading problem.
- Only one permission mode has been tested so far.
- Whether plugin agents surface, and under which names, depends on your Claude Code version behaving as the current docs describe.

> [!NOTE]
> One thing is left out on purpose: issue-tracker sprint and board operations are outside the plugin.

## Development

The plugin is the `mightymodels-plugin` project at the repository root, which is also the uv workspace root, with `core`, `hooks` and `mcp` as members under `packages/`. Every command goes through `make`:

```sh
make setup        # once: install the prek git hooks and sync every package and group
make format       # the prek hooks in the format group
make lint         # the prek hooks in the lint group: ruff check, ty, shellcheck, hygiene checks
make check        # lint, then the unit, agents and smoke tests
make quality      # every prek hook, then the tests CI runs
uv run pytest     # the whole test suite
```

> [!TIP]
> `make quality` matches CI's quality job. `make check` is the faster local loop, but it skips the format hooks, so it can pass where CI fails.

Security reports go through [SECURITY.md](SECURITY.md). Licensed under [Apache-2.0](LICENSE).
