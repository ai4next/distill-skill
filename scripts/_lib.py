#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 共享工具库（唯一事实源 / single source of truth）

本文件是所有 `scripts/` 下工具共用的底层实现：契约常量（字段、schema、维度、
素材类型）、frontmatter 子集解析、信度统计、终端表格渲染、哈希。

设计约束（改动前必读）：

  1. **契约的权威定义在 `references/artifact-format.md`**，本文件只是它的
     可执行形式。改字段名 / 枚举 / 目录名 → 必须同步改契约文档，两边不得漂移。
     （同族 craft-skill 的 `authoring-contract.md` ↔ `check.mjs` 是同一约定。）
  2. 本文件只做**机械**工作：解析、统计、渲染、哈希。
     语义判断（两条主张是否在回答同一个问题、某维度覆盖度打几分）**不在这里**，
     也不在任何脚本里——那是 agent 的活（见 SKILL.md 反模式 #16）。
  3. **纯标准库**。skill 必须自包含，不引入第三方依赖（Python 标准库无 yaml，
     所以 frontmatter 只支持契约限定的子集，见 `parse_frontmatter`）。
  4. 本文件是**库**，不是可执行脚本——没有 `main()`，不打印任何东西。

被谁用：ingest / seal / quality_check / distill_report / meta_scan / eval_record
"""

import hashlib
import json
import os
import re
import sys
import unicodedata

# --------------------------------------------------------------------------
# 契约常量（与 references/artifact-format.md 一一对应）
# --------------------------------------------------------------------------

#: 契约版本。消费者遇到高于此值的档案必须停止并提示升级，不得猜测解析。
SUPPORTED_SCHEMA_VERSION = 1

#: `DISTILLATE.md` frontmatter 必填字段。
REQUIRED_FIELDS = [
    "schema_version", "schema", "slug", "title", "created", "updated", "version",
    "sources_total", "sources_primary", "sources_secondary", "confidence",
    "source_words", "distillate_words", "compression_ratio", "dimensions", "gaps",
]

#: 四种 schema。`custom` 的维度由 `--dimensions` 传入。
SCHEMAS = ("person", "topic", "document", "custom")

#: 各预设 schema 的维度：(编号, 维度名, research/ 文件名)。
#: 与 references/schema-*.md 保持一致。
SCHEMA_DIMENSIONS = {
    "person": [
        ("01", "著作", "01-writings.md"),
        ("02", "对话", "02-conversations.md"),
        ("03", "表达", "03-expression-dna.md"),
        ("04", "他者", "04-external-views.md"),
        ("05", "决策", "05-decisions.md"),
        ("06", "时间线", "06-timeline.md"),
    ],
    "topic": [
        ("01", "领域共识", "01-consensus.md"),
        ("02", "流派分歧", "02-schools.md"),
        ("03", "关键概念", "03-concepts.md"),
        ("04", "经典案例", "04-cases.md"),
        ("05", "争议前沿", "05-frontier.md"),
        ("06", "演进脉络", "06-evolution.md"),
    ],
    "document": [
        ("01", "论点树", "01-argument-tree.md"),
        ("02", "证据链", "02-evidence-chain.md"),
        ("03", "术语表", "03-glossary.md"),
        ("04", "隐含假设", "04-assumptions.md"),
        ("05", "内部矛盾", "05-contradictions.md"),
        ("06", "信息缺口", "06-gaps.md"),
    ],
}

#: 各预设 schema 的**专属正文段**（标题须逐字，`section()` 严格匹配）。
#:
#: 与 `references/schema-*.md` 的「schema 专属正文段」小节保持一致。
#: 插在「核心骨架」与「矛盾与张力」之间，是各 schema 相对通用骨架的**独有交付物**
#: （document 的「可执行结论」、person 的「表达DNA」、topic 的「流派对比表」）。
#:
#: **不进 `quality_check.py` 的 12 项硬检查**：那 12 项是通用结构契约，
#: 对所有 schema 一致；专属段由 schema 文档的「硬性要求」约束，并由
#: `test_distill.py` 的同步测试逐字比对（本常量 ↔ schema 文档）。
SCHEMA_SECTIONS = {
    "person": ["身份与时间线", "心智模型", "决策启发式", "表达DNA",
               "价值观与反模式", "智识谱系"],
    "topic": ["框架总览", "流派对比表", "概念词典", "案例库", "适用边界"],
    "document": ["论点树（含层级）", "证据链映射", "术语表", "隐含假设清单",
                 "可执行结论"],
}

#: 扩展名 → 素材类型。**类型名 == `sources/` 子目录名**，两者必须一致。
TYPE_BY_EXT = {
    "books": {".pdf", ".epub", ".mobi", ".azw3", ".djvu"},
    "transcripts": {".srt", ".vtt"},
    "articles": {".html", ".htm", ".mhtml", ".mht"},
    "notes": {".txt", ".md", ".markdown", ".rst", ".org", ".docx", ".doc"},
    "chat": {".jsonl", ".json"},
    "code": {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".kt", ".rs",
        ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".scala",
        ".sh", ".bash", ".zsh", ".sql", ".yaml", ".yml", ".toml", ".ini",
    },
    "video": {".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".m4a", ".wav", ".flac"},
}

#: `sources/` 下的全部子目录（= 素材类型 + other），按此顺序创建。
SOURCES_SUBDIRS = list(TYPE_BY_EXT.keys()) + ["other"]

#: 核心骨架条目数上下限。少于下限 = 没提炼，多于上限 = 没取舍。
#: 放在这里而不是散在检查函数里：它是契约的一部分（artifact-format.md §八、
#: distillation-framework.md §十都写这个数），测试靠它去核对文档没漂移。
SKELETON_MIN, SKELETON_MAX = 3, 10

#: 评分卡维度与分值（权威定义在 `references/quality-scorecard.md`）。
#:
#: **生成力排在第一位，且分值最高——因为它是判定线。**
#: 「拿产物去回答一个素材里没直接出现过、但相关的新问题。摘要答不了，蒸馏能答。」
#: 这条判定线把质量定义在**素材之外**，而覆盖度/信度/浓度/可溯源性/矛盾保留/
#: 缺口诚实六项测的全是「多忠实地搬了素材」。此前生成力只以「3 道题」的形式
#: 出现、**不占任何分值**，于是流程里最锋利的那句话在度量上等于不存在：
#: 一份完美的摘要能拿满分，而摘要不是蒸馏。
#:
#: 分值从覆盖度/信度/浓度各挪 5 分、可溯源性挪 5 分给生成力，总分仍为 100。
SCORECARD_DIMENSIONS = (
    ("生成力", 20),
    ("覆盖度", 15),
    ("信度", 15),
    ("浓度", 15),
    ("可溯源性", 10),
    ("矛盾保留", 15),
    ("缺口诚实", 10),
)
SCORECARD_TOTAL = sum(v for _, v in SCORECARD_DIMENSIONS)

#: 已知二进制：不做文本解码，`words` 记 null 由 agent 抽文本后回填。
BINARY_EXTS = {
    ".pdf", ".epub", ".mobi", ".azw3", ".djvu", ".docx", ".doc",
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".m4a", ".wav", ".flac",
}

#: 矛盾分类（见 distillation-framework.md §五）。
TENSION_TYPES = ("时间性", "领域性", "本质张力", "本质性张力")

#: 张力类型必须**成标签**才算数：`时间性张力` / `时间性矛盾` / `本质性张力`。
#:
#: 只做 `"时间性" in sec` 的子串匹配时，一句「本节尚无内容，但按要求写出『时间性』
#: 这个词」就能让「矛盾已分类」判 PASS——占位档案白拿一项。要求类型词与
#: 张力/矛盾/分歧 连用，仍然纯机械，但把「出现这个词」和「做了这个分类」区分开了。
TENSION_LABEL_RE = re.compile(r"(?:时间性|领域性|本质性?)\s*(?:张力|矛盾|分歧)")

#: 和稀泥 = **信息量净减少**，不是某种句式。
#:
#: 判据：把调和后的句子还原，还能不能取出被调和前的两条主张？
#:   `他在工作中主张放权、在家庭中事无巨细，因为他对「可控性」的权重随场景不同`
#:     → 两条主张都在，信息量**增加** → 这是**综合**，合法。
#:   `虽然他在工作中主张放权，但他在家庭中事无巨细，其实两者并不冲突`
#:     → 「并不冲突」抹掉了差异，读者再也取不出那条张力 → **和稀泥**，非法。
#:
#: 所以本正则只收**否认对立**的断言（抹平的实质），**不收裸的「虽然…但是」**：
#: 转折句式是描述张力的合法形式，用它写一条已分类的时间性/领域性张力
#: 恰恰是正确写法。把句式当罪证，等于惩罚正确输出，并诱导作者删掉真实矛盾
#: ——那正是铁律 2 要防的事。转折句式改由 `TURN_RE` 做**软诊断**（见下）。
HARMONY_RE = re.compile(
    r"其实(?:两者|二者)?(?:是)?(?:互补|一致|统一|相通)的?"
    r"|(?:两者|二者|二者之间|其实)并?不矛盾"
    r"|本质(?:上)?(?:是)?统一(?:的)?"
    r"|并不冲突"
    r"|殊途同归"
    r"|说到底是(?:同一|一)回事"
)

#: 转折句式。**它本身不是和稀泥**，只是抹平的高发句式。
#: 仅当矛盾段**没有任何张力类型标注**时，才作为软诊断提示复核：
#: 缺了类型标注的转折，多半是把矛盾揉成了温吞共识。有类型标注则完全合法。
TURN_RE = re.compile(r"虽然[^。；！？\n]{0,40}但是")

#: 显式声明「查过了，确实没有矛盾」。与 HARMONY_RE 是**相反**的两件事：
#:   HARMONY_RE 惩罚「有矛盾却抹平」；NO_TENSION_RE 承认「没有就是没有」。
#: 没有它，一份内部自洽的材料会被硬性要求编造一条矛盾出来——直接违反铁律 1。
#:
#: 收「未发现矛盾 / 未发现前后不一致」这类**主动声明核查过**的句式（含「任何」等
#: 插入语），不收裸的「无矛盾」：后者在正文里常是「两者无矛盾」这类被抹平的结论，
#: 正是 HARMONY_RE 要拦的东西。宁可漏认（退化成要求写类型词），不可误认。
NO_TENSION_RE = re.compile(
    r"未(?:发现|检出|见到|观察到)(?:任何)?(?:矛盾|前后不一致|自相矛盾|不一致之处)"
    r"|无内部矛盾"
    r"|不存在矛盾"
    r"|矛盾状态\s*[:：]\s*无"
)

#: 「未发现矛盾」声明的最小长度。一行「无矛盾。」就交差，大概率是漏读而非真的没有。
#: 低于此长度只提示不拦截（见 quality_check 的软诊断）——避免把诚实标注变成新的形式主义。
NO_TENSION_MIN_CHARS = 20

#: 显式空值记号。用于区分「未回填」（null）与「判定为零」（0）——
#: 这是本 skill 诚实哲学在数据层的体现（不知道就说不知道）。
NULL_TOKENS = ("null", "none", "nil", "~", "")

# --------------------------------------------------------------------------
# 正则
# --------------------------------------------------------------------------

CONF_LABEL_RE = re.compile(r"信度\s*[:：]\s*([ABCD])")
CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")
LATIN_RE = re.compile(r"[A-Za-z0-9]+")

#: 任意层级的 Markdown 标题：`## 核心骨架`。用于给 `section()` 的 miss 定位真因。
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)

#: Markdown 表格行与分隔行。schema-*.md 的专属段大量用「带信度列的表格」。
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

#: 表格「信度」列里的合法单元格。比裸字母多认一个「级」字（`A 级`），
#: 其余带中文的单元格一律不认——列名已给了语义，不必再猜。
TABLE_CONF_CELL_RE = re.compile(r"^([ABCD])\s*(?:级)?\s*$")

#: 核心骨架的顶层条目符号。`+` 与 `1)` / `1、` 都是合法 Markdown 列表，
#: 不认会让合法档案的骨架数量凭空少一条（进而撞上下限 FAIL）。
#:
#: 顿号分支用 `\s*` 而非 `\s+`：中文序号列表最常见的形式是「1、内容」**不带空格**。
#: `.` 和 `)` 分支仍要求空格——否则 `1.5 倍` 会被当成「第 1 条：5 倍」。
SKELETON_ITEM_RE = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+|\d+、\s*)(.+?)\s*$")

#: 引号包裹的片段。里面的字是**被引用的**，不是作者的主张——
#: 判定和稀泥时必须先剥掉，否则「本节刻意未使用『其实两者并不冲突』这类表述」
#: 会被当成和稀泥本身（惩罚正确输出）。
QUOTED_SPAN_RE = re.compile(
    r"「[^」]*」|『[^』]*』|“[^”]*”|\"[^\"]*\"|‘[^’]*’|《[^》]*》")

#: 「提及而非主张」的前置否定词。命中片段前 16 字内出现这些词，
#: 说明作者在**讨论**这种写法（禁止/避免/不使用），而不是在用它。
MENTION_GUARD_RE = re.compile(
    r"禁止|不许|不要|不得|避免|未使用|不使用|没有使用|刻意未|不采用|拒用|警惕")

# --------------------------------------------------------------------------
# frontmatter 子集解析（契约 §2.1）
# --------------------------------------------------------------------------


def strip_quotes(s):
    """去掉首尾成对的引号。"""
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def is_null(value):
    """判断一个值是否表示「未回填」。

    兼容三种来源：解析后的 `None`、旧档案里写成字符串的 `"null"`、
    以及 frontmatter 里留空的值。数值 `0` **不是** null——零是判定结果。
    """
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in NULL_TOKENS:
        return True
    return False


def parse_scalar(val):
    """解析一个 YAML 子集标量：行内列表 / 行内映射 / 普通标量。

    普通标量会做类型收敛：带引号的保持字符串，纯整数转 int，
    null 记号转 None。这样 `version: 3` 可直接参与比较，
    `meta_sources: null` 可被 `is_null()` 识别。
    """
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(x) for x in re.split(r"[,，]", inner)]
    if val.startswith("{") and val.endswith("}"):
        out = {}
        for part in re.split(r"[,，]", val[1:-1]):
            if ":" in part:
                k, _, v = part.partition(":")
                out[strip_quotes(k)] = parse_scalar(v)
        return out
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        return val[1:-1]          # 显式引号 → 恒为字符串
    if val.lower() in NULL_TOKENS:
        return None
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    return val


def parse_frontmatter(text):
    """解析契约限定的 YAML 子集，返回 `(frontmatter_dict, body)`。

    解析失败（无 frontmatter / 未闭合）返回 `(None, 原文)`。

    支持：`key: 标量` / `key: [行内列表]` / `key: {行内映射}` / `key:` + `- 项` 块列表。
    不支持（契约禁止）：嵌套多行映射、多行字符串、锚点别名、注释。
    """
    if text is None:
        return None, text
    text = text.lstrip("\ufeff")          # 容忍 BOM
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, text

    data, current_key = {}, None
    pending_empty = set()                  # 值为空但尚未收到块列表项的 key
    for line in lines[1:end]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and (line[:1] in (" ", "\t") or current_key):
            if current_key is not None and isinstance(data.get(current_key), list):
                data[current_key].append(parse_scalar(stripped[2:]))
                pending_empty.discard(current_key)
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if not val:
            data[key] = []
            current_key = key
            pending_empty.add(key)
        else:
            data[key] = parse_scalar(val)
            current_key = None
    # 空值且无块列表项 → 显式 null（「未回填」），而不是空列表
    for key in pending_empty:
        data[key] = None
    return data, "\n".join(lines[end + 1:])


def section(body, *titles):
    """取 `## <title>` 段的内容，直到下一个同级或更高级标题。

    传入多个标题时返回第一个命中的（用于兼容段名变体，如
    「心智模型 / 核心框架」与「核心框架」）。未命中返回 `None`。

    匹配是**严格的**：标题须逐字、独占一行、且为二级。`## 核心骨架（3-10 条）`
    或 `### 核心骨架` 都不算命中——契约就是这么定的。但 miss 时**必须能说清原因**，
    否则调用方只会得到「没提炼」这类指向错误根因的失败信息，agent 会去改内容，
    而真正的问题在标题格式。诊断见 `near_miss_headings`。
    """
    for t in titles:
        m = re.search(r"^##\s+" + re.escape(t) + r"\s*$(.*?)(?=^##\s|\Z)",
                      body, re.M | re.S)
        if m:
            return m.group(1)
    return None


def near_miss_headings(body, title):
    """找出「看着像目标段、其实不匹配」的实际标题，返回可读的诊断行列表。

    `section()` 只认逐字独占一行的 `## <title>`。写成带后缀的
    `## 核心骨架（3-10 条）`、或层级写错的 `### 核心骨架`，都会静默 miss。
    这里把这类标题找出来，让失败信息指向真正的根因（标题格式），
    而不是误导 agent 去改正文内容。
    """
    out = []
    for m in HEADING_RE.finditer(body or ""):
        level, text = len(m.group(1)), m.group(2).strip()
        if level == 2 and text == title:
            continue                              # 这就是正主，不是 near miss
        if text == title:
            out.append("%s %s（层级写错了：须为 `## %s`）"
                       % ("#" * level, text, title))
        elif title in text:
            out.append("%s %s（标题须逐字为 `## %s`，不能带后缀）"
                       % ("#" * level, text, title))
    return out


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------


def count_words(text):
    """CJK 按字计，拉丁按词计。与 ingest 的字数口径一致。"""
    if text is None:
        return 0
    return len(CJK_RE.findall(text)) + len(LATIN_RE.findall(text))


def table_conf_by_line(text):
    """找出「带信度列的 Markdown 表格」里的信度字母，返回 `{行号: 字母}`。

    `schema-person.md` / `schema-topic.md` / `schema-document.md` 的专属段
    大量规定用带「信度」列的表格（`| 场景 | 启发式 | 反例 | 信度 |`）。
    若只认行尾括号，照契约写的档案会被**系统性少计**；一份主要靠表格承载主张的
    档案甚至会误判「正文未检出任何信度标记」而硬性 FAIL——检查在惩罚正确输出。

    认的是**表头里明确写了「信度」那一列**的数据行：列名给了语义，比「行尾裸字母」
    安全得多（不会把正文里的 `附录（A）` 误吃进分母）。无表头或列名不符的表格不认。
    """
    lines = (text or "").splitlines()
    out = {}
    col = None
    for i, line in enumerate(lines):
        cells = _split_table_cells(line)
        if cells is None:
            col = None                            # 表格结束，列定义失效
            continue
        if col is not None and not TABLE_SEP_RE.match(line):
            if col < len(cells):
                m = TABLE_CONF_CELL_RE.match(cells[col])
                if m:
                    out[i] = m.group(1)
            continue
        # 当前行是表头？判据：下一行是分隔行，且本行有名为「信度」的列
        if (i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1])
                and "信度" in cells):
            col = cells.index("信度")
    return out


def _split_table_cells(line):
    """拆一行 Markdown 表格为单元格列表；不是表格行则返回 None。"""
    m = TABLE_ROW_RE.match(line)
    if not m:
        return None
    return [c.strip() for c in m.group(1).split("|")]


def count_confidence(text):
    """统计正文里的信度标记，返回 `{"A":n,"B":n,"C":n,"D":n}`。

    认三种写法：
    - **行尾**元数据：`…（A）` / `…（A · sources/x.md）` / `…（B | §段名）`
    - 显式标签：`信度: A`
    - **带「信度」列的表格**：表头声明列名，数据行写裸字母（见 `table_conf_by_line`）

    行中间的 `（A）` **不算**。契约 §2.3 明确把「行中间出现（A）」定义为非元数据；
    而且中文正文里 `附录（A）`、`图（B）` 这类写法很常见，宽松匹配会把它们
    误当成信度，从而虚增分母、稀释 D 级占比。

    同一行同时出现多种写法时**只计一次**：它们描述的是同一个标记，都数会让分母
    虚高，并把 D 级占比往重复字母的方向拉偏（重复的是 A 就低估 D 级占比，
    重复的是 D 就高估）。优先级：行尾元数据 > 表格信度列 > `信度: X` 标签。
    """
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    table = table_conf_by_line(text)
    for i, line in enumerate((text or "").splitlines()):
        _, conf = split_trailing_meta(line)
        if conf:
            counts[conf] += 1
            continue
        if i in table:
            counts[table[i]] += 1
            continue
        for m in CONF_LABEL_RE.finditer(line):
            counts[m.group(1)] += 1
    return counts


def conf_total(counts):
    """信度标记总数。"""
    return sum((counts or {}).get(k, 0) or 0 for k in "ABCD")


def d_ratio(counts):
    """D 级（推断）占比，返回 0-100 的浮点数；无标记时返回 0。"""
    total = conf_total(counts)
    if not total:
        return 0.0
    return 100.0 * ((counts or {}).get("D", 0) or 0) / total


def format_conf(counts):
    """把信度分布渲染成 `A22 B18 C8 D2`；无标记时返回 `—`。"""
    if not counts or not conf_total(counts):
        return "—"
    return "A%d B%d C%d D%d" % tuple((counts or {}).get(k, 0) or 0 for k in "ABCD")


#: 行尾元数据括号：`（A）` / `（A · sources/x.md）` / `[B | §决策启发式]`
#: 允许括号后再跟一个句末标点（`主张……（A · sources/x.md）。`）——LLM 写档案时
#: 很自然会这么收尾，若不容忍就会把整行判成「无信度标记」而硬性 FAIL。
TRAILING_META_RE = re.compile(
    r"[（(【\[]([^（）()【】\[\]]*)[）)】\]]([。．.；;，,]*)\s*$")

#: 独立的信度字母（前后不能再接字母，避免把 `AB` 里的 A 当信度）
STANDALONE_CONF_RE = re.compile(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])")

#: 元数据分隔符：信度与出处之间用它隔开
META_SEP_RE = re.compile(r"[·|,，/、]")


def split_trailing_meta(text):
    """拆出行尾的「信度 + 出处」元数据，返回 `(正文, 信度字母或 None)`。

    推荐的写法是**信度与出处一次写全**，可溯源性与信度同时可机械检查：

        `主张……（A · sources/books/x.pdf）`
        `主张……（A）`
        `主张……（B | §决策启发式）`

    不剥离 `（A 方案）` 这类正文括号——括号内含中文且没有元数据分隔符时，
    判定为正文而非元数据（宁可漏认，不可误吃正文）。
    """
    text = (text or "").strip()
    m = TRAILING_META_RE.search(text)
    if not m:
        return text, None
    inner = m.group(1)
    letters = STANDALONE_CONF_RE.findall(inner)
    if len(letters) != 1:
        return text, None
    rest = STANDALONE_CONF_RE.sub("", inner)
    if CJK_RE.search(rest) and not META_SEP_RE.search(inner):
        return text, None
    return text[:m.start()].strip(), letters[0]


def skeleton_items(body):
    """取「## 核心骨架」段的顶层条目。

    返回 `[(去元数据文本, 信度字母或 None, 是否有出处指针), ...]`。
    信度只认**行尾**元数据（`…（A）` 或 `…（A · sources/x.md）`）；
    出处指针判定见 `has_source_pointer`。

    只取**顶层**条目：缩进的子条目是对上一条的展开，不是并列的骨架条目，
    算进来会让骨架数量虚高（进而撞上 >10 的上限）。

    条目符号认 `-` `*` `+` 与 `1.` `1)` `1、`——不认后几种会让合法档案的骨架
    数量凭空少一条，进而撞上下限 FAIL。缩进（行首空白）不算条目。
    """
    sec = section(body, "核心骨架")
    if sec is None:
        return []
    out = []
    for line in sec.splitlines():
        m = SKELETON_ITEM_RE.match(line)
        if not m:
            continue
        raw = m.group(1)
        clean, conf = split_trailing_meta(raw)
        out.append((clean, conf, has_source_pointer(raw)))
    return out


def harmony_matches(text):
    """返回正文里**否认对立**式调和的命中片段列表（已排除引用与提及）。

    `HARMONY_RE` 本身是纯字符串匹配，分不清「主张」与「提及」。一份**明确否定
    抹平写法**的档案——「本节刻意未使用『其实两者并不冲突』这类抹平表述」——
    会被原样判成和稀泥并硬性 FAIL。这与曾经把「虽然…但是」当罪证是同一类错误：
    判据落在了字符串上，而不是落在「这句话是不是在抹平」上。

    所以这里做两层剥离：

    1. **剥引号**：`「」『』“”""《》` 里的字是被引用的，不是作者的主张。
    2. **剥提及**：命中片段前 16 字内出现 `MENTION_GUARD_RE` 的否定词
       （禁止 / 避免 / 未使用 / 警惕…），说明作者在**讨论**这种写法，不是在使用。

    宁可漏认（多拦一个没拦住的调和），不可误认（把否定抹平的句子判成抹平）——
    误认会训练作者删掉真实矛盾，那正是铁律 2 要防的事。
    """
    if not text:
        return []
    scrubbed = QUOTED_SPAN_RE.sub("", text)
    out = []
    for m in HARMONY_RE.finditer(scrubbed):
        left = scrubbed[max(0, m.start() - 16):m.start()]
        if MENTION_GUARD_RE.search(left):
            continue
        out.append(m.group(0))
    return out


def has_harmony(text):
    """正文里是否存在否认对立式调和（判据见 `harmony_matches`）。"""
    return bool(harmony_matches(text))


def labeled_tension_types(text):
    """返回正文里**成标签**出现的张力类型（去重，保持出现顺序）。

    「出现『时间性』三个字」不等于「做了时间性张力的分类」。判据见
    `TENSION_LABEL_RE`：类型词要与 张力/矛盾/分歧 连用。
    """
    out = []
    for m in TENSION_LABEL_RE.finditer(text or ""):
        label = re.sub(r"\s+", "", m.group(0))
        if label not in out:
            out.append(label)
    return out


def declaration_sentence(text):
    """返回「未发现矛盾」声明**所在的整句**；没有声明则返回空串。

    长度门槛必须量在**声明句**上，而不是整段上。量整段的话，
    「未发现矛盾。」后面接 30 个「哈」就能过——契约要的是「显式声明
    **并说明核查范围**」，即那句话本身得说清楚比对了什么。

    取句范围以 `。！？\n` 为界，所以「已比对全文各章节的立场陈述，
    未发现前后不一致。」整句都算进来（核查范围在声明之前，也该计入）。
    """
    m = NO_TENSION_RE.search(text or "")
    if not m:
        return ""
    bounds = "。！？\n"
    start = max([text.rfind(c, 0, m.start()) for c in bounds] + [-1]) + 1
    ends = [text.find(c, m.end()) for c in bounds]
    ends = [e for e in ends if e != -1]
    end = min(ends) + 1 if ends else len(text)
    return text[start:end].strip()


#: 出处指针：素材相对路径 / 文件名带扩展名 / URL / `§` 段锚点 / `[S003]` 素材号。
SOURCE_POINTER_RE = re.compile(
    r"sources/[\w./一-鿿-]+"
    r"|[\w一-鿿-]+\.(?:pdf|epub|srt|vtt|md|txt|html|json|jsonl|docx)"
    r"|https?://[^\s)>\]]+"
    r"|§\s*\S+"
    r"|\[S\d{3}\]"
)


def has_source_pointer(text):
    """判断一行文本里有没有可回查的出处指针。

    注意：这是**软诊断**用的启发式——有指针不等于指针是真的。
    真伪核对只能由拿到 `sources/` 的 agent 做（Phase 5 溯源抽查）。
    """
    return bool(SOURCE_POINTER_RE.search(text or ""))


# --------------------------------------------------------------------------
# 终端渲染（CJK 全角按 2 列计宽）
# --------------------------------------------------------------------------


def dw(s):
    """字符串的终端显示宽度：CJK 全角算 2 列。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
               for c in str(s))


