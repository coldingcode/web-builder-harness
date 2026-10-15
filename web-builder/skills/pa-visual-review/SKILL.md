---
name: pa-visual-review
description: Visual review checklist for product acceptance: checks design direction alignment, cross-page consistency, visual hierarchy, empty/loading/error states, and mobile responsiveness based on the evaluator's screenshot evidence bundle (desktop and 390px). Evaluated solely from evidence without running the app.
disable-model-invocation: true
user-invocable: false
---

# Visual Review (Evidence-Based)

## Core Principles

Screenshots are meant to be **read**. Open each image one by one using the Read tool, and verify whether the layout, colors, typography, and spacing conform to the design direction in `spec.md` and remain consistent across pages.

You do not run the application or capture new screenshots. If a necessary state lacks a screenshot, treat it as an evidence gap as described below.

## Step 1: Collect Evidence Inventory

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" context` to obtain the `evidence_dir`.
2. Use Glob to list `*.png` in the evidence directory, grouping them by page and viewport (desktop / 390px).
3. Read the "Design Direction" section of `spec.md`, noting expectations for primary color, neutral colors, typographic hierarchy, border radius, and spacing.

## Step 2: Item-by-Item Review

**2.1 Design Direction Alignment**

Verify against `spec.md`: Is the primary color applied to primary actions? Does typography match specified hierarchy? Are background colors and border radii consistent? If the spec is silent on an attribute, do not impose arbitrary requirements—only judge what the spec explicitly promised.

**2.2 Cross-Page Consistency**

Compare multiple screenshots side by side:

- Similar buttons (primary, secondary, danger) share identical appearance.
- Same-level headings share identical font sizes.
- Card and list item spacing remains uniform.
- Form inputs follow consistent styling.

Document each inconsistency: which two screenshots, which element, and what differs.

**2.3 Visual Hierarchy**

Evaluate each page individually:

- Is the most important action visually prominent?
- Does secondary information avoid competing with primary content?
- Can users locate the primary entry point immediately at first glance?

**2.4 State Completeness**

- Empty state: Contains explanatory copy and a clear call-to-action, not a blank area.
- Loading state: Provides visible loading indicators rather than flickering or abrupt content shifts.
- Error state: Clarifies what went wrong and provides a recovery action.

**2.5 Mobile Responsiveness (390px)**

Compare desktop and mobile screenshots:

- Content is not truncated; no accidental horizontal scrolling.
- Typography remains readable on mobile viewports.
- Primary buttons are large enough for comfortable touch targets.
- Tables and charts adapt gracefully without overflow or disappearance.
- Navigation remains fully usable on mobile.

## Step 3: Severity Classification

- **P0 (Blocker)**: Blank page, severe layout breakage, primary features unusable on mobile, or user-facing placeholder copy.
- **P1 (Major)**: Significant component inconsistency across pages, empty state is a blank white screen, or broken visual hierarchy preventing users from finding primary actions.
- **P2 (Minor)**: Minor, systematic deviations in spacing or typography.

## Scoring (Visual Dimension, Max 25 Points)

Deduct points starting from 25 down to a minimum of 0:

- Deduct 5 points for each P1
- Deduct 2 points for each P2
- P0 issues are not deducted here; they are listed in the verdict's `p0` array and directly cause the sprint to fail.

## Evidence Gaps

If a necessary state lacks a screenshot, do not guess what it looks like. Record an entry in `findings` with `severity: "minor"` and `issue` starting with "Missing evidence: ", specifying the missing state. Evidence gaps do not deduct points, but the evaluator should capture them in the next cycle.
