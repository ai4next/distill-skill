# 蒸馏档案格式契约（Artifact Contract）

> 本文件是 **蒸馏.skill（distill）** 与 **拘神.skill（summon）** 之间的接口定义。
>
> distill 按此格式**写**，summon 按此格式**读**。任何一方改格式，必须先改本文件并升 `schema_version`。

## 一、目录结构

档案落在**用户工作区**，不在任何 skill 仓库内部（skill 必须自包含，档案属于用户数据）。

```
distilled/<slug>/
├── DISTILLATE.md      # 主档案（人可读 + 机器可消费）—— 消费入口
├── manifest.json      # 素材清单、维度状态、缺口、变更记录 —— 增量蒸馏的依据
├── research/          # 分维度提炼底稿
│   ├── 01-<dim>.md
│   ├── 02-<dim>.md
│   └── ...
├── sources/           # 原始素材（本地归集；网络来源记 URL 不落盘）
│   ├── books/
│   ├── transcripts/
│   ├── articles/
│   ├── notes/
│   ├── chat/
│   ├── code/
│   ├── video/
│   └── other/
├── EVALS.jsonl        # 评测历史（追加式，**每次评分都记，不被覆盖**）——见 §七
└── QUALITY.md         # 蒸馏质量评分卡（Phase 5 产出，**每次重跑会被覆盖**）
```

> **为什么 `EVALS.jsonl` 和 `QUALITY.md` 并存**：`QUALITY.md` 是「当前快照」，每次重跑覆盖；`EVALS.jsonl` 是「历史流水」，只追加。没有它，分数历史会被覆盖销毁，无法回答「这版比上版好在哪」。

> **综合档案**（由 N 份档案综合而来）沿用 `topic` schema，`sources[]` 存的是**那 N 份档案**，见 `meta-synthesis.md`。

`sources/` 的子目录名与 `manifest.json` 中 `sources[].type` **一一对应**（`books` / `transcripts` / `articles` / `notes` / `chat` / `code` / `video` / `other`），便于脚本按目录反推类型。

`<slug>`：小写字母、数字、连字符，如 `munger`、`anti-fragile-decision`、`acme-postmortem`。

## 二、DISTILLATE.md

### 2.1 YAML 子集约束（重要）

为保证 **stdlib-only 脚本可解析**（Python 标准库无 yaml 模块），frontmatter 只允许以下子集：

| 允许 | 示例 |
|------|------|
| `key: 标量` | `slug: munger` |
| `key: [行内列表]` | `dimensions: [著作, 对话, 表达]` |
| `key:` + `- 项` 块列表 | `gaps:`<br>`  - 早期记录稀少` |
| `key: {行内映射}` | `confidence: {A: 22, B: 18, C: 8, D: 2}` |

**禁止**：嵌套多行映射、多行字符串（`|` / `>`）、锚点与别名、注释。
标量中含 `:` `#` `[` `]` `{` `}` 时用双引号包裹，如 `title: "反脆弱：从不确定性中获益"`。

### 2.2 frontmatter 字段

```yaml
---
schema_version: 1
schema: person            # person | topic | document | custom
slug: munger
title: 查理·芒格 · 认知档案
created: 2026-09-22
updated: 2026-09-22
version: 1                # 档案自身版本，每次增量蒸馏 +1
sources_total: 50
sources_primary: 31
sources_secondary: 19
confidence: {A: 22, B: 18, C: 8, D: 2}
source_words: 412000
distillate_words: 10800
compression_ratio: "38:1"
dimensions: [著作, 对话, 表达, 他者, 决策, 时间线]
gaps:                     # 信息缺口，summon 必须映射进人格的「诚实边界」
  - 早期（1990 年前）决策记录稀少
  - 家庭生活维度本人主动不公开
---
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `schema_version` | ✅ | 契约版本，当前 `1` |
| `schema` | ✅ | 四种预设之一或 `custom` |
| `slug` | ✅ | 与目录名一致 |
| `title` | ✅ | 档案标题 |
| `created` / `updated` | ✅ | `YYYY-MM-DD` |
| `version` | ✅ | 档案版本，增量蒸馏递增 |
| `sources_total` / `sources_primary` / `sources_secondary` | ✅ | 来源计数 |
| `confidence` | ✅ | 信度四级分布（见 `distillation-framework.md`） |
| `source_words` / `distillate_words` / `compression_ratio` | ✅ | 蒸馏比 = 素材总字数 : 档案字数 |
| `dimensions` | ✅ | 维度名列表，顺序对应 `research/` 文件编号 |
| `gaps` | ✅ | 信息缺口列表，**允许为空列表但必须存在**（空表示无已知缺口） |

### 2.3 正文骨架

正文分两部分：**通用段**（所有 schema 共有，summon 强依赖）+ **schema 专属段**。

```markdown
# <title>

