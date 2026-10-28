# Data Model: 内容任务规划 Agent

**Status**: 对应本地实现；已用离线测试验证，实际证据见 docs/03-evaluation.md。
**Requirements**: FR-001–FR-020；[接口](contracts/model-and-tools.md)。

## 1. 领域实体与关系

| 实体 | 主要字段 | 关系与校验 |
| --- | --- | --- |
| Request | request_id、fingerprint、raw_input、input、execution_config、mode、material_digest、rules_digest、config_digest | request_id 唯一；raw_input 保留原始业务输入，execution_config 仅保存脱敏执行配置；主题去首尾空白，预算统一两位，截止时间转 UTC；内容摘要与版本同时参与指纹 |
| Run | run_id、request_id、status、reason_code、started_at、owner_pid/host、rounds_used、max_rounds、simulated_elapsed_seconds、actual_elapsed_seconds、simulation_extra_seconds、logical_now | 一个请求首期仅一轮运行，不自动续跑；max_rounds 为 1–100 的整数，默认 12；耗时非负，logical_now 为带时区 UTC 时间 |
| Candidate | candidate_id、variant、goal、audience、assumptions、material_ids、revision、estimate_id | 业务条件变化时创建新 candidate_id，revision 按请求内新候选顺序递增，旧版本不可原地修改；引用必须来自成功检索；模型声明内容必须与用户事实区分 |
| Step | step_id、kind、candidate_revision、depends_on、status、artifact_ids、reusable | 由领域层根据动作和实际结果建立依赖，不信任模型自报成功 |
| Attempt | attempt_id、step_id、round、action、arguments、status、quality、result、error、duration_seconds | 唯一调用尝试；失败、部分结果和替代尝试分别留存 |
| Material | material_id、version、topic/tags、text | 全部合成；引用必须存在且被检索返回，空结果有明确 observation |
| Rule | version、variant、success_cost_minor、success_duration_seconds、failure_duration_seconds、available | 缺费用或耗时即不可确认可行；失败费用明确为 0；禁用形式不能被选择 |
| Estimate | estimate_id、candidate_revision、rules_digest、required_artifacts、spent_at_quote、remaining_cost_minor、projected_total_minor、remaining_seconds、feasible、violations | 每次估算记录历史；金额和时间由规则计算，不接收模型给定数值 |
| LedgerEntry | attempt_id、request_id、amount_minor、rule_version、artifact_id | 每个成功付费尝试至多一笔；失败、复用、估算不能入账 |
| Artifact | artifact_id、request_id、kind、content、source_ids、candidate_revision、validity | 素材、脚本可位于状态快照；已保存最终方案正文位于 artifacts 表，按请求唯一 |
| Event | run_id、sequence、round、event_type、payload、timestamp、mode | 顺序递增；模型动作、工具观察、状态变化及终态均可关联 |

指纹是规范化 JSON 的 SHA-256，包含所有影响行为的内容：业务输入、可选偏好、资料和规则版本及摘要、
mode、模型标识/endpoint、最大轮数、故障配置与 Mock 策略；不包含 API key、输出目录或请求标识自身。
模型 endpoint 在指纹中使用去除认证信息的规范形式，禁止将密钥放入 URL。
缺失或无效字段以明确的缺失/无效标记参与指纹，不强行解析为合法值。
同一标识补充缺失字段也视为新条件，首期需使用新请求标识。

同一组规范化内容形式、目标、受众、业务假设、素材引用及规则版本/摘要对应同一候选身份。
再次估算同一候选只新增 Estimate，不增加候选 revision；业务条件变化才创建新候选版本。
同一候选已有成功脚本时，再次 generate_script 只复用原产物，模型传入不同草稿也不覆盖它。
首期不支持业务条件不变时的脚本改写，失败或部分生成尚未形成成功脚本时仍可重新尝试。

## 2. 存储设计

一个状态库，四张表；具体建表语句在实施阶段编写：

