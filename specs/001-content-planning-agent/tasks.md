---
description: "内容任务规划 Agent 的按用户故事组织的实施与验证任务"
---

# Tasks: 内容任务规划 Agent

**Input**: Design documents from `specs/001-content-planning-agent/`。
**Prerequisites**: [plan.md](plan.md)、[spec.md](spec.md)、[research.md](research.md)、
[data-model.md](data-model.md)、[contracts/cli.md](contracts/cli.md)、
[contracts/model-and-tools.md](contracts/model-and-tools.md)、[quickstart.md](quickstart.md)。
**Governance**: [项目宪章](../../.specify/memory/constitution.md)。
**Status**: 原52项及独立审查后T053–T057均完成；133项离线测试、两个依赖反例、同版v5两条真实路径和定向复核通过。个人实践/人工审核与可选续跑不由任务勾选替代，详见docs/07-review-fixes.md。

**Tests**: 规格 FR-023 及宪章明确要求可执行测试，因此包含测试任务。
测试先按契约和业务结果编写，确认相应待实现行为失败，再实现和验证；不要求用户逐次批准测试。
真实模型评估不进入默认离线测试，也不能由 Mock 替代。

**Organization**: Phase 1–2 为共享前置；Phase 3–8 对应 US1–US6；Phase 9 为最终交付检查。
US1–US5 为 P1，US6 为 P2，但六个故事均属于完整考核交付范围。

## Format: `[ID] [P?] [Story] Description`

- Task ID 连续递增；所有任务使用复选框和具体仓库相对路径；仅已完成任务勾选。
- `[P]` 只代表在明确前置完成后，可以与同组不同文件的任务并行；不授权自动启动子代理。
- `[USn]` 只用于对应用户故事阶段；Setup、Foundational、Polish 不加故事标签。
- 任务中引号为设计约束的原文；完整字段定义和契约以链接文档为准，不在实现时自行弱化。

## Path Conventions

采用单项目：`src/content_agent/`、`tests/`、`data/`、`examples/`、`docs/` 均位于仓库根目录。
本清单路径对应实现与交付文件；完成证据见 docs/03-evaluation.md。
`.state/` 是忽略提交的运行状态；SQLite 中的方案为权威产物，导出 JSON 是派生副本。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 建立 Python 3.12+、标准库运行时与 pytest 开发环境，不引入 Agent 框架、服务部署或界面。

- [X] T001 在 pyproject.toml、requirements-dev.txt、src/content_agent/__init__.py 和 src/content_agent/__main__.py 建立可安装的单包项目与 content-agent 入口，设置 Python 3.12+、pytest 配置并锁定实际验证的构建/测试依赖版本；建立 plan.md 规定的目录，记录实施开始时间。
- [X] T002 [P] 在 .gitignore 和 .env.example 配置忽略 .state/、.venv/、真实 .env 及缓存，声明 MODEL_ENDPOINT、MODEL_NAME、MODEL_API_KEY；注明 Mock 无需变量、不自动加载 .env，示例中不得放真实密钥（依赖 T001）。
- [X] T003 [P] 在 data/materials.json 和 data/rules.json 创建版本化合成素材与三种形式费用耗时表，逐项落实工具契约基线；保持“全部合成；引用必须存在且被检索返回，空结果有明确 observation”和“缺费用或耗时即不可确认可行；失败费用明确为 0；禁用形式不能被选择”（依赖 T001）。

**Checkpoint**: 可创建隔离环境并安装包；素材与规则能读取且没有真实业务数据。

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 定义所有故事共享的领域类型、状态、存储边界、提供者接口和可注入测试依赖。
**Gate**: T004–T008 完成后开始故事实现；此阶段不提前实现完整业务流程。