## 一句话
[一句话概括这份档案的骨架，≤50 字]

## 核心骨架
[本档案最重要的 N 条主张/框架，每条一行，带信度标记]

## 心智模型 / 核心框架
### <名称>
**一句话**：…
**证据**：…（≥2 个不同场景，标注信度等级）
**生成力**：能推断出什么新立场
**局限**：什么情况下失效

## 表达特征
[仅 person / fictional 类需要；topic / document 写「风格与语域」]

## 矛盾与张力
[保留矛盾，不要调和。标注类型：时间性 / 领域性 / 本质张力]

## 信息缺口
[与 frontmatter 的 gaps 一致，可展开说明]

## 变更记录
| 日期 | 动作 | 说明 |
|------|------|------|
```

**schema 专属段**由各 schema 文件定义（`schema-person.md` / `schema-topic.md` / `schema-document.md`），插在「核心骨架」与「矛盾与张力」之间。

## 三、manifest.json

```json
{
  "schema_version": 1,
  "slug": "munger",
  "schema": "person",
  "title": "查理·芒格 · 认知档案",
  "created": "2026-09-22",
  "updated": "2026-09-22",
  "version": 1,
  "source_words": 412000,
  "sources_primary": 31,
  "sources_secondary": 19,
  "sources": [
    {
      "id": "S001",
      "path": "sources/books/poor-charlies-almanack.pdf",
      "origin": "local",
      "type": "book",
      "title": "穷查理宝典",
      "url": null,
      "words": 180000,
      "sha256": "9f2c…",
      "added": "2026-09-22",
      "dimensions": ["著作", "表达"]
    }
  ],
  "dimensions": [
    {
      "id": "01",
      "name": "著作",
      "file": "research/01-writings.md",
      "status": "complete",
      "sources": 12,
      "confidence": {"A": 6, "B": 4, "C": 2, "D": 0},
      "coverage": 85
    }
  ],
  "gaps": ["早期（1990 年前）决策记录稀少"],
  "meta_sources": null,
  "source_overlap": [],
  "changes": [
    {"date": "2026-09-22", "action": "initial", "note": "首次蒸馏", "sources_added": 50}
  ],
  "distillate_sha256": "3a71…"
}
```

| 字段 | 说明 |
|------|------|
| `source_words` | 素材总字数（`ingest.py` 自动统计；二进制素材需 agent 抽文本后回填） |
| `sources_primary` / `sources_secondary` | 一手/二手来源计数。**脚本无法自动判定，默认 0**，由 agent 在 Phase 3 回填 |
| `sources[].origin` | `local`（用户提供/已下载）或 `web`（仅记 URL，不落盘） |
| `sources[].type` | `book` / `transcript` / `article` / `notes` / `chat` / `video` / `code` / `other` |
| `sources[].sha256` | 内容哈希，**增量蒸馏的判重依据** |
| `dimensions[].status` | `complete` / `partial` / `missing` |
| `dimensions[].coverage` | 0-100，该维度信息覆盖度 |
| `changes[]` | 追加式变更日志，**不覆盖历史** |
| `meta_sources` | **综合档案专用**：被综合的档案 slug 列表；普通档案为 `null` |
| `source_overlap` | **综合档案专用**：来源重叠检测结果，如 `[{"archives": ["munger","buffett"], "shared": ["sources/books/berkshire-letters.pdf"]}]`。**重叠的档案不构成独立佐证**，见 `meta-synthesis.md` |
| `distillate_sha256` | 主档案哈希，供 summon 校验「人格是否基于当前档案铸造」 |

## 四、消费规则（summon 侧强制）

summon 铸造人格时：

1. **必读**：`DISTILLATE.md` 的 frontmatter + 正文；`manifest.json` 的 `sources` 与 `gaps`
2. **只读不写**：summon 绝不修改档案。发现档案不足 → 回报用户，建议回 distill 补维度
3. **缺口映射**：`gaps` 与 `confidence` 中 D 级占比高的维度，**必须**映射进人格的「诚实边界」段
4. **来源映射**：`manifest.json` 的 `sources` 映射进人格的「调研信息源」段，标注一手/二手
5. **溯源标记**：人格 frontmatter 记 `source_distillate: <slug>` 与 `source_distillate_sha256`，便于检测档案漂移

## 五、版本兼容

| 变更类型 | 是否 breaking | 处理 |
|---------|--------------|------|
| 新增可选字段 | 否 | 直接加，不升版本 |
| 新增 `meta_sources` / `source_overlap` / `EVALS.jsonl` | 否 | 已加，不升版本 |
| 新增 schema 预设 | 否 | 加文件 + 更新 `schema` 枚举 |
| 重命名字段 | 是 | 升 `schema_version`，旧档案需迁移 |
| 删除字段 | 是 | 升 `schema_version` |
| 修改 YAML 子集约束 | 是 | 升 `schema_version` |

消费者遇到**高于自己支持的 `schema_version`** → 停止并提示用户升级 skill，不要猜测解析。

### 不属于本契约的文件

**`FEEDBACK.jsonl` 不在本契约内。** 它由 summon 写入**自己的**人格目录（`~/.claude/skills/<slug>-persona/FEEDBACK.jsonl`），规范见 拘神.skill 的 `roster-format.md`。

这是刻意的归属划分：

| 数据 | 归属 | 谁能写 |
|------|------|--------|
| `distilled/<slug>/` 下的一切 | distill | **只有 distill** |
| `~/.claude/skills/<slug>-persona/` 下的一切 | summon | **只有 summon** |

distill 在用户主动运行「补充蒸馏」时**只读**人格目录的 `FEEDBACK.jsonl`，用于发现缺口。**任何一方都不写对方的地盘**——这是两个 skill 能保持独立通用的前提。

## 六、最小合法示例

```markdown
---
schema_version: 1
schema: topic
slug: anti-fragile-decision
title: 反脆弱决策 · 认知档案
created: 2026-09-22
updated: 2026-09-22
version: 1
sources_total: 12
sources_primary: 7
sources_secondary: 5
confidence: {A: 5, B: 4, C: 3, D: 0}
source_words: 96000
distillate_words: 4200
compression_ratio: "23:1"
dimensions: [领域共识, 流派分歧, 关键概念, 经典案例, 争议前沿, 演进脉络]
gaps: []
---

