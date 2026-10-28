# 评估与交付状态

离线业务功能与模型协议夹具测试通过。用户随后提供 DeepSeek 配置，已取得两条真实观察驱动路径：预算 12→8，以及生成失败后改选 lean。累计保留 9 次实际尝试；独立审查后已修复依赖来源与交付范围问题，当前两条主验收路径均为 content-planning-v5。真实结果仅证明这些运行的决策行为，不代表任意输入的可靠性或正文可直接发布。

本机 Python 3.12.12，运行时仅标准库。默认测试 **133 项通过，0 失败/错误，4.559 秒**；[原始结果](../examples/test-results/pytest.xml)。干净环境同样 133 项通过，4.599 秒；[干净测试](../examples/test-results/clean-pytest.xml)、[安装/运行记录](../examples/test-results/clean-reproduction.json)。报告仅删除 hostname 元数据。

13 个实际 CLI 场景中最长 0.100 秒，满足本机离线单请求 2 秒目标；测试集低于 30 秒目标。这是当前环境实测，不代表所有机器或真实模型的性能保证。每次命令及实际退出码见 [场景记录](../examples/test-results/scenario-runs.json)。

## 实际场景

所有下表材料均为 `mode=mock`，由 `scripts/run_examples.py` 调用公开 CLI 产生。每个目录含 input.json、output.json、trace.jsonl、manifest.json、execution.json；成功保存另有 artifact.json。manifest 校验核心文件，执行命令报告为补充。

| 场景 | 预期 | 实际状态 / 费用 / 退出码 | 输入与输出 | Trace |
|---|---|---|---|---|
| normal | 完成，8.00，6 轮 | completed / 8.00 / 0 | [输入](../examples/mock/normal/input.json) · [输出](../examples/mock/normal/output.json) | [Trace](../examples/mock/normal/trace.jsonl) |
| missing-budget | 缺预算，零调用 | awaiting_input / 0.00 / 2 | [输入](../examples/mock/missing-budget/input.json) · [输出](../examples/mock/missing-budget/output.json) | [Trace](../examples/mock/missing-budget/trace.jsonl) |
| missing-deadline | 缺截止时间，零调用 | awaiting_input / 0.00 / 2 | [输入](../examples/mock/missing-deadline/input.json) · [输出](../examples/mock/missing-deadline/output.json) | [Trace](../examples/mock/missing-deadline/trace.jsonl) |
| missing-both | 同时列两项缺失 | awaiting_input / 0.00 / 2 | [输入](../examples/mock/missing-both/input.json) · [输出](../examples/mock/missing-both/output.json) | [Trace](../examples/mock/missing-both/trace.jsonl) |
| insufficient-materials | 检索 empty 后停止 | incomplete / 0.00 / 3 | [输入](../examples/mock/insufficient-materials/input.json) · [输出](../examples/mock/insufficient-materials/output.json) | [Trace](../examples/mock/insufficient-materials/trace.jsonl) |
| budget-replan | 12 超限后改选 8，重估保存 | completed / 8.00 / 0 | [输入](../examples/mock/budget-replan/input.json) · [输出](../examples/mock/budget-replan/output.json) | [Trace](../examples/mock/budget-replan/trace.jsonl) |
| no-feasible | 仅 12 可用，缺口 2 | incomplete / 0.00 / 3 | [输入](../examples/mock/no-feasible/input.json) · [输出](../examples/mock/no-feasible/output.json) | [Trace](../examples/mock/no-feasible/trace.jsonl) |
| tool-failure | 一次生成失败后替代，保留检索 | completed / 3.00 / 0 | [输入](../examples/mock/tool-failure/input.json) · [输出](../examples/mock/tool-failure/output.json) | [Trace](../examples/mock/tool-failure/trace.jsonl) |
| tool-failure-stop | 持续失败，未完成且不收费 | incomplete / 0.00 / 3 | [输入](../examples/mock/tool-failure-stop/input.json) · [输出](../examples/mock/tool-failure-stop/output.json) | [Trace](../examples/mock/tool-failure-stop/trace.jsonl) |
| save-failure-stop | 第 5 轮保存失败，耗尽额度 | incomplete / 8.00 / 3 | [输入](../examples/mock/save-failure-stop/input.json) · [输出](../examples/mock/save-failure-stop/output.json) | [Trace](../examples/mock/save-failure-stop/trace.jsonl) |
| save-failure | 模型显式重试保存，首次失败保留 | completed / 8.00 / 0 | [输入](../examples/mock/save-failure/input.json) · [输出](../examples/mock/save-failure/output.json) | [Trace](../examples/mock/save-failure/trace.jsonl) |
| partial-result | 首次 failed/partial，替代后完成 | completed / 3.00 / 0 | [输入](../examples/mock/partial-result/input.json) · [输出](../examples/mock/partial-result/output.json) | [Trace](../examples/mock/partial-result/trace.jsonl) |
| limit | 1 轮上限，无额外调用 | incomplete / 0.00 / 3 | [输入](../examples/mock/limit/input.json) · [输出](../examples/mock/limit/output.json) | [Trace](../examples/mock/limit/trace.jsonl) |

