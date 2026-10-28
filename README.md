# 选题 2：内容任务规划 Agent

帮助运营人员在预算与截止时间内生成并保存内容活动方案。提供 Python CLI、四类本地合成业务工具、模型工具调用接口、SQLite 状态与账本、可核对的执行证据。

仓库：[lwwdsb/AgentForPlanning](https://github.com/lwwdsb/AgentForPlanning)。仓库公开。最终提交 SHA 通过 `git rev-parse HEAD` 获取；不把 SHA 写回同一个提交。

**当前验证：离线测试通过，并已用 DeepSeek `deepseek-flash` 验证预算改选与生成失败改选两条真实路径。原始成功、失败和提示修订记录见 [真实评估](examples/real/README.md)。这些运行不代表所有输入的可靠性；Mock 仍只证明流程。**

## 安装与最短演示

已验证 Python 3.12.12 / macOS；要求 Python 3.12+。运行时仅标准库，无 Agent 框架。构建与测试依赖锁定在依赖文件。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-build-isolation --no-deps -e .

# 用当前时间生成未来一天的截止时间。不会覆盖运行时的真实时钟。
python - <<'PY'
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
Path('.state').mkdir(exist_ok=True)
value = {'theme': '校园读书周', 'budget': '10.00',
         'deadline': (datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
         'preferred_variant': 'standard'}
Path('.state/demo.json').write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
PY

content-agent run --input .state/demo.json --mode mock --request-id demo-1 --state .state/demo.db --evidence-dir .state/demo-evidence
content-agent show --request-id demo-1 --state .state/demo.db --view artifact
content-agent show --request-id demo-1 --state .state/demo.db --evidence-dir .state/demo-reexport
```

正常输出：`completed`、费用 `8.00`、6 个决策轮次、720 秒合成工具耗时，以及 SQLite 中的方案位置。实际执行不需要等待 720 秒。

完全离线且未安装包时也可运行：在仓库根目录使用 `PYTHONPATH=src python3.12 -m content_agent` 替代上述 `content-agent`。Mock 无需模型变量或网络。默认 `--data-dir data` 相对仓库根目录；请在根目录执行示例。

## 批量验证与评审入口

```bash
python -m pytest -q --junitxml=examples/test-results/pytest.xml
python scripts/run_examples.py
```

第二条命令重新生成未来截止时间、使用新状态库并实际执行 13 个场景、重复执行和冲突验证，更新 `examples/mock/` 中的证据。历史证据的截止时间可能已过，不要把复用旧结果当成一次新运行。查看命令、用时与退出码：[scenario-runs.json](examples/test-results/scenario-runs.json)。

| 材料 | 评审内容 |
|---|---|
| [需求](docs/01-requirements.md) | 用户、范围、验收标准 |
| [方案](docs/02-solution.md) | 模型循环、费用、时间、依赖、事务与幂等 |
| [评估](docs/03-evaluation.md) | 预期/实际、全部 FR/SC 映射、限制 |
| [AI 使用](docs/04-ai-usage.md) | AI 辅助、用户修改、验证来源 |
| [复盘](docs/05-retrospective.md) | 实际用时、难点与未完成部分 |
| [正常方案](examples/mock/normal/artifact.json) | 活动内容、引用、假设、实际依赖与费用明细 |
| [预算改选 Trace](examples/mock/budget-replan/trace.jsonl) | 12 超限 → 8 可行 → 生成 → 重估 → 保存 |
| [生成失败 Trace](examples/mock/tool-failure/trace.jsonl) | 原失败保留 → 替代形式完成 |
| [实现任务](specs/001-content-planning-agent/tasks.md) | 已完成任务及明确待办 |

目录职责：`src/` 为业务实现，`tests/` 为默认不联网的可执行测试，`data/` 为合成资料/规则，`examples/` 为实际证据，`docs/` 为评审文档，`specs/` 与 `.specify/` 为规格与治理。`.state/`、`.venv/`、真实 `.env` 不提交。

## CLI 与状态

```text
content-agent run --input FILE --mode mock|real
  [--request-id ID] [--state .state/content-agent.db] [--data-dir data]
  [--max-rounds 12] [--fault none] [--evidence-dir DIR]
content-agent show --request-id ID [--state .state/content-agent.db]
  [--view result|trace|artifact] [--evidence-dir DIR]
content-agent recover --request-id ID [--state .state/content-agent.db]
```

输入为 JSON 对象：`theme`、字符串金额 `budget`、带时区 ISO 8601 `deadline`，可选 `preferred_variant`（premium/standard/lean，默认 premium）。缺失或无效字段一次返回，不调用模型或工具。金额以整数百分单位计算，估算不收费，失败不收费但消耗规则时间，旧成功步骤的费用保留。

每次模型请求先消耗一轮；结束、无效动作和服务错误也计数。默认 12 轮，可设 1–100。模型决定下一动作，执行器只校验及执行。第 12 轮合法结束可以完成；第 12 轮仅保存则返回 `limit_reached` 并保留产物。

同一请求 ID 和条件重复提交返回原 `run_id` 与 `reused=true`，不新增模型/工具调用、费用或保存。输入、模式、规则、故障或额度变化返回 `input_conflict`。新请求使用新 ID。重复失败请求不自动续跑。`recover` 仅在同主机确认原 PID 已不存在时标记 `interrupted`，保留已提交成果，不执行续跑；进程存活或无法确认时拒绝。

SQLite `artifacts` 表中的方案是权威产物，`saved_plan.location` 是库内逻辑位置，通过 `show` 读取。导出是派生副本，包含原始输入、历史结果、JSONL Trace、带校验摘要的 manifest 和已有方案。`show --evidence-dir` 只读同一快照；不重判当前截止时间，不读取模型密钥。复用请求的证据包仍是原始记录，当前调用的 `reused=true` 在 stdout；重复验证材料另外记录调用输出。

| 退出码 | 含义 |
|---:|---|
| 0 | run 完成，或 show/recover 成功 |
| 2 | 待补充/修正输入 |
| 3 | 未完成或已有运行进行中 |
| 4 | 请求条件冲突 |
| 64 | 命令、配置或输入文件格式错误；recover 无法确认原进程已退出 |
| 66 | 找不到请求或保存方案 |
| 70 | 内部错误 |
| 74 | 证据文件导出失败；已有业务结果不丢失，可用 show 重试 |

故障参数：`generate-once`、`generate-always`、`save-once`、`partial-generate`，默认 `none`。所有注入均记入配置、指纹和 Trace。一次保存失败未恢复返回未完成；模型显式重试成功后才能完成，失败记录不会覆盖。

## 真实模型入口（DeepSeek 已实测）

在当前 shell 安全配置 `MODEL_ENDPOINT`（完整 HTTPS Chat Completions URL）、`MODEL_NAME`、`MODEL_API_KEY`。密钥只由真实适配器发送至指定端点，不写入日志或参数；不要把密钥粘贴到聊天、命令历史或仓库。程序不自动读取 `.env`，变量声明见 [.env.example](.env.example)。

```bash
content-agent run --input examples/inputs/budget-replan.json --mode real --request-id real-budget-1 --state .state/real.db --data-dir examples/fixtures/budget-replan --evidence-dir .state/manual-evidence/budget-replan
content-agent run --input examples/inputs/tool-failure.json --mode real --request-id real-failure-1 --state .state/real.db --data-dir examples/fixtures/tool-failure --fault generate-once --evidence-dir .state/manual-evidence/tool-failure
```

先用批量脚本刷新输入日期。端点需支持原生 `tools`、`strict` schema、`tool_choice=required` 和禁用并行工具调用；已实测 `https://api.deepseek.com/beta/chat/completions` + `deepseek-flash`；其他端点/模型组合需另行验证。DeepSeek 配置关闭 thinking，并适配其支持的 schema 关键字；本地长度与业务守卫不放宽。HTTP 单次 socket 超时 30 秒、响应上限 1 MiB、禁止重定向、无隐式重试；出错明确终止，不回退 Mock。真实 token 费用不在合成业务预算中。

只有实际观察到超预算后的改选，以及工具失败后的调整或停止，才计为真实决策证据；不能用离线 Trace 补写真实执行。两条验收路径现已取得，首次未命中的运行也保留在 `examples/real/attempts/`。

也可复制 `.env.example` 为本机 `.env` 后填写密钥，用不执行 shell 语句的评估脚本显式加载：

```bash
python scripts/run_real_examples.py --env-file .env --case budget-replan
python scripts/run_real_examples.py --env-file .env --case tool-failure
```

脚本逐次保留实际输入和输出，不会覆盖已有主验收证据。`.env` 不提交 Git，主 CLI 仍不自动加载该文件。
