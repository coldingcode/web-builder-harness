---
name: pa-ux-heuristics
description: Interaction and usability checklist for product acceptance, based on Nielsen's 10 Usability Heuristics. Evaluated solely from the evaluator's walkthrough logs, console logs, and screenshots without running the app. Provides evaluation criteria and common P0/P1 scenarios for each heuristic.
disable-model-invocation: true
user-invocable: false
---

# Interaction & Usability Review (Evidence-Based)

## Core Principles

You read evidence only; you do not interact with the interface. For each heuristic, first find backing evidence: the evaluator's `report.md`, console logs, and screenshots. If evidence cannot be found, handle it according to the "Evidence Gaps" section below—never score based on guesswork.

## The Ten Heuristics

**1. Visibility of System Status**
Is feedback provided after asynchronous operations (loading indicators, success/failure notices, content updates)?
- P0: Interface shows no change after an operation, or the user cannot determine whether it succeeded or failed.

**2. Match Between System and the Real World**
Does the copy speak the user's language rather than technical jargon or raw error codes? Is the workflow order intuitive to the user?
- P1: Technical jargon, error codes, or unhandled system exceptions shown to the user.

**3. User Control and Freedom**
Are destructive operations guarded by confirmations? Can users exit multi-step workflows easily? Can mistakes be undone?
- P0: Irreversible operations (such as deletion) have no confirmation and cannot be restored.
- P1: Partially completed form inputs are lost upon cancellation/navigation without warning.

**4. Consistency and Standards**
Are styles and behaviors consistent across pages for similar elements? Is a unified visual language used for dangerous/critical actions?
- P1: Primary action buttons differ visually across different pages.

**5. Error Prevention**
Are required fields and format constraints communicated before submission? Do validation hints point directly to specific fields?
- P1: Format errors are only indicated after submission, or only vague errors like "Please check input" are shown.

**6. Recognition Rather than Recall**
Do multi-step forms display summaries of entered data? Do selectors show the active item? Are active filter criteria visible on results pages?
- P1: After navigation, the user cannot see or confirm what they just selected.

**7. Flexibility and Efficiency of Use**
Can primary tasks be completed via keyboard? Is the focus order logical?
- P1: Focus is lost, jumping erratically, or core workflows cannot be operated via keyboard.

**8. Aesthetic and Minimalist Design**
Does each page focus on a clear primary goal? Is secondary information clearly visually subordinated to primary content?
- P1: More than 5 actions compete with equal visual prominence on a single page.
- P2: Long passages of explanatory text lack summaries or hierarchy.

**9. Help Users Recognize, Diagnose, and Recover from Errors**
Do error messages explain the root cause and provide clear recovery instructions? Are they placed near the offending inputs? Are user inputs preserved after a failure?
- P1: Only displays "Operation failed" with no explanation, or form inputs are wiped after submission failure.

**10. Help and Documentation**
Are hints provided for complex tasks? Is onboarding available for first-time use? Are consequences explained before critical actions execute?
- P1: New users cannot understand how to begin or proceed.

## Scoring (Usability Dimension, Max 25 Points)

Deduct points starting from 25 down to a minimum of 0:

- Deduct 10 points for each P0
- Deduct 5 points for each P1
- Deduct 2 points for each P2

## Evidence Gaps

If a state required by a heuristic was not captured (e.g., no screenshot of error states, or no record of a confirmation dialog), do not deduct points. Instead, record an entry in `findings` with `severity: "minor"` and `issue` starting with "Missing evidence: ", stating the reason (e.g., "Missing evidence: deletion confirmation dialog for Heuristic 3 not captured"). The evaluator will capture it in the next cycle.

## Output Requirements

Each assessment must specify: Heuristic number, outcome (Pass / Issue / Missing Evidence), and rationale (pointing to specific evidence files or items in `report.md`).
