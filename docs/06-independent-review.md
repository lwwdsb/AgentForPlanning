# 独立要求核验报告

> 本报告保留对原提交的审查结论与反例。发现 A/B 及后续补充反例的修复和定向复核见 [修复记录](07-review-fixes.md)。旧字符串协议反例适用于被审查提交，当前复现入口见修复记录。

审查日期：2026-10-27（America/Los_Angeles；UTC 2026-10-28）。审查提交：`fdb528d1454c3b37825733911adb36bb85ef8f63`。审查对象为选题 2，仓库 https://github.com/lwwdsb/AgentForPlanning 。本报告由全新上下文的独立审查 Agent 根据原始考核要求、当前代码及实际验证形成，未预设项目达标。

**结论：核心 Agent 循环与五类必验收场景有充分实现和运行证据，但目前不宜无保留宣称“所有要求完整完成”。** 已复现一项 P2：多次检索后，输出及保存方案的步骤依赖可能指向错误的素材来源。该问题影响原始要求中的“步骤依赖与真实状态”。另有已披露的正文内容范围问题，以及需要用户本人完成的个人实践与人工验收；这些不能用测试通过数量替代。

没有发现预算算术越界扣费、失败尝试被覆盖成成功、重复请求重复收费、上限后继续执行等已证实问题。未发现 P0/P1 阻塞。以下“通过”只表示所列范围已经核验，不代表所有输入或模型运行都可靠。

## 已执行的独立检查

