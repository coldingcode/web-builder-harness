---
name: pa-spec-audit
description: Spec audit checklist for product acceptance: cross-reference spec.md with feature list scenarios to identify scope cuts (promised but unbuilt), gold plating (unrequested additions), and directional drift. Evaluated solely from the evidence bundle without running the app.
disable-model-invocation: true
user-invocable: false
---

# Spec Audit (Evidence-Based)

## Core Principles

**The specification is a product promise, not an implementation suggestion.**

The audit question is: Is what the user received the exact same thing promised to them originally?

Three types of deviation:

- **Scope Cut (Under-delivery)**: Promised in the spec, but not implemented or only partially implemented.
- **Gold Plating**: Implemented, but not requested in the spec, adding unnecessary complexity.
- **Directional Drift**: The feature exists, but fails to solve the user's original problem.

## Step 1: Build the Cross-Reference Table

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" context` to obtain this sprint's features and evidence directory.
2. Read the "Core User Journeys" and "Out of Scope" sections of `.web-builder/spec.md`.
3. For each feature in this sprint, find the corresponding user journey in `spec.md` and map them:

```markdown
| Feature | Promise in Spec | Actual Behavior in Evidence | Deviation Type | Notes |
|---|---|---|---|---|
| F-001 | User can quickly add todos | Press Enter in input to add | None | — |
| F-003 | (Not mentioned in spec) | Added tag filtering | Gold Plating | Increases UI complexity |
```

Simultaneously check the `scenarios` in the feature list: verify whether they cover all behaviors promised by the specification.

## Step 2: Evaluate the Three Deviation Types

**Scope Cut (Under-delivery)**

| Severity | Example | Level |
|---|---|---|
| Core promise missing | Spec promises "can export data", but no export option exists in evidence | P0 |
| Feature incomplete | Spec promises "supports batch deletion", but evidence only shows single-item deletion | P1 |
| Missing detail | Spec promises "shows creation time", but the field is missing from the list | P2 |

**Gold Plating**

Evaluation criteria (only qualifies as gold plating if all conditions are met):

- Not mentioned in any user journey in the spec.
- Not essential infrastructure required to implement a specified feature.
- Adds interface complexity or creates visual distraction.

For every instance of gold plating, document: feature name, evidence location, impact, and recommendation (keep, remove, or defer to a later sprint).

**Directional Drift**

This is the hardest yet most critical category to detect. Evaluation method: Read the product background and user goals in the spec, then ask from the user's perspective: "After completing this workflow, has my original problem been solved?"

Example: The spec states "users need to jot down ideas quickly without interruptions", but the implementation displays a "Saved successfully!" modal alert on every save. The feature works, but violates the product intent of "unobtrusive flow"—flagged as directional drift.

## Step 3: Journey Intent

For each core journey in `spec.md`, verify:

- Journey entry point is supported. The user might not always enter from the home page.
- Journey destination is genuinely reached. For example, the goal of signup is "start using the product", not merely "seeing a signup successful message".
- At critical decision points, the user possesses sufficient information. For example, can the user review a complete order summary before payment?

## Scoring (Spec Dimension, Max 20 Points)

Deduct points starting from 20 down to a minimum of 0:

- Deduct 10 points for each Scope Cut P0
- Deduct 4 points for each Scope Cut P1
- Deduct 1 point for each Scope Cut P2
- Deduct 10 points for each Directional Drift
- Deduct 3 points for each Gold Plating (capped at 9 points deduction total)

Unmet journey intent is scored under the "Scenario Completeness & Flow Quality" dimension (max 30 points); do not deduct double points here.

## Evidence Gaps

If unable to determine whether a promise was fulfilled (due to missing screenshots or walkthrough logs in the evidence bundle), do not deduct points. Instead, record an entry in `findings` with `severity: "minor"` and `issue` starting with "Missing evidence: ", detailing the unverified promise.
