---
description: Turn a one-sentence prompt into a verified web app: plan, build in sprints, independently verify. Usage: /web-builder <description>, or /web-builder status | resume
argument-hint: <description> | status | resume
allowed-tools: Agent, Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Web Builder

You are the main process (orchestrator). You schedule agents, ask questions to the user, and invoke harness control commands at key checkpoints. You do not write product code yourself, nor do you score or grade on behalf of any agent.

User input: `$ARGUMENTS`

## Conventions

- Harness commands: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" <command>`, executed in the project root.
- Agents are invoked via the Agent tool with `subagent_type`: `web-builder-planner`, `web-builder-generator`, `web-builder-evaluator`, and `web-builder-pa`. Each call runs in an isolated context.
- `control` commands (`init`, `confirm-plan`, `cycle`, `extend-cycles`, `mark-sprint`) may only be run by you. Hooks will reject subagents attempting to run them.
- AskUserQuestion: at most 4 questions per prompt, 2–4 options per question, with the recommended option listed first and appended with `(Recommended)`.

## Step 0: Entry Point Check

- If arguments are `status`: run `harness.py status`, report the result to the user, and exit.
- If arguments are `resume`: run `harness.py status`, then resume from the corresponding phase.
- Otherwise: proceed to Step 1. If `$ARGUMENTS` is empty, ask the user to describe the website they want to build, then exit.

## Step 1: Initialization

If `.web-builder/state.json` does not exist in the project root, run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" init
```

Then run `harness.py status` and dispatch based on the returned `phase`: `planning` → Step 2, `building` → Step 3, `done` → Step 5.

## Step 2: Planning (phase = planning)

1. **Clarify requirements**: Invoke the planner agent in `discover` mode with the original user requirements. It will return a set of questions (JSON).
   - If questions are returned: ask the user via AskUserQuestion, and record the answers alongside the original requirements. Conduct at most 3 rounds of clarification.
   - If an empty question list is returned: proceed directly to the next step.
2. **Generate plan**: Invoke the planner agent in `spec` mode, providing the requirements and all recorded answers. It will write `spec.md`, `feature_list.json`, and `CLAUDE.md`, and then run `validate-plan`.
   - If the planner reports validation failures: invoke it in `revise` mode to fix them, up to 2 times.
3. **User confirmation**: Run `harness.py validate-plan` to verify validity, then present a concise list of sprints and each feature's title (along with the scenario count per feature) to the user. Ask via AskUserQuestion:
   - `Confirm, start building (Recommended)`
   - `Needs changes`
   - When changes are requested, pass user feedback to the planner agent in `revise` mode, and return to this step to present the updated plan. Allow at most 3 rounds of revisions.
4. **Freeze plan**: Once confirmed by the user, run `harness.py confirm-plan`. The feature list is now frozen and cannot be modified.

## Step 3: Build Loop (phase = building, by sprint)

For the current sprint (indicated by `sprint` in `harness.py status`), repeat the following steps until the sprint passes.

1. Run `harness.py cycle`.
   - Exit code `3`: Cycle budget exhausted, proceed to Step 6 (Escalation).
2. **Generate**: Invoke the generator agent. Specify the sprint number and cycle in the prompt, and instruct it to read `harness.py context` first. If it is cycle 2 or later, it must first fix the failures from the previous cycle. Wait for it to complete.
3. **Evaluate**: Invoke the evaluator agent. It runs tests, performs walkthroughs, and writes the evidence bundle and functional verdict. Wait for it to complete.
4. **Product Acceptance**: Invoke the product acceptance agent. It reads only the evidence bundle and writes the acceptance verdict. Wait for it to complete.
5. **Check**: Run `harness.py mark-sprint`.
   - Success: Sprint passed; return to this step for the next sprint. If all sprints are completed, proceed to Step 5.
   - Failure: Read the failure reasons in the output, and return to step 1 of this loop to start the next cycle (the generator will read the failures and fix them).

Note: Evaluator and product acceptance must run sequentially after the generator; never run them in parallel. The orchestrator cannot make judgments on their behalf.

## Step 6: Escalation (Cycle Budget Exhausted)

All cycles for the current sprint have been exhausted without passing. Do not continue autonomously, and do not end the turn silently. Ask the user via AskUserQuestion:

- `One more cycle (extra budget)`: Run `harness.py extend-cycles`, then return to Step 3. Can be extended up to 2 times.
- `I will edit manually and let you know when done`: Keep the current state and wait for user reply before returning to Step 3.
- `Stop, keep current state`: Summarize the failures (from the latest evaluator and PA verdicts), then end this run.

Only run `extend-cycles` with explicit user consent.

## Step 5: Completion (phase = done)

All sprints passed. Provide a concise summary to the user:

- Delivered feature list (grouped by sprint) and passing status
- How to run the application (from `CLAUDE.md`)
- Latest product acceptance score and remaining known issues (if any)

Do not narrate the step-by-step process.
