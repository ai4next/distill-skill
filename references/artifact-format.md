# 蒸馏档案格式契约

> 本文件定义**蒸馏档案**这一产物的格式契约——它是本 skill 的对外格式规范，不绑定任何具体消费者。
>
> 蒸馏流程按此格式**写**；任何要读这份档案的下游（人或工具）按此格式**读**。
> 改格式必须先改本文件并升 `schema_version`；`scripts/` 只是本契约的可执行形式。

## 目录

| 节 | 内容 | 谁需要读 |
|----|------|---------|
| [一](#一目录结构) | 目录结构 | 所有人 |
| [二](#二distillatemd) | `DISTILLATE.md`（[2.1 YAML 子集](#21-yaml-子集约束重要) · [2.2 frontmatter 字段](#22-frontmatter-字段) · [2.3 出处与信度标记](#23-出处与信度标记写法可机械检查) · [2.4 正文骨架](#24-正文骨架)） | 写档案的 agent |
| [三](#三manifestjson) | `manifest.json` | 写档案的 agent、增量蒸馏 |
| [四](#四消费规则消费者侧强制) | 消费规则 | **下游消费者** |
| [五](#五版本兼容) | 版本兼容 | 下游消费者 |
| [六](#六最小合法示例) | 最小合法示例 | 第一次写档案时先看这个 |
| [七](#七evalsjsonl评测历史) | `EVALS.jsonl` | 跑评分卡时 |
| [八](#八校验工具与契约同步) | 校验工具与契约同步 | 改契约或改脚本时 |

## 一、目录结构

档案落在**用户工作区**，不在任何 skill 仓库内部（skill 必须自包含，档案属于用户数据）。

```
distilled/<slug>/
├── DISTILLATE.md      # 主档案（人可读 + 机器可消费）—— 消费入口
├── manifest.json      # 素材清单、维度状态、缺口、变更记录 —— 增量蒸馏的依据
├── research/          # 分维度提炼底稿
│   ├── 01-<dim>.md
│   └── ...
├── sources/           # 原始素材（本地归集；网络来源记 URL 不落盘）
│   ├── books/  transcripts/  articles/  notes/
│   └── chat/  code/  video/  other/
├── EVALS.jsonl        # 评测历史（追加式，**每次评分都记，不被覆盖**）——见 §七
├── QUALITY.md         # 蒸馏质量评分卡（Phase 5 产出，**每次重跑会被覆盖**）
└── REFINE.md          # 对抗精炼补丁候选清单（Phase 5.5 产出，见 adversarial-refine.md）
```

> **`QUALITY.md` 与 `REFINE.md` 都是快照**（重跑覆盖），`EVALS.jsonl` 是流水（只追加）。
> 三者并存不是冗余：快照回答「现在怎么样」，流水回答「这版比上版好在哪」。

> **综合档案**（由 N 份档案综合而来）沿用 `topic` schema，`sources[]` 存的是**那 N 份档案**，见 `meta-synthesis.md`。

`sources/` 的子目录名与 `manifest.json` 中 `sources[].type` **一一对应**——`sources[].type` 的枚举是 `books` / `transcripts` / `articles` / `notes` / `chat` / `code` / `video` / `other`，便于脚本按目录反推类型。

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
gaps:                     # 信息缺口，下游必须映射为「诚实边界 / 局限说明」
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
| `confidence` | ✅ | 信度四级分布（见 `distillation-framework.md` §三） |
| `source_words` / `distillate_words` / `compression_ratio` | ✅ | 蒸馏比 = 素材总字数 : 档案字数。`compression_ratio` **由 `seal.py` 从另两个数派生**，不要手算 |
| `dimensions` | ✅ | 维度名列表，顺序对应 `research/` 文件编号 |
| `gaps` | ✅ | 信息缺口列表，**允许为空列表但必须存在**（空表示无已知缺口） |

#### `null` 与 `0` 的区别（本契约的诚实性基石）

这是 framework §六「区分『没看』与『没有』」在数据层的落地。**混淆会让下游把「没数」
当成「数出来是零」**，从而得出错误结论。

| 写法 | 含义 | 允许出现在 |
|------|------|-----------|
| `sources_primary: 0` | 判定结果：确实没有一手来源 | frontmatter（已判定） |
| `sources_primary: null` | 未回填 | **manifest.json**（Phase 3 前） |
| `coverage: 0` | 判定结果：该维度确实没覆盖 | manifest |
| `coverage: null` | 未回填 | **manifest**（Phase 3 前） |
| `gaps: []` | 判定结果：确实无已知缺口 | frontmatter + manifest |
| `gaps:`（留空） | 未回填 → **质检判 FAIL** | 不允许 |

**frontmatter 里的计数字段在交付时必须已回填**——到 Phase 3 结束时 agent 已经知道这些数，
用 `0` 冒充「还没数」是装懂。`manifest.json` 在 Phase 3 之前可以是 `null`。

#### 测不到的数写 `null`，不要估

`source_words` 对文本素材由 `ingest.py` 自动统计；**二进制素材（PDF/EPUB/视频）脚本抽不出文本**，
此时写 `null` 并列入软诊断，由 agent 在 Phase 1 用文档读取工具抽取后回填。

**要求一个流程拿不到的数，就是在训练 agent 估算**——这与铁律 1 直接冲突。
所以契约允许 `null`，而不是逼出一个看起来精确的假数字。同理，`compression_ratio`
是 `source_words / distillate_words` 的商，属于**派生值**：`seal.py` 会在封存时自动写入，
两个数任一为 `null` 时则不派生（保持原值）。**不要手算**——手算的比值会和实测值
在软诊断里对不上，那是一次纯粹自找的告警。

> **迁移说明**：本约定之前，`ingest.py` 把脚本无法判定的字段一律写 `0`，于是「未回填」与
> 「判定为 0」无法区分。新版 `ingest.py` 会在**无歧义**时把旧默认值（`coverage=0` 且
> `sources=0/null` 且 `confidence` 全 0）迁移成 `null`；真判定（如一手 0、二手 5）不会被误迁移。
> 这属于**语义澄清**，非 breaking 变更，故 `schema_version` 仍为 `1`。

### 2.3 出处与信度标记写法（可机械检查）

正文里**每条主张**都要能回答两个问题：**多可信**（信度 A/B/C/D）与**从哪来**（出处指针）。
推荐把两者写在行尾的同一对括号里，中间用 `·` 分隔：

```markdown
## 核心骨架
- 用可逆性判断替代预测，只在错了也不致命时下注（A · sources/notes/note1.md）
- 反过来想：先问什么会导致失败，再倒推该做什么（A · sources/books/x.pdf）
- 激励机制错，人就做错事，先看激励再看人（B · §决策启发式）
```

| 写法 | 是否被识别 |
|------|-----------|
| `…（A）` | ✅ 信度 |
| `…（A · sources/books/x.pdf）` | ✅ 信度 + 出处 |
| `…（B \| §决策启发式）` | ✅ 信度 + 出处（`\|` 也作分隔符） |
| **带「信度」列的表格**：表头写 `信度`，数据行写裸字母 | ✅ 信度（见下） |
| `…（A 方案）` | ❌ 视为正文括号，不当作元数据 |
| 行中间出现 `（A）` | ❌ 只认**行尾**元数据 |
| 无「信度」列名的表格里的裸字母 | ❌ 不认 |

**表格写法**：`schema-*.md` 的专属段大量规定用带「信度」列的表格。表头**必须**有一列叫
`信度`，数据行的该列写裸字母（`A` / `B` / `A 级`）：

```markdown
| 场景 | 启发式 | 反例 / 失效条件 | 信度 |
|------|--------|----------------|------|
| 面对高收益承诺 | 先问最坏情况是否致命 | 收益不可验证时失效 | A |
```

列名给了语义，所以不必猜单元格内容；反过来，**没有列名的表格一律不认**——
中文正文里 `附录（A）`、`图（B）` 这类写法太常见，宽松匹配会虚增分母、稀释 D 级占比。

> **为什么信度必须能被机械数出来**：D 级占比 ≤20% 是铁律 3 的硬指标，
> 而「正文有没有信度标记」是第 5 项结构检查。若契约规定的写法与脚本能识别的
> 写法不一致，照契约写的档案会被系统性少计、甚至误判 FAIL——**检查在惩罚正确输出**。
> 所以写法表与 `_lib.count_confidence` 必须一一对应，改一边必须改另一边。

**可接受的出处指针**（`_lib.has_source_pointer`）：`sources/…` 相对路径、
带扩展名的文件名、`http(s)://` URL、`§段名`、`[S003]` 素材号。

> `quality_check.py` 会**硬性**检查**核心骨架的每条**都同时带信度标记与出处指针
> （第 4 项；铁律 3 明写「无信度标记的条目视为不合格」，本节开头明写「每条主张都要能
> 回答两个问题：多可信、从哪来」）。骨架之外的条目仍只进软诊断。
> **有指针 ≠ 指针为真**——真伪只能由拿到 `sources/` 的 agent 在 Phase 5 溯源抽查时核对。

### 2.4 正文骨架

正文分两部分：**通用段**（所有 schema 共有，下游强依赖）+ **schema 专属段**。

```markdown
# <title>

## 一句话
[一句话概括这份档案的骨架，≤50 字]

## 核心骨架
[本档案最重要的 N 条主张/框架，每条一行，带信度标记与出处指针；3-10 条]

## 心智模型 / 核心框架
### <名称>
**一句话**：…
**证据**：…（≥2 个不同场景，标注信度等级）
**生成力**：能推断出什么新立场
**局限**：什么情况下失效

## 表达特征
[仅 person 类需要（含虚构角色）；topic / document 写「语域与风格」]

## 矛盾与张力
[保留张力，不要否认对立。标注类型：时间性 / 领域性 / 本质性张力。
 确实核查过且没有矛盾时，显式写「未发现矛盾」并说明核查范围——
 留空或不置一词会判 FAIL，因为无法区分「真的没有」与「没看」。
 判据与三类张力的定义见 framework §五]

## 信息缺口
[与 frontmatter 的 gaps 一致，可展开说明]

## 变更记录
| 日期 | 动作 | 说明 |
|------|------|------|
```

**schema 专属段**由各 schema 文件定义（`schema-person.md` / `schema-topic.md` / `schema-document.md`），插在「核心骨架」与「矛盾与张力」之间。

`custom` schema **没有专属段**：自定义的是 `research/` 的维度划分（2-8 个，编号 `01`-`08`），
`DISTILLATE.md` 正文只用上面这套通用段。这样 `quality_check.py` 的 12 项结构检查
（都只看通用段）对 `custom` 依然成立。

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
| `sources_primary` / `sources_secondary` | 一手/二手来源计数。**脚本无法自动判定**，未回填时写 `null`（**不是 `0`**），由 agent 在 Phase 3 回填 |
| `sources[].origin` | `local`（用户提供/已下载）或 `web`（仅记 URL，不落盘） |
| `sources[].type` | 素材类型，枚举与 `sources/` 子目录名一一对应（复数）：`books` / `transcripts` / `articles` / `notes` / `chat` / `code` / `video` / `other` |
| `sources[].sha256` | 内容哈希，**增量蒸馏的判重依据**，也是跨档案来源重叠检测的键 |
| `dimensions[].status` | `complete` / `partial` / `missing` |
| `dimensions[].coverage` | 0-100，该维度信息覆盖度。**未回填写 `null`**（`0` 是「判定为没有覆盖」，见 §2.2） |
| `dimensions[].sources` / `dimensions[].confidence` | 同上：未回填写 `null` |
| `changes[]` | 追加式变更日志，**不覆盖历史** |
| `meta_sources` | **综合档案专用**：被综合的档案 slug 列表；普通档案为 `null` |
| `source_overlap` | **综合档案专用**：来源重叠检测结果，如 `[{"archives": ["munger","buffett"], "shared": ["sources/books/berkshire-letters.pdf"]}]`。**重叠的档案不构成独立佐证**，见 `meta-synthesis.md` §三 |
| `heldout` | **留出验证专用**：被留出、未交给提炼 agent 的素材相对路径列表。Phase 0 决定，Phase 5 用它做生成力的 ground truth（见 `quality-scorecard.md`）。不做留出时为 `[]` |
| `questions` | **冻结的评测题目**：Phase 2 之前从 `sources/` 出题后落盘，此后不得增删改。每项含 `id` / `kind`（`generative` / `gap`）/ `text` / `status`（`active` / `retired`）。**先有题、后有档案**——这是防出题污染的唯一办法 |
| `distillate_sha256` | 主档案 `DISTILLATE.md` 的内容哈希（sha256 of raw bytes），由 **`seal.py`** 写入。下游消费者据此判断「手里的产物是否还基于当前这版档案」 |

**`distillate_sha256` 由脚本写入，不要手填**：

```bash
python3 scripts/seal.py distilled/<slug>            # 封存（写入哈希）
python3 scripts/seal.py distilled/<slug> --check    # 只校验（CI / 质检用）
```

档案内容一改，哈希就过期。`quality_check.py` 会检查这一点——
**哈希过期 = 下游的漂移检测会给出错误结论**，所以是硬性 FAIL 而不是提醒。

## 四、消费规则（消费者侧强制）

任何读取本档案的下游（人、工具、另一个 skill）都应遵守：

1. **必读**：`DISTILLATE.md` 的 frontmatter + 正文；`manifest.json` 的 `sources` 与 `gaps`
2. **只读不写**：消费者**绝不修改档案**。发现档案不足 → 回报用户，建议回到蒸馏流程补维度或补素材
3. **缺口映射**：`gaps` 与 `confidence` 中 D 级占比高的维度，**必须**映射为下游产物中的「诚实边界 / 局限说明」
4. **来源映射**：`manifest.json` 的 `sources` 映射为下游产物的「信息源」说明，标注一手/二手
5. **溯源标记**：下游产物应记录来源档案的 `slug` 与铸造时的 `distillate_sha256`，以便检测档案漂移

> **档案是只读输入，不是可编辑的中间态。** 下游产物与档案之间的漂移只能靠
> 「重新消费当前档案」来消除，**不能靠改档案去迁就产物**——那会污染档案的可信度。

## 五、版本兼容

| 变更类型 | 是否 breaking | 处理 |
|---------|--------------|------|
| 新增可选字段、新增 schema 预设、新增附属文件（`meta_sources` / `source_overlap` / `EVALS.jsonl`） | 否 | 直接加，不升版本 |
| 重命名字段 / 删除字段 / 修改 YAML 子集约束 | 是 | 升 `schema_version`，旧档案需迁移 |

消费者遇到**高于自己支持的 `schema_version`** → 停止并提示用户升级，不要猜测解析。

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
- 预测系统性失效，但暴露设计可工程化（A · sources/books/antifragile.pdf）
- 杠铃策略：极端保守 + 极端激进，砍掉中间（A · sources/books/antifragile.pdf）
- 可选择性 > 正确性（B · §关键概念）

## 矛盾与张力
**领域性张力**：在个人财务上主张极端保守，在创业投入上主张极端激进——
条件差异在于「可承受的最大损失」不同（A · sources/books/antifragile.pdf）。
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
 "scores":{"生成力":16,"覆盖度":12,"信度":13,"浓度":12,"可溯源性":8,"矛盾保留":13,"缺口诚实":8},
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
| `scores` / `total` / `grade` | ✅ | 各维度得分与总分等级。维度名与分值见 `quality-scorecard.md`（七维，`_lib.SCORECARD_DIMENSIONS` 是其可执行常量，合计 100） |

### 为什么题目内嵌而不做全局题库

- 档案内容会变（缺口被补、条目被修正），**全局固定题库会与档案脱节**
- 缺口题尤其危险：缺口补上后，正确答案从「拒答」变成「真答」，而评分规则仍把拒答记为正确 → **越完整的档案分越低**（虚假退步）
- 所以：题目随记录冻结，缺口补上后把该题标 `retired`，`compare` 显式提示「本次对比无效」

### 追加纪律

- **只追加，不修改历史行**。发现记错 → 追加一条更正记录，不改旧行
- 每条必须带 `models` 与 `scorers`——没有这两个字段，分数不可信
- **`artifact_sha256` 与 `version` 用 `--artifact` 自动填**，不要手抄（64 位哈希手抄必然出错，
  而它是「这次评的到底是哪一版」的唯一依据）：

  ```bash
  python3 scripts/eval_record.py record --file distilled/<slug>/EVALS.jsonl \
      --json '<记录 JSON>' --artifact distilled/<slug>
  ```

  `eval_record.py` 负责写入与对比，见其 docstring。

---

## 八、校验工具与契约同步

**契约的权威定义是本文件**，`scripts/` 下的工具只是它的**可执行形式**。改一边必须改另一边。

| 工具 | 职责 | 读写 |
|------|------|------|
| `scripts/_lib.py` | **唯一事实源**：契约常量（字段/schema/维度/素材类型）、frontmatter 子集解析、信度统计、表格渲染、哈希 | 库，不执行 |
| `scripts/ingest.py` | 素材归集；生成/增量更新 `manifest.json` | 写 manifest |
| `scripts/seal.py` | 计算并写入 `distillate_sha256`（`--check` 只校验） | 写 manifest 一个字段 |
| `scripts/quality_check.py` | **12 项结构检查** + 软诊断（本契约的可执行形式） | 只读 |
| `scripts/distill_report.py` | Phase 1.5 / 2.5 检查点摘要表 | 只读 |
| `scripts/meta_scan.py` | 跨档案：来源重叠 / slug 碰撞 / 候选对照矩阵 / 互补缺口 | 只读（`--out` 写 `meta_scan.json`） |
| `scripts/eval_record.py` | `EVALS.jsonl` 写入 / 历史 / 对比 | 只追加 |

### 8.1 十二项结构检查（`quality_check.py`）

**这十二项拦的是结构缺陷，不是内容真伪。** 它们能发现「缺段落」「信度没标」
「缺口没写」「哈希没封存」，但发现不了「推断编得像真的」——一份字段齐全、
标记规范的档案完全可能是编造的。**过了这十二项 ≠ 质量合格**，
只等于「没有结构性缺陷，值得花一次评分」。生成力与诚实度必须由独立 agent 跑
`quality-scorecard.md`，绝不能用静态检查代替。

| # | 检查 | 依据 |
|---|------|------|
| 1 | frontmatter 完整性（字段 + schema 枚举 + `schema_version` 受支持） | §2.2 / §五 |
| 2 | frontmatter 交叉校验（`dimensions` 与 schema 匹配 / `slug` 与目录名一致 / `sources_total == 一手 + 二手` / `confidence` 形如 `{A:n,…}` / 日期形态） | §2.2 |
| 3 | 核心骨架 3-10 条 | `distillation-framework.md` §十 |
| 4 | **骨架条目元数据**：每条骨架都带信度标记**且**带出处指针 | 铁律 3 / §2.3 |
| 5 | 正文有信度标记且 D 级 ≤20% | 铁律 3 |
| 6 | 矛盾已分类（类型词须**成标签**，如 `时间性张力`）或显式声明「未发现矛盾」且交代核查范围；**无否认对立式调和** | 铁律 2 / framework §五 |
| 7 | `gaps` 已回填；**缺口段非空**；`gaps` 空但存在 `coverage<40` 的维度 → 判装懂 | `quality-scorecard.md` 缺口诚实 |
| 8 | `manifest.sources` 非空（档案必须有素材依据） | 铁律 3 / §三 |
| 9 | 非 `missing` 的维度都有 `research/` 底稿 | §一 / §三 |
| 10 | `coverage` 与一手/二手计数不得停在 `null`（交付前须回填） | §2.2 |
| 11 | 浓度每千字 5-20 条独立条目（`###` 小节须有内容才算条目） | framework §七 |
| 12 | manifest 契约字段齐备 + `distillate_sha256` 已封存且未过期 | §三 |

> **第 4、7、8、9、10 项此前只是软诊断**，而评测的断言却承诺了它们——
> 承诺与执行对不上，评测就在说谎。现在落成硬检查：它们各自对应契约里一句明确的
> 要求（铁律 3、§2.2、§2.3、§三），不是新加的门槛。

> **检查 6 的两种合法写法**：① 给出张力并标注类型（时间性 / 领域性 / 本质性张力）；
> ② 确实核查过而无矛盾时，显式声明「未发现矛盾」**并说明核查范围**。
> 两者都没有 → FAIL。留空无法区分「真的没有」与「没看」——**不知道就说不知道**
> 意味着「没有」也必须被明确说出来，而不是靠沉默暗示。
> 长度门槛量在**声明句**上（`_lib.declaration_sentence`），不是整段上：
> 一句「未发现矛盾。」后面补几十个字凑长度不算交代核查范围。
>
> **类型词必须成标签**（`时间性张力` 而非孤立的「时间性」）：只做子串匹配时，
> 一句「按要求写出『时间性』这个词」就能让占位档案白拿这一项。
>
> **和稀泥拦的是「信息量净减少」，不是句式**（完整判据见 framework §五）。
> `HARMONY_RE` 只命中**否认对立**的断言（「其实两者并不冲突」「殊途同归」）。
> 匹配前会**剥掉引号内的引用**、并跳过前 16 字内有「禁止/避免/未使用」等否定词的
> **提及**——一份明确否定抹平写法的档案（「本节刻意未使用『其实两者并不冲突』这类
> 表述」）不该被判成和稀泥。剥离只影响判定，不改写正文。

**软诊断**（只提示，不影响通过判定）：前后端信度分布不一致、自报字数与压缩比和实测值偏差、
manifest 与正文 `version` 不一致、维度状态与 `research/` 底稿对不上、
矛盾段声明「未发现矛盾」、转折句式但缺类型标注。软诊断是给 agent 的线索，**不是评分**。

```bash
python3 scripts/quality_check.py distilled/<slug>          # 人读
python3 scripts/quality_check.py distilled/<slug> --json   # 机器读
```

### 8.2 改动纪律（工程类反模式的家）

以下几条反模式编号在 SKILL.md 的黑名单里（编号是外部契约，不要重排），细节在这里：

| # | 反模式 | 细节 |
|---|--------|------|
| 7 | 把档案塞进 skill 目录 | 档案属于用户工作区。skill 必须自包含，用户数据不属于 skill（§一） |
| 16 | 让脚本做语义判定 | 脚本只做机械抽取（对照矩阵、重叠检测、静态检查）。「这两条是不是在回答同一个问题」「是不是真对立」必须由 agent 读语义判断 |
| 17 | 缺口填上后不退役对应题目 | 缺口题的正确答案会从「拒答」变成「真答」，不标 `retired` 就会得出「越完整分越低」的假退步（§七） |
| 20 | 手抄 `artifact_sha256` / `version` | 用 `--artifact` 自动填（§七） |
| 21 | 档案改完不重新封存哈希 | 哈希过期 → 下游会误判「产物仍与档案同步」。`seal.py` 封存，`quality_check.py` 硬性拦截（§三） |

**改契约的纪律**：

1. **改字段名 / 枚举 / `sources/` 子目录名** → 同时改本文件与 `scripts/_lib.py`；
   `test/test_distill.py::TestContractSync` 会检查两边是否同步。
2. **改检查规则** → 同时改本文件 §8.1 与 `quality_check.py`。
3. **改 `_lib.sha256_file`** → 等于让所有基于旧哈希的下游产物误报漂移（算法是契约的一部分），不要动。
4. 改完跑测试：`python3 -m unittest discover -s test -v`
