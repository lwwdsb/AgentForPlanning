# 评估与交付状态

离线业务功能与模型协议夹具测试通过。**真实模型动态决策未验证**：用户明确安排稍后配置模型，本轮没有调用真实模型，也不把 Mock 或假 HTTP 测试当作真实 ReAct 效果证明。

本机 Python 3.12.12，运行时仅标准库。默认测试 **113 项通过，0 失败/错误，4.235 秒**；[原始结果](../examples/test-results/pytest.xml)。干净环境同样 113 项通过，4.238 秒；[干净测试](../examples/test-results/clean-pytest.xml)、[安装/运行记录](../examples/test-results/clean-reproduction.json)。报告仅删除 hostname 元数据。

13 个实际 CLI 场景中最长 0.076 秒，满足本机离线单请求 2 秒目标；测试集低于 30 秒目标。这是当前环境实测，不代表所有机器或真实模型的性能保证。每次命令及实际退出码见 [场景记录](../examples/test-results/scenario-runs.json)。

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

## 全部需求与成功标准映射

“离线通过”仅指执行器/协议/文档对应行为已验证，不扩大为真实模型质量或个人能力结论。下表是需求关联覆盖，不是代码行覆盖率。

| 要求 | 验证与证据 | 结论 |
|---|---|---|
| FR-001 | tests/test_cli.py：正常 run、UUID、输入格式；normal | 离线通过 |
| FR-002 | test_invalid_input_precedes_real_config；missing-* | 离线通过 |
| FR-003 | data/materials.json、data/rules.json；test_configuration_changes_conflict | 通过 |
| FR-004 | test_normal_run、test_no_materials_observed_before_stopping、test_generation_failures_preserve_success | 离线通过 |
| FR-005 | test_saved_plan_has_dependencies_and_cost_detail；normal/artifact.json | 离线通过 |
| FR-006 | test_real_adapter_runs_same_loop_with_actual_tool_observations；真实模式接口已实现 | 协议通过；真实决策未验证 |
| FR-007 | budget-replan、tool-failure、partial-result；真实模式未运行 | Mock 通过；真实调整未验证 |
| FR-008 | test_invalid_params_and_unmet_dependencies_are_observations、test_cannot_finish_without_save | 离线通过 |
| FR-009 | generation/save 故障测试、test_repeat_failure_or_progress_subprocess | 离线通过 |
| FR-010 | test_old_success_not_advertised_as_reusable_for_new_candidate、保存重试测试 | 离线通过 |
| FR-011 | test_decimal_money、test_history_spend_and_boundary、test_generation_reused_does_not_execute_or_charge_again | 离线通过 |
| FR-012 | test_unknown_rules_never_assumed_zero、历史 3+8>10、失败费用测试 | 离线通过 |
| FR-013 | test_budget_12_to_8、test_no_feasible_gap；预算改选与无解 Trace | Mock 通过；真实决策未验证 |
| FR-014 | test_exact_deadline、test_time_causes_model_alternative、模型等待及工具实际耗时测试 | 离线通过 |
| FR-015 | test_candidate_identity_script_immutability_and_stale_quote、test_time_after_save_can_prevent_completion_preserving_artifact | 离线通过 |
| FR-016 | test_limit_finish_order、test_twelfth_round_finish_no_hidden_request；limit | 离线通过 |
| FR-017 | test_repeat_and_business_conflict、test_configuration_changes_conflict、test_claim_atomic_and_running_reuse | 离线通过 |
| FR-018 | test_save_transaction_rolls_back_preserving_script_and_ledger、终态复用与 recover 测试 | 离线通过 |
| FR-019 | 各 Trace 的 decision/observation/tool_started/tool_settled/terminal 事件；原生协议关联测试 | 离线通过 |
| FR-020 | test_mock_and_show_do_not_read_model_secrets、test_invalid_json_and_missing_real_config；examples/real/README.md | 通过；真实模式无静默回退 |
| FR-021 | 13 个场景 + 重导出 + 重复与冲突材料 | 离线证据齐备 |
| FR-022 | examples/real/README.md；T046 未完成 | 未验证，按用户安排延后 |
| FR-023 | 113 项 pytest；本表；pytest.xml 与 clean-pytest.xml | 离线通过 |
| FR-024 | README、src、tests、data、examples、docs、依赖、.env.example；只读导出测试 | 本地材料通过 |
| FR-025 | 选题 2；GitHub 公开仓库已核对；最终 SHA 在提交后报告 | 已推送公开仓库，最终 SHA 见交付消息 |
| SC-001 | normal：费用 8.00，720 秒合成工具耗时，6 轮，有方案和依赖 | 离线通过 |
| SC-002 | missing-budget/deadline/both；empty 与输入校验测试 | 离线通过 |
| SC-003 | budget-replan 12→8；no-feasible 缺口 2.00 | Mock 通过；真实决策未验证 |
| SC-004 | tool-failure/save-failure/partial-result；failed 保留且费用不重复 | Mock 通过；真实调整未验证 |
| SC-005 | repeat 与 repeat-conflict，数据库数量对照 | 离线通过 |
| SC-006 | 上限 1、最后一轮 11/12、无效动作与模型错误计轮 | 离线通过 |
| SC-007 | Decimal、未知费用、依赖、过期报价、时间等于/不足/已过边界 | 离线通过 |
| SC-008 | 完整 Trace 与至少三类场景已有；两条真实路径缺失 | 部分完成 |
| SC-009 | 干净环境复现、五份文档、实际用时；真实模型与最终提交状态分别披露 | 离线交付完成；真实模型效果未验证 |