| 表 | 主键/唯一约束 | 权威内容 |
| --- | --- | --- |
| requests | request_id PRIMARY KEY；run_id UNIQUE | 指纹、所有领域快照、当前结果、进程归属、计数与费用摘要 |
| events | (run_id, sequence) PRIMARY KEY | 不可改写的决策、观察和状态事件 JSON |
| ledger | attempt_id PRIMARY KEY | 成功实际费用明细，以整数百分单位存储 |
| artifacts | artifact_id PRIMARY KEY；request_id UNIQUE | 最终保存方案正文及校验摘要 |

- 请求认领以短写事务和唯一约束实现；相同指纹读取原记录，不启动新模型请求。
- 每轮模型请求前提交额度消耗；模型调用期间不持有写事务。
- 工具尝试先持久化 running，再执行本地计算；结果、费用、事件和状态在单次事务提交。
- save_plan 的最终方案正文、保存成功状态、费用和引用必须在同一事务提交。
  保存注入故障在该事务提交前发生，任何失败均不产生成功保存记录。
- SQLite 为唯一权威。`artifacts/<id>` 是状态库内逻辑位置，必须通过 show 读取；
  文件导出是派生副本，导出失败不得破坏数据库中的已有结果。
- 初次执行保存 raw_input、脱敏 execution_config、结果、事件与已有方案，支持后续仅从状态库重建证据包。
  show 导出不得追加事件、更新时间、重算历史费用或重新检查当下截止时间，原始运行记录保持不变。
- 首期没有远端业务副作用；不能把这套事务保证推广成外部工具的恰好执行一次。

## 3. 状态转换

运行状态：

- 新请求 → `awaiting_input`：一次列明输入问题，不调模型或业务工具。
- 新请求 → `running`：输入有效、成功认领，开始模型循环。
- `running` → `completed`：模型 finish(completed)，且保存、依赖、预算、时间等全部验证通过。
- `running` → `incomplete`：模型主动停止、模型服务失败、调用额度耗尽、不可恢复错误或进程中断。
- `input_conflict` 是重复提交的返回状态，不修改原请求的状态、产物和费用。
- `completed`、`incomplete`、`awaiting_input` 均为本期不可自动续跑的终态；重复提交只读取。

步骤状态：`pending → running → succeeded | failed`；未执行且不再需要的步骤为 `skipped`。
部分成功表示 `status=failed, quality=partial` 并保留可用内容和缺口，不将其计为成功或收费。
替代步骤使用新 step_id 和 attempt_id，引用可复用的成功前置结果。
成功的旧步骤保持成功历史；`reusable=false` 表示候选变化后不再适用，不能篡改其实际状态。

保存成功后只允许 finish；拒绝继续修改或重新保存，以保证一个请求只有一份最终保存产物。
保存失败且尚未产生最终产物时，模型可在剩余额度内选择重新保存；新尝试使用新 attempt_id，
原失败尝试保持 failed。重试成功且其余条件满足时允许 completed；停止或额度耗尽则 incomplete。
finish 的完成条件未满足时返回 rejected observation；允许在剩余额度中修正，
但不能通过模型一句“成功”绕过守卫。

崩溃后保留已提交的成功结果。显式 recover 仅在同一主机、已确认 owner_pid 不存在时，
将 running 尝试记为 failed（error=interrupted）、运行改为 incomplete，不重新调用工具或补记未提交费用。
进程存活或无法确认时拒绝恢复；不实现跨主机恢复、自动续跑或 PID 复用的自动判断。

## 4. 金额不变量

- 对输入直接构造 Decimal，拒绝非有限、负数或超过两位小数；不静默四舍五入。
- 持久化 `minor = amount × 100` 的整数；输出两位小数字符串，禁止 JSON 浮点参与金额计算。
- `spent_total = sum(ledger.amount_minor)`；重新规划、失败、产物失效都不能删除账本。
- `projected_total = spent_total + remaining_cost(candidate, reusable_artifacts)`。
- 估算不是支出；有效成功结果才入账；同一 attempt_id 不重复记账。
- 每个付费动作前，根据当前账本重新计算候选剩余总费用；此前存在可行估算并不豁免重新检查。
- 例：历史花费 3、剩余 8、预算 10，应拒绝预计总费用 11；不能用剩余费用代替总费用。
- 等于预算允许通过；费用未知必须返回 unknown_cost，不能假定零费用。