- [X] T004 在 src/content_agent/domain.py 定义 Request、Run、Candidate、Step、Attempt、Estimate、Artifact、LedgerEntry、Event 及结果类型，保留 data-model.md 全部字段，包括原始输入/脱敏配置与逻辑时钟统计；原样落实“max_rounds 为 1–100 的整数，默认 12”、“耗时非负，logical_now 为带时区 UTC 时间”、步骤“pending → running → succeeded | failed”及 skipped、“status=failed, quality=partial”、运行 awaiting_input/running/completed/incomplete 和返回 input_conflict；保持“唯一调用尝试；失败、部分结果和替代尝试分别留存”和“由领域层根据动作和实际结果建立依赖，不信任模型自报成功”。
- [X] T005 [P] 在 src/content_agent/store.py 建立 requests、events、ledger、artifacts 四表及短事务接口，落实“request_id PRIMARY KEY；run_id UNIQUE”、“(run_id, sequence) PRIMARY KEY”、“attempt_id PRIMARY KEY”、“artifact_id PRIMARY KEY；request_id UNIQUE”；支持原子请求认领、快照/事件读取、轮次持久化与事务回滚，模型调用期间不持有写事务（依赖 T004）。
- [X] T006 [P] 在 src/content_agent/providers.py 定义真实与 Mock 共用的 decide 接口、五个动作的原生工具参数 schema 及统一观察结构，落实“所有对象均 additionalProperties=false，全部属性列入 required，可选属性允许 null”和 decision_summary“不超过 200 字”；为 tools/runner 提供明确的输入输出边界，不实现替代选择的执行器分支（依赖 T004）。
- [X] T007 [P] 在 src/content_agent/domain.py 实现 Decimal 金额、含 UTC/单调时间的可注入 Clock、规范化与请求指纹基础函数，落实“拒绝非有限、负数或超过两位小数；不静默四舍五入”、“主题去首尾空白，预算统一两位，截止时间转 UTC”及指纹“不包含 API key、输出目录或请求标识自身”；以实际累计时长加各工具模拟额外时长推进 logical_now，模型等待不能被模拟时长抵消；指纹纳入模式、模型标识/去认证 endpoint、轮数、资料/规则版本与摘要、偏好和故障/Mock 配置（依赖 T004）。
- [X] T008 在 tests/conftest.py 建立独立临时 SQLite、合成规则、可控 Clock、计数型假模型/HTTP 响应夹具，禁止默认测试联网；夹具复用 T004–T007 的公开接口，不预写业务执行 Trace（依赖 T005–T007）。

**Checkpoint**: 共享类型与契约确定、状态库可原子读写、测试可独立控制时间和模型输出。

## Phase 3: User Story 1 - 获得可执行且已保存的活动方案 (Priority: P1) — MVP

**Goal**: 完整输入经过模型动作、四类工具、费用核对和保存，得到可读取方案与真实步骤记录。
**Independent Test**: 主题完整、预算 10、偏好 standard、截止时间充足时，Mock 经同一执行器完成；
费用 8.00、方案内容完整、保存产物可 show 读取，实际模型模式可通过同一入口接入。

### Tests for User Story 1

- [X] T009 [P] [US1] 在 tests/test_cli.py 编写正常 run/show 契约测试：显式 mode、缺省 UUID、stdout 单一 JSON、诊断 stderr、方案读取、结果必需字段与完成退出码 0；验证 run 的完整证据包导出和 show --evidence-dir 的只读重新导出，核对原始输入/脱敏配置/历史结果/Trace/manifest/方案齐备且无新增调用、费用、事件或状态变化；对应 US1-1–US1-3，先确认未实现行为失败。
- [X] T010 [P] [US1] 在 tests/test_provider_contract.py 编写原生工具 schema、单次模型动作、assistant/tool_call_id 关联、工具观察进入下一次请求的协议测试，验证 generate_script 正文来自模型参数且无嵌套模型调用；使用假 HTTP，不算真实模型证据。
- [X] T011 [P] [US1] 在 tests/test_runner.py 和 tests/test_domain.py 编写检索→估算→生成→再估算→保存→finish 的正常链路、精确费用、依赖未满足不能成功和内容完整性测试；用实际工具返回值核对状态、产物与账本，不能只检查日志文本。

### Implementation for User Story 1

- [X] T012 [P] [US1] 在 src/content_agent/tools.py 实现四类工具的正常路径，检索“最多 3 条”“每条正文最多 1000 字”，生成草稿“非空、最多 4000 字”；保持“业务条件变化时创建新 candidate_id，revision 按请求内新候选顺序递增，旧版本不可原地修改；引用必须来自成功检索；模型声明内容必须与用户事实区分”和“每次估算记录历史；金额和时间由规则计算，不接收模型给定数值”；成功脚本不可原地改写，相同候选不同草稿也只复用，生成前估算、生成后重新估算才可保存（依赖 T009–T011）。
- [X] T013 [P] [US1] 在 src/content_agent/providers.py 实现 urllib.request 真实适配器及正常路径 Mock，配置完整 HTTPS endpoint、模型名、环境密钥；使用 required 工具调用、禁用并行调用/流式/重定向，socket 超时 30 秒、响应上限 1 MiB、无隐式重试；原样反馈模型 assistant 与 tool 观察，不硬编码真实模型下一步（依赖 T009–T011）。
- [X] T014 [US1] 在 src/content_agent/store.py 保存原始业务输入和脱敏执行配置，并实现工具结果提交：尝试先记 running，结果、状态、事件、时钟统计与费用同一短事务完成；落实“每个成功付费尝试至多一笔；失败、复用、估算不能入账”、“已保存最终方案正文位于 artifacts 表，按请求唯一”和事件“顺序递增”；保存正文、保存成功状态与引用不得分开提交（依赖 T012–T013）。
- [X] T015 [US1] 在 src/content_agent/runner.py 串联真实/Mock 的观察—决策—执行循环，逐轮持久化计数、校验工具参数与依赖、执行预算/时间守卫并反馈实际观察；模型等待计入实际累计时长，每次工具结算仅补规则耗时超出实际耗时的部分；只有合法 finish(completed) 且保存与约束均通过才完成，finish(incomplete) 要有非空原因，所有结果由权威状态计算（依赖 T014）。
- [X] T016 [US1] 在 src/content_agent/cli.py、src/content_agent/__main__.py 和 src/content_agent/store.py 接通 run/show、输入文件、模式、状态路径、资料目录、请求标识、上限及 evidence-dir 参数；实现 run 的完整证据包导出和 show --evidence-dir 的同一只读快照重新导出，保存原始输入/脱敏配置/历史结果/Trace/manifest/已有方案，不调用模型/工具或改变原状态；按 contracts/cli.md 序列化结果和退出码，show 成功返回 0、导出失败返回 74，真实模式配置错误不静默变成 Mock（依赖 T015）。
- [X] T017 [US1] 创建 examples/inputs/normal.json，并实际运行正常 Mock 和 show --evidence-dir，将完整输入、实际结果、Trace、manifest 及方案分别导出至 examples/mock/normal/ 和 examples/mock/normal-reexport/；运行 T009–T011，确认总费用 8.00、内容完整、原运行记录与重新导出一致且无额外调用/费用/事件，记录真实用时而不将结果当作真实模型证据（依赖 T016）。

