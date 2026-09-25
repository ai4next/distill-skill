# 蒸馏档案格式契约（Artifact Contract）

> 本文件定义**蒸馏档案**这一产物的格式契约——它是本 skill 的对外格式规范，不绑定任何具体消费者。
>
> 蒸馏流程按此格式**写**；任何要读这份档案的下游（人或工具）按此格式**读**。
> 改格式必须先改本文件并升 `schema_version`；`scripts/` 只是本契约的可执行形式。

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
├── QUALITY.md         # 蒸馏质量评分卡（Phase 5 产出，**每次重跑会被覆盖**）
└── REFINE.md          # 对抗精炼补丁候选清单（Phase 5.5 产出，见 adversarial-refine.md）
```

> **`QUALITY.md` 与 `REFINE.md` 都是快照**（重跑覆盖），`EVALS.jsonl` 是流水（只追加）。
> 三者并存不是冗余：快照回答「现在怎么样」，流水回答「这版比上版好在哪」。

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
| `confidence` | ✅ | 信度四级分布（见 `distillation-framework.md`） |
| `source_words` / `distillate_words` / `compression_ratio` | ✅ | 蒸馏比 = 素材总字数 : 档案字数 |
| `dimensions` | ✅ | 维度名列表，顺序对应 `research/` 文件编号 |
| `gaps` | ✅ | 信息缺口列表，**允许为空列表但必须存在**（空表示无已知缺口） |

**`null` 与 `0` 的区别（重要）**：frontmatter 里的计数字段在**交付时必须已回填**，
因为到 Phase 3 结束时 agent 已经知道这些数。**不要用 `0` 冒充「还没数」**：

| 写法 | 含义 | 允许出现在 |
|------|------|-----------|
| `sources_primary: 0` | 判定结果：确实没有一手来源 | frontmatter（已判定） |
| `sources_primary: null` | 未回填 | **manifest.json**（Phase 3 前） |
| `gaps: []` | 判定结果：确实无已知缺口 | frontmatter + manifest |
| `gaps:`（留空） | 未回填 → **质检判 FAIL** | 不允许 |

> 这条规则是铁律 1「不知道就说不知道」在数据层的体现。
> 把「未回填」写成 `0` 会让下游（评分卡的覆盖度规则、`meta_scan.py` 的互补缺口）
> 把「没数」当成「数出来是零」，从而得出错误结论。

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
| `…（A 方案）` | ❌ 视为正文括号，不当作元数据 |
| 行中间出现 `（A）` | ❌ 只认**行尾**元数据 |

**可接受的出处指针**（`_lib.has_source_pointer`）：`sources/…` 相对路径、
带扩展名的文件名、`http(s)://` URL、`§段名`、`[S003]` 素材号。

> `quality_check.py` 会**硬性**检查骨架条目有没有信度标记，
> 并把「缺出处指针」列为**软诊断**（有指针 ≠ 指针为真；
> 真伪只能由拿到 `sources/` 的 agent 在 Phase 5 溯源抽查时核对）。

### 2.4 正文骨架

正文分两部分：**通用段**（所有 schema 共有，下游强依赖）+ **schema 专属段**。

