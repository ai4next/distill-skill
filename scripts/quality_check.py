#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 档案静态质检

对 DISTILLATE.md 做 6 项结构检查（Phase 5 的第一道关，之后还要跑独立 agent 评分卡）。

用法:
    python3 quality_check.py <DISTILLATE.md 路径>

退出码:
    0 = 6 项全过
    1 = 有未通过项，或参数/文件有误

注意:
    本脚本只做**静态结构检查**——它能发现「缺段落」「信度没标」「缺口没写」，
    但发现不了「推断编得像真的」。生成力与诚实度必须由独立 agent 跑
    references/quality-scorecard.md，绝不能用本脚本代替。
"""

import os
import re
import sys

REQUIRED_FIELDS = [
    "schema_version", "schema", "slug", "title", "created", "updated", "version",
    "sources_total", "sources_primary", "sources_secondary", "confidence",
    "source_words", "distillate_words", "compression_ratio", "dimensions", "gaps",
]

CONF_MARKER_RE = re.compile(r"[（(【\[]\s*([ABCD])\s*[）)】\]]")
CONF_LABEL_RE = re.compile(r"信度\s*[:：]\s*([ABCD])")
CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")
LATIN_RE = re.compile(r"[A-Za-z0-9]+")

TENSION_TYPES = ("时间性", "领域性", "本质张力", "本质性张力")


def usage_error(msg):
    print("❌ " + msg)
    print("用法: python3 quality_check.py <DISTILLATE.md 路径>")
    sys.exit(1)


def strip_quotes(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def parse_scalar(val):
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [strip_quotes(x) for x in inner.split(",")]
    if val.startswith("{") and val.endswith("}"):
        out = {}
        for part in val[1:-1].split(","):
            if ":" in part:
                k, _, v = part.partition(":")
                out[strip_quotes(k)] = strip_quotes(v)
        return out
    return strip_quotes(val)


def parse_frontmatter(text):
    """解析契约限定的 YAML 子集，返回 (dict, body)。解析失败返回 (None, text)。"""
    if not text.lstrip().startswith("---"):
        return None, text
    start = text.index("---") + 3
    end = text.find("\n---", start)
    if end == -1:
        return None, text
    fm_raw = text[start:end]
    body = text[end + 4:]
    data, current_key = {}, None
    for line in fm_raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line[:1] in (" ", "\t") and line.strip().startswith("- "):
            if current_key is not None and isinstance(data.get(current_key), list):
                data[current_key].append(strip_quotes(line.strip()[2:]))
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if not val:
            data[key] = []
            current_key = key
        else:
            data[key] = parse_scalar(val)
            current_key = None
    return data, body


def section(body, title):
    """取 `## title` 段的内容，直到下一个同级或更高级标题。"""
    m = re.search(r"^##\s+" + re.escape(title) + r"\s*$(.*?)(?=^##\s|\Z)",
                  body, re.M | re.S)
    return m.group(1) if m else None


def count_words(text):
    return len(CJK_RE.findall(text)) + len(LATIN_RE.findall(text))


def check_frontmatter(fm):
    if fm is None:
        return False, "未找到 frontmatter（文件须以 --- 开头）"
    missing = [f for f in REQUIRED_FIELDS if f not in fm]
    if missing:
        return False, "缺少字段: " + "、".join(missing)
    return True, "%d 个必填字段齐全 ✅" % len(REQUIRED_FIELDS)


def check_skeleton(body):
    sec = section(body, "核心骨架")
    if sec is None:
        return False, "缺少「## 核心骨架」段"
    items = re.findall(r"^\s*(?:[-*]|\d+\.)\s+\S", sec, re.M)
    n = len(items)
    if n < 3:
        return False, "核心骨架仅 %d 条（需 ≥3）" % n
    if n > 10:
        return False, "核心骨架 %d 条（>10，说明没取舍）" % n
    return True, "%d 条核心骨架 ✅" % n


def check_confidence(body, fm):
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for m in CONF_MARKER_RE.finditer(body):
        counts[m.group(1)] += 1
    for m in CONF_LABEL_RE.finditer(body):
        counts[m.group(1)] += 1
    total = sum(counts.values())
    if total == 0:
        return False, "正文未检出任何信度标记（A/B/C/D）"
    d_ratio = 100.0 * counts["D"] / total
    if d_ratio > 20:
        return False, "D 级（推断）占 %.0f%%（需 <20%%），素材不足" % d_ratio
    return True, "%d 处信度标记，D 级占 %.0f%% ✅" % (total, d_ratio)


def check_tensions(body):
    sec = section(body, "矛盾与张力")
    if sec is None:
        return False, "缺少「## 矛盾与张力」段"
    found = [t for t in TENSION_TYPES if t in sec]
    if not found:
        return False, "矛盾段未标注类型（需含 时间性/领域性/本质张力 之一）"
    if re.search(r"虽然.{0,30}但是", sec) and not found:
        return False, "疑似和稀泥式调和"
    return True, "矛盾已分类: " + "、".join(found) + " ✅"


def check_gaps(body, fm):
    if fm is None or "gaps" not in fm:
        return False, "frontmatter 缺少 gaps 字段"
    sec = section(body, "信息缺口")
    if sec is None:
        return False, "缺少「## 信息缺口」段"
    return True, "gaps 字段 + 信息缺口段齐备 ✅"


def check_density(body):
    words = count_words(body)
    if words < 200:
        return False, "正文仅 %d 字，样本太小无法评估浓度（真实档案通常 2000 字以上）" % words
    sec = section(body, "核心骨架")
    items = len(re.findall(r"^\s*(?:[-*]|\d+\.)\s+\S", sec, re.M)) if sec else 0
    items += len(re.findall(r"^###\s+\S", body, re.M))
    per_k = items * 1000.0 / words
    if per_k < 5:
        return False, "每千字 %.1f 条（<5，水太多，继续去水）" % per_k
    # 上限只在正文够长时才有意义：短文档天然条目密度高
    if per_k > 20 and words >= 800:
        return False, "每千字 %.1f 条（>20，没展开，读者理解不了）" % per_k
    note = "（正文偏短，上限未判定）" if per_k > 20 else ""
    return True, "每千字 %.1f 条独立条目 ✅%s" % (per_k, note)


def main():
    if len(sys.argv) < 2:
        usage_error("缺少 DISTILLATE.md 路径参数")

    path = os.path.abspath(os.path.expanduser(sys.argv[1]))
    if not os.path.isfile(path):
        usage_error("文件不存在: " + path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        usage_error("读取失败: %s" % e)

    fm, body = parse_frontmatter(text)

    checks = [
        ("frontmatter 完整性", check_frontmatter(fm)),
        ("核心骨架数量", check_skeleton(body)),
        ("信度标记与 D 级占比", check_confidence(body, fm)),
        ("矛盾保留与分类", check_tensions(body)),
        ("缺口诚实", check_gaps(body, fm)),
        ("浓度（每千字条目数）", check_density(body)),
    ]

    print("质量检查: %s" % os.path.basename(path))
    print("=" * 58)
    passed = 0
    for name, (ok, detail) in checks:
        mark = "✅ PASS" if ok else "❌ FAIL"
        print("  %-20s %s  %s" % (name, mark, detail))
        passed += 1 if ok else 0
    print("=" * 58)
    print("结果: %d/%d 通过" % (passed, len(checks)))

    if passed == len(checks):
        print("🎉 全部通过。下一步：由独立 agent 跑 references/quality-scorecard.md")
        sys.exit(0)
    if passed >= len(checks) - 1:
        print("⚠️  基本通过，建议修复不通过项后交付")
    else:
        print("❌ 多项不通过，建议回到 Phase 2/3 迭代（迭代上限 2 轮）")
    sys.exit(1)


if __name__ == "__main__":
    main()