测试文件：[CLI](../tests/test_cli.py)、[执行器](../tests/test_runner.py)、[领域规则](../tests/test_domain.py)、[SQLite](../tests/test_store.py)、[模型协议](../tests/test_provider_contract.py)。完整验收定义见 [规格](../specs/001-content-planning-agent/spec.md)。

## 内容核对、失败与限制

本轮 AI 直接读取 normal、budget-replan、tool-failure、save-failure、partial-result 的实际方案做了内容抽查：素材引用均为 reading-1/reading-2，已由检索返回；正文未承诺素材之外的奖品、参与人数或场地；时间、渠道、目标与受众假设显式留待运营确认；保存依赖指向成功生成与最新估算；normal/budget/save 为 8.00，故障替代为 3.00。此项是 AI 审阅，不代表用户本人已做人工验收，也不能推广为模型语义真实性保证。

开发中发现并修正：正常链路模块缺失、故障注入/恢复未实现（9 项失败）、保存方案缺实际依赖与费用明细、旧候选脚本误列为当前可复用。修正后相关测试及最终全量测试通过。尚未观察到真实服务失败或真实模型重规划，因为本轮没有发出真实请求。

真实 HTTP 适配器由假 HTTP 响应验证单动作、关联 ID、观察传回、错误/截断/拒答/超时/过大响应/重定向；没有已实测端点或模型组合。单次 socket 超时不等于严格整次运行时限。外部模型 token 费用不属于合成业务预算。

本期不实现跨运行续跑、同条件脚本改写或跨主机恢复。PID 无法确认或复用时采取拒绝恢复策略。导出文件是派生副本，需 manifest 摘要检查完整性；权威方案仍在 SQLite。

## 交付状态

- 题号：选题 2（用户确认）。
- 仓库：[lwwdsb/AgentForPlanning](https://github.com/lwwdsb/AgentForPlanning)，已通过 GitHub API 确认公开，当前账号 ADMIN；公开读取无需评审账号授权。
- 最终 commit SHA：本地实现及证据已推送 main；以 git rev-parse HEAD 和远端分支核对后的实际值在交付消息报告，不写入同一提交。
- 真实模型验证 T046：保持未完成，按用户安排稍后配置。
- 远端提交 T052：已完成，选题 2、公开 URL 与实际提交均可核对；最终 SHA 在交付消息报告。
