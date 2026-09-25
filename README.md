<div align="center">

# 蒸馏.skill

> 把一堆原始素材蒸成一瓶高浓度认知。摘要让你读得更快，蒸馏让你想得更远。

</div>

## 它能做什么？

| 场景 | 说明 |
|------|------|
| 素材提炼 | 一堆 PDF / 访谈稿 / 会议纪要 / 聊天记录 → 结构化认知档案 |
| 建立体系 | 从零散资料里抽出骨架、信度、矛盾、缺口 |
| 可溯源 | 每条主张带信度等级和出处，能追回原文 |
| **跨档案综合** | N 份档案 → 共识骨架 / 分歧图谱 / 断层线 / 互补缺口 |
| 增量更新 | 新素材进来只重跑受影响的维度，不全量重来 |
| 质量可验证 | 7 项静态检查 + 独立评分卡 + 对抗精炼，分数历史可对比 |
| 可独立交付 | 档案自包含、格式有契约、内容有哈希；不依赖任何其他 skill |

## 蒸馏不是摘要

| | 摘要 | 蒸馏 |
|---|------|------|
| 目标 | 变短 | 变浓 |
| 保留 | 主要意思 | 结构、信度、矛盾、缺口 |
| 丢失 | 细节 | 水分 |
| 判断标准 | 概括得全不全 | 拿它推断新问题，推得对不对 |

**判定线**：拿产物去回答一个素材里没直接出现过、但相关的新问题。摘要答不了，蒸馏能答。

## 工作流

```
入口分流 → 素材归集 → 🔴清点确认 → 分维度提炼 → 🔴质量确认
        → 交叉验证 → 档案合成 → 封存哈希 → 静态质检(7项) → 独立评分 → 对抗精炼 → 交付
```

三种预设 schema：

| schema | 适用 | 维度 |
|--------|------|------|
| `person` | 某个人 / 虚构角色 | 著作 / 对话 / 表达 / 他者 / 决策 / 时间线 |
| `topic` | 某领域 / 方法论 / 流派 | 领域共识 / 流派分歧 / 关键概念 / 经典案例 / 争议前沿 / 演进脉络 |
| `document` | 论文 / 书籍 / 代码库 / 纪要 / 聊天记录 | 论点树 / 证据链 / 术语表 / 隐含假设 / 内部矛盾 / 信息缺口 |

也支持 `custom` 自定义 2-8 个维度。

## 核心方法论

- **去水三问** — 删掉它结论会变吗？出现过几次？是主张还是例子？
- **信度四级** — A 一手直引 / B 一手转述 / C 二手分析 / D 推断（D 级须 <20%）
- **三重验证** — 跨域复现 + 生成力 + 排他性，全过才进核心骨架
- **矛盾三类** — 时间性 / 领域性 / 本质张力，保留不调和
- **蒸馏比** — 压缩率与浓度，每千字 8-15 条独立条目为健康区间
- **出处与信度同行** — `主张……（A · sources/books/x.pdf）`，让可溯源性与信度都可机械检查

## 目录结构

```
distill-skill/
├── SKILL.md                          # 主技能定义（流程、检查点、降级表、反模式）
├── README.md                         # 本文件
├── references/
│   ├── distillation-framework.md     # 方法论核心（去水三问/信度四级/三重验证）
│   ├── schema-person.md              # 人物 schema
│   ├── schema-topic.md               # 主题 schema
│   ├── schema-document.md            # 文档 schema
│   ├── meta-synthesis.md             # 跨档案综合（共识/分歧/断层线/独立性规则）
│   ├── artifact-format.md            # 档案格式契约（含 EVALS.jsonl、null 语义、校验工具）
│   ├── quality-scorecard.md          # 蒸馏质量评分卡
│   └── adversarial-refine.md         # 对抗精炼（信度/浓度攻击者）
├── scripts/                          # 纯标准库 Python
│   ├── _lib.py                       # 唯一事实源（契约常量/解析/统计/渲染/哈希）
│   ├── ingest.py                     # 素材归集 + 生成/增量更新 manifest.json
│   ├── seal.py                       # 封存 distillate_sha256（--check 只校验）
│   ├── quality_check.py              # 档案静态质检（7 项硬检查 + 软诊断）
│   ├── distill_report.py             # 检查点摘要表
│   ├── meta_scan.py                  # 跨档案对照矩阵 + 来源重叠/slug 碰撞检测
│   └── eval_record.py                # 评测历史记录与对比（拒绝过度断言）
└── test/
    └── test_distill.py               # 测试套件（python3 -m unittest discover -s test -v）
```

产出落在用户工作区 `distilled/<slug>/`，不在 skill 目录内——skill 必须自包含。

## 质量门

档案定稿前跑两道机械关，再进独立 agent 评分：

```bash
python3 scripts/seal.py distilled/<slug>            # 封存内容哈希（下游漂移检测依据）
python3 scripts/quality_check.py distilled/<slug>   # 7 项硬检查 + 软诊断
```

7 项硬检查：frontmatter 完整性 / 核心骨架 3-10 条 / 信度标记与 D 级占比 /
矛盾保留与分类（含和稀泥检测）/ 缺口诚实 / 浓度 / manifest 契约与哈希封存。

**`null` ≠ `0`**：脚本无法判定的字段（`coverage`、一手/二手计数）写 `null` 表示「未回填」，
`0` 表示「判定为没有」。混淆会让下游把「没数」当成「数出来是零」。

跑测试：

```bash
python3 -m unittest discover -s test -v
```

`references/artifact-format.md` 是契约的权威定义，`scripts/` 是它的可执行形式——
改一边必须改另一边，`test_distill.py::TestContractSync` 会检查漂移。

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
```

## 许可

MIT
