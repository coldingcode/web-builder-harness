# Changelog

## 9.0.0

Renamed to `web-builder-harness` and published under `coldingcode`. The harness was reworked after a review of v8.

### Fixed

- **Blocking now works.** The v8 hook scripts exited with 1 to block, which Claude Code treats as a non-blocking error, so most gates never stopped anything. v9 uses a Python dispatcher (`scripts/hooks.py`) that exits with 2 to block.
- **The Stop gate cannot be bypassed by a bare `stop`.** It keeps the run going while a sprint has unpassed features, and releases only when a block produced no progress or the cycle budget is spent.
- **Chinese prompts are no longer rejected.** The prompt check counts CJK characters and Latin words instead of using `wc -w`, which returns 0 for Chinese text.
- **Commit-message checks handle real commands.** `git commit -am 'msg'`, `--amend --no-edit` and single-quoted messages are parsed correctly.
- **Hooks are scoped to harness projects.** Outside a folder with `.web-builder/state.json`, every hook is a no-op.
- **The orchestrator cannot write project files** during planning or building. Changes go to the planner or generator.
- **Locked config cannot be rewritten from the shell.** Bash redirection, `open(...)` and similar writes to `.claude/settings*.json` or `.claude/hooks/` are blocked, not only Write and Edit.
- **Scenario tags are enforced.** Every feature needs at least one scenario starting with `[错误]`/`[error]` or `[边界]`/`[edge]`.
- **Verdicts are internally consistent.** A PASS verdict cannot list failures; a FAIL verdict must list at least one, with `feature`, `scenario`, `expected` and `actual`.
- **Evidence bundles must contain `report.md`** plus at least one result file or screenshot.
- **Test data guard is narrower.** It no longer blocks legitimate files under `tests/`.
- **Stale and placeholder content removed.** `your-org` URLs, the example email, the non-existent `init.sh` and `tests/fixtures/` template, and the claim that session start created directories all went away.

### Changed

- **Product acceptance is read-only.** The PA reads the evidence bundle the evaluator collects and does not start the app. Its rubric scores four dimensions to 100 with a pass mark of 80, and any P0 item fails the sprint.
- **One evidence walkthrough feeds two judgements.** The evaluator collects evidence once, and the PA judges it. Gold-plating is owned by one place: the `pa-spec-audit` checklist.
- **Pass status is script-owned.** Only `harness.py mark-sprint` sets `passes`, and only after both verdicts and the evidence bundle check out.
- **Scope is frozen by hash after confirmation.** `plan_confirmed.json` records a hash that excludes pass status.
- **Cycle budget.** Each sprint gets 3 build/verify cycles. The user may approve up to 2 extra cycles through `extend-cycles`.
- **Playwright tests persist.** Generator writes `tests/e2e/sprint-N/*.spec.ts` with `@playwright/test`. The evaluator reruns them, including earlier sprints as regression checks. The `playwright-cli` dependency is removed.
- **Project template.** `CLAUDE.md` is replaced by `.claude/rules/web-builder.md`. The plugin no longer ships `.claude/settings.json`. The hooks decide what may be written, and Claude Code asks you to confirm each file write and shell command.
- **Retired skills.** `pa-user-scenarios` and `pa-regression` are removed. Their useful parts are now covered by the feature scenarios and the persisted regression tests.
- **Removed.** `.mcp.json`, the `notify` hooks, the `bash-failure` and `stop-failure` scripts, and the nine shell scripts.
- **Tests.** Replaced the 276-check shell suite with `tests/test_harness.py` (standard library, 49 tests).
- **Docs.** Bilingual README, English primary. The v8 design and review are archived in `docs/history/` with a stale-notice banner.

### Known limitations

- Plugin prompts are still in Chinese.
- Decisions from the original plan that changed: a PostToolUse hook was dropped, because PreToolUse already validates every verdict and feature-list write. Append-only feature edits were replaced by the scope hash, which freezes the list after confirmation.
- The `Agent` tool name used in the command and agent frontmatter was checked against the Claude Code subagent documentation.
- Scope cannot change after confirmation. Start a new run in a new folder to change it.
- Claude Code asks you to confirm each file write and shell command, because the plugin does not ship a permission allowlist.

## 8.0.0

Last release under the previous name (`web-builder-harness-zh`). See `docs/history/`.