**Checkpoint**: 正常链路可演示并可独立复核。该 MVP 不是完整考核达标，尚须 US2–US6。

## Phase 4: User Story 2 - 补齐信息或了解无法继续的原因 (Priority: P1)

**Goal**: 缺输入、格式错误或无资料时，明确告知问题，不虚构约束、不收费或伪造素材。
**Independent Test**: 分别缺预算、缺截止时间、同时缺两项和无匹配素材，核对字段列表、调用计数及结果。

### Tests for User Story 2

- [X] T018 [P] [US2] 在 tests/test_cli.py 编写缺预算/缺截止时间/同时缺失、空主题、无时区时间、非字符串/非有限/负数/多于两位小数预算及未知字段测试；断言输入问题一次返回、退出码 2、零模型/业务调用/费用，且输入检查先于真实模型配置检查。
- [X] T019 [P] [US2] 在 tests/test_runner.py 编写检索 empty 后模型收到实际观察并停止的测试，断言没有伪造引用、脚本或保存，结果包含资料缺口与已执行检索记录；与缺字段的零调用路径区分。

### Implementation for User Story 2

- [X] T020 [US2] 在 src/content_agent/domain.py 完成聚合输入校验及缺失/无效字段指纹编码，落实“缺失或无效字段以明确的缺失/无效标记参与指纹，不强行解析为合法值”和“缺少依据时为 null 并注明未知”；不默认预算/截止时间，未知金额不输出伪造的 0（依赖 T018–T019）。
- [X] T021 [US2] 在 src/content_agent/cli.py、src/content_agent/tools.py、src/content_agent/runner.py 和 src/content_agent/providers.py 接通 awaiting_input、检索 empty 的观察与 Mock 停止动作，确保缺字段时不初始化真实模型请求，资料不足时由模型观察后结束；补齐输入使用新请求标识（依赖 T020）。
- [X] T022 [US2] 创建 examples/inputs/missing-budget.json、examples/inputs/missing-deadline.json、examples/inputs/missing-both.json、examples/inputs/insufficient-materials.json，实际运行并输出至 examples/mock/missing-budget/、examples/mock/missing-deadline/、examples/mock/missing-both/、examples/mock/insufficient-materials/，保留实际退出码、零调用或 empty 证据（依赖 T021）。

**Checkpoint**: US2 不依赖预算重规划或故障注入即可验收，正常链路仍然通过。

## Phase 5: User Story 3 - 超预算后改选可行方案或明确停止 (Priority: P1)

**Goal**: 模型看到估算后改选或停止；历史费用与耗时保留，替代方案重新校验。
**Independent Test**: 预算 10、12→8 完成；仅可选 12 时缺口 2；历史 3+剩余 8 时不得误判可行。

### Tests for User Story 3

- [X] T023 [P] [US3] 在 tests/test_domain.py 编写历史费用 3+8>10、0.10+0.20=0.30、零预算、等于预算、未知价格、候选变化失效与费用不可冲销测试；验证相同条件重新估算不增加候选 revision、不同草稿不能覆盖成功脚本、业务条件变化新建候选并保留历史；同时覆盖工具模拟 1 分钟后模型等待 5 分钟累计 6 分钟、工具实际 8 分钟/模拟 10 分钟只累计 10 分钟、交错多轮与失败耗时不重置、截止时间等于/不足/已过边界及模型延迟到期。
- [X] T024 [P] [US3] 在 tests/test_runner.py 编写两次估算 12→8、所有形式不可行、时间不足改选/停止、生成后未重估禁止保存、旧 estimate_id/候选/规则不匹配被拒绝的集成测试；断言观察实际进入下一轮，执行器没有自行选择替代方案。