重复执行证据：[已完成请求重复两次](../examples/mock/repeat/normal/results.json)、[未完成请求重复两次](../examples/mock/repeat/no-feasible/results.json)。前后 requests/events/ledger/artifacts 数量完全相同，原 run_id 和费用保持不变。修改预算后的 [冲突结果](../examples/mock/repeat-conflict/output.json) 返回 4，未产生新 Trace；[调用与数量](../examples/mock/repeat-conflict/execution.json) 指向原 normal 记录。

[normal-reexport](../examples/mock/normal-reexport/manifest.json) 与 normal 的五个核心文件逐字节相同；show 读取不写状态、不重新核验当前截止时间。导出失败 74、三种 stdout 视图、进行中快照和只读重试另由 CLI 测试覆盖。

## 真实模型路径与改进

模型为 `deepseek-flash`，完整端点为 `https://api.deepseek.com/beta/chat/completions`，非 thinking、原生 strict tool calling、每轮一个动作、最多 12 轮。详见 [全部运行与协议依据](../examples/real/README.md)、[机器可读汇总](../examples/real/summary.json)。日期为洛杉矶 2026-10-27，原始 Trace 使用 UTC 2026-10-28。

| 真实路径 | 预期与实际 | 退出码 / 轮次 / 实测耗时 | 证据 |
|---|---|---|---|
| 预算改选 | premium 12.00 超预算 → standard 8.00 → 生成、同候选重估、保存、结束；实际支出 8.00 | 0 / 7 / 13.83 秒 | [输入](../examples/real/content-planning-v5/budget-replan/input.json) · [输出](../examples/real/content-planning-v5/budget-replan/output.json) · [Trace](../examples/real/content-planning-v5/budget-replan/trace.jsonl) · [方案](../examples/real/content-planning-v5/budget-replan/artifact.json) |
| 生成失败 | standard 注入一次失败 → 模型估算 lean 3.00 → 生成、重估、保存；原 failed 与检索结果保留，失败不收费 | 0 / 8 / 15.71 秒 | [输入](../examples/real/content-planning-v5/tool-failure/input.json) · [输出](../examples/real/content-planning-v5/tool-failure/output.json) · [Trace](../examples/real/content-planning-v5/tool-failure/trace.jsonl) · [方案](../examples/real/content-planning-v5/tool-failure/artifact.json) |

第一次预算运行虽发生 12→8，但生成后使用旧报价保存被拒；随后把流程状态写入 assumptions，产生新候选，模型停止且剩余工作描述错误地把缺口归给保存。执行器的 16.00 预计总额实际来自历史支出 8 + 新候选生成 8，保存费用仍为 0；不能采用模型的错误费用解释。原始记录见 [首次输出](../examples/real/attempts/real-budget-replan-20261028T050939Z-5f14f5/output.json)。增加“重估保持业务字段相同”的提示及成功工具观察中的精确参数后，下一次预算路径完成（策略 v2）。

第一次故障运行由模型显式重试同一候选后完成，费用 8.00；不是执行器自动重试，但不满足已批准 US4 的替代形式路径，因此 acceptance_path_passed=false。见 [首次故障输出](../examples/real/attempts/real-tool-failure-20261028T051100Z-d8590f/output.json)。按规格增加通用的“失败后优先评估其他可用形式”提示，下一次模型自行选 lean 完成（策略 v3）。首次验收的预算证据是 v2、故障证据是 v3；这些历史文件保留。审查修复后另取得同一 v5 提示/schema/实现摘要的两条真实路径，当前表格引用 v5。

首次四次运行有 29 份模型响应元数据。加上修复阶段共保留 9 次尝试、60 次模型请求、59 份有效响应元数据；v5 首次预算运行因非单一工具响应停止、费用为零，随后新请求通过。已记录 total_tokens 合计 594958，缺少该无效响应的 usage，也包含重复上下文与缓存，不能作为完整货币账单。没有可靠性统计或跨模型比较。两条实际路径满足本次动态决策证据要求；边界场景继续由明确标记的离线测试覆盖。