## 5. 时间不变量

- 输入为带时区的绝对时间，内部使用 aware UTC datetime；不从测试输入覆盖真实时钟。
- 首期顺序执行。工具耗时在 rules 中以整数秒保存，界面与记录可显示分钟。
- 使用可注入的单调时钟测量实际时长；运行开始时记录 monotonic_started，起始 logical_now 为 started_at。
- `actual_elapsed_seconds = clock.monotonic() - monotonic_started`，包含模型等待、工具实际执行及其他实际处理时间。
- 每次实际执行工具结束后，`simulation_extra_seconds += max(0, rule_duration_seconds - actual_tool_elapsed_seconds)`。
  rule_duration_seconds 按成功/失败规则选取；部分生成采用失败耗时。模拟额外耗时只在该尝试结算时加一次。
- `logical_now = started_at + timedelta(seconds=actual_elapsed_seconds + simulation_extra_seconds)`。
- `effective_now = max(clock.now_utc(), logical_now)`。
- `estimated_finish = effective_now + remaining_seconds(candidate, reusable_artifacts)`。
- simulated_elapsed_seconds 单独累计各次已执行工具的规则耗时，用于审计，不能再直接代替 logical_now。
  模型等待按实际时长累计，工具按实际耗时与规则模拟耗时的较大值累计；两者顺序相加，不相互抵消。
  校验拒绝、复用和 finish 不增加规则模拟耗时，但其实际处理/模型等待时间仍计入实际时长。
- 模型响应后、付费动作前、保存前及 finish 前重新检查时间。保存动作完成后也校验截止时间；
  超时产物仍保留，但不得报告按期 completed。
- 等于截止时间允许通过，晚于截止时间返回约束违反。历史耗时不得因改选清零。
- 例：已执行工具模拟 1 分钟、实际耗时为 0，随后模型等待 5 分钟，逻辑累计为 6 分钟。
  工具实际耗时 8 分钟、规则耗时 10 分钟时，该工具累计 10 分钟，不是 18 分钟。

## 6. 执行额度、协议与幂等

每次请求模型前先增加 rounds_used，Mock 采用同一口径；finish、无效输出、服务错误各占一轮。
每轮最多一个业务调用；无自动模型或工具重试。HTTP 超时/协议不可解析直接 incomplete，
可关联到单一 tool_call 的参数或动作错误则回传 rejected，让模型在剩余轮数内修正。

先处理当轮合法结束动作，再检查额度：第 12 轮合法 finish 可以完成；
第 12 轮仅保存且尚无合法 finish 时返回 limit_reached，保留保存产物，不发第 13 次模型请求。

相同 request_id 与指纹：终态返回原结果，`reused=true`；running 返回当前进度，业务执行次数为 0。
不同指纹：返回 input_conflict，原记录不变。新 request_id 是新业务请求，允许再次规划及发生费用。

## 7. Trace 与结果

Trace 导出为 JSONL，包含 `schema_version`、run/request 标识、mode、round、sequence、
模型 assistant 动作、工具参数与关联 ID、observation、费用和状态变化，以及公开 decision_summary。
下一轮动作通过对应 round 和 observation sequence 关联；终态事件说明最终结果或剩余工作。
保留执行所需的模型消息与工具观察，删除认证头，不保存模型内部思维过程。

结果包含当前计划、全部步骤/尝试、可复用成果、预算及已花/剩余估算、时间校验、
保存位置、模式、计数、原因、缺口、remaining_work、原始 Trace 引用与复用标记。
缺口仅根据已估算或完整枚举的可用形式报告；缺少依据时为 null 并注明未知。
