# Implementation Plan: 内容任务规划 Agent

**Branch**: `main`；逻辑功能标识 `001-content-planning-agent`，功能文件位于对应 specs 目录。
**Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-content-planning-agent/spec.md`。
**Stage**: 本地实现、离线验证与 DeepSeek 两条真实动态路径完成，当前事实与限制见 docs/03-evaluation.md。

## Summary

构建单用户 Python CLI，采用原生模型工具调用循环、四类本地业务工具和 SQLite 权威状态。
模型接收真实观察后选择检索、估算、生成、保存或结束；执行器负责动作验证、步骤依赖、
预算与截止时间守卫以及默认 12 轮上限，不替模型选择替代方案。

先估算再付费生成；预算改选和故障恢复保留历史成功结果与费用。真实模型与离线 Mock 共用执行器，
模式显式可见。保存的方案正文位于 SQLite，通过 show 命令读取和导出，避免文件与数据库双写。
US1 即提供完整证据包导出，show --evidence-dir 可只读重建材料，不触发业务执行。
交付重点为可复制入口、准确状态及至少两条真实观察驱动的决策路径。

## Technical Context

**Language/Version**: Python 3.12+，最终记录实际验证的小版本。

**Primary Dependencies**: 运行时仅 Python 标准库；开发依赖 pytest，构建依赖 setuptools，
实现阶段锁定实际验证版本；不使用 Agent 框架或模型 SDK。

**Storage**: SQLite 保存 requests、events、ledger、artifacts；产物正文为 JSON。
素材与工具规则为版本化 JSON 文件，JSONL Trace 与结果 JSON 为从权威状态导出的评审材料。

**Testing**: pytest 的领域单元测试、CLI 子进程集成测试及模型协议契约测试；
真实模型路径作为显式运行的评估，不加入默认离线测试。

**Target Platform**: 本地 macOS / Linux，Python 3.12+；不要求服务端、容器或线上部署。

**Project Type**: 单一 Python CLI 项目，命令名 `content-agent`。

**Performance Goals**: 离线单请求在普通开发机 2 秒内完成，默认离线测试集 30 秒内完成，
作为待实测目标；真实调用单次 socket 超时 30 秒，无隐式重试，最多 12 轮。
该超时不宣称严格整次运行 wall-clock 上界，运行结果仍受业务截止时间检查。

**Constraints**: 金额精确到 0.01 模拟单位；依赖顺序执行；输入时间带时区；
每轮最多一个业务动作；真实模型不可用不静默切 Mock；只使用合成业务数据，不提交密钥。
模型实际等待与工具耗时顺序累计，工具实际与模拟耗时取较大值，不能让两类耗时相互抵消。
成功脚本不可原地改写；业务条件不变时只复用，同次运行内未成功的保存可由模型选择重试。

**Scale/Scope**: 一个运营人员、四类工具、三种候选形式、默认 12 个决策轮次；
保证本地同一请求幂等，不承诺远端业务恰好执行一次、多用户并发或跨运行续跑。

## Constitution Check

*GATE: 调研前初查与 Phase 1 设计后复查均通过。通过表示设计符合约束，不代表业务已验收。*

| 宪章原则 | 初查 | 设计后 | 设计落实与后续验证 |
| --- | --- | --- | --- |
| I. 业务目标与核心链路 | PASS | PASS | CLI 输入与四类工具见 contracts/；US1–US2 验证完整结果和缺失信息 |
| II. 真实有界决策 | PASS | PASS | 原生 tool_calls、实际观察、显式 finish、12 轮；真实路径见 quickstart |
| III. 状态与约束一致 | PASS | PASS | 事务账本、依赖、UTC+模拟耗时、幂等指纹；见 data-model |
| IV. 真实运行证据 | PASS | PASS | 计划覆盖全部必验收点的运行材料及边界测试；真实与 Mock 分目录并区分结论 |
| V. 简约与诚实交付 | PASS | PASS | 标准库运行栈；不增加界面、部署、运行时多 Agent 或续跑 |

无宪章例外。题号、仓库 URL、最终 SHA 和评审权限在交付时填实；
真实模型可用性在实施时验证，不作为当前已通过的运行结论。
宪章顶部临时同步报告按其规则在提交宪章前移除，本次不修改宪章。

## Project Structure

### Documentation (this feature)

```text
specs/001-content-planning-agent/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   └── model-and-tools.md
└── checklists/requirements.md
```

`tasks.md` 记录实施顺序与完成状态。

### Source Code (repository root)

以下结构已建立：

```text
README.md
pyproject.toml
requirements-dev.txt
.env.example
.gitignore
src/content_agent/
├── __init__.py
├── __main__.py
├── cli.py           # run / show / recover
├── domain.py        # 状态、金额、时间、指纹与不变量
├── runner.py        # 有界观察—决策—执行循环
├── providers.py     # 真实 HTTP / 显式 Mock
├── tools.py         # 检索、估算、生成、保存
└── store.py         # SQLite 短事务及证据导出
tests/
├── test_domain.py
├── test_runner.py
├── test_store.py
├── test_provider_contract.py
└── test_cli.py
data/
├── materials.json
└── rules.json
examples/
├── inputs/
├── fixtures/
├── mock/
├── real/
└── test-results/
docs/
├── 01-requirements.md
├── 02-solution.md
├── 03-evaluation.md
├── 04-ai-usage.md
└── 05-retrospective.md
```

**Structure Decision**: 一个包承担单用户业务闭环，使用小模块分离模型、工具、领域规则与存储，
不引入通用工作流框架、仓库抽象层或服务部署。评审目录结构按宪章保留；
`docs/01-requirements.md` 引用本规格并提供验收摘要，避免两份独立需求漂移。

## Complexity Tracking

无需要豁免的宪章违规。SQLite 的额外成本用于同一事务内保存产物、状态和费用；
所有其他选择均以三小时核心链路范围为准。

## Design Decisions & Execution Flow

1. 解析输入并一次报告缺失字段；校验通过后对规范化输入与有效配置计算指纹，原子认领请求。
2. 重复请求读取既有结果或进度；冲突不改原记录；仅新请求进入模型循环。
3. 将业务约束、可选形式、工具契约、素材规则及当前状态交给模型；每次请求前持久化消耗一轮。
4. 保留模型 assistant tool_calls，经守卫执行最多一个工具；观察连同实际状态、费用、时间反馈模型。
5. 估算不决定下一动作；模型选择继续、替代或 finish。生成参数含模型当轮生成的脚本，工具不再调模型。
   同一候选已有成功脚本时只返回原产物；业务条件变化才创建新候选版本并重新估算。
6. 每个工具结果与费用、状态在短事务中一起提交；模型调用期间不持有写事务。
7. save_plan 保存当前方案，finish 才提出运行结束；执行器验证完成条件。
   第 12 轮 finish 合法可以成功；第 12 轮仅保存则保留产物、返回上限未完成，不追加总结调用。
8. 保存未恢复时停止或额度耗尽返回未完成；模型选择重试且新保存尝试成功、全部条件通过时允许完成，
   原失败尝试保持失败。工具和模型实际耗时写入统一逻辑时钟，计时细则见 data-model.md。
9. 输出来自数据库的结果和 Trace；US1 接通 run/show 的完整证据导出，
   show --evidence-dir 只读原始状态，导出失败返回 74，不触发模型/工具或改变业务结果。

详细接口见 [CLI 契约](contracts/cli.md)、[模型与工具契约](contracts/model-and-tools.md)；
状态、不变量、预算和时间语义见 [数据模型](data-model.md)。

## Validation Strategy & Delivery

- 预算：12→8、3+8>10、0.10+0.20=0.30、零预算、未知价格与历史支出不被清零。
- 状态：依赖未满足拒绝、部分结果不记成功、保存未恢复与重试成功分别验收，保留原失败、检索和已付费脚本。
- 候选：同候选不同草稿也复用原脚本；业务条件变化新建候选，重新估算，旧产物和支出保留。
- 时间：等于边界通过、预计超时改选或停止、工具 1 分钟后模型等待 5 分钟累计 6 分钟、
  实际工具 8 分钟/模拟 10 分钟只累计 10 分钟、实际模型延迟导致到期、失败耗时不重置。
- 额度：无效动作和 finish 计数、最后一轮合法终结、耗尽后零新增模型或工具调用。
- 幂等：跨进程相同请求重复、改变规则冲突、失败请求重复、进行中不启动第二执行器。
- 协议：正确关联工具结果、空/多动作拒绝、截断/超时明确失败、Mock 无网络、日志无认证信息。
- 证据：US1 即能导出完整材料，show 可只读重新导出且无新增调用/费用/事件；导出失败不改变原结果。
  执行 quickstart 场景生成实际文件，评估文档逐项引用；真实路径缺失必须记录为未验证。

建议实现时间分配：20 分钟领域规则与工具、55 分钟执行器与存储、25 分钟模型与 CLI、
45 分钟测试和运行证据、35 分钟文档和复现。该分配是实施预算，不是已投入时长；
必须在复盘中记录真实用时与未完成项。


## 独立审查后实现补充

新增 content.py 维护结构化交付范围校验和事实/建议分区渲染；依赖解析由最近同类步骤改为实际引用 ID。17 项修复回归、133 项全量测试及同版 v5 的两条真实路径见 [修复报告](../../docs/07-review-fixes.md)。规则升至 1.1，旧实际证据保持历史属性。