### Implementation for User Story 3

- [X] T025 [US3] 在 src/content_agent/domain.py 完善可复用产物与剩余费用/时间计算，严格落实“projected_total = spent_total + remaining_cost(candidate, reusable_artifacts)”、“logical_now = started_at + timedelta(seconds=actual_elapsed_seconds + simulation_extra_seconds)”、“effective_now = max(clock.now_utc(), logical_now)”和“estimated_finish = effective_now + remaining_seconds(candidate, reusable_artifacts)”；模型等待计入实际时长，每个工具仅一次补充 max(规则耗时−实际工具耗时, 0)，simulated_elapsed_seconds 只作审计，历史成本/耗时不清零、等于约束允许通过（依赖 T023–T024）。
- [X] T026 [US3] 在 src/content_agent/tools.py 和 src/content_agent/runner.py 实现不可行估算的 success/feasible=false 观察、旧报价失效、付费前/保存前/finish 前再核对，以及有依据的费用/时间缺口；费用或耗时未知不得确认可行，不从一份失败报价推断所有形式无解；同一候选不同草稿也须由工具守卫复用成功脚本，不再执行业务工具、计费或增加规则模拟耗时，真实处理时间仍计入时钟；业务条件变化才新建候选并重估，不支持同条件脚本改写（依赖 T025）。
- [X] T027 [US3] 在 src/content_agent/providers.py 扩展 Mock 对超预算和超时观察的替代/停止行为，真实提示只要求先评估用户偏好并提供可选形式，不将替代动作硬编码为系统指令（依赖 T026）。
- [X] T028 [US3] 创建 examples/inputs/budget-replan.json、examples/inputs/no-feasible.json 以及 examples/fixtures/budget-replan/ 和 examples/fixtures/no-feasible/ 的材料/规则，前者仅开放 premium/standard、后者仅 premium；实际运行生成 examples/mock/budget-replan/ 和 examples/mock/no-feasible/，核对最终 8.00 或缺口 2.00，保留两次实际报价（依赖 T027）。

**Checkpoint**: 成本或时间约束驱动模型调整；不能以最终费用恰好合适替代中间观察与改选证据。

## Phase 6: User Story 4 - 工具失败后保留成果并调整后续动作 (Priority: P1)

**Goal**: 失败/部分成功不被当作成功，模型保留有效成果后替代或停止，上限与中断语义明确。
**Independent Test**: 检索成功后注入生成失败；核对后续模型动作、素材保留、失败状态和费用；另验保存失败及额度耗尽。

### Tests for User Story 4

- [X] T029 [P] [US4] 在 tests/test_runner.py 编写生成一次/持续失败、部分生成、模型服务中断、未知工具/非法参数/依赖缺失/提前 finish 的测试；将保存失败拆成未恢复且停止/额度耗尽返回 incomplete 与模型重试成功后满足全部条件返回 completed 两条路径，断言旧失败保留、新尝试成功、脚本和费用不重复；覆盖第 12 轮合法 finish、第 12 轮仅保存和耗尽后零新增调用，失败/无效动作计轮次、失败不收费但按规则计耗时。
- [X] T030 [P] [US4] 在 tests/test_store.py 编写保存提交前故障回滚、已提交脚本/账本不丢失、死进程 recover、活进程/主机不同/无法确认时拒绝 recover 的测试；验证保存失败无成功产物、新 attempt_id 重试成功只产生一份最终方案且原失败记录保留，未重试时无伪造保存位置；检查数据库实际表内容，不以返回的“保存成功”字段代替原子性验证。

### Implementation for User Story 4

- [X] T031 [US4] 在 src/content_agent/tools.py 和 src/content_agent/domain.py 实现 none/generate-once/generate-always/save-once/partial-generate 注入、失败观察与按规则耗时，保留部分内容和新旧尝试；落实“成功的旧步骤保持成功历史”和“reusable=false”只表示失效，不能改写成功历史（依赖 T029–T030）。
- [X] T032 [US4] 在 src/content_agent/runner.py 和 src/content_agent/providers.py 完成错误/部分结果的反馈、Mock 替代或停止及严格终止顺序；保存失败可由模型显式选择新尝试，成功且全部条件满足才允许完成，未恢复则停止/耗尽返回未完成；原样落实“finish、无效输出、服务错误各占一轮”和“第 12 轮仅保存且尚无合法 finish 时返回 limit_reached”，不得隐式重试或补第 13 次总结请求（依赖 T031）。
- [X] T033 [US4] 在 src/content_agent/store.py 和 src/content_agent/cli.py 接通 recover 命令，仅在同一主机确认 owner_pid 不存在时将运行改为 incomplete/interrupted、running 尝试改为 failed/error=interrupted；不自动续跑、不补记未提交费用，不能确认时拒绝且不更改原状态（依赖 T032）。
- [X] T034 [US4] 创建 examples/inputs/tool-failure.json、examples/inputs/save-failure.json、examples/inputs/partial-result.json、examples/inputs/limit.json 及 examples/fixtures/tool-failure/，实际运行并生成 examples/mock/tool-failure/、examples/mock/tool-failure-stop/、examples/mock/save-failure-stop/、examples/mock/save-failure/、examples/mock/partial-result/、examples/mock/limit/；保存失败未恢复用例使用 Mock 正常前序加 save-once/max-rounds=5 并确认实际命中失败，恢复用例由模型显式重试成功，分别核对 incomplete/completed、原失败不被覆盖及费用不重复（依赖 T033）。