## 全部需求与成功标准映射

“离线通过”仅指执行器/协议/文档对应行为已验证，不扩大为真实模型质量或个人能力结论。下表是需求关联覆盖，不是代码行覆盖率。

| 要求 | 验证与证据 | 结论 |
|---|---|---|
| FR-001 | tests/test_cli.py：正常 run、UUID、输入格式；normal | 离线通过 |
| FR-002 | test_invalid_input_precedes_real_config；missing-* | 离线通过 |
| FR-003 | data/materials.json、data/rules.json；test_configuration_changes_conflict | 通过 |
| FR-004 | test_normal_run、test_no_materials_observed_before_stopping、test_generation_failures_preserve_success | 离线通过 |
| FR-005 | test_saved_plan_has_dependencies_and_cost_detail、test_dependencies_follow_all_actual_material_producers；normal/artifact.json 与两个依赖修复反例 | 离线通过 |
| FR-006 | 协议测试；real/content-planning-v5 下 budget-replan 与 tool-failure 的 decision/observation/model_response 事件 | 协议与两条实际循环通过 |
| FR-007 | Mock 三类调整；真实 budget-replan、tool-failure | 预算与故障真实调整通过；partial 仅离线 |
| FR-008 | test_invalid_params_and_unmet_dependencies_are_observations、test_cannot_finish_without_save | 离线通过 |
| FR-009 | generation/save 故障测试、test_repeat_failure_or_progress_subprocess | 离线通过 |
| FR-010 | test_old_success_not_advertised_as_reusable_for_new_candidate、保存重试测试 | 离线通过 |
| FR-011 | test_decimal_money、test_history_spend_and_boundary、test_generation_reused_does_not_execute_or_charge_again | 离线通过 |
| FR-012 | test_unknown_rules_never_assumed_zero、历史 3+8>10、失败费用测试 | 离线通过 |
| FR-013 | test_budget_12_to_8、test_no_feasible_gap；真实 budget-replan | 12→8 实测通过；无解仅离线 |
| FR-014 | test_exact_deadline、test_time_causes_model_alternative、模型等待及工具实际耗时测试 | 离线通过 |
| FR-015 | test_candidate_identity_script_immutability_and_stale_quote、test_time_after_save_can_prevent_completion_preserving_artifact | 离线通过 |
| FR-016 | test_limit_finish_order、test_twelfth_round_finish_no_hidden_request；limit | 离线通过 |
| FR-017 | test_repeat_and_business_conflict、test_configuration_changes_conflict、test_claim_atomic_and_running_reuse | 离线通过 |
| FR-018 | test_save_transaction_rolls_back_preserving_script_and_ledger、终态复用与 recover 测试 | 离线通过 |
| FR-019 | 各 Trace 的 decision/observation/tool_started/tool_settled/terminal 事件；原生协议关联测试 | 离线通过 |
| FR-020 | test_mock_and_show_do_not_read_model_secrets、test_invalid_json_and_missing_real_config；examples/real/README.md | 通过；真实模式无静默回退 |
| FR-021 | 13 个场景 + 重导出 + 重复与冲突材料 | 离线证据齐备 |
| FR-022 | examples/real/README.md、summary.json 与两条完整真实证据 | 两条路径已取得，T046 完成 |
| FR-023 | 133 项 pytest；本表；pytest.xml 与 clean-pytest.xml | 离线通过 |
| FR-024 | README、src、tests、data、examples、docs、依赖、.env.example；只读导出测试 | 本地材料通过 |
| FR-025 | 选题 2；GitHub 公开仓库已核对；最终 SHA 在提交后报告 | 已推送公开仓库，最终 SHA 见交付消息 |
| SC-001 | normal：费用 8.00，720 秒合成工具耗时，6 轮，有方案和依赖 | 离线通过 |
| SC-002 | missing-budget/deadline/both；empty 与输入校验测试 | 离线通过 |
| SC-003 | 真实 budget-replan 12→8；Mock no-feasible 缺口 2.00 | 所列实际场景通过；不推算普遍成功率 |
| SC-004 | 真实 tool-failure 保留 failed 与素材后改选；其他故障有 Mock 证据 | 生成故障真实路径通过；保存/partial 仅离线 |
| SC-005 | repeat 与 repeat-conflict，数据库数量对照 | 离线通过 |
| SC-006 | 上限 1、最后一轮 11/12、无效动作与模型错误计轮 | 离线通过 |
| SC-007 | Decimal、未知费用、依赖、过期报价、时间等于/不足/已过边界 | 离线通过 |
| SC-008 | 13 个离线场景与两条真实路径；完整 Trace 及全部失败尝试 | 证据齐备 |
| SC-009 | 干净环境复现、五份文档、实际用时、真实路径与失败披露 | 工程材料齐备；个人理解与人工验收由用户完成 |

