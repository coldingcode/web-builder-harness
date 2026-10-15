#!/usr/bin/env python3
"""Hook dispatcher for Web Builder Harness (v9).

Invoked by hooks/hooks.json as:  python3 hooks.py <event>
Events: session-start | prompt-submit | pre-bash | pre-write | stop

Exit codes follow the Claude Code hook protocol:
  0  allow. For SessionStart and UserPromptSubmit, stdout is added to the context.
  2  block. stderr is fed back to Claude (for PreToolUse it blocks the tool call;
     for Stop it keeps Claude working; for UserPromptSubmit it erases the prompt).

Every event is a no-op outside a Web Builder project (no .web-builder/state.json),
so installing the plugin never changes unrelated repositories.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402  (same directory)


def block(message: str) -> None:
    sys.stderr.write(message.strip() + "\n")
    sys.exit(2)


def read_event() -> dict:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def project_root(event: dict) -> Path:
    return Path(event.get("cwd") or os.getcwd())


def role_of(event: dict) -> str:
    """'main' for the orchestrator, otherwise the subagent name without the 'web-builder-' prefix."""
    raw = str(event.get("agent_type") or "")
    if not raw:
        return "main"
    name = raw.rsplit(":", 1)[-1]
    return name[len("web-builder-"):] if name.startswith("web-builder-") else name


# ---------- PreToolUse: Bash ----------

PROTECTED_STATE = re.compile(r"\.web-builder/(state\.json|plan_confirmed\.json|feature_list\.json)")
GRADER_OUTPUT = re.compile(r"\.web-builder/(verdicts|evidence)")
WRITE_HINT = re.compile(r">(?!&)|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b|\btruncate\b|\bdd\b|\bwrite_text\b|\bwrite_bytes\b|\bopen\s*\(")
LOCKED_CONFIG = re.compile(r"\.claude/(settings[^\s\"']*\.json|hooks/)")
CONTROL_CMD = re.compile(r"harness\.py[\"']?\s+(init|confirm-plan|cycle|extend-cycles|mark-sprint)\b")
CONVENTIONAL = re.compile(r"^(feat|fix|test|docs|refactor|chore|style|perf|build|ci)(\([^()\s]+\))?!?: \S")


def commit_subject(command: str):
    """Subject line of the first `git commit` in the command.

    Returns None when there is no commit or the message is reused/amended,
    '' when a commit has no -m message, otherwise the subject text.
    """
    for segment in re.split(r"&&|\|\||;|\||\n", command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        for i in range(len(tokens) - 1):
            if tokens[i] == "git" and tokens[i + 1] == "commit":
                return _message_from(tokens[i + 2:])
    return None


def _message_from(args: list):
    reuse = any(a in ("--amend", "--no-edit", "-C", "-c", "--reuse-message", "--reedit-message")
                or a.startswith(("--fixup", "--squash")) for a in args)
    for i, tok in enumerate(args):
        if tok in ("-F", "--file") or tok.startswith("--file="):
            return None  # message comes from a file; not inspectable here
        if tok in ("-m", "--message") and i + 1 < len(args):
            return args[i + 1].split("\n", 1)[0]
        if tok.startswith("--message="):
            return tok.split("=", 1)[1].split("\n", 1)[0]
        if re.match(r"^-[a-zA-Z]*m$", tok) and i + 1 < len(args):
            return args[i + 1].split("\n", 1)[0]
        glued = re.match(r"^-[a-zA-Z]*m(.+)$", tok)  # e.g. -am"feat: x" glued by the shell
        if glued and not tok.startswith("--"):
            return glued.group(1).split("\n", 1)[0]
    return None if reuse else ""


def check_bash(event: dict, root: Path) -> None:
    command = str((event.get("tool_input") or {}).get("command") or "")
    role = role_of(event)
    if CONTROL_CMD.search(command) and role != "main":
        block("Only the orchestrator may run harness control commands (init, confirm-plan, cycle, "
              "mark-sprint). Subagents produce their deliverables and stop.")
    if LOCKED_CONFIG.search(command) and WRITE_HINT.search(command):
        block("Permission and hook configuration is locked during a harness run. "
              "Ask the user to change it by hand.")
    if PROTECTED_STATE.search(command) and WRITE_HINT.search(command) and "harness.py" not in command:
        block("Harness state is maintained by harness.py only. Do not write .web-builder/state.json, "
              "plan_confirmed.json or feature_list.json from the shell.")
    if GRADER_OUTPUT.search(command) and WRITE_HINT.search(command) and role not in ("evaluator", "pa"):
        block("Only the evaluator and product-acceptance agents may write verdicts or evidence.")
    subject = commit_subject(command)
    if subject is not None and not CONVENTIONAL.match(subject):
        block("Commit message must follow Conventional Commits, for example "
              "'feat(todo): persist items in localStorage'. Got: " + repr(subject))


# ---------- PreToolUse: Write | Edit | MultiEdit ----------

MOCK_NAME = re.compile(r"(_mock\.|_sample\.|\.seed\.|\.fake\.|\.fixture\.|\.dummy\.|\.stub\.)")


def check_write(event: dict, root: Path, state: dict) -> None:
    tool = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input") or {}
    raw = str(tool_input.get("file_path") or "")
    if not raw:
        return
    role = role_of(event)
    target = Path(raw) if Path(raw).is_absolute() else root / raw
    try:
        rel = target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        block(f"Writes outside the project directory are not allowed in a Web Builder project: {raw}")

    if role == "main" and state.get("phase") in ("planning", "building"):
        block("The orchestrator does not write project files during a run. Product code is written by the "
              "generator and planning files by the planner; delegate the change to the right agent.")

    if re.match(r"^\.claude/(settings[^/]*\.json|hooks/)", rel):
        block("Permission and hook configuration is locked during a harness run. "
              "Ask the user to change it by hand.")
    if rel.startswith(".web-builder/"):
        return _check_harness_file(rel, tool, tool_input, root, state, role)

    if role in ("evaluator", "pa"):
        block(f"The {role} agent is read-only for project files. It may write only "
              ".web-builder/verdicts/ (and the evaluator may write .web-builder/evidence/).")
    if role == "planner":
        if rel != "CLAUDE.md":
            block("The planner may write CLAUDE.md and .web-builder/ planning files only.")
        return
    if state.get("phase") == "planning":
        block("The feature list is not confirmed yet. Finish planning (spec and feature list) "
              "and get the user's approval before writing product code.")
    if MOCK_NAME.search(Path(rel).name) and not rel.startswith("tests/"):
        block("Mock, seed, sample and fixture data belongs under tests/, not in product code. "
              "Remove this file or move it under tests/.")


def _check_harness_file(rel: str, tool: str, tool_input: dict, root: Path, state: dict, role: str) -> None:
    if rel in (".web-builder/state.json", ".web-builder/plan_confirmed.json"):
        block("state.json and plan_confirmed.json are maintained by harness.py only.")
    if rel == ".web-builder/feature_list.json":
        if role != "planner":
            block("Only the planner may write the feature list.")
        if harness.confirmed_file(root).exists():
            block("The feature list is frozen after the user confirmed it. To change scope, "
                  "start a new planning run in an empty project.")
        if tool != "Write":
            block("Write the whole feature list with Write; partial edits are not allowed.")
        _, err = harness.validate_feature_text(str(tool_input.get("content") or ""))
        if err:
            block(f"Invalid feature list: {err}")
        return
    if rel == ".web-builder/spec.md":
        if role != "planner":
            block("Only the planner may write .web-builder/spec.md.")
        return
    if rel.startswith(".web-builder/verdicts/"):
        if role not in ("evaluator", "pa"):
            block("Only the evaluator and product-acceptance agents may write verdicts.")
        expected = f".web-builder/verdicts/sprint-{state.get('sprint')}-{role}.json"
        if rel != expected:
            block(f"Verdict file for this run must be {expected}.")
        if tool != "Write":
            block("Write verdict files with Write.")
        err = harness.validate_verdict_text(str(tool_input.get("content") or ""), role, state)
        if err:
            block(f"Invalid verdict: {err}")
        return
    if rel.startswith(".web-builder/evidence/"):
        if role != "evaluator":
            block("Only the evaluator writes evidence bundles.")
        return
    block(f"Not a writable harness file: {rel}")


# ---------- Stop gate ----------

def check_stop(event: dict, root: Path, state: dict) -> None:
    if state.get("phase") != "building":
        return
    if state.get("cycles", 0) >= harness.cycle_limit(state):
        return  # cycle budget spent: the orchestrator must ask the user, so let the turn end
    sprint = state["sprint"]
    pending = [f["id"] for f in harness.load_features(root) if f["sprint"] == sprint and not f["passes"]]
    if not pending:
        return
    sig = harness.progress_signature(root, state)
    if event.get("stop_hook_active") and sig == state.get("last_block_sig"):
        return  # nothing changed since the last block: release instead of looping
    if state.get("stop_blocks", 0) >= harness.STOP_BLOCK_LIMIT:
        return
    state["last_block_sig"] = sig
    state["stop_blocks"] = state.get("stop_blocks", 0) + 1
    harness.save_state(root, state)
    block(f"Sprint {sprint} is not finished. Still pending: {', '.join(pending)}. Continue the cycle "
          "(generator -> evaluator -> product acceptance -> `harness.py mark-sprint`). If the cycle "
          "budget is spent, ask the user with AskUserQuestion instead of stopping.")


# ---------- UserPromptSubmit ----------

PROMPT = re.compile(r"^/web-builder(?:\s+(?P<arg>.*))?$", re.S)


def check_prompt(event: dict) -> None:
    match = PROMPT.match(str(event.get("prompt") or "").strip())
    if not match:
        return
    arg = (match.group("arg") or "").strip()
    if arg.split(" ", 1)[0] in ("status", "resume", "help"):
        return
    cjk = len(re.findall(r"[一-鿿]", arg))
    words = len(re.findall(r"[A-Za-z][A-Za-z0-9'-]*", arg))
    if cjk + 2 * words < 4:
        block("Describe the website after the command, for example: "
              "/web-builder a pomodoro timer web app. An empty or very short request cannot be planned.")


# ---------- dispatch ----------

def main(argv: list) -> int:
    if len(argv) != 2 or argv[1] not in ("session-start", "prompt-submit", "pre-bash", "pre-write", "stop"):
        sys.stderr.write("usage: hooks.py session-start|prompt-submit|pre-bash|pre-write|stop\n")
        return 1
    event_name = argv[1]
    event = read_event()

    if event_name == "prompt-submit":
        check_prompt(event)
        return 0

    root = project_root(event)
    if not harness.is_project(root):
        return 0
    state = harness.load_state(root)

    if event_name == "session-start":
        print(harness.status_text(root, state))
    elif event_name == "pre-bash":
        check_bash(event, root)
    elif event_name == "pre-write":
        check_write(event, root, state)
    elif event_name == "stop":
        check_stop(event, root, state)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