**Checkpoint**: 失败记录真实、成果不丢失、计费和额度可核查；recover 仅标记中断，不算加分项失败续跑。

## Phase 7: User Story 5 - 重复执行时获得一致结果 (Priority: P1)

**Goal**: 相同标识和条件复用已有结果；条件变化冲突；新标识表示独立请求。
**Independent Test**: CLI 跨进程执行同一完成请求至少两次，再改预算/规则，核对费用、产物和调用数量。

### Tests for User Story 5

- [X] T035 [P] [US5] 在 tests/test_store.py 编写原子认领、同标识同指纹读终态/进度、不同指纹不覆盖、费用 attempt_id 唯一及 artifacts 按请求唯一的测试，检查记录计数与真实内容；已失败或 awaiting_input 的同条件请求不自动续跑。
- [X] T036 [P] [US5] 在 tests/test_cli.py 编写跨进程重复完成/失败/进行中请求、同标识修改主题/预算/截止时间/资料规则内容或版本/模式/故障/轮数的冲突测试，以及新标识允许重做；确认旧费用与方案不变、原 run_id 复用、reused=true、无新增模型和业务调用。

### Implementation for User Story 5

- [X] T037 [US5] 在 src/content_agent/domain.py 和 src/content_agent/store.py 补全规范化指纹与认领比较：落实“request_id 唯一”和“内容摘要与版本同时参与指纹”；同一标识补充缺失字段也需新请求，命中终态返回原结果，running 只读进度，不因换输出目录产生新执行（依赖 T035–T036）。
- [X] T038 [US5] 在 src/content_agent/runner.py 和 src/content_agent/cli.py 将幂等判断放在模型/工具执行前，接通 input_conflict/退出码 4 与 running/in_progress，不重置故障计数、不重复记费用、不覆盖保存方案；返回原 Trace 引用而不伪造新执行事件（依赖 T037）。
- [X] T039 [US5] 使用 examples/inputs/normal.json 和 examples/inputs/no-feasible.json 实际跨进程重复完成及失败请求，再使用独立修改输入验证冲突；将各次实际请求、结果、退出码与原 Trace 关联导出至 examples/mock/repeat/ 和 examples/mock/repeat-conflict/，记录前后 ledger/artifacts 数量以证明零新增（依赖 T038）。

**Checkpoint**: 重复执行是可验证的状态复用，不是删除状态后重新跑一次。

## Phase 8: User Story 6 - 评审核对决策和验证结果 (Priority: P2)

**Goal**: 形成可复现的运行记录与文档，严格区分离线流程和真实模型效果。
**Independent Test**: 评审仅依赖仓库入口、材料与命令即可核对至少三类场景、全部验收点和两条真实动态路径；
若真实模型条件不具备，明确标为未验证，不能通过 Mock 宣称完整达标。

### Tests for User Story 6

- [X] T040 [P] [US6] 在 tests/test_cli.py 扩展 US1 已有完整证据导出测试，覆盖 show 三种 stdout 视图与 evidence-dir 独立、进行中快照标记、导出失败 74 后 show --evidence-dir 重试完整材料包、历史未完成结果 show 成功仍返回 0、无方案 show artifact 返回 66；断言只读快照内容一致、不读取模型密钥、不重判当前截止时间、不增加调用/账本/事件/时间或改变状态，复用不生成假 Trace。
- [X] T041 [P] [US6] 在 tests/test_provider_contract.py 完善零/多 tool_calls、重复或缺失 ID、截断/拒答/非法顶层、单调用参数拒绝的消息关联，以及 HTTP 失败/超时/过大响应/重定向拒绝和日志无密钥测试；默认离线，Mock 禁止联网或读取真实密钥。

### Implementation & Evaluation for User Story 6