# 反脆弱决策 · 认知档案

## 一句话
用凸性暴露替代风险预测：不猜黑天鹅，而是让自己从波动中获益。

## 核心骨架
- 预测系统性失效，但暴露设计可工程化（A）
- 杠铃策略：极端保守 + 极端激进，砍掉中间（A）
- 可选择性 > 正确性（B）
...
```

## 七、EVALS.jsonl（评测历史）

**问题**：`QUALITY.md` 每次重跑评分都被覆盖，分数历史随之销毁——无法回答「这版比上版好在哪」。

**解法**：`EVALS.jsonl` 追加式记录，**只增不改**。每行一条独立的评测记录。

```json
{"schema_version":1,"run_id":"2026-09-22T10:30:00Z","version":3,
 "date":"2026-09-22","artifact_sha256":"3a71…",
 "models":{"answer":"claude-sonnet-5","score":"claude-opus-5"},"scorers":2,
 "questions":[
   {"id":"q1","kind":"known","text":"…","status":"active"},
   {"id":"q4","kind":"gap","text":"…","status":"retired","retired_reason":"该缺口已补，题目失效"}
 ],
 "scores":{"覆盖度":18,"信度":16,"浓度":15,"可溯源性":12,"矛盾保留":13,"缺口诚实":8},
 "total":82,"grade":"B","notes":"…"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `schema_version` | ✅ | 当前 `1` |
| `run_id` | ✅ | 唯一标识（建议 ISO8601 时间戳） |
| `version` | ✅ | 被评测档案的 `version` |
| `artifact_sha256` | ✅ | 被评测档案的内容哈希，用于确认评的是哪一版 |
| `models` | ✅ | `{answer, score}` 两个模型标识——**评分必须独立于答题** |
| `scorers` | ✅ | 评分 agent 数量。**`<2` 时 `compare` 拒绝给出趋势结论** |
| `questions` | ✅ | **题目内嵌在记录里**，不做全局题库。含 `id` / `kind` / `text` / `status` |
| `questions[].status` | ✅ | `active` / `retired`。**缺口被补上后必须标 `retired`** |
| `scores` / `total` / `grade` | ✅ | 各维度得分与总分等级 |

### 为什么题目内嵌而不做全局题库

- 档案内容会变（缺口被补、条目被修正），**全局固定题库会与档案脱节**
- 缺口题尤其危险：缺口补上后，正确答案从「拒答」变成「真答」，而评分规则仍把拒答记为正确 → **越完整的档案分越低**（虚假退步）
- 所以：题目随记录冻结，缺口补上后把该题标 `retired`，`compare` 显式提示「本次对比无效」

### 追加纪律

- **只追加，不修改历史行**。发现记错 → 追加一条更正记录，不改旧行
- 每条必须带 `models` 与 `scorers`——没有这两个字段，分数不可信
- `eval_record.py` 负责写入与对比，见其 docstring