| 检查 | 实际结果与边界 |
|---|---|
| 当前代码与测试读取 | 检查全部 `src/content_agent/` 模块、测试、规则、交付文档与证据生成脚本；不只依据任务勾选或文档结论 |
| 默认离线测试 | **116 passed，0 failures/errors/skips，4.363 秒**。命令：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/agent-independent-pytest --junitxml=/tmp/agent-independent-pytest.xml` |
| 全新 CLI 输入 | **15 组**：正常、缺预算、缺截止时间、两者均缺、无素材、12→8、无可行方案、一次生成失败、持续生成失败、部分生成、保存失败重试、1 轮上限、保存后无结束额度、已过截止时间、零预算。状态、费用和退出码符合预期 |
| 重复执行 | 对上述每组再次运行，结果仅增加 `reused=true`，数据库文件逐字节不变；输入冲突另由默认测试覆盖 |
| 证据包 | **20 份 manifest、71 个核心文件哈希全部相符**；14 份 Mock 包含重导出，6 份 real 包含 4 次独立尝试及 2 份主验收副本，不能算作 6 次独立真实运行 |
| 权威状态与指纹 | 只读打开上述全部 20 个包所指向的现有 SQLite 库；导出结果、事件、方案与权威快照一致；规范化输入/config/资料/规则组成的请求指纹，以及 manifest 的三个摘要一致 |
| 证据内部一致性 | 当前资料和规则摘要匹配；Trace 序号、请求/运行 ID、模型轮数、调用关联、输出观察、成功尝试收费、保存方案费用明细和步骤记录相符；主验收副本与原始尝试逐字节一致 |
| 干净运行 | 从该提交 `git archive HEAD` 导出到 `/tmp`，创建**无 pip、无第三方包**的新 venv，按 README 的 `PYTHONPATH=src python -m content_agent` 入口运行：completed，8.00，退出 0 |
| 历史真实动作离线重放 | 读取 4 次历史 assistant 工具动作，在当前执行器下重放；仅映射新生成的产物/报价 ID，并以历史开始时间驱动测试时钟。4 次最终状态、费用、观察状态序列及候选形式序列均相同。**这是执行器兼容性验证，不是新的真实模型调用** |

15 组 CLI 中，正常/预算改选/保存重试完成且费用为 8.00；一次生成失败和部分生成改选后完成且费用为 3.00；缺输入零轮数、零工具调用、零费用；持续失败、无解、过期、零预算及额度不足均未完成。过期输入的 Mock 会耗尽 12 轮，最终 reason 为 `limit_reached`，各观察明确拒绝 `deadline_exceeded`；没有被判为按期完成。

审查未调用付费模型、未读取真实 `.env`、未修改实现或既有证据、未提交或推送。临时检查脚本与输出位于 `/tmp`；关键反例在本报告内完整保留，结论不依赖临时文件长期存在。

## 原始硬性要求矩阵

| 原始要求 | 当前实现位置及实际证据 | 结论 |
|---|---|---|
| 帮助运营按主题、预算和截止时间完成内容方案 | `cli.py:89`、`domain.py:72`、`tools.py:112`；normal 的输入/输出/方案，新鲜 CLI 和干净运行 | 核心流程通过；正文业务质量另见发现 B |
| CLI/HTTP/Notebook 至少一个可复制入口 | README 安装与源代码入口、`pyproject.toml`、`cli.py:56`；干净无第三方运行 | 通过；未在本次重新联网下载依赖 |
| 至少一次“模型选动作→工具→观察→模型继续/结束” | `providers.py:197` 发送真实 HTTP 请求；`runner.py:131` 循环，`:153` 记录决策，`:178` 回填 tool 观察；协议测试及真实 Trace | 通过代码核验和历史证据核对；外部来源边界见下文 |
| 至少两条不同工具结果后的模型动作调整 | real/budget-replan：Trace 第 13 行报价 12，第 16 行模型改 standard，第 19 行报价 8；real/tool-failure：第 19 行生成失败，第 22 行模型选 lean，第 25 行报价 3 | 历史证据通过；预算为提示 v2，故障为 v3，不是同版本两条新运行 |
| 步骤、参数、返回摘要、后续动作及简要公开决策依据 | `runner.py:153–183`；真实 Trace 的 decision/observation，assistant 参数中的 `decision_summary` | 通过；没有要求或依赖内部思维 |
| 执行步数/工具调用上限，耗尽明确未完成 | `runner.py:131–185`；limit、saved-no-finish；`test_limit_finish_order`、`test_twelfth_round_finish_no_hidden_request` | 通过；每轮最多一个动作，finish/拒绝亦计轮 |
| 素材检索、脚本生成、成本估算、方案保存四类工具 | `tools.py:66–147`；正常运行五次业务调用及保存方案 | 通过；业务工具为允许的本地合成工具 |
| 任务计划、步骤状态、工具结果、费用、已保存方案或未完成原因 | `runner.py:12–55`、`tools.py:129`；所有输出与 SQLite 产物 | 字段与保存通过；依赖真实性**部分通过**，见发现 A |
| 正常完成 | `test_normal_run`；examples/mock/normal；独立新鲜和干净运行均为 8.00 completed | 通过 |
| 缺预算或截止时间 | `domain.py:72–101`、`runner.py:96–127`；missing-budget/deadline/both；新鲜验证零调用 | 通过 |
| 工具失败后由模型调整或停止，保留成功结果，失败不得记成功 | `runner.py:221–252`；真实故障 Trace、生成/保存/持续失败/partial 测试；原 failed 和素材保留，失败不收费 | 通过；partial 的真实模型决策未另行验证 |
| 超预算改选；无可行方案返回未完成与缺口 | `domain.py:274`、`tools.py:28`；12→8 真实路径，no-feasible 缺口 2.00；历史费用加剩余费用测试 | 通过；发现 B 不属于已证实的算术超支 |
| 预算、截止时间、步骤依赖及真实状态 | 整数金额、报价上下文与实时重校验；时间边界/模型等待/保存后超时测试；独立多次检索反例 | 预算、时间及失败状态通过；依赖图**部分通过** |
| 重复执行 | `runner.py:102–115`、`store.py:50–75`；重复/冲突测试、15 组独立重复 DB 不变 | 通过；同 ID 同条件复用，变化冲突 |
| 至少 3 组实际输入/输出/Trace，覆盖全部验收点，评估引用文件 | 13 组 Mock 场景，4 次真实尝试，docs/03-evaluation.md 的逐项链接；20 包校验通过 | 通过；Mock 明确不证明真实模型能力 |
| README、src、tests、examples、data、docs/01–05、依赖文件、变量说明 | 文件存在，内容与实现交叉检查；`.env.example`；运行时标准库，无 Agent 框架 | 通过 |
| 解释取舍、AI 辅助、修改结果和未完成部分 | docs/02、04、05；提示修订和失败尝试公开保留；116 测试与实录 | 工程记录通过；个人手写修改/理解能力未验证 |
| 记录实际用时，建议投入 3 小时 | docs/05、implementation-session.json、real-validation-session.json 披露计时边界及未计入阶段 | 所记录阶段可核对；没有完整个人总投入的独立证据。3 小时是建议，不是超时失败条件 |
| 题号、GitHub URL、最终 SHA；仓库评审可读 | 选题 2；本文提交 SHA、README URL。主线程当次 `gh repo view` 核验 public/main，`git ls-remote` 与上述 SHA 一致 | 通过；远端实时核验来源为主线程，独立 Agent 未重复联网 |
| 同仓库交付，无真实密钥/隐私 | Git 当前和历史文件名检查只有 `.env.example`；`.gitignore` 忽略 `.env`、`.env.*`、`.state/`、`.venv/`；真实示例使用合成资料 | 文件名/忽略范围通过；没有读取真实密钥，也不以此声称已证明所有历史文本绝无敏感信息 |

## 发现 A：P2，步骤依赖没有绑定实际使用的产物

位置：[`src/content_agent/runner.py:77`](../src/content_agent/runner.py) 的 `dependencies()`，尤其第 83–85 行；第 206–207 行在执行前调用它。它仅按工具类别选“最近一个成功步骤”，没有接收当前 `material_ids`、`estimate_id` 或 `script_id`。

最小动作序列：

1. 检索“校园读书周”，成功获得 `reading-1/reading-2`。
2. 检索“校园环保”，成功获得 `green-1`。
3. 估算 standard，素材明确指定 `reading-1/reading-2`。
4. 生成读书脚本；对同一候选重估；保存；完成。

**实际结果：completed，8.00，但估算和生成步骤的检索依赖指向第二步（只有 green-1）。真正提供 reading-1/reading-2 的第一步没有任何后续依赖。** 错误也进入保存方案的 `execution_steps`。此外，生成后的重估使用已有脚本作为 `required_artifacts`，依赖图却仍只连检索，没有连到生成步骤。

这不是素材越权或实际费用越界：素材已正确检索，脚本引用守卫仍有效。影响在于输出的执行计划和依赖关系不真实，违反原始要求的重点核验项，也使文档“实际步骤依赖”承诺不完整。现有测试只确认依赖 ID 指向某个成功步骤，未检查该步骤是否产出了本次使用的素材。

最小修复：按本次动作实际引用的素材/报价/脚本 ID 查找产出它们的成功步骤；涉及多次检索的素材要保留全部必要来源；生成后的重估应记录已有脚本依赖。加入此反例及“素材分散在两次检索中”的回归测试，再更新受影响的说明/证据。不要通过禁止模型再次检索来掩盖问题。

可在仓库根目录直接执行下面的离线反例；仅在 `/tmp` 写临时数据库，不调用真实模型：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3.12 - <<'PY'
import json, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from content_agent.cli import load_data
from content_agent.providers import action
from content_agent.runner import run_request
from content_agent.store import Store

class OfflineProbe:
    def decide(self, c, messages):
        n = c['rounds_used']
        candidate = c['candidates'][-1] if c['candidates'] else None
        if n <= 2:
            name = 'search_materials'
            args = {'query': '校园读书周' if n == 1 else '校园环保'}
        elif n in (3, 5):
            name = 'estimate_cost'
            args = dict(variant='standard', material_ids=['reading-1', 'reading-2'],
                        goal='推广阅读', audience='校园读者', assumptions=['受众待确认'])
        elif n == 4:
            name = 'generate_script'
            args = dict(candidate_id=candidate['candidate_id'],
                        estimate_id=candidate['estimate_id'],
                        material_ids=candidate['material_ids'], script_draft='读书周分享书单。')
        elif n == 6:
            name = 'save_plan'
            args = dict(candidate_id=candidate['candidate_id'],
                        estimate_id=candidate['estimate_id'],
                        script_id=c['scripts'][candidate['candidate_id']]['artifact_id'])
        else:
            name = 'finish'
            args = dict(outcome='completed', reason_code=None, remaining_work=[])
        return action(name, {**args, 'decision_summary': '离线依赖来源反例'}, n)

with tempfile.TemporaryDirectory(dir='/tmp') as temp:
    store = Store(Path(temp) / 'state.db')
    raw = dict(theme='校园读书周', budget='10.00', preferred_variant='standard',
               deadline=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    result = run_request(raw, 'dependency-probe',
                         dict(mode='mock', max_rounds=12, fault='none'),
                         load_data('data'), store, OfflineProbe())
    steps = result['steps']
    assert result['status'] == 'completed'
    assert steps[0]['artifact_ids'] == ['reading-1', 'reading-2']
    assert steps[1]['artifact_ids'] == ['green-1']
    assert steps[2]['depends_on'] == [steps[1]['step_id']]
    assert steps[3]['depends_on'][0] == steps[1]['step_id']
    assert steps[3]['step_id'] not in steps[4]['depends_on']
    print(json.dumps(dict(status=result['status'], spent=result['costs']['spent_total'],
          selected_materials=result['plan']['current_candidate']['material_ids'],
          recorded_dependency_materials=steps[1]['artifact_ids']), ensure_ascii=False))
    store.close()
PY
```