def truncate(s, width):
    """按显示宽度截断，超出加省略号。"""
    s = str(s)
    if width <= 1:
        return ""
    if dw(s) <= width:
        return s
    out, used = "", 0
    for c in s:
        w = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        if used + w > width - 1:
            break
        out += c
        used += w
    return out + "…"


def render_table(header, groups, widths):
    """渲染终端表格，返回行列表（调用方自行 print）。

    `groups` 是「行组」列表，组与组之间用 `├─┼─┤` 分隔——
    用于表达「主体行 / 合计行」这类语义分组。
    """
    def rule(left, mid, right):
        return left + mid.join("─" * w for w in widths) + right

    def fmt_row(cells):
        out = "│"
        for i, w in enumerate(widths):
            c = cells[i] if i < len(cells) else ""
            s = truncate(c, w - 1)
            pad = w - dw(s) - 1
            out += " " + s + (" " * pad if pad > 0 else "") + "│"
        return out

    lines = [rule("┌", "┬", "┐")]
    if header is not None:
        lines.append(fmt_row(header))
        lines.append(rule("├", "┼", "┤"))
    for gi, rows in enumerate(groups):
        if gi:
            lines.append(rule("├", "┼", "┤"))
        for r in rows:
            lines.append(fmt_row(r))
    lines.append(rule("└", "┴", "┘"))
    return lines


