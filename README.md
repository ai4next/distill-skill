<div align="center">

# 蒸馏.skill

> 把一堆原始素材蒸成一瓶高浓度认知。摘要让你读得更快，蒸馏让你想得更远。

</div>

## 它是什么

一份好的蒸馏档案是一套**可运行的认知**——不是「这堆材料讲了什么」，而是
「拿这套认知，你能想到什么原来想不到的」。

判定只有一条：**拿产物去回答一个素材里没直接出现过、但相关的新问题。摘要答不了，蒸馏能答。**
方法论与推理链见 [SKILL.md](SKILL.md) 的「第一原理」。

## 它能做什么

| 场景 | 说明 |
|------|------|
| 素材提炼 | 一堆 PDF / 访谈稿 / 会议纪要 / 聊天记录 → 结构化认知档案 |
| 建立体系 | 从零散资料里抽出骨架、信度、矛盾、缺口 |
| 可溯源 | 每条主张带信度等级和出处，能追回原文 |
| **跨档案综合** | N 份档案 → 共识骨架 / 分歧图谱 / 断层线 / 互补缺口 |
| 增量更新 | 新素材进来只重跑受影响的维度，不全量重来 |
| **拿档案答题** | 用档案回答素材里没出现过的新问题，答案必须指回骨架条目 |
| 质量可验证 | 12 项结构检查 + 独立评分卡 + 留出验证 + 对抗精炼，分数历史可对比 |
| 可独立交付 | 档案自包含、格式有契约、内容有哈希；不依赖任何其他 skill |

三种预设 schema：

| schema | 适用 | 维度 |
|--------|------|------|
| `person` | 某个人 / 虚构角色 | 著作 / 对话 / 表达 / 他者 / 决策 / 时间线 |
| `topic` | 某领域 / 方法论 / 流派 | 领域共识 / 流派分歧 / 关键概念 / 经典案例 / 争议前沿 / 演进脉络 |
| `document` | 论文 / 书籍 / 代码库 / 纪要 / 聊天记录 | 论点树 / 证据链 / 术语表 / 隐含假设 / 内部矛盾 / 信息缺口 |

也支持 `custom` 自定义 2-8 个维度。

## 安装

```bash
npx skills add ai4next/distill-skill
```

或手动克隆到你的 runtime skills 目录（如 `~/.claude/skills/distill-skill/`）。

## 使用

```
蒸馏一下这些材料：~/Downloads/munger/
把这个访谈稿提炼成体系
我又有几篇新材料，补充蒸馏一下
把这三个人综合一下，他们分歧在哪
```

## 工作流

```
入口分流 → 素材归集 → 🔴清点确认 → 冻结生成力题 → 分维度提炼 → 🔴质量确认
        → 交叉验证 → 档案合成(长结构) → 封存哈希
        → 结构检查(12项) → 独立评分 → 留出验证 → 对抗精炼 → 🔴交付
```

三个 🔴 是让用户纠偏的检查点。逐 Phase 操作细节见 [SKILL.md](SKILL.md)，
方法论见 [references/distillation-framework.md](references/distillation-framework.md)。

**题目先于档案存在**：生成力题在 Phase 1.8 从 `sources/` 出好并冻结，Phase 5 才用。
Phase 5 才出题 = 让写档案的人自己挑考题，判定线那 20 分会直接虚高。

## 结构检查与质量门

**这是两件事，别混。**

```bash
python3 scripts/seal.py distilled/<slug>            # 封存内容哈希（下游漂移检测依据）
python3 scripts/quality_check.py distilled/<slug>   # 12 项结构检查 + 软诊断
```

12 项结构检查：frontmatter 完整性与交叉校验 / 核心骨架 3-10 条 / 骨架条目元数据 /
信度标记与 D 级占比 / 矛盾保留与分类（含**否认对立**检测）/ 缺口诚实 / 素材清单非空 /
维度底稿齐备 / 元数据已回填 / 浓度 / manifest 契约与哈希封存。

> **过了这 12 项 ≠ 质量合格。** 它们拦的是**结构缺陷**，不是内容真伪——一份字段齐全、
> 标记规范的档案完全可能是编造的。过了只等于「没有结构性缺陷，值得花一次评分」。

再过独立 agent 评分卡（**七维 100 分**）：生成力 20 / 覆盖度 15 / 信度 15 / 浓度 15 /
可溯源性 10 / 矛盾保留 15 / 缺口诚实 10。

**生成力排第一且分值最高，因为它是判定线。** 其余六维测的都是「多忠实地搬了素材」，
只有它测「素材之外长出了什么」——一份覆盖完整、信度扎实、出处齐全的档案**完全可以
是一份完美的摘要**。生成力 ≤7 分时等级封顶 C，无论其余六维多漂亮。

**覆盖度/信度/缺口诚实要核证据，不是读数字。** 这三项合计 40 分，此前直接读生产者自报的
`coverage` / `confidence` / `gaps`——数字全填好看就锁定 40 分。现在评分 agent 必须打开
`research/` 底稿与 `sources/` 去核。

