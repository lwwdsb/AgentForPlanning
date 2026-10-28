# CLI Contract: content-agent

**Version**: 1.0.0（已实现；真实端点/模型组合尚未实测）
**Related**: [数据模型](../data-model.md)、[模型与工具](model-and-tools.md)。

## 命令

```text
content-agent run --input FILE --mode mock|real
  [--request-id ID] [--state .state/content-agent.db] [--data-dir data]
  [--max-rounds 12] [--fault none] [--evidence-dir DIR]
content-agent show --request-id ID [--state .state/content-agent.db]
  [--view result|trace|artifact] [--evidence-dir DIR]
content-agent recover --request-id ID [--state .state/content-agent.db]
```

- mode 必须显式给出；不推断、不回退。request-id 缺省生成 UUID 并在结果中返回。
- max-rounds 是 1–100 的整数，默认 12；测试上限由此控制，不通过隐藏环境变量修改。
- fault 仅用于合成业务工具测试：none、generate-once、generate-always、save-once、partial-generate。
  故障设定进入请求指纹、输出和 Trace，不能对评审隐瞒。一次失败按请求中的工具调用次数定义，
  重复同一请求不重置故障计数。
- data-dir 包含 materials.json 和 rules.json；使用规则内容摘要及版本判断是否能复用。
- run 的 stdout 仅包含一份结果 JSON；诊断写 stderr。show trace 输出 JSONL，
  show artifact 输出方案 JSON，show result 输出结果 JSON。
- evidence-dir 可选，创建 input.json、output.json、trace.jsonl、manifest.json，
  有保存方案时增加 artifact.json。manifest 记录模式、配置、规则摘要、输出校验摘要及运行时间。
  文件由实际状态导出，不能预先生成“实际输出”。
- show --evidence-dir DIR 只从状态库读取原始输入、脱敏配置、历史结果、Trace 和方案重建完整证据包；
  --view 仅选择 stdout 视图，默认 result，与证据包导出独立。不得调用模型/业务工具、读取模型密钥、
  新增费用/事件、修改状态/历史时间或根据当前截止时间重新判定原结果。
  终态或进行中结果都可导出，进行中材料必须标明为该时刻快照，不冒充最终结果。
- 导出失败写 stderr 并返回 74，stdout 仍可给出已提交的业务结果；
  run 的结果可附临时 evidence_export_error，不写回数据库。show 保持所选 stdout 视图不变，
  错误只写 stderr。再次 show --evidence-dir DIR 可重试完整导出而不重复业务工具。
  show 导出成功返回 0，不沿用原运行的业务退出码；完整证据包以同一只读快照生成，避免字段间混入不同状态。
- recover 只在确认原进程不存活时标记 interrupted，不执行续跑；具体限制见数据模型。

## 业务输入

```json
{
  "theme": "校园读书周",
  "budget": "10.00",
  "deadline": "2030-06-01T18:00:00+08:00",
  "preferred_variant": "standard"
}
```

- theme：非空字符串；budget：非负、有限、最多两位小数的十进制字符串。
- deadline：带 UTC 偏移量的绝对时间；不提供默认值。示例时间仅展示格式，实际运行时选择未来时间。
- preferred_variant 可选，默认 premium，仅作为内容形式偏好，不能覆盖预算和时间约束。
- 未知字段、非法金额、无时区时间均列为输入问题。缺 budget/deadline 的 JSON 仍可进入业务校验，
  一次返回全部问题，而不是由参数解析器先终止。
- 缺失/无效输入不调用模型或业务工具；可以创建 awaiting_input 结果供审阅。
  补充后用新请求标识提交，不修改原记录。

## 结果结构

```json
{
  "schema_version": "1.0.0",
  "request_id": "demo-normal",
  "run_id": "由运行时生成",
  "mode": "mock",
  "status": "completed",
  "reused": false,
  "reason_code": null,
  "input_issues": [],
  "plan": {},
  "steps": [],
  "attempts": [],
  "tool_results": [],
  "costs": {
    "budget": "10.00",
    "spent_total": "8.00",
    "remaining_estimate": "0.00",
    "projected_total": "8.00",
    "budget_gap": "0.00"
  },
  "time": {
    "deadline_utc": "2030-06-01T10:00:00Z",
    "estimated_finish_utc": "实际计算",
    "simulated_elapsed_seconds": 720,
    "actual_elapsed_seconds": 0,
    "simulation_extra_seconds": 720,
    "logical_now_utc": "实际计算",
    "deadline_met": true
  },
  "execution": {"rounds_used": 6, "max_rounds": 12},
  "saved_plan": {"artifact_id": "由运行时生成", "state_path": ".state/content-agent.db"},
  "remaining_work": [],
  "trace_ref": {"run_id": "由运行时生成"},
  "evidence_export_error": null
}
```

此结构示例不是执行证据。正式结果中 plan、steps、attempts、tool_results 必须包含实际内容，
时间和轮次必须取自运行；不得直接复制本示例值。
无保存结果时 saved_plan=null；未知预算或缺口用 null，并给出原因。
status 可取 awaiting_input、running、completed、incomplete、input_conflict。
复用返回原 run_id、原计数、原费用和 reused=true，不假造新运行记录。

## 原因码与退出码

| 场景 | status / reason_code | 退出码 |
| --- | --- | --- |
| 已完成或复用完成结果 | completed / null | 0 |
| 输入缺失或无效 | awaiting_input / input_required 或 invalid_input | 2 |
| 未完成 | incomplete / budget_exceeded、deadline_exceeded、insufficient_materials、tool_failed、limit_reached、model_error、interrupted 或 stopped | 3 |
| 仍在执行的重复请求 | running / in_progress | 3 |
| 同一标识条件变化 | input_conflict / request_conflict | 4 |
| 参数语法、文件格式错误、配置缺失 | 有结构化诊断；不发起模型请求 | 64 |
| show/recover 找不到请求 | 诊断 not_found | 66 |
| 未预期内部错误 | 尽可能记录 incomplete/internal_error 并保留已提交成果 | 70 |
| 输出文件导出失败 | evidence_export_error | 74 |

show 成功读取或导出时返回 0，即使所读历史运行是 incomplete 或 awaiting_input；
run 的状态退出码规则保持不变。show --view artifact 在无保存方案时返回 not_found/66。

业务输入缺失与文件损坏不同；前者必须返回待补充，后者属于无法解析输入。
recover 对仍存活或无法确定状态的进程返回 64，不修改运行。

## 环境与安全边界

- 业务输入检查先于真实模型配置检查；缺预算或截止时间仍应返回 awaiting_input。
- real 模式需要 MODEL_ENDPOINT（完整 HTTPS Chat Completions URL）、MODEL_NAME、MODEL_API_KEY。
- mock 模式不读取密钥且不联网；真实配置缺失必须明确报错，不自动变为 mock。
- .env.example 只声明变量，首期不自动加载 .env；使用 shell 环境传入真实值。
- 模型密钥不进入请求 JSON、指纹、Trace、manifest、错误摘要或命令行参数。
- .state/、.venv/、真实 .env 均忽略提交；提交 examples 中经过检查的合成结果和脱敏模型消息。
