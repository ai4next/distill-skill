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

#: 已知二进制：不做文本解码，`words` 记 null 由 agent 抽文本后回填。
BINARY_EXTS = {
    ".pdf", ".epub", ".mobi", ".azw3", ".djvu", ".docx", ".doc",
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".m4a", ".wav", ".flac",
}

#: 矛盾分类（见 distillation-framework.md §五）。
TENSION_TYPES = ("时间性", "领域性", "本质张力", "本质性张力")

#: 和稀泥式调和的特征句式。**矛盾必须保留并分类，禁止调和**（铁律 2）。
#: 命中即质检不合格——这是铁律，不是风格建议。
HARMONY_RE = re.compile(
    r"虽然[^。；！？\n]{0,30}但是"
    r"|其实(?:两者|二者)?(?:是)?(?:互补|一致|统一|相通的)"
    r"|(?:两者|二者|二者之间|其实)并?不矛盾"
    r"|本质上是统一的"
    r"|并不冲突"
    r"|殊途同归"
)

#: 显式空值记号。用于区分「未回填」（null）与「判定为零」（0）——
#: 这是本 skill 诚实哲学在数据层的体现（不知道就说不知道）。
NULL_TOKENS = ("null", "none", "nil", "~", "")

# --------------------------------------------------------------------------
# 正则
# --------------------------------------------------------------------------

CONF_MARKER_RE = re.compile(r"[（(【\[]\s*([ABCD])\s*[）)】\]]")
CONF_LABEL_RE = re.compile(r"信度\s*[:：]\s*([ABCD])")
CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")
LATIN_RE = re.compile(r"[A-Za-z0-9]+")

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
        return [parse_scalar(x) for x in inner.split(",")]
    if val.startswith("{") and val.endswith("}"):
        out = {}
        for part in val[1:-1].split(","):
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
    """
    for t in titles:
        m = re.search(r"^##\s+" + re.escape(t) + r"\s*$(.*?)(?=^##\s|\Z)",
                      body, re.M | re.S)
        if m:
            return m.group(1)
    return None


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------


def count_words(text):
    """CJK 按字计，拉丁按词计。与 ingest 的字数口径一致。"""
    if text is None:
        return 0
    return len(CJK_RE.findall(text)) + len(LATIN_RE.findall(text))


def count_confidence(text):
    """统计正文里的信度标记，返回 `{"A":n,"B":n,"C":n,"D":n}`。

    两种写法都认：`（A）` / `[A]` 与 `信度: A`。
    """
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for m in CONF_MARKER_RE.finditer(text or ""):
        counts[m.group(1)] += 1
    for m in CONF_LABEL_RE.finditer(text or ""):
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
TRAILING_META_RE = re.compile(r"[（(【\[]([^（）()【】\[\]]*)[）)】\]]\s*$")

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
    """
    sec = section(body, "核心骨架")
    if sec is None:
        return []
    out = []
    for line in sec.splitlines():
        m = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.+?)\s*$", line)
        if not m:
            continue
        raw = m.group(1)
        clean, conf = split_trailing_meta(raw)
        out.append((clean, conf, has_source_pointer(raw)))
    return out


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
    """文件内容的 sha256（十六进制）。

    **算法是契约的一部分**：`distillate_sha256` 用它，下游消费者也用它做漂移检测。
    改动本函数 = 让所有基于旧哈希的下游产物误报漂移。测试用黄金值钉死了它。
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    """字符串的 sha256（UTF-8 编码）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path):
    """读文本文件，失败返回空串（只读工具不应因缺文件而崩）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def load_json(path, default=None):
    """读 JSON，失败返回 default。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


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
