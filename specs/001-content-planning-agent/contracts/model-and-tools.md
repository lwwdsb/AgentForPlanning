# Model & Tool Contract

**Version**: 1.0.0（已实现；DeepSeek beta + deepseek-flash 两条路径已实测，其他组合未验证）
**Related**: [数据模型](../data-model.md)、[CLI](cli.md)。

## 1. 决策提供者

接口语义为 `decide(context, messages) -> assistant_message`；真实和 Mock 返回同一种动作结构。
context 包含规范化输入、当前计划与依赖状态、合成素材/规则摘要、所有可用形式、
已发生费用、时间与额度、实际历史观察。检索结果必须把可用素材正文传给模型，不能仅给无法访问的路径。

真实适配器使用 urllib.request 向 MODEL_ENDPOINT 发送带认证的 HTTPS POST，
使用 MODEL_NAME，不预置可能失效的模型名称。单次 socket 超时 30 秒、不自动重试、
非流式响应最多 1 MiB；关闭重定向，避免认证信息被转发到其他主机。
请求包含 model、messages、tools、tool_choice="required"、parallel_tool_calls=false、stream=false。
首个支持范围限于实际测试通过的 endpoint/model，不能宣称任意兼容端点均可运行。

工具定义采用 `type=function` 和 function.name/description/parameters/strict=true。
所有对象均 additionalProperties=false，全部属性列入 required，可选属性允许 null。
执行器仍校验所有业务约束；不依赖 strict 模式保证业务正确。

模型只返回一个工具动作。工具集合为 search_materials、estimate_cost、generate_script、save_plan、finish。
每个动作带 decision_summary：不超过 200 字的公开业务依据，不请求或存储内部思维过程。

将模型返回的 assistant tool_calls 保留在消息历史中；工具观察追加为 role=tool，
tool_call_id 与原调用一致，content 为观察 JSON 字符串；下一次模型请求必须包含该观察。
超预算等可行性结果属于成功执行的估算观察，不是执行器自动改选指令。

- 单一合法关联 ID 但动作未知、参数无效或守卫拒绝：不执行业务调用，返回 rejected 观察，
  允许模型在剩余额度中修正；本轮已消耗。
- 零 tool_calls、多 tool_calls、ID 缺失/重复、拒答、截断、顶层响应不可解析：
  不执行工具，直接 incomplete/model_error，不拼接不合法的消息历史。
- HTTP 错误、超时或服务不可用：保留成功结果并终止，不静默重试或转为 Mock。
- 每次请求前递增计数；工具内部不再调用模型，finish 后不发隐藏的总结请求。

