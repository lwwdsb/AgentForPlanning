# Quickstart & Validation Guide

**Status**: 实施后的运行与验收指南。当前仅有规格与设计文档，以下应用命令尚不能执行；
本阶段没有产生项目运行结果、测试通过记录或真实模型证据。
**Contracts**: [CLI](contracts/cli.md)、[模型与工具](contracts/model-and-tools.md)。

## 1. 安装目标

在仓库根目录使用 Python 3.12+：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e . -r requirements-dev.txt
content-agent --help
mkdir -p .state/inputs examples/test-results
```

实现时 pyproject.toml 提供 content-agent 入口，requirements-dev.txt 锁定测试依赖。
离线模式无需密钥与网络；安装依赖通常需要网络，已安装环境中的离线运行不需要网络。
.env.example 只描述配置，真实 .env、.state/ 和 .venv/ 不提交。

## 2. 准备可复制输入

实施阶段必须提供 examples/inputs 中下表列出的输入及对应合成规则目录。
每次演示将存在的 deadline 更新为未来时间，并将实际运行输入单独保存；
不要给缺少 deadline 的输入补上该字段。

以下仅准备演示数据，不是业务实现代码：

```bash
python - <<'PY'
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
out = Path('.state/inputs')
out.mkdir(parents=True, exist_ok=True)
for p in Path('examples/inputs').glob('*.json'):
    value = json.loads(p.read_text())
    if 'deadline' in value:
        value['deadline'] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    (out / p.name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
PY
```

故意过期、等于边界及模型延迟测试使用注入 Clock 的测试完成，不修改真实运行时钟。
命令中的请求标识在新的状态库中执行；重复完整演示时使用新的状态库或显式换新标识，
避免将复用结果误认为新的执行证据。

## 3. 离线核心验证

```bash
content-agent run --input .state/inputs/normal.json --mode mock --request-id demo-normal --state .state/demo.db --evidence-dir examples/mock/normal
content-agent run --input .state/inputs/budget-replan.json --mode mock --request-id demo-budget --state .state/demo.db --data-dir examples/fixtures/budget-replan --evidence-dir examples/mock/budget-replan
content-agent run --input .state/inputs/tool-failure.json --mode mock --request-id demo-failure --state .state/demo.db --fault generate-once --data-dir examples/fixtures/tool-failure --evidence-dir examples/mock/tool-failure
```

预期：normal 完成且费用 8.00；budget-replan 观察 12.00 超限后改选 8.00，重新估算再保存；
tool-failure 保留素材和首次失败记录，改选可行方式完成，或明确停止并说明原因。
离线路径是确定性流程验证，不能计为真实模型决策证据。

每个 evidence-dir 必须包含实际 input.json、output.json、trace.jsonl、manifest.json；
保存成功时另有 artifact.json。不要把这些文件预先当作已运行材料提交。

## 4. 其他必验收和失败场景

| 输入 / 设置 | 预期结果 | 对应要求 |
| --- | --- | --- |
| missing-budget.json | awaiting_input，列预算，无业务调用 | US2-1、FR-002 |
| missing-deadline.json | awaiting_input，列截止时间，无业务调用 | US2-2、FR-002 |
| missing-both.json | 一次列出两项缺失 | US2-3 |
| insufficient-materials.json | empty 检索后未完成，资料缺口可见 | US2-4 |
| no-feasible.json + fixtures/no-feasible | 仅 premium 可用，预算 10、所需 12、缺口 2 | US3-2 |
| tool-failure.json + generate-always | 未完成或改选后再次失败停止，素材保留 | US4-2 |
| save-failure.json + save-once + max-rounds=5（Mock 固定正常前序） | 第五轮保存失败且额度耗尽，未完成；保留脚本、费用及失败记录 | US4-3 |
| save-failure.json + save-once（默认额度） | 模型选择新尝试保存成功且全部条件满足后可完成，首次失败不被覆盖 | US4-4 |
| partial-result.json + partial-generate | 不把部分生成标为成功；模型补足、改选或停止 | US4-5 |
| limit.json + max-rounds=1 | 首轮后 limit_reached，零额外调用 | US4-6 |

保存失败与部分结果测试必须同时保留失败发生时的状态；若模型后续成功，
最终 completed 不代表最初失败步骤被覆盖。保存失败未恢复与新尝试保存成功必须分别提供记录。
max-rounds=5 用例要求实际第五轮发生保存失败；若动作顺序不同，则不能将未命中保存的额度失败冒充该场景。

示例命令（退出码 2 和 3 分别表示预期的待补充与未完成）：

```bash
content-agent run --input .state/inputs/missing-budget.json --mode mock --request-id demo-missing --state .state/demo.db --evidence-dir examples/mock/missing-budget
content-agent run --input .state/inputs/no-feasible.json --mode mock --request-id demo-no-feasible --state .state/demo.db --data-dir examples/fixtures/no-feasible --evidence-dir examples/mock/no-feasible
content-agent run --input .state/inputs/limit.json --mode mock --request-id demo-limit --state .state/demo.db --max-rounds 1 --evidence-dir examples/mock/limit
content-agent run --input .state/inputs/save-failure.json --mode mock --request-id demo-save-stop --state .state/demo.db --fault save-once --max-rounds 5 --evidence-dir examples/mock/save-failure-stop
content-agent run --input .state/inputs/save-failure.json --mode mock --request-id demo-save-retry --state .state/demo.db --fault save-once --evidence-dir examples/mock/save-failure
```

预期非零业务退出码不应让批量评估脚本中止整个场景集；评估脚本需要记录每次实际退出码。

## 5. 重复执行与产物读取

```bash
content-agent run --input .state/inputs/normal.json --mode mock --request-id demo-normal --state .state/demo.db
content-agent run --input .state/inputs/normal.json --mode mock --request-id demo-normal --state .state/demo.db
content-agent show --request-id demo-normal --state .state/demo.db --view artifact
content-agent show --request-id demo-normal --state .state/demo.db --view trace
content-agent show --request-id demo-normal --state .state/demo.db --evidence-dir examples/mock/normal-reexport
```

两次重复运行均 reused=true，原 run_id、费用和产物不变；不调用模型或工具。
使用同一标识但不同预算或规则版本必须 input_conflict，旧记录保持不变。
实现测试须查询 ledger/artifacts 数量并通过 CLI 子进程复核，而非只比较 stdout。

show --evidence-dir 从同一只读快照重建 input/output/trace/manifest 和已有方案，
不调用模型/业务工具、不读取模型密钥，不增加账本或事件，也不重新判定当下截止时间。
导出失败返回 74，原数据库结果保持不变；再次 show --evidence-dir 可重试完整导出。
show 成功读取或导出返回 0，即使原运行未完成；run 的业务退出码规则不变。

## 6. 真实模型验证

已实测 DeepSeek beta + deepseek-flash。复制 `.env.example` 为本机 `.env`，在本机编辑器填写密钥；评估脚本显式读取三个变量，不执行 shell 内容。主 CLI 仍只读环境变量。以下命令创建未来截止时间和唯一请求，保留全部尝试，不覆盖已有主验收证据（会产生真实模型费用）：

```bash
python scripts/run_real_examples.py --env-file .env --case budget-replan
python scripts/run_real_examples.py --env-file .env --case tool-failure
```

当前两条实际成功路径与前序失败见 [真实验证](../../examples/real/README.md)。其他兼容端点必须另行验证。

核对完整 assistant/tool 消息关联、预算报价和错误确实进入下一轮模型，
并据此出现改选或停止。预算用例必须实际观察到 12→8 两次报价。
如果模型直接选择可行方案、未进入注入工具、服务不可用或路径不满足目标，
只能记录实际观察，不得补写中间步骤；调整材料/提示后使用新请求再次验证，并记录改动。
两条路径未取得前不能声称真实动态决策验收通过。

## 7. 测试、对照与交付

```bash
python -m pytest -q --junitxml=examples/test-results/pytest.xml
```

默认测试不联网；模型协议测试使用模拟 HTTP 响应验证消息与错误语义，
不将其计为真实模型证据。关键断言见 plan.md 的验证策略：
费用精度/历史支出、依赖/部分成功、截止时间边界、最后一轮结束、保存事务、幂等与模型故障。
另须验证：同候选传入不同草稿仍复用；业务条件变化生成新候选并重估；工具模拟 1 分钟后模型等待
5 分钟累计 6 分钟；工具实际 8 分钟/模拟 10 分钟只累计 10 分钟，不重复计算。

实施时 docs/03-evaluation.md 必须为全部验收点列出输入、预期、实际、退出码、
Trace 和测试结果文件；Mock 与真实模型分开给出结论。docs/04-ai-usage.md 记录 AI 生成、
个人改动及验证，docs/05-retrospective.md 记录实际用时、未完成部分和下一步。

最终从干净环境按 README 复现，检查合成资料与日志无真实密钥或隐私，
提交题号、可访问仓库 URL 与最终 commit SHA。当前设计文件不替代上述交付材料。
