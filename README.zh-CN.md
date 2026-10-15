# Web Builder Harness

[English](README.md) · 中文

一个 Claude Code 插件，把一句话的想法变成一个小型、经过验证的网站。它先做产品规划，再按冲刺构建，每个冲刺都由相互独立的智能体验收。门禁由钩子强制执行，因此构建者无法给自己打分。

## 它做什么

1. **规划。** 规划智能体会提出少量有针对性的问题，写出带设计方向的产品规格，并生成功能清单。每个功能都有具体的用户场景，且至少包含一条以 `[错误]` / `[error]` 或 `[边界]` / `[edge]` 开头的场景。
2. **确认一次。** 你确认功能清单后，范围即被冻结，并记录哈希值。
3. **按冲刺构建。** 每个冲刺依次经过生成、评估、产品验收三个环节。只有评估者和产品验收都通过，冲刺才算通过。每个冲刺最多 3 轮，用尽后由主流程询问你如何处理。

各角色互不越界：

| 角色 | 可以写入 | 不能做 |
|---|---|---|
| 规划智能体 | `CLAUDE.md`、`.web-builder/spec.md`、`feature_list.json`（仅一次） | 写产品代码 |
| 生成智能体 | 产品代码、`tests/` | 修改 `.web-builder/`，修改通过状态 |
| 评估者 | `.web-builder/evidence/`、自己的判定 | 修改代码，做视觉品味评分 |
| 产品验收（PA） | 仅自己的判定 | 运行应用，修改任何文件 |

## 安装

需要 Python 3（`python3` 在 PATH 中），脚本只使用标准库。

在 Claude Code 中执行：

```
/plugin marketplace add coldingcode/web-builder-harness
/plugin install web-builder@web-builder-harness
```

然后在一个空文件夹（或已有仓库）中启动一次运行：

```
/web-builder 一个带任务列表的番茄钟网页应用
```

随时可以用 `/web-builder status` 查看进度，中断后用 `/web-builder resume` 继续。

## 门禁

`web-builder/hooks/hooks.json` 中的钩子调用 `web-builder/scripts/hooks.py`。阻断使用退出码 2，符合 Claude Code 的钩子协议。

- **状态由脚本维护。** `state.json`、`plan_confirmed.json`、`feature_list.json` 不能通过 Write、Edit 或 shell 重定向写入，只有 `harness.py` 能修改。
- **确认即冻结范围。** `confirm-plan` 之后功能清单不能再改写。范围哈希不包含通过状态，因此标记冲刺不会使其失效。
- **判定只来自评估者和产品验收。** 只有这两个智能体能写判定文件，且文件必须与当前冲刺和轮次一致。
- **冲刺只凭证据通过。** `mark-sprint` 要求评估者判定 `PASS`、产品验收分数不低于 80 且没有 P0 问题，并且当轮证据包包含 `report.md` 和至少一个结果文件或截图。
- **先规划，后写代码。** 功能清单确认前，不能写产品代码。
- **提交遵循 Conventional Commits**，例如 `feat(F-001): 支持添加待办`。
- **Stop 门禁。** 冲刺未完成时，主流程不能结束回合。如果一次阻断之后没有任何变化（没有新提交、没有工作区改动、没有新判定），门禁会放行，避免无限循环。轮次用尽后允许结束回合，以便询问你。
- **测试数据只放在 tests 里。** `tests/` 之外的 `*_mock.*`、`*.seed.*`、`*.fake.*` 等文件会被拒绝。
- **编排者不直接写项目文件。** 规划与构建阶段，产品代码由生成智能体写，规划文件由规划智能体写。
- **配置被锁定。** `.claude/settings*.json` 与 `.claude/hooks/` 不能通过 Write、Edit 或 shell 重定向修改。

钩子只在 Web Builder 项目（存在 `.web-builder/state.json` 的文件夹）中生效，安装插件不会影响你的其他仓库。

## 项目结构

运行完成后，你的项目中会包含：

```
.web-builder/
  state.json            运行状态（harness.py）
  spec.md               产品规格与设计方向（规划智能体）
  feature_list.json     功能与冲刺（规划智能体，确认后冻结）
  plan_confirmed.json   确认记录与范围哈希
  verdicts/             sprint-N-evaluator.json、sprint-N-pa.json
  evidence/sprint-N/cycle-C/   report.md、结果文件、截图
CLAUDE.md               所选技术栈的约定与命令（规划智能体）
.claude/rules/web-builder.md   Claude Code 加载的项目规则
tests/e2e/              持久化的 Playwright 测试，每个冲刺一个目录
```

## 仓库结构

```
.claude-plugin/marketplace.json     市场清单
web-builder/
  .claude-plugin/plugin.json
  agents/                           规划、生成、评估、产品验收
  commands/web-builder.md           /web-builder 的编排流程
  hooks/hooks.json
  scripts/harness.py                状态机与控制命令行
  scripts/hooks.py                  钩子分发器
  skills/                           共享参考与产品验收清单
  project-template/                 初始化时复制到项目中
tests/test_harness.py               单元与集成测试
docs/history/                       归档的 v8 设计与自评
```

## 开发

测试套件只使用标准库：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖：状态机、轮次预算与延长、提交信息与写入门禁、判定校验、Stop 门禁的放行规则、提示词检查，以及仓库卫生（清单版本一致、钩子脚本路径有效、没有占位名称）。

## 局限

- 插件的智能体与命令提示词目前是中文。README 提供英文与中文两个版本。生成的应用使用什么语言，取决于你的需求。
- 确认后范围被冻结。要修改范围，请在新文件夹中开始新的运行。
- 评估者与产品验收和生成者运行在同一台本地环境中，它们的独立性来自上下文隔离，而不是机器隔离。
- 插件不提供权限白名单，所以 Claude Code 会要求你确认文件写入和 shell 命令。钩子只负责拦截，不会预先批准任何操作。

## 历史

v9 用 Python 钩子分发器和控制命令行，替换了 v8 的 shell 钩子。v8 的钩子不能可靠地阻断，也与自身的设计文档不一致。v8 的设计与自评归档在 `docs/history/` 中。详见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

[LICENSE](LICENSE)。

## Community 
<a href="https://qm.qq.com/q/xf3G2NODwA" target="_blank"><img src="https://img.shields.io/badge/QQ%20群-1108208001-EB1923?logo=tencentqq&logoColor=white" alt="QQ Group" /></a>
[![LINUX DO](https://img.shields.io/badge/LINUX%20DO-Community-blue)](https://linux.do)