当前提交的稳定输出摘要：`completed / 8.00 / selected_materials=[reading-1,reading-2] / recorded_dependency_materials=[green-1]`。这些断言描述当前缺陷，修复后应改为检查正确来源。

## 发现 B：P2 业务质量缺口，正文范围与廉价档位没有明确对应

位置：[`src/content_agent/tools.py:112`](../src/content_agent/tools.py) 的生成工具仅检查非空草稿及引用/报价；[`data/rules.json:23`](../data/rules.json) 开始的各档位只给价格和耗时，没有声明交付范围。Mock 在 `providers.py:155` 内部把 premium/standard/lean 对应短视频/主题图文/精简文案，但真实模型上下文没有同等明确的结构化形式约束。

已有实证：[`examples/real/tool-failure/artifact.json:1`](../examples/real/tool-failure/artifact.json) 的候选为 lean、支出 3.00，正文仍包含图文预告、30–40 秒短视频和精简文案；其 Trace 第 46 行 finish 也明确把三种内容列为成果。预算成功方案同样包含图文与视频。故障正文还加入素材未确认的“评论区参与”“不设排名、不评奖项”，未逐项作为待确认建议标注。docs/03-evaluation.md:95 已诚实披露，审查没有将其当作新发现的隐瞒行为。

分级说明：**这不是已证实的预算算术错误，也不否定模型发生了改选动作。** 若合成价格定义为“调用一次某档位生成工具”，账本正确；但“改用廉价内容形式后获得可执行方案”的业务效果与项目自行承诺的形式/事实可区分要求只得到部分满足。不能把 `completed` 等同于正文可直接发布。

