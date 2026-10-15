#!/usr/bin/env python3
"""Web Builder Harness control CLI (v9). Standard library only.

Run from the project root:

    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" <command>

Commands:
    init           Create .web-builder/ state and copy the project template
    status         Show phase, sprint and feature progress
    context        Print what the current sprint needs (features, cycle, paths) as JSON
    validate-plan  Validate .web-builder/feature_list.json
    confirm-plan   Freeze the feature list after the user approves it (orchestrator only)
    cycle          Start the next build/verify cycle for the current sprint (max 3)
    mark-sprint    Pass the current sprint when evaluator and PA verdicts pass (orchestrator only)

Exit codes: 0 ok, 1 precondition or validation failure, 3 cycle limit reached.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PLUGIN_ROOT / "project-template"
STATE_DIR = ".web-builder"

MAX_CYCLES = 3          # build/verify attempts per sprint before the user is asked
MAX_EXTENSIONS = 2      # extra cycles the user may approve per sprint
PASS_SCORE = 80         # minimum product-acceptance score
STOP_BLOCK_LIMIT = 10   # Stop-gate blocks per sprint before the gate releases
MAX_FEATURES = 40
MAX_SPRINTS = 6

FEATURE_KEYS = {"id", "title", "sprint", "scenarios", "passes"}
FEATURE_ID = re.compile(r"^F-\d{3}$")
SCENARIO_TAG = re.compile(r"^\[(错误|边界|error|edge)\]", re.IGNORECASE)


class HarnessError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


# ---------- paths and state ----------

def state_file(root: Path) -> Path:
    return root / STATE_DIR / "state.json"


def features_file(root: Path) -> Path:
    return root / STATE_DIR / "feature_list.json"


def confirmed_file(root: Path) -> Path:
    return root / STATE_DIR / "plan_confirmed.json"


def verdict_file(root: Path, role: str, sprint: int) -> Path:
    return root / STATE_DIR / "verdicts" / f"sprint-{sprint}-{role}.json"


def evidence_dir(root: Path, sprint: int, cycle: int) -> Path:
    return root / STATE_DIR / "evidence" / f"sprint-{sprint}" / f"cycle-{cycle}"


def is_project(root: Path) -> bool:
    return state_file(root).is_file()


def load_state(root: Path) -> dict:
    if not is_project(root):
        raise HarnessError("not a Web Builder project; run `harness.py init` first")
    return json.loads(state_file(root).read_text(encoding="utf-8"))


def save_state(root: Path, state: dict) -> None:
    state_file(root).parent.mkdir(parents=True, exist_ok=True)
    state_file(root).write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_features(root: Path) -> list:
    if not features_file(root).is_file():
        return []
    return json.loads(features_file(root).read_text(encoding="utf-8"))["features"]


def save_features(root: Path, features: list) -> None:
    body = {"features": features}
    features_file(root).write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------- validation ----------

def validate_feature_text(text: str, planning: bool = True):
    """Return (features, error). error is None when the feature list is valid.

    planning=True  : every feature must have passes == false (planner output).
    planning=False : passes may be true (used after mark-sprint).
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        return None, 'top level must be {"features": [...]}'
    feats = data["features"]
    if not 1 <= len(feats) <= MAX_FEATURES:
        return None, f"need 1-{MAX_FEATURES} features, got {len(feats)}"

    seen, sprints = set(), set()
    for i, f in enumerate(feats):
        where = f"features[{i}]"
        if not isinstance(f, dict):
            return None, f"{where} must be an object"
        if set(f) != FEATURE_KEYS:
            return None, f"{where} keys must be exactly {sorted(FEATURE_KEYS)}"
        fid = f["id"]
        if not isinstance(fid, str) or not FEATURE_ID.match(fid):
            return None, f"{where}.id must look like F-001"
        if fid in seen:
            return None, f"duplicate id {fid}"
        seen.add(fid)
        if not isinstance(f["title"], str) or not 1 <= len(f["title"].strip()) <= 80:
            return None, f"{fid}.title must be 1-80 characters"
        sprint = f["sprint"]
        if not isinstance(sprint, int) or isinstance(sprint, bool) or not 1 <= sprint <= MAX_SPRINTS:
            return None, f"{fid}.sprint must be an integer 1-{MAX_SPRINTS}"
        sprints.add(sprint)
        sc = f["scenarios"]
        if not isinstance(sc, list) or not 2 <= len(sc) <= 8 or not all(
            isinstance(s, str) and 1 <= len(s.strip()) <= 300 for s in sc
        ):
            return None, f"{fid}.scenarios must be 2-8 non-empty strings"
        if not any(SCENARIO_TAG.match(s.strip()) for s in sc):
            return None, f'{fid}.scenarios needs at least one error or edge case tagged "[error]" or "[edge]"'
        if not isinstance(f["passes"], bool):
            return None, f"{fid}.passes must be a boolean"
        if planning and f["passes"] is not False:
            return None, f"{fid}.passes must be false; only mark-sprint may set it"
    if sprints != set(range(1, max(sprints) + 1)):
        return None, "sprint numbers must be contiguous, starting at 1"
    return feats, None


