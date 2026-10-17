# RGS skills: Claude × Gemini pair development

[繁體中文](README.md) | **English**

Two Claude Code skills that let Claude direct Gemini, through the Antigravity CLI `agy`, to write code. Claude plans and reviews, Gemini implements, and Claude's sub-agents handle chores such as tests, docs and git. Every step has a quality gate, and work can resume where it stopped.

The workflow comes from two real projects, an Android app and a RimWorld mod. The pitfalls hit along the way are built into the scripts and rules.

## Contents

- [What it is](#what-it-is)
- [Which command to use](#which-command-to-use)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [First use in a project](#first-use-in-a-project)
- [Tutorial 1: a small task with /rgs-main](#tutorial-1-a-small-task-with-rgs-main)
- [Tutorial 2: several milestones with /rgs-pr](#tutorial-2-several-milestones-with-rgs-pr)
- [Delegation: batch and digest](#delegation-batch-and-digest)
- [Interruptions and resuming](#interruptions-and-resuming)
- [When you need to step in](#when-you-need-to-step-in)
- [Safety mechanisms](#safety-mechanisms)
- [Files that appear in your project](#files-that-appear-in-your-project)
- [Configuration reference: .rgs/profile.json](#configuration-reference-rgsprofilejson)
- [Troubleshooting](#troubleshooting)
- [Repository layout and development](#repository-layout-and-development)
- [What has been verified, and limits](#what-has-been-verified-and-limits)

## What it is

| Role | Does | Does not |
| :-- | :-- | :-- |
| You | State requirements, approve the design, merge PRs on GitHub, approve releases | — |
| Claude (main conversation) | Clarifies requirements, writes specs and fix notes, reviews Gemini's diff, rules on review findings, maintains the knowledge base | Write product code itself |
| Gemini (agy) | Implements the spec, applies fix notes | Run shell or git, change files outside the spec, read secret files |
| agy reviewer | Fresh, read-only conversation that reviews in parallel along four lenses: security, correctness, architecture, spec | Write any file |
| Claude sub-agents | Run agy, run tests, update docs, commit, open PRs | Fix code; they stop and report on failure |

Why this split? Gemini is cheap and can write code for a long time, but it cannot build or run tests, and it sometimes gets things wrong or goes out of scope. Claude is good at making requirements precise and holding the quality bar. So Claude writes only specs and reviews. Which files Gemini may change is enforced by a hook, not merely requested in a prompt.

## Which command to use

| | `/rgs-main` | `/rgs-pr` |
| :-- | :-- | :-- |
| For | Small features, bug fixes, solo repos | Several features or screens; needs requirements and design docs; needs human checkpoints |
| Flow | Spec → Gemini implements → Claude reviews and tests → push to main on pass | Requirements → design (you approve) → milestones → Gemini implements → Claude reviews → PR → independent agy review → **you merge** → knowledge capture → release |
| On failure | Claude writes fix notes, Gemini revises, Claude reviews again | Same; every agy finding is ruled on by Claude and recorded |
| Output | One commit on main | One PR per milestone; `docs/rgs/` keeps requirements, design, specs and review rulings |
| Subcommands | `status`, `batch`, `digest` | `init`, `plan`, `run M<n>`, `merged <PR#>`, `release <version>`, `status`, `batch`, `digest` |

If unsure, start with `/rgs-main`. When a task needs several milestones, Claude will suggest switching to `/rgs-pr`.

## Prerequisites

| Requirement | How to check |
| :-- | :-- |
| [Claude Code](https://claude.com/claude-code) (CLI or desktop) | — |
| Antigravity CLI `agy` 1.4.0 or later, signed in | `agy --version`; running `agy` once walks you through sign-in |
| Python 3.10+ (standard library only) | `python --version` |
| git with `user.name` / `user.email` set | `git config user.name` |
| A git remote for the project | `git remote -v` |
| For `/rgs-pr`: GitHub CLI, signed in | `gh auth status` |

On Windows, the build and test commands in the profile run in Git Bash by default.

## Installation

1. Get this repository:

   ```bash
   git clone https://github.com/DreamOver9183/RGS_skills.git
   ```

2. Run the installer:

   ```bash
   powershell -ExecutionPolicy Bypass -File RGS_skills/install.ps1
   ```

   It creates three junctions under `~/.claude/skills/`: `rgs-core`, `rgs-main` and `rgs-pr`, all pointing into this repository. A later `git pull` therefore updates the skills too. Install all three, because `rgs-main` and `rgs-pr` use their sibling `rgs-core`.

3. **Start a new Claude Code session.** Skills are loaded only when a session starts. Typing `/` should now list `/rgs-main` and `/rgs-pr`.

To uninstall, run `powershell -ExecutionPolicy Bypass -File RGS_skills/install.ps1 -Uninstall`. It removes only the junctions, never the repository.

macOS / Linux have no installer yet. You can create symlinks by hand; this is not yet verified on those platforms:

```bash
ln -s "$PWD/RGS_skills/skills/rgs-core" "$PWD/RGS_skills/skills/rgs-main" "$PWD/RGS_skills/skills/rgs-pr" ~/.claude/skills/
```

## First use in a project

Open Claude Code in the project folder. The first time you run either command, Claude checks the environment:

```
/rgs-pr init          ← for a /rgs-pr project
/rgs-main <task>      ← /rgs-main runs a shorter version automatically
```

What happens:

1. **Environment check**: agy version and models, Gemini quota, git identity, remote, clean working tree; plus `gh` sign-in for `/rgs-pr`.
2. **`.rgs/profile.json` is drafted**: build and test commands are detected (Gradle, npm, dotnet, cargo, go, pytest/unittest), along with the knowledge-base file (`CLAUDE.md` / `AGENTS.md`) and secret files. Claude shows you the draft to confirm, for example "Is `./gradlew testDebugUnitTest` the right quick check?"
3. **Knowledge base**: if the project has no `CLAUDE.md` or `AGENTS.md`, Claude creates one from a template. It covers architecture rules, secret rules, common commands, conventions and pitfalls.
4. **Permission rules**: Claude lists suggested rules such as:

   ```
   Bash(python -I "D:/Claude Code/RGS_skills/skills/rgs-core/scripts/rgs.py":*)
   ```

   Add them to `permissions.allow` in the project's `.claude/settings.json` so you are not prompted at every step. Claude cannot change its own settings, so this step is yours.

## Tutorial 1: a small task with /rgs-main

Example: add division to `calc.py`.

**1. Hand over the task**

```
/rgs-main add div(a, b) to calc.py, raise ValueError("division by zero") on zero, and add tests
```

**2. Claude writes the spec.** Claude first reads the relevant code and the knowledge base. It then writes `.rgs/runs/add-div/spec.md`, which covers:

- the goal
- the **files that may change** (for example only `calc.py` and `tests/test_calc.py`); Gemini can write only to the files on this list
- implementation notes
- acceptance criteria
- required tests
- relevant past pitfalls

**3. Gemini implements.** Claude creates a separate worktree next to your project, `<project>.rgs/add-div`, on branch `rgs/add-div`, and starts Gemini in the background. A small task takes about 1–3 minutes; a milestone takes about 5–20 minutes. Your main checkout is never touched, so you can keep working.

**4. Claude reviews.** When Gemini finishes, Claude:

- checks that Gemini changed only allowed files, and looks at anything the guard blocked
- reads the whole diff for correctness, compile risks, spec and tests, and project conventions
- runs the profile's quick and verify commands

**5. If it fails, Gemini fixes it.** For example, if the tests miss negative numbers and `0.0`, Claude writes concrete fix notes: the file, the location, and what to change. Gemini applies them in the same conversation, and Claude reviews again. After 4 rounds Claude stops and asks you.

**6. If it passes, it goes to main.** Claude writes the commit message, then:

- runs a secret scan
- commits
- if origin/main moved meanwhile, rebases and reruns the tests
- fast-forward pushes to `origin/main`
- syncs your local main
- removes the worktree and branch

**7. Report.** Claude reports the commit hash, the files changed, how many fix rounds there were, the test results, and anything not yet verified. A badge at the start of the report says who did the work: 🧩 Gemini did it and it passed checks, ⚡ Claude did it, ⚠️ something went wrong or fell back.

For risky changes such as security or data migrations, ask for an independent agy review before the push (`--gate`).

## Tutorial 2: several milestones with /rgs-pr

**1. Initialise (once per project)**

```
/rgs-pr init
```

This sets up the environment check, `profile.json`, the knowledge base and the permission rules (see the previous section). Claude asks before committing these files to the base branch.

**2. Requirements and design**

```
/rgs-pr plan add a favourites page, a restaurant detail page and sharing; favourites must work offline
```

Claude then:

- asks all open questions at once
- writes `docs/rgs/requirements.md`, where every requirement has an ID (R-1, R-2…) and acceptance criteria
- sends sub-agents to study the code architecture and the tests/CI
- writes `docs/rgs/design.md`: verified facts, decision log, risks, milestones M0…Mn, traceability matrix, status overview

**Your part**: read the design and reply "approved" or ask for changes. No code is written before you approve.

**3. Run a milestone**

```
/rgs-pr run M1
```

1. Claude writes the M1 spec.
2. A sub-agent starts Gemini and runs the quick tests.
3. Claude reviews the diff. If it fails, Claude writes fix notes and Gemini revises.
4. A sub-agent runs full verification, updates the knowledge base and README (including real test counts), saves the spec under `docs/rgs/specs/`, pushes the branch and opens the PR.
5. agy runs the merge-gate review in a fresh, read-only conversation, with one subagent per lens. The report is posted as a PR comment.
6. Claude rules on each finding in `docs/rgs/reviews/PR-<N>.md`: adopted, rejected (with a reason), or deferred to a milestone (with a reason). Adopted findings go back to Gemini, followed by a re-review.
7. When no blocker or major finding is open, Claude tells you "PR #N is ready to merge". It includes the verdict, a summary of the rulings, the test counts and anything not yet verified.

**Your part**: look at the PR and the review comment on GitHub, then **merge it yourself**. Claude never runs `gh pr merge`.

**4. Tell Claude after merging**

```
I merged PR #12, please continue with M2
```

Claude then:

- syncs the base branch and removes M1's worktree and branch
- records new decisions, conventions and pitfalls in the knowledge base
- updates the design's status overview and traceability matrix
- starts M2

**Stacked milestones**: if M2 depends on an unmerged M1, Claude stacks M2 on M1's branch (`--stack-on`), so work does not wait for your merge. Once M1 is merged, Claude runs `retarget` to move M2's PR onto the base branch (rebasing first after a squash merge), and only then deletes M1's branch.

**5. Release**

```
/rgs-pr release 1.2.0
```

1. A sub-agent audits docs against code: test counts, version numbers, commands, paths, secrets.
2. The problems it finds are fixed.
3. The version bump goes through the normal PR flow, and you merge it.
4. Artifacts are built from the merged commit, SHA-256 hashes are computed, and release notes are written.
5. **Claude asks you to confirm before creating the GitHub release**, and offers a draft-only release.

## Delegation: batch and digest

These subcommands do not change code. They hand large, noisy work where you only need the conclusion to Gemini. agy runs read-only in an empty temp folder and cannot reach your project.

**digest: long documents or logs**

```
/rgs-main digest logs/app.log which errors happened before the crash, and why?
```

- Lines are first filtered by keyword (for example `ERROR|WARN`), then split into chunks that are processed in parallel.
- Every conclusion comes with a file, line numbers and a verbatim quote. The script checks each quote against the original file and marks it ✓ (verified) or ✗ (check by hand).
- This exists because Gemini, given a very long input at once, once missed an error while claiming it had found them all.

**batch: bulk data**

```
/rgs-main batch transliterate the English names in data/names.jsonl into Traditional Chinese
```

- The input is JSONL, one record per line, each with a unique `id`. You can send only the fields that are needed and attach a validator for automatic checks.
- By default it runs 8 agy processes in parallel, 40 records per batch.
- Every reply is saved. After an interruption or a quota stop, rerunning the same command sends only what is missing.
- Claude suggests a small trial run first and spot-checks the results before you use them.

## Interruptions and resuming

After Claude hits its usage limit, Gemini runs out of quota, or the computer restarts, run:

```
/rgs-main status
/rgs-pr status
```

Claude reads `.rgs/state.json`, which records each task's worktree, branch, Gemini conversation ID, fix round and current step. For `/rgs-pr` it also reads the design's status table. It then continues from the interrupted step. Saying "my usage is back, please continue" works too.

## When you need to step in

| When | What you do |
| :-- | :-- |
| First use in a project | Confirm the profile's commands and secret list; add the permission rules |
| `/rgs-pr` design is ready | Approve or revise it |
| A `/rgs-pr` PR is ready | Review and merge it on GitHub, then tell Claude |
| More than 4 fix rounds | Decide: switch model, split the task, or let Claude take over |
| Gemini quota exhausted | Decide: switch model, retry later, or let Claude take over |
| Push rejected (branch protection, etc.) | Switch to `/rgs-pr`, or sort out permissions yourself |
| Creating a GitHub release | Confirm the version, artifacts and notes |

Claude never writes product code itself without your consent, and never force-pushes.

## Safety mechanisms

- **Isolated worktrees**: Gemini works in `<project>.rgs/<task>` next to your project. The merge-gate review runs in a separate detached worktree. Your main checkout is untouched. Worktrees are deliberately kept out of `%TEMP%`, because Windows Smart App Control blocks test DLLs there, and a run of "0 tests" looks like a pass.
- **Guard hook**: agy's global settings auto-run every tool, and `--mode plan` does not block writes either. So rgs places a PreToolUse hook (`.agents/hooks.json` → `rgs-guard.py`) in the worktree. It:
  - allows writes only to the files listed in the spec
  - allows only read-only listing and search shell commands, with no chaining or redirection
  - blocks reading secret files
  - applies the same limits to subagents
  - denies everything if the hook itself fails
- **No trust in self-reports**: agy can report SUCCESS on a timeout, a denied tool, or a subagent that never replied. The scripts judge success from the actual output, the git diff, the scope check and the test results.
- **Secret scan**: before every commit, the staged diff is scanned for key patterns and protected file names. A hit stops the commit.
- **No auto-merge, no force push**: you always merge `/rgs-pr` PRs yourself, and `/rgs-main` only fast-forwards.

## Files that appear in your project

| Location | Contents | In git |
| :-- | :-- | :-- |
| `.rgs/profile.json` | Project settings | Recommended |
| `.rgs/.gitignore` | Excludes the two entries below | Recommended |
| `.rgs/state.json` | Task state, for resuming | No |
| `.rgs/runs/<task>/` | Spec drafts, prompts, raw agy output, test logs, review reports | No |
| `docs/rgs/` | `/rgs-pr` requirements, design, milestone specs, review rulings | Yes |
| `<project>.rgs/` (next to the project) | Worktrees in progress, removed when tasks finish | — |

## Configuration reference: .rgs/profile.json

`doctor.py --init` drafts the file; any field you leave out takes its default. For a full example, see [`templates/profile.example.json`](skills/rgs-core/templates/profile.example.json).

| Field | Default | Meaning |
| :-- | :-- | :-- |
| `language.docs` / `commits` | `zh-TW` | Language of the docs and commit messages Claude writes, and of agy's review reports and digests. The prompt templates sent to Gemini are always Traditional Chinese; override them in `.rgs/templates/` |
| `knowledge_base` | `["CLAUDE.md"]` | Knowledge-base files, re-read at the start of every phase |
| `remote` / `base_branch` | `origin` / `main` | Where to push and open PRs |
| `docs_dir` | `docs/rgs` | Where `/rgs-pr` documents go |
| `worktree_root` | `<project>.rgs` next to the project | Where worktrees are created |
| `worktree_copy` | `[]` | Untracked files to copy into each worktree, such as `local.properties`; also treated as secrets |
| `shell` / `env` | `bash` / `{}` | Shell and environment variables for build commands, such as `JAVA_HOME` |
| `secrets.deny_read` | `.env*`, `*.pem`, `*.key`, `*_KEY_*`, `*.keystore`, `*.jks` | Files Gemini may not read and that may never be committed |
| `secrets.patterns` | `[]` | Extra secret regular expressions |
| `commands.quick` / `verify` | detected | Quick checks run every round; full verification before delivery |
| `agy.implementer.models` | `gemini-3.8-flash-high` | Implementation model. You can list several; when one runs out of quota, the next is used |
| `agy.reviewer.models` / `lenses` | `gemini-3.8-flash-high` / four lenses | Model and lenses for the merge-gate review |
| `agy.batch` / `agy.digest` | flash-low, 8 workers / flash-high, 4 workers | Models and parallelism for delegation |
| `agy.max_fix_rounds` | `4` | Fix-round limit |
| `agy.fresh_after_input_tokens` | `400000` | Start a fresh Gemini conversation once a resumed one has used this many input tokens |
| `pr.post_review_comment` | `true` | Whether to post the review report on the PR |

## Troubleshooting

| Situation | Cause and fix |
| :-- | :-- |
| The commands don't appear under `/` | Start a new session after installing; check that `~/.claude/skills/` has the three folders |
| A permission prompt at every step | Add the rules from `doctor.py --init` to `.claude/settings.json`. The path in the rule must match the command exactly, including quotes and slashes |
| ⚠️ agy quota exhausted | Use `status` to resume once quota is back, or add fallback models to `models` in the profile |
| Gemini keeps getting blocked by the guard | Look at `guard_denials` in the report. To change a file outside the list, Claude decides whether to widen the list; to run a command, Claude runs it instead |
| `land` rejected (branch protection) | The repo does not allow direct pushes to main; use `/rgs-pr` |
| Garbled Chinese output | The Windows console uses cp950; the scripts handle it. In your own scripts, pass `encoding='utf-8'` |

See [`references/troubleshooting.md`](skills/rgs-core/references/troubleshooting.md) for more. The reference documents are written in Traditional Chinese.

## Repository layout and development

```
skills/
  rgs-main/SKILL.md      /rgs-main workflow
  rgs-pr/SKILL.md        /rgs-pr workflow and subcommands
  rgs-core/              shared core (no SKILL.md, so it is not a command)
    roles.md             roles and hard rules
    references/          gates and review standards, verified agy behaviour, sub-agent briefs, delegation, troubleshooting, script reference
    templates/           spec, requirements, design, fix notes, review note, PR, release notes, knowledge-base skeleton, prompts
    scripts/             rgs.py, review.py, guard.py, doctor.py, batch.py, digest.py, scope_check.py, secret_scan.py
    tests/               unit and integration tests (fake_agy.py stands in for agy, fake_gh.py for gh)
docs/origins/            source material the workflow was distilled from (local paths removed)
install.ps1
```

Run the tests:

```bash
python -m unittest discover -s skills/rgs-core/tests
```

The tests never call the real agy or GitHub and use no quota. The integration tests build a temp repo with a bare remote and run the full flows:

- prepare → implement → fix → check → land
- ship, opening PRs, stacked PRs, review comments, and retarget

To adjust the workflow:

- rules and standards live under `skills/rgs-core/`
- instructions for Gemini live in `templates/` and `templates/prompts/`; a project can override any of them with a file of the same name in `<project>/.rgs/templates/`
- rerun the tests after changing a script

## What has been verified, and limits

- Verified with real Gemini on Windows 11 and agy 1.4.0:
  - `/rgs-main`: implementation, fix rounds, and a rebase-then-push after origin moved
  - `/rgs-pr` on GitHub: opening PRs, stacked PRs, review comments, retarget, and a draft release
  - batch and digest
- agy upgrades can change its behaviour: tool names, the hook format, output fields. The verified behaviour is recorded in [`references/agy-cli.md`](skills/rgs-core/references/agy-cli.md); run `doctor.py` after an upgrade.
- macOS / Linux are not verified yet.
- The skills' internal documents and the prompt templates sent to Gemini are in Traditional Chinese. Set `language.docs` and `language.commits` to `en` to get English docs, commit messages and review reports in your project.
- Gemini's review findings are advice. Claude rules on each one, and you decide what gets merged.