建议明确各档位包含的物料范围，并把形式放入模型可见规则和结构化产物；对未确认参与规则标注建议/待确认。若确认交付内容超出所选档位，应重新估价或返回待修订。随后以新尝试目录保留复核结果，原始证据不改写。

## 证据与版本边界

真实适配器确实构造 HTTPS 请求，解析服务 tool_calls，保存响应 `id/model/usage`，没有在 real 模式回退 Mock。执行器没有硬编码选择 standard 或 lean；选择来自模型返回的动作，提示可建议替代策略。四次历史尝试合计 **29 条模型响应元数据**，失败尝试没有被删除，主验收副本并未伪装成新增运行。

预算成功证据的 `decision_policy_version=content-planning-v2`，故障成功证据为当前 `content-planning-v3`；首次预算为未版本化初始策略。文档已明确披露。当前 Git 提交只保留最终提示正文，manifest 没有代码提交/提示正文的内容哈希，因此不能从包本身精确还原每次历史完整代码与提示。离线重放证明当前执行器对这些历史动作产生相容结果，**不能证明当前 v3 模型再次运行预算路径必定成功**。

响应 ID、usage、本地 SQLite 与哈希的一致性增强可审计性，但不是供应商签名或独立网络见证。本次没有新模型调用、供应商账单核验或外部请求原始报文验证，不把它们说成已独立认证的网络来源。补充当前版本两条真实重跑与提示/代码摘要会改善证据完整性；原始要求未明确要求相同提示版本，故此项列为验证边界，不单独判为原始硬性失败。

## 项目额外约束、可选项和个人事项

| 类别 | 内容 | 审查判断 |
|---|---|---|
| 项目自行增加 | SQLite 权威产物、同 ID 指纹冲突、只读重导出、事务回滚、死进程 recover | 有对应实现/测试；不是原题要求必须采用的架构 |
| 项目自行增加 | 默认 12 轮、可设 1–100、每轮单动作、严格金额字符串和带时区日期、DeepSeek strict schema | 原题只要求有上限及正确输入/预算行为；这些具体约定是实现选择 |
| 项目自行增加 | 故障优先改选其他形式、生成后同候选重估、部分结果不收费、离线性能目标 | 不应把这些具体策略全部反推成原题独立硬要求；初次真实故障显式重试仍属于观察驱动行为，只是未达到项目选定的替代形式验收 |
| 可选加分 | 跨运行失败步骤续跑 | 未实现；原题明确可选，不作为阻碍基础达标的问题 |
| 非必需 | UI、线上部署、多 Agent、生产 Runtime、跨主机恢复 | 未实现不扣原始硬性要求 |
| 用户本人事项 | 亲自复现、修改、解释取舍、学习收获和人工内容验收 | docs/04、05 明确尚未观察到个人源代码修改或人工验收；本报告不代用户补写这些经历，不能认定个人能力考核已经完成 |

建议先修复发现 A，再解决发现 B 的档位含义与正文确认问题；维持已有失败记录及 Mock/真实边界披露。完成修复与对应验证之前，准确交付表述是“核心链路和主要验收场景已验证，仍有一项依赖记录缺陷及内容质量、个人实践边界”，而不是“全部要求无遗漏完成”。