- [X] T042 [P] [US6] 在 src/content_agent/store.py 和 src/content_agent/cli.py 完善 T016 已实现的同一只读快照完整导出，按 T040 增补进行中快照、74 错误与只读重试处理，保留所选 stdout 视图及原始业务结果；审计 JSONL/manifest 的 schema_version、模式、脱敏配置摘要、请求/运行/步骤/轮次、真实参数/观察/下一动作/公开依据，认证信息永不写入记录，不把首次基础导出延后到本任务（依赖 T040–T041）。
- [X] T043 [P] [US6] 在 docs/01-requirements.md 和 docs/02-solution.md 撰写评审文档，引用本规格和设计而不维护冲突需求，明确用户、范围、成功标准、模型观察驱动流程、状态依赖、费用/时间口径、幂等与原生实现取舍（依赖 T040–T041；可与 T042、T044 并行）。
- [X] T044 [P] [US6] 在 docs/04-ai-usage.md 和 docs/05-retrospective.md 如实记录 AI 生成内容、已发生的人工修改及各自验证、最难问题、学习收获、实际用时、未完成部分和下一步；没有人工修改则明确注明，不能代用户虚构贡献（依赖 T040–T041；可与 T042–T043 并行）。
- [X] T045 [US6] 实际运行默认离线测试及 quickstart.md 的正常、信息/资料不足、工具失败、预算重规划、无解、上限与重复场景，将结果写入 examples/test-results/pytest.xml 和对应 examples/mock/ 目录；在 docs/03-evaluation.md 建立验收点→输入/预期/实际/退出码/Trace/测试文件映射，覆盖全部 FR 与 SC（依赖 T042–T044）。
- [X] T046 [US6] 使用显式 real 配置实际运行预算改选与故障改选或停止两条模型路径，将真实输入、输出、消息关联、Trace、配置摘要和保存方案写入 examples/real/budget-replan/、examples/real/tool-failure/；只有实际命中 12→8 和错误观察驱动调整才能完成本任务，模型不可用或路径未命中时在 docs/03-evaluation.md 记录事实且保持本任务未完成，不伪造记录（依赖 T045；需可用模型配置）。
- [X] T047 [US6] 在 docs/03-evaluation.md 对照真实与 Mock 结果逐项说明通过、失败和未验证项，人工抽查方案事实/素材引用与假设、预算明细和状态一致；引用实际运行文件而非设计示例，记录模型/协议支持边界及真实模型路径结论（依赖 T045 和 T046 的实际执行或不可用记录；T046 未完成时可先完整披露限制）。

**Checkpoint**: 至少三类实际材料可复现，全部验收点有证据或明确缺口；
只有 T046 实际完成后，才可以声称真实动态决策证据已齐备。

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: 对齐安装、文档、实际测试、隐私与最终提交信息，不加入非必需功能。

- [X] T048 在 README.md 和 .env.example 对齐已实现的环境/安装/run/show/recover/评审入口和真实/Mock 边界，复用 specs/001-content-planning-agent/quickstart.md 的实际有效步骤；明确数据库权威保存位置、非零业务退出码、复用标识及不自动加载 .env。
- [X] T049 在干净隔离环境按 README.md 复现安装、正常 Mock、一个失败场景、重复执行和默认测试，将环境/命令/实际用时/结果保存至 examples/test-results/clean-reproduction.json 和 examples/test-results/clean-pytest.xml；检查 plan.md 的离线单请求 2 秒/默认测试 30 秒目标，未达则如实记入 docs/03-evaluation.md，修复新增问题后仅重复相关验证。
- [X] T050 检查 .gitignore、.env.example、examples/mock/、examples/real/、docs/04-ai-usage.md 和 docs/05-retrospective.md，移除真实密钥/隐私、认证头和内部思维内容，保留核查决策所需的合成事实与简要依据；补齐最终实际用时、未完成部分和新发生修改的验证，不编造尚未取得的真实证据。
- [X] T051 在提交宪章前按其约定移除 .specify/memory/constitution.md 顶部临时 Sync Impact Report，保留全部治理正文和版本日期；复核 specs/001-content-planning-agent/tasks.md 的完成标记与实际证据一致，未完成真实模型验证或外部交付时不得勾选对应任务。
- [X] T052 在 README.md 提供考核方实际题号和评审入口，核对提交 GitHub URL、私库指定评审账号可读及最终 commit SHA；以 git rev-parse HEAD 的实际值在最终提交信息中报告，不把该 SHA 写回同一个提交造成自引用；仓库/账号/题号未提供或访问未验证时在 docs/03-evaluation.md 记录交付缺口并保持本任务未完成，不虚构 URL、SHA 或权限。

**Checkpoint**: 代码、文档、实际证据与提交身份一致；缺口明确，不能用勾选状态掩盖未完成部分。

## Dependencies & Execution Order

### Phase Dependencies

