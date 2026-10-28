# 独立审查问题修复与复核

本次修复对应 [独立报告](06-independent-review.md) 的发现 A/B。原报告审查提交为 `fdb528d1454c3b37825733911adb36bb85ef8f63`；旧失败记录和真实产物保留，不能把历史内容当作修复后结果。最终提交 SHA 由交付消息给出。

## A：真实产物来源依赖

`runner.dependencies()` 现在以当前动作引用的素材、报价和脚本 ID 查找成功产出步骤。多个检索分别提供素材时会连接全部必要来源；不会因为又执行了一次检索而更换引用来源。生成后重估同时依赖所用脚本，保存依赖实际脚本和实际报价。步骤在保存事务中原样进入方案。

两个可复制的离线反例均已完成且费用 8.00：

- [读书素材后再检索环保](../examples/review-fixes/dependencies/reading-only/output.json)：估算和生成依赖真正提供 reading-1/2 的第一步。
- [素材来自两次检索](../examples/review-fixes/dependencies/mixed-sources/output.json)：估算和生成同时连接 reading-1 与 green-1 的来源；重估另连接生成步骤。

运行 `python scripts/run_dependency_examples.py` 可重新生成实际输入、输出、Trace、manifest 和调用记录。这是明确标记的固定动作离线反例，不作为真实模型决策证据。

## B：单份交付范围、事实与建议

规则升级为 1.1，并向模型公开结构化 `delivery` 合同：

| 档位 | 模拟费用 | 本次唯一交付 | 本地约束 |
|---|---:|---|---|
| premium | 12.00 | 短视频分镜脚本 | 1–6 个分镜，copy 为空 |
| standard | 8.00 | 图文正文 | 一份正文最多 600 字，scenes 为空 |
| lean | 3.00 | 精简文案 | 单段最多 160 字，无换行，scenes 为空 |

各档位报价仅涵盖一份脚本草稿，不包含另一个物料、实际拍摄、设计或投放。新增物料需要重新规划和估价，不能因填写 lean 就把多个物料算成 3.00。

模型通过 `script_draft` 对象提供 format/title/source_facts/copy/scenes/operational_suggestions。执行器拒绝不匹配形式、额外分镜、超过长度或换行的短文、明确跨物料标题及分镜时间结构；拒绝不执行生成、不收费，并把错误反馈模型。独立复核曾进一步发现把多个物料塞进同一行的反例，新增回归后再次核验：原 55 字打包内容被拒，费用为 0；正常提及“短视频、图文传播经验”的主题文案仍完成且费用 3.00。

`source_facts` 只接受当前候选已检索素材的逐字引用。输出将引用与创意分区，所有标题、正文、分镜均注明“创意草稿（待运营审核）”，运营建议另列“待确认，不属于已确认活动规则”。结构化产物保存 `publication_status=requires_operator_review` 及计费范围，不会把模型新增参与规则标记为已确认事实。

这些检查是明确交付结构和保守文本特征检查，不是对任意自然语言的完整语义证明；引用也不等于现实事实已核验。`completed` 表示约束内方案草稿已保存，实际发布仍需运营审核。原题允许本地合成工具，本项目不声称已制作或发布图片/视频成品。

## 最终验证

17 项修复回归先覆盖并复现问题，再修复转绿；全部 **133 项测试通过，4.559 秒**。全新环境同样 **133 项通过，4.599 秒**。[全量结果](../examples/test-results/pytest.xml)、[干净结果](../examples/test-results/clean-pytest.xml)、[复现记录](../examples/test-results/clean-reproduction.json)。13 个公开 CLI 离线场景通过，最长约 0.100 秒，另外保存了上述两个依赖反例。

最终 `content-planning-v5` 两条真实路径使用相同提示摘要、工具 schema 摘要和实现摘要；每个新尝试保存 provenance.json 的提示正文、工具定义、源码及相应资料/规则，摘要与运行配置相符。[同版本核对](../examples/real/current-validation.json)。

| 实际路径 | 结果 | 轮次 / 耗时 | 证据 |
|---|---|---|---|
| 预算 12→8 | completed；8.00；image_text，277 字正文，无分镜 | 7 / 13.83 秒 | [输出](../examples/real/content-planning-v5/budget-replan/output.json) · [方案](../examples/real/content-planning-v5/budget-replan/artifact.json) · [Trace](../examples/real/content-planning-v5/budget-replan/trace.jsonl) |
| 生成失败后改选 | completed；3.00；short_copy，65 字单段，无分镜，原失败保留 | 8 / 15.71 秒 | [输出](../examples/real/content-planning-v5/tool-failure/output.json) · [方案](../examples/real/content-planning-v5/tool-failure/artifact.json) · [Trace](../examples/real/content-planning-v5/tool-failure/trace.jsonl) |

本轮 v4 的两次中间成功保留；随后 v5 第一次预算尝试返回非单一工具动作，执行器在第一轮以 model_error 停止、费用 0。使用新请求显式再次运行预算路径后成功，没有修改失败日志或加入自动重试。全部 9 次历史尝试、60 次模型请求、59 份已持久化有效响应元数据见 [汇总](../examples/real/summary.json)；该次无效协议响应没有记录 usage，因此不把已记录 token 合计当作完整账单。

先前独立审查 Agent 对修复定向复核：A 的单来源、多来源、精确报价/脚本和重估依赖通过；B 的结构与事实/建议分区通过；其补充打包反例也已验证拒绝，正常主题提及通过。本次复核没有再次覆盖所有可能输入，也没有代替用户个人实践或人工内容验收。

## 复现及剩余边界

```bash
python -m pytest -q
python scripts/run_dependency_examples.py
python scripts/run_examples.py
python scripts/run_real_examples.py --env-file .env --case budget-replan
python scripts/run_real_examples.py --env-file .env --case tool-failure
```

最后两条会产生真实模型请求，最多各 12 轮；新证据进入唯一 attempts 目录，版本对应的主验收副本只在不存在时创建。历史证据不改写。旧字符串草稿协议已升级为结构化对象，真实与 Mock 请求指纹包含执行合同；旧证据仍可只读导出，不能以旧请求身份继续新合同。

两个具体审查问题及补充反例已经修复并有对应证据。跨运行失败续跑仍是未实现的可选加分项；个人代码修改、学习收获和人工验收需用户本人完成，不能由本次工程修复代填。实际投入计时见 [本轮记录](../examples/test-results/review-fix-session.json)。