# --------------------------------------------------------------------------
# 文件与哈希
# --------------------------------------------------------------------------


def sha256_file(path):
    """文件内容的 sha256（十六进制）；文件读不到时返回 `None`。

    **算法是契约的一部分**：`distillate_sha256` 用它，下游消费者也用它做漂移检测。
    改动哈希算法 = 让所有基于旧哈希的下游产物误报漂移。测试用黄金值钉死了它。

    读不到（权限、缺失、是目录）返回 `None` 而不是抛异常：调用方全是诊断工具，
    崩掉比报错更糟。调用方**必须**区分 `None`（读不到）与哈希串（读到了）——
    把 `None` 当成空串比较会让「读不到」伪装成「一致」，那是静默的错误通过。
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def sha256_text(text):
    """字符串的 sha256（UTF-8 编码）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path):
    """读文本文件，失败返回空串（只读工具不应因缺文件或编码异常而崩）。

    `UnicodeDecodeError` 必须一起接住：档案可能被 Windows 编辑器存成 GBK，
    或者 `--from-file` 喂进来的是一份非 UTF-8 的旧稿。只接 `OSError` 的话，
    整个 quality_check / seal / meta_scan 会带着 traceback 退出，
    而这几个脚本的定位是「诊断工具」——诊断工具崩掉比报错更糟。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def load_json(path, default=None):
    """读 JSON，失败返回 default。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_manifest(root_or_path):
    """读档案的 `manifest.json`，返回 dict；缺失、坏 JSON 或结构不是对象时返回 None。

    `manifest.json` 是可以被人手改的，也可能被别的工具写坏。JSON 合法但顶层
    不是对象（`[]` / `"x"` / `123`）时，裸的 `.get()` 会让 seal / quality_check /
    meta_scan / distill_report 全部带 traceback 退出——诊断工具崩掉比报错更糟，
    因为它连「哪份档案有问题」都说不出来。这里统一收敛成 None，
    由调用方给一句人话错误。
    """
    path = (root_or_path if os.path.basename(str(root_or_path)) == "manifest.json"
            else os.path.join(str(root_or_path), "manifest.json"))
    data = load_json(path)
    return data if isinstance(data, dict) else None