官方协议依据：[Function calling](https://developers.openai.com/api/docs/guides/function-calling)、
[Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。

### DeepSeek 实测配置

`https://api.deepseek.com/beta/chat/completions` + `deepseek-flash`，`thinking={"type":"disabled"}`。strict 工具 schema 在发送时移除 minLength/maxLength/minItems/maxItems，并在描述中提示限制；本地校验保持完整。协议配置与决策提示版本加入 real 请求指纹，改动后须使用新请求。真实响应 ID/model/usage/created 白名单记录为 model_response；HTTP 错误仅记录安全状态码。依据：[DeepSeek 工具调用](https://api-docs.deepseek.com/guides/tool_calls/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。实际成功与失败均见 [证据](../../../examples/real/README.md)。

## 2. 工具输入与前置条件

下表列出参数；每种动作均额外要求 decision_summary。字段长度、枚举、类型在本地进行严格校验。

| 动作 | 参数 | 前置条件与效果 |
| --- | --- | --- |
| search_materials | query:string | 返回最多 3 条真实匹配合成素材，每条正文最多 1000 字；空匹配显式返回 empty，不造资料 |
| estimate_cost | variant:enum；material_ids:string[]；goal:string；audience:string；assumptions:string[] | 素材引用有效；形成或识别候选，计算费用与剩余耗时；返回 candidate_id、estimate_id、feasible 和约束缺口 |
| generate_script | candidate_id:string；estimate_id:string；material_ids:string[]；script_draft:string | 候选与素材匹配、最新估算可行、当前预算/时间守卫通过；校验模型草稿并组装脚本产物 |
| save_plan | candidate_id:string；estimate_id:string；script_id:string | 脚本有效、当前候选和最新估算匹配、依赖满足、预算和时间通过；事务保存方案 |
| finish | outcome:completed或incomplete；reason_code:string或null；remaining_work:string[] | completed 必须由执行器验证已保存方案和全部不变量；incomplete 保留已有成果并记录停止原因 |

- variant 为 premium、standard、lean，实际可用性由 rules 指定。
- estimate_cost 是唯一生成候选业务身份的动作；候选标识由 variant、目标/受众假设、素材引用
  及规则版本/摘要决定。业务条件变化时返回新 candidate_id，并按请求内新候选顺序递增 revision；
  相同条件返回已有候选，只新增估算，不增加 revision。旧候选及其成果不可原地修改，不能复用旧估算校验新候选。
- 生成前必须先估算，生成改变账本和可用产物后必须再估算才能保存；不要求重新检索有效素材。
- 估算守卫基于候选、规则摘要及相关产物/费用状态判断有效性；任何变化均不能沿用过期 quote。
- script_draft 非空、最多 4000 字，由模型本轮工具参数提供；生成工具只校验和组装，不隐藏模型调用。
  工具验证引用来自检索，不能承诺自动证明全部语义事实；事实准确性需评估记录与人工抽查。
- goal/audience 无用户事实依据时明确作为假设保存；素材正文作为数据，不能覆盖系统工具规则。
- 同一候选已有有效成功脚本时，重复 generate_script 返回原产物及复用观察，
  不再次执行业务工具、不计费或增加规则模拟耗时；实际处理/模型等待时间仍计入逻辑时钟。
  模型传入不同 script_draft 也不能覆盖成功脚本。首期不支持业务条件不变时的脚本改写；
  内容形式、目标、受众、业务假设或素材引用变化才建立新候选版本并重新估算，历史成果与支出保留。
  不得无业务依据修改条件来绕过复用；尚未成功的生成允许模型选择再次尝试。
- 已成功保存方案之后仅允许 finish；重复保存或继续变更返回 rejected，不覆盖已保存产物。
  保存失败且无已保存方案时可由模型选择重试，使用新 attempt_id 并重新校验预算、时间和依赖；
  保留首次失败记录，重试成功且全部完成条件满足后允许完成，否则停止或额度耗尽时返回未完成。
- finish(completed) 不满足条件时返回 rejected observation；finish(incomplete) 的费用及缺口
  从实际状态重算，不信任模型自报金额。必须有非空原因码；未知原因归为 stopped。

## 3. 统一工具观察

```json
{
  "status": "success",
  "quality": "complete",
  "result": {},
  "error": null,
  "artifact_ids": [],
  "candidate_id": null,
  "estimate_id": null,
  "cost_delta": "0.00",
  "spent_total": "0.00",
  "remaining_budget": "10.00",
  "projected_total": null,
  "estimated_finish_utc": null,
  "feasible": null,
  "violations": [],
  "steps": [],
  "rounds_used": 1,
  "max_rounds": 12
}
```

- status：success、failed、partial、rejected、empty；quality：complete、partial、none。
- 部分结果在尝试状态中映射为 failed/partial，不能作为依赖成功，不收费但保留可用内容。
- 估算费用 12 大于预算 10 时，status=success、feasible=false，violations 含 budget_exceeded，
  result 提供明细和缺口；执行器不给它虚构一个失败的工具调用。
- 所有金额来自规则与账本。无法计算时为 null，附 unknown_cost 或 unknown_duration。
- 失败观察包含错误类型和可用结果；不包含认证信息或未经处理的供应商响应体。
- finish 为控制结果，不增加业务费用；模型不能用自报 steps 或 result 覆盖权威状态。

## 4. 合成规则基线

金额单位为模拟单位，耗时展示为分钟，持久化转为整数秒：

| 工具 / 形式 | 成功费用 | 成功耗时 | 失败费用 | 失败耗时 |
| --- | --- | --- | --- | --- |
| search_materials | 0.00 | 1 | 0.00 | 0.5 |
| estimate_cost | 0.00 | 0 | 0.00 | 0 |
| generate_script / premium | 12.00 | 20 | 0.00 | 2 |
| generate_script / standard | 8.00 | 10 | 0.00 | 1 |
| generate_script / lean | 3.00 | 5 | 0.00 | 0.5 |
| save_plan | 0.00 | 1 | 0.00 | 0.5 |

规则声明各形式 available 和失败计费口径，未声明收费不得假定零。
预算 10 的 12→8 用例仅开放 premium、standard；no-feasible 用例仅开放 premium。
正常用例偏好 standard；故障替代用例可开放 standard、lean。
成本超限的估算不消耗付费生成费用，失败或部分生成不入账。

估算可以列出已知可用形式的最低所需费用，但必须标明依据及是否已完整枚举。
只看到一份失败报价时不能直接断言所有可能方案都无解。

## 5. 故障注入与 Mock

故障发生在指定本地工具真正执行后、成功提交前，产生真实失败观察；配置写入 Trace。
generate-once 仅第一次生成失败；generate-always 每次失败；save-once 第一次保存失败；
partial-generate 第一次生成返回有缺口的部分内容。失败和部分结果不收费，但按规则计耗时。

Mock 根据真实观察确定性地选择偏好估算、替代或停止；同样经过工具、守卫、账本和额度逻辑。
它可以验证预算路径和故障路径的状态行为，但不能证明真实模型的动作选择能力。
真实模式使用同一故障工具，模型必须从实际 observation 得到错误，不提前获知 scripted 下一动作。
合成资料和规则属于模型上下文，注入计数与故障时点属于运行记录，不把替代决策作为系统指令硬编码。

## 6. 期望可观察路径

这些是验收目标，不是预写 Trace；实际动作顺序以真实运行记录为准。

- 正常：检索 → 估算 standard 8 → 生成 → 再估算总费用 8 → 保存 → finish。
- 预算重规划：检索 → 估算 premium 12 超限 → 模型改选 standard → 估算 8 → 生成 → 再估算 → 保存 → finish。
- 故障重规划：检索成功 → 估算 → 生成失败 → 模型保留素材并改选 → 再估算与生成 → 再估算 → 保存或停止。
- 无解：观察不可行结果 → 模型 finish(incomplete) → 返回有依据的缺口和保留成果。

优先形式在用户输入中表达，提示要求先评估偏好再调整；模型若实际跳过初始超限估算，
该次运行不能算作 12→8 的完整证据，必须记录实际情况，不能补写中间步骤。