测试文件：[CLI](../tests/test_cli.py)、[执行器](../tests/test_runner.py)、[领域规则](../tests/test_domain.py)、[SQLite](../tests/test_store.py)、[模型协议](../tests/test_provider_contract.py)。完整验收定义见 [规格](../specs/001-content-planning-agent/spec.md)。

## 内容核对、失败与限制

本轮 AI 直接读取 normal、budget-replan、tool-failure、save-failure、partial-result 的实际方案做了内容抽查：素材引用均为 reading-1/reading-2，已由检索返回；正文未承诺素材之外的奖品、参与人数或场地；时间、渠道、目标与受众假设显式留待运营确认；保存依赖指向成功生成与最新估算；normal/budget/save 为 8.00，故障替代为 3.00。此项是 AI 审阅，不代表用户本人已做人工验收，也不能推广为模型语义真实性保证。

首次 v2/v3 真实方案由 AI 逐项读取抽查：素材引用均为检索返回的 reading-1/reading-2；账本分别为 8.00 和 3.00；保存依赖与最新报价对应，失败尝试未改成成功。但正文存在语义缺口：standard 和 lean 草稿都包含多种内容形式，lean 没有严格收窄到单一精简文案；故障方案自行加入“评论区参与”“不设排名、不评奖项”等素材未确认规则，也并非每处都明确标记为建议。当时的执行器尚未约束正文形式。当前已增加结构化单份交付、范围拒绝和逐字事实引用，将所有创意和运营建议标记待审核，详见修复报告。它们作为模型质量问题保留在原始证据中，发布前需运营修订；不能把工具 completed 解读为正文事实全部正确。此检查为 AI 审阅，用户本人尚未给出人工验收意见。

开发中发现并修正：正常链路模块缺失、故障注入/恢复未实现（9 项失败）、保存方案缺实际依赖与费用明细、旧候选脚本误列为当前可复用。修正后相关测试及最终全量测试通过。真实模型另出现了候选身份误改、同候选重试未命中目标，以及一次非单一工具响应；均保留实际记录。

真实 HTTP 适配器由假 HTTP 响应验证单动作、关联 ID、观察传回、错误/截断/拒答/超时/过大响应/重定向；另已实测 DeepSeek beta + deepseek-flash，两条真实路径均有响应标识和 usage。单次 socket 超时不等于严格整次运行时限。外部模型 token 费用不属于合成业务预算。

本期不实现跨运行续跑、同条件脚本改写或跨主机恢复。PID 无法确认或复用时采取拒绝恢复策略。导出文件是派生副本，需 manifest 摘要检查完整性；权威方案仍在 SQLite。

## 独立审查后修复验收

[修复报告](07-review-fixes.md) 记录了发现 A/B 与补充反例、17 项修复回归及独立 Agent 定向复核。两个离线依赖反例具有完整证据；当前 v5 预算方案仅含 277 字图文正文，故障替代方案仅含 65 字单段短文，均无分镜，费用分别 8.00/3.00。新运行的 provenance.json 包含提示、schema、源码与资料/规则快照，摘要与 manifest 中配置一致；[同版核对](../examples/real/current-validation.json)。

默认测试只验证声明的交付结构与已知越界模式，不承诺完整自然语言语义校验。模型创意与新增运营建议仍须人工审核；用户个人能力和实践未由工程修复证明。

## 交付状态

- 题号：选题 2（用户确认）。
- 仓库：[lwwdsb/AgentForPlanning](https://github.com/lwwdsb/AgentForPlanning)，已通过 GitHub API 确认公开，当前账号 ADMIN；公开读取无需评审账号授权。
- 最终 commit SHA：本地实现及证据已推送 main；以 git rev-parse HEAD 和远端分支核对后的实际值在交付消息报告，不写入同一提交。
- 真实模型验证 T046/T056：同版 v5 两条动态路径已完成，前序成功和未命中结果均保留。
- 远端提交 T052：已完成，选题 2、公开 URL 与实际提交均可核对；最终 SHA 在交付消息报告。
