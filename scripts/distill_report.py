#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 检查点摘要

扫描蒸馏档案的 research/ 底稿与 manifest.json，打印 Phase 1.5 / 2.5 检查点用的
质量摘要表：各维度的条目数、信度分布、关键发现、矛盾点、缺口。

用法:
    python3 distill_report.py <档案目录>

示例:
    python3 distill_report.py distilled/munger
    python3 distill_report.py .          # 当前目录就是档案目录

只读不写：不修改任何文件，只往 stdout 打印。
"""

import json
import os
import re
import sys
import unicodedata

CONF_MARKER_RE = re.compile(r"[（(【\[]\s*([ABCD])\s*[）)】\]]")
CONF_LABEL_RE = re.compile(r"信度\s*[:：]\s*([ABCD])")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
PATH_RE = re.compile(r"(?:sources/[\w./一-鿿-]+|[\w一-鿿-]+\.(?:pdf|epub|srt|vtt|md|txt|html))")
CONTRADICTION_RE = re.compile(r"矛盾|相反|但实际上|争议|张力|不一致")

STATUS_ICON = {"complete": "✅", "partial": "🟡", "missing": "❌"}


def usage_error(msg):
    print("❌ " + msg)
    print("用法: python3 distill_report.py <档案目录>")
    sys.exit(1)


def read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def count_confidence(text):
    """统计信度标记 A/B/C/D 的出现次数。"""
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for m in CONF_MARKER_RE.finditer(text):
        counts[m.group(1)] += 1
    for m in CONF_LABEL_RE.finditer(text):
        counts[m.group(1)] += 1
    return counts


def count_sources(text):
    """统计底稿中引用的来源数（URL + 素材文件路径，去重）。"""
    urls = set(URL_RE.findall(text))
    paths = set(PATH_RE.findall(text))
    return len(urls) + len(paths), len(urls), len(paths)


def count_entries(text):
    """统计条目数：优先数 ### 标题，回落 ## 标题，再回落列表项。"""
    for pattern in (r"^###\s+\S", r"^##\s+\S"):
        n = len(re.findall(pattern, text, re.M))
        if n:
            return n
    return len(re.findall(r"^\s*(?:[-*]|\d+\.)\s+\S", text, re.M))


def dw(s):
    """终端显示宽度：CJK 全角算 2 列。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in str(s))


def truncate(s, width):
    """按显示宽度截断，超出加省略号。"""
    s = str(s)
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


def extract_findings(text, max_items=3):
    """取前 N 个 ### 标题；没有则取加粗短语；再没有取首个非标题行。"""
    items = re.findall(r"^###\s+(.+)$", text, re.M)
    if not items:
        items = re.findall(r"\*\*(.{2,40}?)\*\*", text)
    if not items:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith(">"):
                items = [line[:50]]
                break
    return [i.strip() for i in items[:max_items]]


def fmt_conf(c):
    total = sum(c.values())
    if not total:
        return "—"
    return "A%d B%d C%d D%d" % (c["A"], c["B"], c["C"], c["D"])


def main():
    if len(sys.argv) < 2:
        usage_error("缺少档案目录参数")

    root = os.path.abspath(os.path.expanduser(sys.argv[1]))
    if not os.path.isdir(root):
        usage_error("目录不存在: " + root)

    mpath = os.path.join(root, "manifest.json")
    if not os.path.isfile(mpath):
        usage_error("未找到 manifest.json，这不是一个蒸馏档案目录: " + root)
    try:
        with open(mpath, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (ValueError, OSError) as e:
        usage_error("manifest.json 解析失败: %s" % e)

    dims = manifest.get("dimensions", [])
    research_dir = os.path.join(root, "research")

    W = (14, 16, 16, 46)
    rows, all_conf, contradictions, missing = [], {"A": 0, "B": 0, "C": 0, "D": 0}, [], []

    for d in dims:
        name = d.get("name", "?")
        fname = os.path.basename(d.get("file", ""))
        fpath = os.path.join(research_dir, fname)
        if not os.path.isfile(fpath):
            rows.append((name, "❌ 缺失", "—", "—", "底稿未生成"))
            missing.append(name)
            continue
        text = read(fpath)
        conf = count_confidence(text)
        for k in all_conf:
            all_conf[k] += conf[k]
        n_src, n_url, n_path = count_sources(text)
        n_ent = count_entries(text)
        findings = extract_findings(text)
        rows.append((
            name,
            "%d 条 / %d 源" % (n_ent, n_src),
            fmt_conf(conf),
            truncate(" ".join(findings), W[3] - 2) if findings else "—",
            "",
        ))
        for line in text.splitlines():
            if CONTRADICTION_RE.search(line) and len(contradictions) < 5:
                s = line.strip().lstrip("-*># ").strip()
                if s and len(s) > 6:
                    contradictions.append(s[:70])

    # 表格
    line = "┌" + "┬".join("─" * w for w in W) + "┐"
    sep = "├" + "┼".join("─" * w for w in W) + "┤"
    end = "└" + "┴".join("─" * w for w in W) + "┘"

    def row(cells):
        out = "│"
        for c, w in zip(cells, W):
            s = truncate(c, w - 1)
            pad = w - dw(s) - 1
            out += " " + s + " " * (pad if pad > 0 else 0) + "│"
        return out

    print("蒸馏检查点摘要: %s" % manifest.get("title") or root)
    print(line)
    print(row(("维度", "条目 / 来源", "信度分布", "关键发现")))
    print(sep)
    for name, ent, conf, find, _ in rows:
        print(row((name, ent, conf, find)))
    print(sep)

    src_total = len(manifest.get("sources", []))
    primary = manifest.get("sources_primary")
    pct = ""
    if isinstance(primary, int) and src_total:
        pct = " (一手占比 %d/%d)" % (primary, src_total)
    print(row(("素材总量", "%d 个" % src_total, fmt_conf(all_conf),
               truncate("字数 %s%s" % (manifest.get("source_words") or "—", pct), W[3] - 2))))
    print(row(("矛盾点", "%d 处" % len(contradictions), "",
               truncate(contradictions[0], W[3] - 2) if contradictions else "无")))
    print(row(("信息不足维度", "%d 个" % len(missing), "",
               truncate("、".join(missing), W[3] - 2) if missing else "无")))
    print(end)

    if len(contradictions) > 1:
        print("")
        print("矛盾点明细:")
        for c in contradictions:
            print("  - " + c)

    total_entries = sum(int(r[1].split(" 条")[0]) for r in rows if " 条" in r[1])
    d_total = sum(all_conf.values())
    warnings = []
    if missing:
        warnings.append("缺失维度: " + "、".join(missing))
    if src_total < 10:
        warnings.append("素材总数 <10，档案质量会受限（framework §九）")
    if d_total and all_conf["D"] / d_total > 0.20:
        warnings.append("D 级（推断）占比 %.0f%% > 20%%，素材不足，应标注缺口而非靠推断填充"
                        % (100.0 * all_conf["D"] / d_total))
    if total_entries and not contradictions:
        warnings.append("未检出矛盾点——确认是真的无矛盾，还是被调和掉了（framework §五）")

    if warnings:
        print("")
        for w in warnings:
            print("  ⚠️  " + w)
    else:
        print("")
        print("  ✅ 未检出结构性问题")

    print("")
    print("  提示：本表只做静态检查。生成力与诚实度须由独立 agent 跑 quality-scorecard.md。")


if __name__ == "__main__":
    main()