def manifest_dimensions(manifest):
    """返回 `manifest["dimensions"]` 里的 dict 项列表（非 dict 项被丢弃）。

    `manifest.json` 可以被手改，也可能被别的工具写坏。顶层不是对象已由
    `load_manifest` 收敛，但**嵌套结构**畸形（`"dimensions": ["著作"]`、
    `"sources": ["a"]`）会让裸的 `.get()` 在 quality_check / distill_report /
    meta_scan / ingest 里**同时** traceback——而 quality_check 崩在第 5 项，
    比第 12 项的 manifest 检查更早，连「manifest 缺字段」这句人话都说不出来。

    所以所有读嵌套结构的地方都必须走这里，不要在脚本里裸迭代。
    """
    dims = (manifest or {}).get("dimensions")
    if not isinstance(dims, list):
        return []
    return [d for d in dims if isinstance(d, dict)]


def manifest_sources(manifest):
    """返回 `manifest["sources"]` 里的 dict 项列表（非 dict 项被丢弃）。

    与 `manifest_dimensions` 同因：畸形嵌套不该让诊断工具崩掉。
    """
    srcs = (manifest or {}).get("sources")
    if not isinstance(srcs, list):
        return []
    return [s for s in srcs if isinstance(s, dict)]


def write_json(path, obj):
    """写 JSON（UTF-8、缩进 2、末尾换行），目录不存在则创建。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def append_jsonl(path, obj):
    """追加一行 JSON（只增不改，用于 EVALS.jsonl）。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_jsonl(path):
    """读 JSONL，逐行解析；坏行打印告警后跳过。"""
    out = []
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError as e:
                print("⚠️  %s 第 %d 行 JSON 解析失败，跳过: %s" % (path, n, e))
    return out


# --------------------------------------------------------------------------
# 档案定位
# --------------------------------------------------------------------------


def resolve_archive_dir(path):
    """把「档案目录」或「DISTILLATE.md 路径」统一成档案目录（绝对路径）。"""
    p = os.path.abspath(os.path.expanduser(path))
    if os.path.isdir(p):
        return p
    if os.path.basename(p) == "DISTILLATE.md":
        return os.path.dirname(p)
    # 传了别的文件 → 认为它就在档案目录里
    return os.path.dirname(p)


def usage_error(msg, usage):
    """统一的用法错误出口（退出码 1）。"""
    print("❌ " + msg)
    print("用法: " + usage)
    sys.exit(1)
