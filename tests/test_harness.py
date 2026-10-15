"""Tests for Web Builder Harness v9.

Run from the repository root:

    python3 -m unittest discover -s tests -v

Standard library only. The hook tests run scripts/hooks.py in a subprocess with the
same JSON protocol Claude Code uses: exit 0 allows, exit 2 blocks.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "web-builder"
HOOKS = PLUGIN / "scripts" / "hooks.py"
HARNESS = PLUGIN / "scripts" / "harness.py"
sys.path.insert(0, str(PLUGIN / "scripts"))
import harness  # noqa: E402


def feature_doc(passes=False, sprint=1, scenarios=None):
    return json.dumps({"features": [{
        "id": "F-001",
        "title": "添加待办",
        "sprint": sprint,
        "scenarios": scenarios or ["回车新增一条待办", "[错误] 提交空白内容时显示提示且列表不变"],
        "passes": passes,
    }]}, ensure_ascii=False)


def two_sprint_doc():
    return json.dumps({"features": [
        {"id": "F-001", "title": "添加待办", "sprint": 1,
         "scenarios": ["回车新增一条", "[错误] 空白提交有提示"], "passes": False},
        {"id": "F-002", "title": "完成待办", "sprint": 2,
         "scenarios": ["点击复选框标记完成", "[边界] 取消完成可以恢复"], "passes": False},
    ]}, ensure_ascii=False)


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="wb-test-")
        self.root = Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(HARNESS), *args], cwd=self.root,
                              capture_output=True, text=True)

    def hook(self, event, payload=None, agent=None):
        data = dict(payload or {})
        data["cwd"] = str(self.root)
        if agent:
            data["agent_type"] = agent
        proc = subprocess.run([sys.executable, str(HOOKS), event], input=json.dumps(data),
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def write_file(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def bash(self, command, agent=None):
        return self.hook("pre-bash", {"tool_name": "Bash", "tool_input": {"command": command}}, agent)

    def write(self, rel, content, agent=None, tool="Write"):
        payload = {"tool_name": tool, "tool_input": {"file_path": rel, "content": content}}
        return self.hook("pre-write", payload, agent)


class PlanningCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.cli("init").returncode, 0)

    def confirm_single_sprint(self):
        self.write_file(".web-builder/feature_list.json", feature_doc())
        self.assertEqual(self.cli("validate-plan").returncode, 0)
        self.assertEqual(self.cli("confirm-plan").returncode, 0)


class TestInitAndPlan(PlanningCase):
    def test_init_creates_state_and_template_files(self):
        state = json.loads((self.root / ".web-builder/state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "planning")
        self.assertFalse((self.root / ".claude/settings.json").exists())
        self.assertTrue((self.root / ".claude/rules/web-builder.md").is_file())
        gitignore = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".web-builder/evidence/", gitignore)

    def test_init_is_idempotent(self):
        out = self.cli("init")
        self.assertEqual(out.returncode, 0)
        self.assertIn("Already initialised", out.stdout)

    def test_valid_feature_list_passes_validation(self):
        feats, err = harness.validate_feature_text(feature_doc())
        self.assertIsNone(err)
        self.assertEqual(len(feats), 1)

    def test_planning_rejects_passes_true(self):
        _, err = harness.validate_feature_text(feature_doc(passes=True))
        self.assertIsNotNone(err)

    def test_sprint_numbers_must_be_contiguous(self):
        doc = json.dumps({"features": [{"id": "F-001", "title": "a", "sprint": 2,
                                        "scenarios": ["[错误] x", "y"], "passes": False}]})
        _, err = harness.validate_feature_text(doc)
        self.assertIn("contiguous", err)

    def test_each_feature_needs_an_error_or_edge_scenario(self):
        _, err = harness.validate_feature_text(feature_doc(scenarios=["只有一条"]))
        self.assertIsNotNone(err)
        _, err = harness.validate_feature_text(feature_doc(scenarios=["正常流程一", "正常流程二"]))
        self.assertIn("tagged", err)
        _, err = harness.validate_feature_text(feature_doc(scenarios=["[error] 空输入", "正常流程"]))
        self.assertIsNone(err)
        _, err = harness.validate_feature_text(feature_doc(scenarios=["[边界] 超长标题", "正常流程"]))
        self.assertIsNone(err)

    def test_confirm_plan_freezes_and_starts_building(self):
        self.confirm_single_sprint()
        state = json.loads((self.root / ".web-builder/state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "building")
        self.assertEqual(state["sprint"], 1)
        self.assertTrue((self.root / ".web-builder/plan_confirmed.json").is_file())
        self.assertEqual(self.cli("confirm-plan").returncode, 1)


class TestBuildLoop(PlanningCase):
    def setUp(self):
        super().setUp()
        self.write_file(".web-builder/feature_list.json", two_sprint_doc())
        self.assertEqual(self.cli("confirm-plan").returncode, 0)

    def evidence(self, sprint):
        base = f".web-builder/evidence/sprint-{sprint}/cycle-1"
        self.write_file(f"{base}/report.md", "ok")
        self.write_file(f"{base}/results.json", "{}")

    def grade(self, cycle, evaluator="PASS", score=90, p0=None, sprint=1):
        self.write_file(f".web-builder/verdicts/sprint-{sprint}-evaluator.json", json.dumps(
            {"role": "evaluator", "sprint": sprint, "cycle": cycle,
             "verdict": evaluator, "failures": []}))
        self.write_file(f".web-builder/verdicts/sprint-{sprint}-pa.json", json.dumps(
            {"role": "pa", "sprint": sprint, "cycle": cycle,
             "score": score, "p0": p0 or []}))

    def test_mark_sprint_requires_verdicts_and_evidence(self):
        self.assertEqual(self.cli("cycle").returncode, 0)
        out = self.cli("mark-sprint")
        self.assertEqual(out.returncode, 1)
        self.assertIn("evaluator verdict", out.stdout)
        self.assertIn("evidence bundle", out.stdout)

    def test_evidence_bundle_needs_report_and_a_result(self):
        self.cli("cycle")
        base = ".web-builder/evidence/sprint-1/cycle-1"
        self.grade(cycle=1)
        self.write_file(f"{base}/results.json", "{}")
        self.assertIn("must contain report.md", self.cli("mark-sprint").stdout)
        (self.root / base / "results.json").unlink()
        self.write_file(f"{base}/report.md", "ok")
        self.assertIn("at least one result file", self.cli("mark-sprint").stdout)

    def test_mark_sprint_rejects_low_score_and_p0(self):
        self.cli("cycle")
        self.evidence(1)
        self.grade(cycle=1, score=79)
        self.assertIn("below the pass mark", self.cli("mark-sprint").stdout)
        self.grade(cycle=1, score=95, p0=["移动端按钮不可点击"])
        self.assertIn("P0", self.cli("mark-sprint").stdout)

    def test_mark_sprint_passes_and_advances(self):
        self.cli("cycle")
        self.evidence(1)
        self.grade(cycle=1)
        self.assertEqual(self.cli("mark-sprint").returncode, 0)
        feats = harness.load_features(self.root)
        self.assertTrue(feats[0]["passes"])
        self.assertFalse(feats[1]["passes"])
        state = json.loads((self.root / ".web-builder/state.json").read_text(encoding="utf-8"))
        self.assertEqual((state["phase"], state["sprint"], state["cycles"]), ("building", 2, 0))

        self.cli("cycle")
        self.evidence(2)
        self.grade(cycle=1, sprint=2)
        self.assertEqual(self.cli("mark-sprint").returncode, 0)
        state = json.loads((self.root / ".web-builder/state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "done")

    def test_cycle_budget_and_extension(self):
        for _ in range(harness.MAX_CYCLES):
            self.assertEqual(self.cli("cycle").returncode, 0)
        self.assertEqual(self.cli("cycle").returncode, 3)
        self.assertEqual(self.cli("extend-cycles").returncode, 0)
        self.assertEqual(self.cli("cycle").returncode, 0)

    def test_scope_change_after_confirmation_is_detected(self):
        doc = json.loads(two_sprint_doc())
        doc["features"][0]["title"] = "被偷偷改掉的标题"
        self.write_file(".web-builder/feature_list.json", json.dumps(doc, ensure_ascii=False))
        self.cli("cycle")
        self.evidence(1)
        self.grade(cycle=1)
        out = self.cli("mark-sprint")
        self.assertEqual(out.returncode, 1)
        self.assertIn("scope changed", out.stderr)

    def test_orchestrator_does_not_write_project_files_during_build(self):
        self.assertEqual(self.write("src/app.js", "x")[0], 2)
        self.assertEqual(self.write("src/app.js", "x", agent="web-builder-generator")[0], 0)

    def test_scope_hash_ignores_passes(self):
        feats = json.loads(two_sprint_doc())["features"]
        before = harness.scope_hash(feats)
        feats[0]["passes"] = True
        self.assertEqual(before, harness.scope_hash(feats))


class TestBashGate(PlanningCase):
    def test_non_harness_directory_is_untouched(self):
        shutil.rmtree(self.root / ".web-builder")
        code, _, _ = self.bash('git commit -m "bad"')
        self.assertEqual(code, 0)

    def test_commit_message_format(self):
        self.assertEqual(self.bash('git commit -m "bad message"')[0], 2)
        self.assertEqual(self.bash('git commit -m "feat(todo): add items"')[0], 0)
        self.assertEqual(self.bash("git commit -am 'fix: keep state'")[0], 0)
        self.assertEqual(self.bash('git commit -m "feat(F-001): 支持添加待办"')[0], 0)
        self.assertEqual(self.bash("git commit --amend --no-edit")[0], 0)
        self.assertEqual(self.bash("git commit")[0], 2)

    def test_shell_cannot_write_state_files(self):
        self.assertEqual(self.bash("echo '{}' > .web-builder/state.json")[0], 2)
        self.assertEqual(self.bash("python3 harness.py status")[0], 0)

    def test_control_commands_are_orchestrator_only(self):
        cmd = 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" mark-sprint'
        self.assertEqual(self.bash(cmd, agent="web-builder-generator")[0], 2)
        self.assertEqual(self.bash(cmd)[0], 0)

    def test_shell_cannot_rewrite_locked_config(self):
        self.assertEqual(self.bash("echo '{}' > .claude/settings.json")[0], 2)
        self.assertEqual(self.bash("python3 -c \"open('.claude/settings.json','w').write('{}')\"")[0], 2)
        self.assertEqual(self.bash("cat .claude/settings.json")[0], 0)

    def test_only_graders_write_verdicts_from_shell(self):
        cmd = "echo '{}' > .web-builder/verdicts/sprint-1-pa.json"
        self.assertEqual(self.bash(cmd, agent="web-builder-generator")[0], 2)
        self.assertEqual(self.bash(cmd, agent="web-builder-pa")[0], 0)


class TestWriteGate(PlanningCase):
    def test_product_code_blocked_before_confirmation(self):
        self.assertEqual(self.write("src/app.js", "x")[0], 2)
        self.assertEqual(self.write("CLAUDE.md", "x", agent="web-builder-planner")[0], 0)
        self.assertEqual(self.write("src/app.js", "x", agent="web-builder-planner")[0], 2)

    def test_planner_writes_valid_feature_list_only_before_confirmation(self):
        self.assertEqual(self.write(".web-builder/feature_list.json", feature_doc(),
                                    agent="web-builder-planner")[0], 0)
        self.assertEqual(self.write(".web-builder/feature_list.json", feature_doc(passes=True),
                                    agent="web-builder-planner")[0], 2)
        self.assertEqual(self.write(".web-builder/feature_list.json", feature_doc(),
                                    agent="web-builder-generator")[0], 2)
        self.assertEqual(self.write(".web-builder/feature_list.json", "{}", agent="web-builder-planner",
                                    tool="Edit")[0], 2)

    def test_state_and_confirmation_files_are_never_writable(self):
        self.assertEqual(self.write(".web-builder/state.json", "{}")[0], 2)
        self.assertEqual(self.write(".web-builder/plan_confirmed.json", "{}")[0], 2)

    def test_path_outside_project_is_blocked(self):
        self.assertEqual(self.write("/etc/hosts-copy", "x")[0], 2)

    def test_claude_settings_are_locked(self):
        self.assertEqual(self.write(".claude/settings.json", "{}")[0], 2)

    def test_mock_data_only_allowed_under_tests(self):
        self.confirm_single_sprint()
        gen = "web-builder-generator"
        self.assertEqual(self.write("src/todos_mock.js", "x", agent=gen)[0], 2)
        self.assertEqual(self.write("tests/e2e/todos_mock.js", "x", agent=gen)[0], 0)


class TestVerdictGate(PlanningCase):
    def setUp(self):
        super().setUp()
        self.confirm_single_sprint()
        self.cli("cycle")

    def verdict(self, role, cycle=1, sprint=1, agent=None, **extra):
        body = {"role": role, "sprint": sprint, "cycle": cycle, **extra}
        return self.write(f".web-builder/verdicts/sprint-{sprint}-{role}.json",
                          json.dumps(body), agent=agent or f"web-builder-{role}")

    def test_evaluator_verdict_must_match_current_cycle(self):
        self.assertEqual(self.verdict("evaluator", verdict="PASS", failures=[])[0], 0)
        self.assertEqual(self.verdict("evaluator", cycle=2, verdict="PASS", failures=[])[0], 2)

    def test_pa_verdict_needs_numeric_score(self):
        self.assertEqual(self.verdict("pa", score=85, p0=[])[0], 0)
        self.assertEqual(self.verdict("pa", score="high", p0=[])[0], 2)

    def test_graders_cannot_write_verdicts_for_each_other(self):
        self.assertEqual(self.verdict("pa", agent="web-builder-evaluator", score=90, p0=[])[0], 2)

    def test_evaluator_is_read_only_for_product_code(self):
        self.assertEqual(self.write("src/app.js", "x", agent="web-builder-evaluator")[0], 2)
        self.assertEqual(self.write("src/app.js", "x", agent="web-builder-pa")[0], 2)

    def test_only_evaluator_writes_evidence(self):
        self.assertEqual(self.write(".web-builder/evidence/sprint-1/cycle-1/report.md", "x",
                                    agent="web-builder-evaluator")[0], 0)
        self.assertEqual(self.write(".web-builder/evidence/sprint-1/cycle-1/report.md", "x",
                                    agent="web-builder-generator")[0], 2)


class TestStopGate(PlanningCase):
    def test_stop_allowed_during_planning(self):
        self.assertEqual(self.hook("stop", {"stop_hook_active": False})[0], 0)

    def test_stop_blocked_while_sprint_pending_then_released_without_progress(self):
        self.confirm_single_sprint()
        code, _, err = self.hook("stop", {"stop_hook_active": False})
        self.assertEqual(code, 2)
        self.assertIn("F-001", err)
        self.assertEqual(self.hook("stop", {"stop_hook_active": True})[0], 0)

    def test_stop_allowed_when_cycle_budget_is_spent(self):
        self.confirm_single_sprint()
        for _ in range(harness.MAX_CYCLES):
            self.cli("cycle")
        self.assertEqual(self.hook("stop", {"stop_hook_active": False})[0], 0)


class TestPromptGate(ProjectCase):
    def test_bare_command_is_rejected(self):
        self.assertEqual(self.hook("prompt-submit", {"prompt": "/web-builder"})[0], 2)
        self.assertEqual(self.hook("prompt-submit", {"prompt": "/web-builder 做个"})[0], 2)

    def test_real_request_passes(self):
        self.assertEqual(self.hook("prompt-submit", {"prompt": "/web-builder 做一个番茄钟网页应用"})[0], 0)
        self.assertEqual(self.hook("prompt-submit", {"prompt": "/web-builder build a todo app"})[0], 0)
        self.assertEqual(self.hook("prompt-submit", {"prompt": "/web-builder status"})[0], 0)
        self.assertEqual(self.hook("prompt-submit", {"prompt": "随便聊聊"})[0], 0)


class TestSessionStart(PlanningCase):
    def test_status_is_injected(self):
        code, out, _ = self.hook("session-start")
        self.assertEqual(code, 0)
        self.assertIn("Web Builder: phase=planning", out)


class TestVerdictRules(unittest.TestCase):
    """Pure validation of grader verdicts, no project directory needed."""
    STATE = {"sprint": 1, "cycles": 1}
    FAILURE = {"feature": "F-001", "scenario": "空白提交", "expected": "提示", "actual": "新增空项"}

    def check(self, body, role="evaluator"):
        payload = {"role": role, "sprint": 1, "cycle": 1, **body}
        return harness.validate_verdict_text(json.dumps(payload, ensure_ascii=False), role, self.STATE)

    def test_pass_must_have_no_failures(self):
        self.assertIsNone(self.check({"verdict": "PASS", "failures": []}))
        self.assertIsNotNone(self.check({"verdict": "PASS", "failures": [self.FAILURE]}))

    def test_fail_must_list_failures(self):
        self.assertIsNotNone(self.check({"verdict": "FAIL", "failures": []}))
        self.assertIsNone(self.check({"verdict": "FAIL", "failures": [self.FAILURE]}))

    def test_failure_items_need_their_fields(self):
        self.assertIsNotNone(self.check({"verdict": "FAIL", "failures": [{"feature": "F-001"}]}))

    def test_pa_score_bounds(self):
        self.assertIsNone(self.check({"score": 80, "p0": []}, role="pa"))
        self.assertIsNotNone(self.check({"score": 101, "p0": []}, role="pa"))


class TestRepositoryHygiene(unittest.TestCase):
    def read_json(self, rel):
        return json.loads((REPO / rel).read_text(encoding="utf-8"))

    def test_manifests_are_valid_and_versions_agree(self):
        market = self.read_json(".claude-plugin/marketplace.json")
        plugin = self.read_json("web-builder/.claude-plugin/plugin.json")
        self.assertEqual(plugin["version"], "9.0.0")
        self.assertEqual(market["plugins"][0]["version"], plugin["version"])
        self.assertEqual(market["metadata"]["version"], plugin["version"])
        self.assertEqual(market["plugins"][0]["source"], "./web-builder")

    def test_urls_point_to_coldingcode(self):
        plugin = self.read_json("web-builder/.claude-plugin/plugin.json")
        self.assertTrue(plugin["repository"].startswith("https://github.com/coldingcode/"))
        self.assertEqual(plugin["author"]["name"], "coldingcode")

    def test_hook_commands_reference_existing_script(self):
        hooks = self.read_json("web-builder/hooks/hooks.json")["hooks"]
        for event, groups in hooks.items():
            for group in groups:
                for hook in group["hooks"]:
                    match = re.search(r'"\$\{CLAUDE_PLUGIN_ROOT\}/([^"]+)"', hook["command"])
                    self.assertIsNotNone(match, hook["command"])
                    self.assertTrue((PLUGIN / match.group(1)).is_file(), match.group(1))

    def test_no_shell_hooks_remain(self):
        self.assertEqual(list((PLUGIN / "scripts").glob("*.sh")), [])
        self.assertFalse((PLUGIN / ".mcp.json").exists())

    def test_template_ships_rules_only(self):
        template = PLUGIN / "project-template"
        self.assertTrue((template / ".claude/rules/web-builder.md").is_file())
        self.assertFalse((template / ".claude/settings.json").exists())

    def test_agent_names_match_files(self):
        for path in (PLUGIN / "agents").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            name = re.search(r"^name: (.+)$", text, re.M).group(1).strip()
            self.assertEqual(name, path.stem)

    def test_no_placeholder_or_legacy_names(self):
        banned = ["your-org", "harness@example.com", "Harness Engineering",
                  "web-builder-harness-zh", "web-builder-marketplace-zh"]
        skip = {"docs/history", "tests/test_harness.py", "CHANGELOG.md"}
        for path in REPO.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix == ".pyc":
                continue
            rel = path.relative_to(REPO).as_posix()
            if any(rel.startswith(s) for s in skip):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for word in banned:
                self.assertNotIn(word, text, f"{word} found in {rel}")


if __name__ == "__main__":
    unittest.main()
