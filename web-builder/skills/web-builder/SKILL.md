---
name: web-builder
description: Shared reference for Web Builder Harness: phase model, file layout, gate rules, and role responsibilities. Read when planning, building, evaluating, or modifying the harness.
user-invocable: false
---

# Web Builder Reference

Web Builder splits "planning - building - acceptance" into isolated roles and enforces gates using hooks and state files. This document describes the structure and rules only; for operational instructions, see `commands/web-builder.md` and the individual agent definitions.

## Roles

| Role | When It Runs | What It Can Write | What It Cannot Do |
|---|---|---|---|
| Main Process (Orchestrator) | Always | Run control commands, ask user questions | Grade or score on behalf of other roles |
| Planner Agent | Planning phase | `CLAUDE.md`, `.web-builder/spec.md`, `feature_list.json` (once only) | Write product code |
| Generator Agent | Every cycle of each sprint | Product code, `tests/` | Write under `.web-builder/`, modify `passes` |
| Evaluator | After generation | `.web-builder/evidence/`, `verdicts/sprint-N-evaluator.json` | Modify any code, score visual design |
| Product Acceptance (PA) | After evaluation | `verdicts/sprint-N-pa.json` | Run the application, modify any files |

Generators do not evaluate their own output; evaluators and product acceptance do not modify product code; verdicts may only be written by their designated roles.

## Phases

```
planning ──(user confirmation + confirm-plan)──▶ building ──(all sprints pass mark-sprint)──▶ done
                                                   │  ▲
                                                   └──┘  each sprint: cycle → generate → evaluate → acceptance → mark-sprint
```

- `planning`: Allows writing planning files; prohibits writing product code.
- `building`: Progresses sprint by sprint. Up to 3 cycles per sprint; user may approve up to 2 extra cycles.
- `done`: All sprints passed.

## File Layout

```
.web-builder/
  state.json            Process state (maintained by harness.py)
  spec.md               Product specification and design direction (written by planner agent)
  feature_list.json     Feature list (written once by planner agent, frozen after confirmation)
  plan_confirmed.json   Confirmation record with scope hash (written by harness.py)
  verdicts/             sprint-N-evaluator.json, sprint-N-pa.json
  evidence/sprint-N/cycle-C/   Evidence bundle: report.md, result JSON, screenshots
```

## Feature List Format

Each feature contains `id` (`F-001`), `title`, `sprint` (contiguous starting from 1), `scenarios` (2–8 items, with at least one starting with `[error]` or `[edge]`), and `passes` (must be `false` during planning). The scope hash excludes `passes`, so updating pass status via `mark-sprint` does not invalidate the confirmation record.

## Gate Rules

- **State files**: `state.json`, `plan_confirmed.json`, and `feature_list.json` cannot be written via Write/Edit or shell.
- **Feature list**: Can only be written in full using Write by the planner agent, and only before confirmation.
- **Verdict files**: Can only be written by the corresponding evaluator or product acceptance agent; file name, `sprint`, and `cycle` must match the current state.
- **Evidence directory**: Can only be written by the evaluator, and must include `report.md` along with at least one result file or screenshot.
- **Orchestrator**: Does not directly write project files during planning and building phases; delegates edits to designated agents.
- **Locked configurations**: Neither Write, Edit, nor shell redirections can modify `.claude/settings*.json` or `.claude/hooks/`.
- **Control commands**: `init`, `confirm-plan`, `cycle`, `extend-cycles`, and `mark-sprint` may only be executed by the main process.
- **Commit messages**: Must follow Conventional Commits.
- **Stop gate**: In the `building` phase, stops are blocked while the current sprint has unpassed features. If there is no progress (commits, workspace diffs, verdict files) across two consecutive checks, it releases to prevent infinite loops; it also releases when the cycle budget is exhausted so the orchestrator can prompt the user.
- **Test data**: Product code must not contain mock, seed, sample, or fake data files.

## Pass Criteria

A sprint passes only when all of the following are satisfied:

1. Evaluator verdict is `PASS` (`failures` is empty), and this cycle's evidence bundle contains `report.md` plus at least one result file or screenshot;
2. Product acceptance score is at least 80, with no P0 blocker issues;
3. `mark-sprint` validation succeeds (scope has not changed, verdicts match the current cycle).

## Verification

Run tests after modifying the harness itself:

```bash
python3 -m unittest discover -s tests -v
```