**矛盾段不许留空**：有矛盾就分类记录；确实核查过而无矛盾，显式声明「未发现矛盾」
并交代核查范围。沉默会被判 FAIL——区分不了「真的没有」和「没看」；但也不许为了
拿满分编一条矛盾出来，所以**核查记录的质量决定得分（8-15）**，而不是「有没有找到矛盾」。

**`null` ≠ `0`**：脚本无法判定的字段（`coverage`、一手/二手计数）写 `null` 表示「未回填」，
`0` 表示「判定为没有」。交付态不该有 `null`（第 10 项会硬拦）。见
[references/artifact-format.md](references/artifact-format.md) §2.2。

**做不到独立评分就不评分**：运行环境无法 spawn 独立 agent 时，跳过评分卡，
标注「本档案未经独立评分」且不给等级——冒充独立评分的自评分，危害不是分数低，
是**看起来像有分数**。

## 拿档案回答新问题

交付不是终点。判定线本来就是「拿产物回答素材里没出现过的新问题」——
评分卡每跑一次都在做这件事，这个模式只是把它交给你：

| # | 动作 |
|---|------|
| 1 | 读 `DISTILLATE.md`（`gaps` 与 `confidence` 必读），**只读不写** |
| 2 | 按**骨架条目**作答：先指出依据的是哪一条，再给立场 |
| 3 | 问题落在 `gaps` 范围内 → **明确拒答**：「这超出档案范围，已知缺口是…」 |

**指不回骨架的答案不许说出口**——那用的是模型自己的常识，不是这份档案。
这也正是评分卡测生成力的方式，区别在于评分卡是抽查，而这里是日常使用。

## 跨档案综合

把 N 份已有档案综合成一份「这个领域的共识与分歧」：

```
蒸馏一下芒格 → 蒸馏一下巴菲特 → 蒸馏一下林奇
→ 把这三个人综合一下，他们分歧在哪
```

**必须先跑来源重叠检测**。如果两份档案共享同一批素材（比如都出自《伯克希尔股东信》），
它们**不构成独立佐证**——「两人共识」可能只是一份素材数了两次：

```bash
python3 scripts/meta_scan.py distilled/munger distilled/buffett distilled/lynch \
    --out distilled/value-investing
```

综合档案产出：共识骨架 / 分歧图谱 / 共享心智模型 / 互补缺口 / **断层线**（分歧的价值观根源）/ 涌现结论。

## 增量更新

```
① 补素材          → python3 scripts/ingest.py <新素材> --out distilled/<slug>
② 只重跑受影响维度 → 复用未受影响的 research/ 底稿
③ 更新档案         → version++ ，标注「已被 X 修正」而非静默删除
④ 重新封存         → python3 scripts/seal.py distilled/<slug>
⑤ 复检             → quality_check.py 确认结构未破；eval_record.py compare 看是否真变好
```

**档案是自包含的**：`DISTILLATE.md` + `manifest.json` 即可独立交付；
`research/` 供溯源，`EVALS.jsonl` 留分数历史。不依赖任何其他 skill 或外部目录。

## 目录结构

```
distill-skill/
├── SKILL.md                          # 主技能定义（判定线 / 第一原理 / 铁律 / 流程 / 反模式）
├── README.md                         # 本文件
├── references/
│   ├── distillation-framework.md     # 方法论核心（去水三问 / 信度四级 / 三重验证 / 矛盾 / 缺口）
│   ├── generative-moves.md           # 生成算子（判定线的**生产**：张力外推/结构迁移/边界外推/反问题/组合）
│   ├── schema-person.md              # 人物 schema
│   ├── schema-topic.md               # 主题 schema
│   ├── schema-document.md            # 文档 schema
│   ├── meta-synthesis.md             # 跨档案综合（共识/分歧/断层线/独立性规则）
│   ├── artifact-format.md            # 档案格式契约（含 EVALS.jsonl、null 语义、校验工具）
│   ├── quality-scorecard.md          # 蒸馏质量评分卡（出题纪律 / 留出验证 / 核证据）
│   └── adversarial-refine.md         # 对抗精炼（信度/浓度攻击者）
├── scripts/                          # 纯标准库 Python
│   ├── _lib.py                       # 唯一事实源（契约常量/解析/统计/渲染/哈希）
│   ├── ingest.py                     # 素材归集 + 生成/增量更新 manifest.json
│   ├── seal.py                       # 封存 distillate_sha256 + 派生 compression_ratio
│   ├── quality_check.py              # 档案结构检查（12 项 + 软诊断）
│   ├── distill_report.py             # 检查点摘要表
│   ├── meta_scan.py                  # 跨档案对照矩阵 + 来源重叠/slug 碰撞检测
│   └── eval_record.py                # 评测历史记录与对比（拒绝过度断言）
└── test/
    └── test_distill.py               # 测试套件（python3 -m unittest discover -s test -v）
```

产出落在用户工作区 `distilled/<slug>/`，不在 skill 目录内——skill 必须自包含。

## 开发

```bash
python3 -m unittest discover -s test -v   # 契约、脚本、回归
```

`references/artifact-format.md` 是契约的权威定义，`scripts/` 是它的可执行形式——
改一边必须改另一边，`test_distill.py::TestContractSync` 会检查漂移。

## 许可

MIT