- Setup：T001 完成后 T002 与 T003 可并行。
- Foundational：T004 依赖 Setup；T005/T006/T007 依赖 T004 且可并行；T008 在三者完成后执行。
- 所有故事依赖 T001–T008。US1 实现共用可运行核心，US2–US5 在此基础上各自独立验收。
- US6 的证据汇总依赖 US1–US5 相关路径；真实模型验证额外依赖可用模型配置，不阻止继续编写限制说明。
- Polish 依赖已实现的故事和评估记录；若 T046 被外部条件阻塞，可完成其他复现/文档检查，
  但完整考核交付结论必须保留缺口。T052 依赖实际提交仓库和指定评审身份。

### User Story Dependencies

```text
Setup(T001–T003) → Foundational(T004–T008) → US1(T009–T017)
                                             ├→ US2(T018–T022) ─┐
                                             ├→ US3(T023–T028) ─┤
                                             ├→ US4(T029–T034) ─┼→ US6(T040–T047) → Polish(T048–T052)
                                             └→ US5(T035–T039) ─┘
可用真实模型配置 ─────────────────────────────────────────────────→ T046
实际提交仓库/题号/评审身份 ─────────────────────────────────────────→ T052
```

逻辑独立表示 US2–US5 的验收不依赖其他异常故事完成，不表示可以同时修改同一个源文件。
单人实施按 Phase 3→4→5→6→7 顺序合并，避免 domain.py、runner.py、tools.py、providers.py、
store.py、cli.py 的变更冲突。US6 的文档可在相应已验证结果出现后持续补充。

### Within Each User Story

1. 完成该故事测试任务并确认待实现断言失败；不把缺少真实模型配置伪装成测试成功。
2. 按依赖完成类型/规则、业务工具或提供者、执行器、CLI 接通与实际运行记录。
3. 运行对应测试、核对实际状态/账本/产物，达到本故事 Independent Test 后再标记完成。
4. 未变更的验证不重复堆叠；新增行为、修复或干净环境复现需要时才扩大验证。

### Parallel Opportunities

- Setup：T002 / T003；Foundation：T005 / T006 / T007。
- US1：T009 / T010 / T011；三者完成后 T012 / T013。
- US2：T018 / T019；US3：T023 / T024；US4：T029 / T030；US5：T035 / T036。
- US6：T040 / T041；两者完成后 T042 / T043 / T044。
- 所有组都要求阶段前置已完成；同组文件互不冲突。后续依赖组不能与其前置任务同时开始。

## Parallel Example: User Story 1

T001–T008 完成后同时编写 T009（tests/test_cli.py）、T010（tests/test_provider_contract.py）和
T011（tests/test_runner.py、tests/test_domain.py）；测试任务完成后才并行 T012（tools.py）与
T013（providers.py）。T014–T017 依次集成与运行，不能与其前置任务并行。

## Parallel Example: User Story 2

US1 完成后同时编写 T018（tests/test_cli.py）与 T019（tests/test_runner.py）；
随后顺序完成 T020–T022。缺预算和无资料场景分别断言零调用与实际 empty 观察。

## Parallel Example: User Story 3

US1 完成且共享文件未被其他故事占用时，并行 T023（tests/test_domain.py）和
T024（tests/test_runner.py）；预算、时钟公式与模型调整的实现按 T025–T028 顺序完成。

## Parallel Example: User Story 4

US1 完成且共享文件空闲时，并行 T029（tests/test_runner.py）与 T030（tests/test_store.py）；
随后 T031–T034 串行，避免故障注入、事务与额度修复交叉覆盖。

## Parallel Example: User Story 5

US1 完成且共享文件空闲时，并行 T035（tests/test_store.py）与 T036（tests/test_cli.py）；
T037–T039 串行，实际子进程复用必须读取同一个状态库。

## Parallel Example: User Story 6

相关业务故事完成后并行 T040（tests/test_cli.py）与 T041（tests/test_provider_contract.py）；
随后 T042（store.py、cli.py）、T043（docs/01、02）与 T044（docs/04、05）可并行。
T045 收集离线结果后，T046 才运行真实模型路径；T047 依据实际结果或不可用记录写结论。

## Implementation Strategy

### MVP First (User Story 1 Only)

完成 T001–T017，使用正常输入在 Mock 中证明可运行闭环，并保留真实模型接入能力。
MVP 检查点要求方案可读取、费用准确、状态可信；它不是考核全部完成的声明。
模型驱动的重规划效果仍需 US3/US4 的真实路径及 US6 的证据验收。

### Incremental Delivery

1. US1：先形成可运行闭环。
2. US2：处理缺输入与无资料，防止虚构约束或依据。
3. US3：实现预算和时间重规划，核对历史费用。
4. US4：验证失败保留、部分结果和有界执行。
5. US5：跨进程证明重复请求不产生重复副作用。
6. US6：收集实际输入输出、真实模型路径并形成五份文档。
7. Polish：干净环境复现、隐私检查与最终提交信息核验。

### Time & Scope Control