```markdown
# <title>

## 一句话
[一句话概括这份档案的骨架，≤50 字]

## 核心骨架
[本档案最重要的 N 条主张/框架，每条一行，带信度标记与出处指针]

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
| `sources_primary` / `sources_secondary` | 一手/二手来源计数。**脚本无法自动判定**，未回填时写 `null`（**不是 `0`**），由 agent 在 Phase 3 回填 |
| `sources[].origin` | `local`（用户提供/已下载）或 `web`（仅记 URL，不落盘） |
| `sources[].type` | `book` / `transcript` / `article` / `notes` / `chat` / `video` / `code` / `other` |
| `sources[].sha256` | 内容哈希，**增量蒸馏的判重依据**，也是跨档案来源重叠检测的键 |
| `dimensions[].status` | `complete` / `partial` / `missing` |
| `dimensions[].coverage` | 0-100，该维度信息覆盖度。**未回填写 `null`**——`0` 是「判定为没有覆盖」，`null` 是「还没判」 |
| `dimensions[].sources` / `dimensions[].confidence` | 同上：未回填写 `null` |
| `changes[]` | 追加式变更日志，**不覆盖历史** |
| `meta_sources` | **综合档案专用**：被综合的档案 slug 列表；普通档案为 `null` |
| `source_overlap` | **综合档案专用**：来源重叠检测结果，如 `[{"archives": ["munger","buffett"], "shared": ["sources/books/berkshire-letters.pdf"]}]`。**重叠的档案不构成独立佐证**，见 `meta-synthesis.md` |
| `distillate_sha256` | 主档案 `DISTILLATE.md` 的内容哈希（sha256 of raw bytes），由 **`seal.py`** 写入。下游消费者据此判断「手里的产物是否还基于当前这版档案」（消费者拿得到档案文件时可直接哈希比对；本字段是异地兜底与镜像） |

**`distillate_sha256` 由脚本写入，不要手填**：

```bash
python3 scripts/seal.py distilled/<slug>            # 封存（写入哈希）
python3 scripts/seal.py distilled/<slug> --check    # 只校验（CI / 质检用）
```

档案内容一改，哈希就过期。`quality_check.py` 会检查这一点——
**哈希过期 = 下游的漂移检测会给出错误结论**，所以是硬性 FAIL 而不是提醒。

> **`null` 语义的迁移说明**：本约定之前，`ingest.py` 把脚本无法判定的字段一律写 `0`，
> 于是「未回填」与「判定为 0」无法区分。新版 `ingest.py` 会在**无歧义**时把旧默认值
> （`coverage=0` 且 `sources=0/null` 且 `confidence` 全 0）迁移成 `null`；
> 真判定（如一手 0、二手 5）不会被误迁移。这属于**语义澄清**，非 breaking 变更，
> 故 `schema_version` 仍为 `1`（`distillate_sha256` 字段本身未变，算法也未变）。

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
| 新增可选字段 | 否 | 直接加，不升版本 |
| 新增 `meta_sources` / `source_overlap` / `EVALS.jsonl` | 否 | 已加，不升版本 |
| 新增 schema 预设 | 否 | 加文件 + 更新 `schema` 枚举 |
| 重命名字段 | 是 | 升 `schema_version`，旧档案需迁移 |
| 删除字段 | 是 | 升 `schema_version` |
| 修改 YAML 子集约束 | 是 | 升 `schema_version` |

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
- **`artifact_sha256` 与 `version` 用 `--artifact` 自动填**，不要手抄：

  ```bash
  python3 scripts/eval_record.py record --file distilled/<slug>/EVALS.jsonl \
      --json '<记录 JSON>' --artifact distilled/<slug>
  ```

  手抄 64 位哈希必然出错，而这个字段是「这次评的到底是哪一版」的唯一依据。

---

## 八、校验工具与契约同步

**契约的权威定义是本文件**，`scripts/` 下的工具只是它的**可执行形式**。改一边必须改另一边。

| 工具 | 职责 | 读写 |
|------|------|------|
| `scripts/_lib.py` | **唯一事实源**：契约常量（字段/schema/维度/素材类型）、frontmatter 子集解析、信度统计、表格渲染、哈希 | 库，不执行 |
| `scripts/ingest.py` | 素材归集；生成/增量更新 `manifest.json` | 写 manifest |
| `scripts/seal.py` | 计算并写入 `distillate_sha256`（`--check` 只校验） | 写 manifest 一个字段 |
| `scripts/quality_check.py` | **7 项结构检查** + 软诊断（本契约的可执行形式） | 只读 |
| `scripts/distill_report.py` | Phase 1.5 / 2.5 检查点摘要表 | 只读 |
| `scripts/meta_scan.py` | 跨档案：来源重叠 / slug 碰撞 / 候选对照矩阵 / 互补缺口 | 只读（`--out` 写 `meta_scan.json`） |
| `scripts/eval_record.py` | `EVALS.jsonl` 写入 / 历史 / 对比 | 只追加 |

### 8.1 七项硬检查（`quality_check.py`）

| # | 检查 | 依据 |
|---|------|------|
| 1 | frontmatter 完整性（字段 + schema 枚举 + `schema_version` 受支持） | §2.2 / §五 |
| 2 | 核心骨架 3-10 条 | `distillation-framework.md` §十 |
| 3 | 正文有信度标记且 D 级 <20% | 铁律 3 |
| 4 | 矛盾已分类且**无和稀泥式调和** | 铁律 2 / framework §五 |
| 5 | `gaps` 已回填；`gaps` 空但存在 `coverage<40` 的维度 → 判装懂 | `quality-scorecard.md` 缺口诚实 |
| 6 | 浓度每千字 5-20 条独立条目 | framework §七 |
| 7 | manifest 契约字段齐备 + `distillate_sha256` 已封存且未过期 | §三 |

**软诊断**（只提示，不影响通过判定）：前后端信度分布不一致、骨架条目缺出处指针、
`coverage` / 一手二手计数未回填、自报字数与压缩比和实测值偏差、manifest 与正文 `version` 不一致、
维度状态与 `research/` 底稿对不上。软诊断是给 agent 的线索，**不是评分**。

```bash
python3 scripts/quality_check.py distilled/<slug>          # 人读
python3 scripts/quality_check.py distilled/<slug> --json   # 机器读
```

### 8.2 改动纪律

1. **改字段名 / 枚举 / `sources/` 子目录名** → 同时改本文件与 `scripts/_lib.py`；
   `test/test_distill.py::TestContractSync` 会检查两边是否同步。
2. **改检查规则** → 同时改本文件 §8.1 与 `quality_check.py`。
3. **改 `_lib.sha256_file`** → 等于让所有基于旧哈希的下游产物误报漂移（算法是契约的一部分），不要动。
4. 改完跑测试：`python3 -m unittest discover -s test -v`
