# DeepSeek 真实模型验证

2026-10-27（America/Los_Angeles）使用 `deepseek-flash`，端点 `https://api.deepseek.com/beta/chat/completions`，关闭 thinking，启用原生 strict 工具调用。凭据只来自本机 `.env`，没有提交到仓库。

| 验收路径 | 实际结果 | 模拟业务费用 | 轮次 | 证据 |
|---|---|---:|---:|---|
| 预算改选（v5） | premium 报价 12 超限，模型改选 standard 8，生成后重估、保存、结束 | 8.00 | 7 | [输出](content-planning-v5/budget-replan/output.json) · [Trace](content-planning-v5/budget-replan/trace.jsonl) |
| 工具失败改选（v5） | standard 首次生成失败，模型改选 lean，保留素材与原失败，重估保存 | 3.00 | 8 | [输出](content-planning-v5/tool-failure/output.json) · [Trace](content-planning-v5/tool-failure/trace.jsonl) |

这证明上述实际运行中发生了观察驱动的动作调整，不代表任意输入或模型版本都能可靠完成。业务工具仍为本地合成工具；模型 token 账单与模拟业务预算分开。

当前主验收为 content-planning-v5，两条路径提示/schema/实现摘要一致。预算方案是一份 277 字图文正文，故障改选方案是一段 65 字精简文案，均无视频分镜；事实引用与待审核创意/运营建议分区，报价仅覆盖所列草稿。[同版配置核对](current-validation.json)、[修复报告](../../docs/07-review-fixes.md)。

`attempts/` 累计保留 9 次实际尝试，没有补写或删除失败路径。以下是首次四次运行的历史：

- 第一次预算运行：出现 12→8，但模型在重估时将流程状态添加到 assumptions，形成新候选并停止；本地预算与依赖守卫正确拒绝了错误保存。
- 第二次预算运行：增加精确重估字段的反馈与提示（decision_policy_version=content-planning-v2）后，完成保存。
- 第一次故障运行：模型显式重试同一候选后完成，业务成功，但未命中既定的“选择替代形式”验收点。
- 第二次故障运行：按已批准规格补充“生成失败时优先评估未失败形式”的通用提示（content-planning-v3），由模型自主选择 lean 并完成。没有在执行器硬编码替代选择。

首次预算成功证据对应 v2，首次故障成功证据对应 v3；v3 新增内容只涉及生成失败后的策略。各次实际版本、请求 ID、模型响应标识和 token usage 位于 manifest/Trace，汇总见 [运行汇总](summary.json)。未为获得相同结果无限重试，也没有将未命中路径标为通过。

修复阶段另有 v4 两次中间成功和 v5 三次运行：v5 第一次预算运行以 expected_one_tool_call 停止、未执行业务工具、费用 0；随后新请求预算成功，故障路径也成功。当前两条 v5 文件上表可读。历史总汇见 summary.json，首次四次汇总另保留在 [initial-summary.json](initial-summary.json)。v4/v5 的 provenance.json 保存完整提示、工具定义、源码快照；v5 还保存当次资料/规则。execution.json 的 provenance_digest 和 manifest 的提示/schema/实现摘要可交叉核对，不是供应商签名。

复现（会调用真实 API 并产生模型费用，每次最多 12 轮）：

```bash
python scripts/run_real_examples.py --env-file .env --case budget-replan
python scripts/run_real_examples.py --env-file .env --case tool-failure
```

每次使用新请求和未来截止时间，证据进入唯一的 `attempts/` 目录。已有主验收目录保留；通过路径的首次副本进入对应策略版本目录，新结果始终在对应尝试目录中。

协议依据：[DeepSeek 工具调用](https://api-docs.deepseek.com/guides/tool_calls/) 与 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。DeepSeek 不支持的 schema 长度关键字仅从发送格式移除；执行器仍执行原有长度、引用、预算、依赖和时间校验。
