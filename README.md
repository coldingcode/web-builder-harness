# Web Builder Harness

[中文](README.zh-CN.md) · English

A Claude Code plugin that turns a one-sentence idea into a small, verified web app. It plans the product, builds it in sprints, and checks every sprint with independent agents, enforced by hooks so the builder cannot grade its own work.

## What it does

1. **Plan.** A planner asks a few focused questions, writes a product spec with a design direction, and produces a feature list. Each feature has concrete user scenarios, including at least one tagged `[错误]` / `[error]` or `[边界]` / `[edge]` case.
2. **Confirm once.** You approve the feature list. From then on the scope is frozen and recorded with a hash.
3. **Build in sprints.** Each sprint goes through generate → evaluate → product acceptance. A sprint passes only when both graders pass it. A sprint gets up to 3 cycles; after that the orchestrator asks you what to do.

The roles never overlap:

| Role | Writes | Does not |
|---|---|---|
| Planner | `CLAUDE.md`, `.web-builder/spec.md`, `feature_list.json` (once) | write product code |
| Generator | product code, `tests/` | touch `.web-builder/`, change pass status |
| Evaluator | `.web-builder/evidence/`, its verdict | edit code, score visual taste |
| Product acceptance (PA) | its verdict only | run the app, edit any file |

## Install

Requires Python 3 on your `PATH` (`python3`). The scripts use only the standard library.

In Claude Code:

```
/plugin marketplace add coldingcode/web-builder-harness
/plugin install web-builder@web-builder-harness
```

Then, in an empty folder (or an existing repo), start a run:

```
/web-builder a pomodoro timer web app with a task list
```

Check progress at any time with `/web-builder status`, and resume an interrupted run with `/web-builder resume`.

## Gates

Hooks in `web-builder/hooks/hooks.json` run `web-builder/scripts/hooks.py`. Blocking uses exit code 2, as the Claude Code hook protocol requires.

- **State is script-owned.** `state.json`, `plan_confirmed.json` and `feature_list.json` cannot be written with Write, Edit or shell redirection. Only `harness.py` changes them.
- **Confirmation freezes scope.** After `confirm-plan`, the feature list cannot be rewritten. The scope hash ignores pass status, so marking a sprint does not invalidate it.
- **Verdicts come only from graders.** The evaluator and PA are the only agents that can write verdict files, and the file must match the current sprint and cycle.
- **Sprints pass only on evidence.** `mark-sprint` requires an evaluator `PASS`, a PA score of at least 80 with no P0 issues, and an evidence bundle for that cycle containing `report.md` plus at least one result file or screenshot.
- **Planning comes before code.** Product code cannot be written until the feature list is confirmed.
- **Commits follow Conventional Commits**, for example `feat(F-001): add todo persistence`.
- **Stop gate.** While a sprint is unfinished, the orchestrator cannot end its turn. If a block produces no change at all (no new commit, no working-tree edit, no verdict), the gate releases so the run cannot loop forever. When the cycle budget is spent, the turn may end so you can be asked.
- **Test data stays in tests.** Files named like `*_mock.*`, `*.seed.*` or `*.fake.*` are refused outside `tests/`.
- **The orchestrator writes no project files during a run.** Product code comes from the generator and planning files from the planner.
- **Config is locked.** `.claude/settings*.json` and `.claude/hooks/` cannot be changed by Write, Edit or shell redirection.

The hooks do nothing outside a Web Builder project (a folder with `.web-builder/state.json`), so installing the plugin does not affect your other repositories.

## Project layout

After a run, your project contains:

```
.web-builder/
  state.json            run state (harness.py)
  spec.md               product spec and design direction (planner)
  feature_list.json     features and sprints (planner, frozen after confirmation)
  plan_confirmed.json   confirmation record with scope hash
  verdicts/             sprint-N-evaluator.json, sprint-N-pa.json
  evidence/sprint-N/cycle-C/   report.md, results, screenshots
CLAUDE.md               conventions and commands for the chosen stack (planner)
.claude/rules/web-builder.md   project rules loaded by Claude Code
tests/e2e/              persisted Playwright tests, one folder per sprint
```

## Repository layout

```
.claude-plugin/marketplace.json     marketplace manifest
web-builder/
  .claude-plugin/plugin.json
  agents/                           planner, generator, evaluator, pa
  commands/web-builder.md           the /web-builder orchestration
  hooks/hooks.json
  scripts/harness.py                state machine and control CLI
  scripts/hooks.py                  hook dispatcher
  skills/                           shared reference and PA checklists
  project-template/                 copied into each project on init
tests/test_harness.py               unit and integration tests
docs/history/                       archived v8 design and self-review
```

## Development

The test suite uses only the standard library:

```bash
python3 -m unittest discover -s tests -v
```

It covers the state machine, the cycle budget and extensions, the commit-message and write gates, verdict validation, the Stop gate's release rule, the prompt check, and repository hygiene (manifest versions, hook script paths, no placeholder names).

## Limitations

- The plugin's agent and command prompts are written in Chinese. The README is in English and Chinese. The generated app's language follows your request.
- Scope is frozen after confirmation. To change scope, start a new run in a new folder.
- The evaluator and PA run in the same local environment as the generator, so they are independent by context, not by machine.
- The plugin ships no permission allowlist, so Claude Code asks you to confirm file writes and shell commands. The hooks only block operations; they never pre-approve one.

## History

Version 9 replaces the v8 shell hooks, which did not reliably block and did not match their own design document, with the Python dispatcher and control CLI described here. The v8 design and self-review are archived in `docs/history/`. See [CHANGELOG.md](CHANGELOG.md).

## License

[LICENSE](LICENSE).

## Community 
<a href="https://qm.qq.com/q/xf3G2NODwA" target="_blank"><img src="https://img.shields.io/badge/QQ%20群-1108208001-EB1923?logo=tencentqq&logoColor=white" alt="QQ Group" /></a>

[![LINUX DO](https://img.shields.io/badge/LINUX%20DO-Community-blue)](https://linux.do/t/topic/3028705)
