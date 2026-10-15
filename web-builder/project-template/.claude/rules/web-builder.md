# Web Builder Harness Project Rules

This project is managed by Web Builder Harness (start by running `/web-builder` in Claude Code).

- `.web-builder/` holds process state maintained by `harness.py`. Do not manually edit `state.json`, `plan_confirmed.json`, or `feature_list.json`, and do not write `verdicts/` or `evidence/` by hand.
- Do not write product code before the feature list is confirmed by the user.
- Commit messages must follow Conventional Commits, for example `feat(F-001): support adding todos`.
- Sample and test data belongs under `tests/` only. Product code must not contain mock, seed, sample, or fake data.
- Every feature requires corresponding Playwright end-to-end tests located under `tests/e2e/`.
- Development, build, and test commands follow `CLAUDE.md`.