三小时是建议投入，不是对 52 个任务工时的保证。按 plan.md 的 180 分钟预算优先核心链路，
持续记录实际用时；若不足，保留全部验收任务并明确未完成状态，不用删任务降低标准。
界面、线上部署、多 Agent 和失败续跑均不扩展进本次任务。
实施开始时没有 Git 仓库；用户现已提供公开远端 lwwdsb/AgentForPlanning，并确认选题 2。真实模型配置按用户安排延后。

## Requirements Traceability

| 需求 | 实施与验证任务 |
| --- | --- |
| FR-001–FR-002 | T004、T007、T009、T016、T018、T020–T022 |
| FR-003–FR-005 | T003、T011–T012、T014、T017、T019、T021、T043 |
| FR-006–FR-007 | T006、T010、T013、T015、T024、T026–T029、T031–T032、T046 |
| FR-008–FR-010 | T004、T011、T015、T024、T029–T033 |
| FR-011–FR-013 | T003、T007、T011–T012、T014、T023–T028 |
| FR-014–FR-015 | T007、T011–T015、T023–T026、T029–T030 |
| FR-016 | T004、T009、T015、T029、T032、T034 |
| FR-017–FR-018 | T005、T007、T030、T033、T035–T039 |
| FR-019–FR-020 | T002、T006、T010、T013–T017、T040–T042、T047–T048 |
| FR-021–FR-023 | T017–T019、T022–T024、T028–T030、T034–T036、T039–T047、T049 |
| FR-024 | T001–T003、T009、T014、T016–T017、T040、T042–T045、T047–T051 |
| FR-025 | T048–T052 |

| 成功标准 | 验证任务 |
| --- | --- |
| SC-001 | T009、T011、T017、T045 |
| SC-002 | T018–T022、T045 |
| SC-003 | T023–T024、T028、T046–T047 |
| SC-004 | T029–T030、T034、T045–T047 |
| SC-005 | T035–T036、T039、T045 |
| SC-006 | T029、T032、T034、T045 |
| SC-007 | T023–T026、T045 |
| SC-008 | T040–T047 |
| SC-009 | T043–T050、T052 |

## Task Summary

| 范围 | 任务编号 | 数量 | 独立验收要点 |
| --- | --- | --- | --- |
| Setup | T001–T003 | 3 | 项目可安装，合成素材与规则可读 |
| Foundational | T004–T008 | 5 | 类型、事务、提供者接口与测试夹具可用 |
| US1 | T009–T017 | 9 | 正常方案保存、可读取、费用 8.00、状态与依赖一致 |
| US2 | T018–T022 | 5 | 缺预算/截止时间零调用，无素材则明确停止 |
| US3 | T023–T028 | 6 | 12→8 改选后重估，无解返回缺口，历史 3+8 不被忽略 |
| US4 | T029–T034 | 6 | 注入失败保留成果、不误报成功、达到额度不再调用 |
| US5 | T035–T039 | 5 | 跨进程重复零新增费用/产物，输入变化冲突 |
| US6 | T040–T047 | 8 | 实际材料可复核，真实路径与 Mock 结论分开 |
| Polish | T048–T052 | 5 | 干净环境复现、隐私检查与最终提交身份可验证 |
| 合计 | T001–T052 | 52 | MVP 为 T001–T017，完整交付需要所有必需任务 |

标记 `[P]` 的任务共 23 项，分为上文列出的 10 组；仅同组且前置完成后可同时进行。

## Notes

- 本轮授权修订已同步保存未恢复/重试成功、成功脚本只复用、顺序逻辑时间与只读完整导出；
  基础导出前移至 T016，T042 仅完善边界，任务编号和总数保持不变。
- 当前所有复选框保持未勾选，不能把任务清单的格式检查等同业务测试通过。
- T046 需要实际真实模型路径；T052 需要实际提交身份及访问条件，不是可被 Mock 满足的任务。
- 每条任务只在对应行为、测试或文档内容确实完成后勾选，未取得证据必须留为未完成。
- `.specify/extensions.yml` 不存在，before_tasks 与 after_tasks 钩子按规则跳过。


## 独立审查后修复（2026-10-27）

- [X] T053 添加并复现真实产物依赖及交付范围反例，先观察失败再修复。
- [X] T054 按素材、报价、脚本 ID 连接成功来源步骤；多次检索及生成后重估均保留准确依赖。
- [X] T055 明确各档位单份交付合同，结构化草稿强制检查范围，事实逐字溯源，创意与运营建议显式待审核；保持费用和状态守卫。
- [X] T056 当前提示版本完成两条真实路径，记录提示/工具schema/实现快照摘要，保留既有运行；全量测试、离线场景与干净环境复现。
- [X] T057 独立复核修复、更新设计/评估/复盘与修复对应说明，检查凭据与证据一致，提交并核对远端 SHA。