def scope_hash(features: list) -> str:
    """Hash of the confirmed scope. `passes` is excluded so mark-sprint does not change it."""
    scope = [{k: v for k, v in f.items() if k != "passes"} for f in sorted(features, key=lambda f: f["id"])]
    return hashlib.sha256(json.dumps(scope, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def validate_verdict_text(text: str, role: str, state: dict):
    """Return an error string, or None when a grader verdict is well formed for the current cycle."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return "verdict must be a JSON object"
    if data.get("role") != role:
        return f'"role" must be "{role}"'
    if data.get("sprint") != state["sprint"] or data.get("cycle") != state["cycles"]:
        return f'"sprint" and "cycle" must be {state["sprint"]} and {state["cycles"]} (the current cycle)'
    if role == "evaluator":
        if data.get("verdict") not in ("PASS", "FAIL"):
            return '"verdict" must be "PASS" or "FAIL"'
        if not isinstance(data.get("failures"), list):
            return '"failures" must be a list (empty when none)'
        failures = data["failures"]
        if data["verdict"] == "PASS" and failures:
            return 'a PASS verdict must have an empty "failures" list'
        if data["verdict"] == "FAIL" and not failures:
            return "a FAIL verdict must list at least one failure"
        for item in failures:
            if not isinstance(item, dict) or not all(k in item for k in ("feature", "scenario", "expected", "actual")):
                return 'each failure needs "feature", "scenario", "expected" and "actual"'
    elif role == "pa":
        score = data.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 100:
            return '"score" must be an integer 0-100'
        if not isinstance(data.get("p0"), list):
            return '"p0" must be a list (empty when none)'
    else:
        return f"unknown grader role {role!r}"
    return None


def _read_verdict(root: Path, role: str, sprint: int):
    path = verdict_file(root, role, sprint)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _require_valid_features(root: Path) -> list:
    if not features_file(root).is_file():
        raise HarnessError(".web-builder/feature_list.json is missing")
    feats, err = validate_feature_text(features_file(root).read_text(encoding="utf-8"))
    if err:
        raise HarnessError(f"feature list invalid: {err}")
    return feats


def _check_scope(root: Path, features: list) -> None:
    confirmed = json.loads(confirmed_file(root).read_text(encoding="utf-8"))
    if scope_hash(features) != confirmed["scope_sha256"]:
        raise HarnessError("feature scope changed after confirmation; restore .web-builder/feature_list.json")


# ---------- progress ----------

def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout if out.returncode == 0 else ""


def progress_signature(root: Path, state: dict) -> str:
    """Fingerprint of observable work. Unchanged between two Stop-gate blocks means no progress."""
    digest = hashlib.sha256()
    digest.update(_git(root, "rev-parse", "HEAD").encode())
    digest.update(_git(root, "diff", "HEAD", "--no-color").encode())
    for name in _git(root, "ls-files", "--others", "--exclude-standard").splitlines():
        path = root / name
        # state.json is rewritten by the Stop gate itself, so it must not count as progress
        if path.is_file() and name != f"{STATE_DIR}/state.json":
            st = path.stat()
            digest.update(f"{name}:{st.st_size}:{st.st_mtime_ns}".encode())
    passing = sum(1 for f in load_features(root) if f["passes"])
    digest.update(f"{state.get('sprint')}:{state.get('cycles')}:{passing}".encode())
    return digest.hexdigest()


def status_text(root: Path, state: dict) -> str:
    feats = load_features(root)
    done = sum(1 for f in feats if f["passes"])
    head = (f"phase={state['phase']} sprint={state['sprint']} "
            f"cycle={state['cycles']}/{cycle_limit(state)} passing={done}/{len(feats)}")
    if state["phase"] == "planning":
        hint = ("Planning. Next: validate the feature list, get the user's approval, "
                "then run `harness.py confirm-plan`.")
    elif state["phase"] == "building":
        pending = [f["id"] for f in feats if f["sprint"] == state["sprint"] and not f["passes"]]
        hint = (f"Building sprint {state['sprint']}; pending: {', '.join(pending) or 'none'}. "
                "Next: `harness.py cycle`, then generator -> evaluator -> PA -> `harness.py mark-sprint`.")
    else:
        hint = "All sprints passed. Next: summarise the result for the user."
    return f"Web Builder: {head}\n{hint}"


# ---------- commands ----------

def _merge_gitignore(root: Path) -> int:
    target = root / ".gitignore"
    wanted = [line for line in (TEMPLATE_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#")]
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    existing = set(text.splitlines())
    missing = [line for line in wanted if line not in existing]
    if missing:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n# web-builder-harness\n" + "\n".join(missing) + "\n"
        target.write_text(text, encoding="utf-8")
    return len(missing)


def cmd_init(root: Path, _args) -> int:
    if is_project(root):
        print("Already initialised: .web-builder/state.json exists.")
        return 0
    save_state(root, {"version": 1, "phase": "planning", "sprint": 0, "cycles": 0,
                      "stop_blocks": 0, "last_block_sig": ""})
    copied = []
    for rel in (".claude/rules/web-builder.md",):
        dst = root / rel
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATE_DIR / rel, dst)
        copied.append(rel)
    added = _merge_gitignore(root)
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-b", "main"], cwd=root, capture_output=True)
    print(f"Initialised Web Builder state. Copied: {', '.join(copied) or 'nothing (files already exist)'}; "
          f".gitignore entries added: {added}.")
    return 0


def cmd_status(root: Path, _args) -> int:
    print(status_text(root, load_state(root)))
    return 0


def cmd_context(root: Path, _args) -> int:
    state = load_state(root)
    sprint, cycle = state["sprint"], state["cycles"]
    feats = [f for f in load_features(root) if f["sprint"] == sprint]
    info = {
        "phase": state["phase"],
        "sprint": sprint,
        "cycle": cycle,
        "max_cycles": cycle_limit(state),
        "pass_score": PASS_SCORE,
        "features": feats,
        "evidence_dir": evidence_dir(root, sprint, cycle).relative_to(root).as_posix() if sprint and cycle else None,
        "verdicts": {role: f".web-builder/verdicts/sprint-{sprint}-{role}.json" for role in ("evaluator", "pa")},
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def cmd_validate_plan(root: Path, _args) -> int:
    feats = _require_valid_features(root)
    print(f"feature list OK: {len(feats)} features across {max(f['sprint'] for f in feats)} sprint(s)")
    return 0


def cmd_confirm_plan(root: Path, _args) -> int:
    state = load_state(root)
    if state["phase"] != "planning":
        raise HarnessError(f"plan is already confirmed (phase={state['phase']})")
    feats = _require_valid_features(root)
    sprints = sorted({f["sprint"] for f in feats})
    record = {
        "confirmed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope_sha256": scope_hash(feats),
        "features": len(feats),
        "sprints": len(sprints),
    }
    confirmed_file(root).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    state.update(phase="building", sprint=sprints[0], cycles=0, stop_blocks=0, last_block_sig="")
    save_state(root, state)
    print(f"Plan confirmed: {len(feats)} features in {len(sprints)} sprint(s). Starting sprint {sprints[0]}.")
    return 0


def cycle_limit(state: dict) -> int:
    """Base cycle budget plus any extensions the user approved (at most MAX_EXTENSIONS)."""
    return MAX_CYCLES + state.get("extra_cycles", 0)


def cmd_cycle(root: Path, _args) -> int:
    state = load_state(root)
    if state["phase"] != "building":
        raise HarnessError(f"cannot start a cycle in phase {state['phase']}")
    limit = cycle_limit(state)
    if state["cycles"] >= limit:
        print(f"Sprint {state['sprint']} has used all {limit} cycles. Stop and ask the user "
              "(AskUserQuestion) whether to extend the budget or stop.")
        return 3
    state["cycles"] += 1
    save_state(root, state)
    evidence_dir(root, state["sprint"], state["cycles"]).mkdir(parents=True, exist_ok=True)
    print(f"Sprint {state['sprint']}, cycle {state['cycles']}/{limit} started.")
    return 0


def cmd_extend_cycles(root: Path, _args) -> int:
    """Grant one extra cycle for the current sprint. Run only after the user explicitly approves."""
    state = load_state(root)
    if state["phase"] != "building":
        raise HarnessError(f"cannot extend cycles in phase {state['phase']}")
    if state.get("extra_cycles", 0) >= MAX_EXTENSIONS:
        raise HarnessError(f"cycle budget already extended {MAX_EXTENSIONS} time(s)")
    state["extra_cycles"] = state.get("extra_cycles", 0) + 1
    save_state(root, state)
    print(f"Cycle budget for sprint {state['sprint']} extended to {cycle_limit(state)}.")
    return 0


def cmd_mark_sprint(root: Path, _args) -> int:
    state = load_state(root)
    if state["phase"] != "building":
        raise HarnessError(f"cannot mark a sprint in phase {state['phase']}")
    sprint, cycle = state["sprint"], state["cycles"]
    features = load_features(root)
    _check_scope(root, features)

    problems = []
    ev = _read_verdict(root, "evaluator", sprint)
    pa = _read_verdict(root, "pa", sprint)
    if ev is None or ev.get("cycle") != cycle:
        problems.append("evaluator verdict for this cycle is missing")
    elif ev.get("verdict") != "PASS":
        problems.append("evaluator verdict is FAIL")
    if pa is None or pa.get("cycle") != cycle:
        problems.append("PA verdict for this cycle is missing")
    else:
        if pa.get("p0"):
            problems.append(f"PA reported P0 issues: {pa['p0']}")
        if pa.get("score", 0) < PASS_SCORE:
            problems.append(f"PA score {pa.get('score')} is below the pass mark of {PASS_SCORE}")
    bundle = evidence_dir(root, sprint, cycle)
    rel_bundle = bundle.relative_to(root).as_posix()
    if not (bundle / "report.md").is_file():
        problems.append(f"evidence bundle must contain report.md: {rel_bundle}/report.md")
    elif not [p for p in bundle.iterdir() if p.name != "report.md"]:
        problems.append(f"evidence bundle needs at least one result file or screenshot besides report.md: {rel_bundle}")
    if problems:
        print("Sprint NOT passed:\n- " + "\n- ".join(problems))
        return 1

    for f in features:
        if f["sprint"] == sprint:
            f["passes"] = True
    save_features(root, features)
    remaining = sorted({f["sprint"] for f in features if not f["passes"]})
    if remaining:
        state["sprint"] = remaining[0]
    else:
        state["phase"] = "done"
    state.update(cycles=0, extra_cycles=0, stop_blocks=0, last_block_sig="")
    save_state(root, state)
    print(f"Sprint {sprint} passed (PA score {pa['score']}). " + status_text(root, state))
    return 0


COMMANDS = {
    "init": cmd_init,
    "status": cmd_status,
    "context": cmd_context,
    "validate-plan": cmd_validate_plan,
    "confirm-plan": cmd_confirm_plan,
    "cycle": cmd_cycle,
    "extend-cycles": cmd_extend_cycles,
    "mark-sprint": cmd_mark_sprint,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="harness.py", description="Web Builder Harness control CLI")
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](Path.cwd(), args)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
