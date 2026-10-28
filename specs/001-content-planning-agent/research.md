# Research: 内容任务规划 Agent

**Date**: 2026-10-27
**Scope**: 本文保留设计阶段调研结论；当前实现与运行证据见 [评估](../../docs/03-evaluation.md)，已补充 DeepSeek 两条真实路径；设计阶段的其他候选不视为实测。

## R1. 最小运行栈

- **Decision**: Python 3.12+，CLI 入口；运行时使用 argparse、dataclasses、decimal、sqlite3、
  datetime、urllib.request 等标准库。测试选择 pytest，开发依赖在实现时锁定实际验证版本。
- **Rationale**: 单用户、四类本地工具、默认 12 轮无需 Agent 框架；运行依赖少，
  决策来源与业务守卫可以直接核对。Python 小版本在最终测试记录中写明，不假设评审机器已安装。
- **Alternatives considered**: LangGraph、ADK、AgentScope 能承担运行编排，但本期需要的状态与控制
  已可用少量领域代码表达；HTTP 服务和 Notebook 会扩大入口与部署工作量。
- **Sources**: [argparse](https://docs.python.org/3.12/library/argparse.html)，
  [sqlite3](https://docs.python.org/3.12/library/sqlite3.html)。

## R2. 模型接入与脚本生成

- **Decision**: 一个真实模型适配器，使用 Chat Completions 风格的原生工具调用，
  通过显式配置的 HTTPS endpoint、模型名和密钥请求模型。禁用并行工具调用，关闭隐式重试，
  每次模型请求最多一个动作；执行器继续验证模型输出，不将供应商的结构约束视为业务校验。
- **Rationale**: 模型自行提出检索、估算、生成、保存或结束动作；下一次请求带上实际工具观察。
  generate_script 的 script_draft 来自模型本轮工具参数，工具校验并组装脚本，
  不在业务工具里隐藏第二次模型调用。finish 是控制动作，不计业务费用。
- **Alternatives considered**: 预写决策或 if/else 只能用于明确标记的 Mock；模型 SDK 减少网络代码，
  但新增依赖与默认重试语义；自由文本 JSON 输出需要额外协议恢复，首期不作为第二套接入。
- **Boundary**: 首个接入仅保证已实际验证的供应商和模型组合；相似协议的第三方服务不能直接视为兼容。
  不预填可能过期的模型名。具体消息协议见 [model-and-tools.md](contracts/model-and-tools.md)。
- **Sources**: [Function calling](https://developers.openai.com/api/docs/guides/function-calling)，
  [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。

## R3. 保存、账本与重复执行

- **Decision**: SQLite 是唯一权威状态源。保存方案正文、步骤状态和费用在同一个短事务提交；
  US1 即提供 CLI 完整证据导出，show --evidence-dir 可从原始输入、脱敏配置与历史状态只读重建证据包，
  不调用模型/工具、不新增费用/事件或修改原结果，导出文件只是派生副本。请求标识唯一，费用按 attempt_id 唯一。
- **Rationale**: 避免文件已写但状态提交失败、或收费已计但成果丢失。相同标识和指纹返回既有状态，
  不再调用模型或工具；输入、资料、规则、模式或影响行为的配置变化必须冲突。
- **Alternatives considered**: 纯 JSON 文件更轻，但跨文件原子性需要额外恢复设计；
  数据库与外部文件同时作为权威会形成双写；服务端数据库和队列超出单用户范围。
- **Boundary**: 本期业务工具均无不可撤销的远端副作用；SQLite 不保证真实外部服务恰好执行一次。
  崩溃后不自动续跑，明确恢复为未完成并保留已提交内容。
- **Sources**: [SQLite transactions](https://www.sqlite.org/lang_transaction.html)，
  [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html)。

## R4. 预算、失败与历史成本

- **Decision**: 金额从字符串解析 Decimal，校验有限、非负、最多两位小数；内部存整数百分单位，
  输出固定两位字符串。费用只对有效成功结果入账；失败、拒绝、复用不收费，规则表必须明确。
  预计总费用 = 全部已发生费用 + 当前候选尚需费用。
- **Rationale**: 避免二进制浮点误差与重规划清空历史成本。估算不入账，复用内容不再收费，
  被替换的成功生成仍保留已发生支出。
- **Alternatives considered**: 浮点费用加容差会模糊预算边界；只计算当前方案价格会漏掉历史成本。
- **Sources**: [decimal](https://docs.python.org/3.12/library/decimal.html)。

## R5. 截止时间与决策上限

- **Decision**: 带时区时间转换为 UTC；时钟可在测试中注入，真实入口禁止覆盖 wall clock。
  使用单调时钟统计实际累计时长（包含模型等待），每个工具只补充 max(规则模拟耗时−实际工具耗时, 0)。
  logical_now = started_at + 实际累计时长 + 各工具模拟额外时长之和；
  effective_now = max(wall_now, logical_now)，预计完成 = effective_now + 剩余顺序耗时。
  模型等待与工具耗时顺序累计，工具按实际/模拟较大值累计，不能用两类总时长直接取大导致相互抵消。
  失败/部分结果按失败规则补充模拟耗时，拒绝、复用和 finish 不增加规则耗时，但实际耗时仍被记录。
- **Rationale**: 不必真实等待模拟分钟数，同时真实模型延迟和实际超时仍然影响可行性。
  默认 12 次模型决策，无效输出、网络失败、finish 均占一轮；一轮最多一个业务调用。
  合法 finish 在第 12 轮可以成功；第 12 轮仅保存而未结束时不能增加第 13 次模型请求。
- **Alternatives considered**: 只看 wall clock 会忽略业务耗时；只看模拟时间会忽略真实超时；
  实际累计与模拟累计直接取大则会丢失部分顺序等待；工具实际与规则耗时直接相加又会重复计算。
  自动重试会隐藏额度与费用，故首期不启用；保存失败由模型显式选择重试，记录新尝试并保留首次失败。
- **Sources**: [Aware datetimes](https://docs.python.org/3.12/library/datetime.html)。

## R6. 验证与交付边界

- **Decision**: 使用相同执行器运行真实模型与显式 Mock；离线行为按观察结果确定性选择动作，
  只验证流程。真实模型至少保留预算改选和工具失败改选或停止两条实际路径；
  prompt 只引导先评估偏好方案，不伪造工具结果或保证模型必然走某个预写路径。
- **Rationale**: 真实模型可直接选中便宜方案，因此只能把实际观察到的超预算路径算作对应证据；
  没有取得目标路径时如实记录并继续调整合成材料或提示，不能改写日志冒充命中。
- **Scope decision**: 成功脚本不可原地改写，同一候选重复生成只复用；业务条件变化创建新候选并重新估算。
  首期不增加同条件脚本改写入口。保存失败未恢复时不能完成，显式重试成功且其余条件通过时可以完成，
  失败记录必须保留；两种结果分别验证。
- **Alternatives considered**: 仅断言最终结果不能说明模型是否观察到工具错误；
  固定 Trace 或 Mock 成功不能证明真实模型动态决策。
- **Outcome**: 技术选型、供应商协议、保存原子性、金额、时间和额度语义均已确定，
  无阻塞设计问题。实际模型可用性及真实路径效果保留给实现和评估阶段验证。
