#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 检查点摘要

扫描蒸馏档案的 `research/` 底稿与 `manifest.json`，打印 Phase 1.5 / 2.5 检查点用的
质量摘要表：各维度的条目数、来源数、信度分布、关键发现、矛盾点、缺口。

用法:
    python3 distill_report.py <档案目录>

示例:
    python3 distill_report.py distilled/munger
    python3 distill_report.py .          # 当前目录就是档案目录

只读不写：不修改任何文件，只往 stdout 打印。
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

USAGE = "python3 distill_report.py <档案目录>"

URL_RE = re.compile(r"https?://[^\s)>\]]+")
PATH_RE = re.compile(r"(?:sources/[\w./一-鿿-]+|[\w一-鿿-]+\.(?:pdf|epub|srt|vtt|md|txt|html))")
CONTRADICTION_RE = re.compile(r"矛盾|相反|但实际上|争议|张力|不一致")


def count_sources(text):
    """统计底稿中引用的来源数（URL + 素材文件路径，去重）。"""
    urls = set(URL_RE.findall(text))
    paths = set(PATH_RE.findall(text))
    return len(urls) + len(paths)


def count_entries(text):
    """统计条目数：优先数 ### 标题，回落 ## 标题，再回落列表项。"""
    for pattern in (r"^###\s+\S", r"^##\s+\S"):
        n = len(re.findall(pattern, text, re.M))
        if n:
            return n
    return len(re.findall(r"^\s*(?:[-*]|\d+\.)\s+\S", text, re.M))


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


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if argv else 1)

    root = os.path.abspath(os.path.expanduser(argv[0]))
    if not os.path.isdir(root):
        _lib.usage_error("目录不存在: " + root, USAGE)

    mpath = os.path.join(root, "manifest.json")
    if not os.path.isfile(mpath):
        _lib.usage_error("未找到 manifest.json，这不是一个蒸馏档案目录: " + root, USAGE)
    manifest = _lib.load_json(mpath)
    if manifest is None:
        _lib.usage_error("manifest.json 解析失败: " + mpath, USAGE)

    dims = manifest.get("dimensions", []) or []
    research_dir = os.path.join(root, "research")

    W = (12, 8, 8, 16, 40)
    rows, footer = [], []
    all_conf, contradictions, missing, unfilled_cov = (
        {"A": 0, "B": 0, "C": 0, "D": 0}, [], [], [])

    for d in dims:
        name = d.get("name", "?")
        fname = os.path.basename(d.get("file", "") or "")
        fpath = os.path.join(research_dir, fname)
        if _lib.is_null(d.get("coverage")) and d.get("status") != "missing":
            unfilled_cov.append(name)
        if not fname or not os.path.isfile(fpath):
            rows.append((name, "❌ 缺失", "—", "—", "底稿未生成"))
            missing.append(name)
            continue
        text = _lib.read_text(fpath)
        conf = _lib.count_confidence(text)
        for k in all_conf:
            all_conf[k] += conf[k]
        findings = extract_findings(text)
        rows.append((
            name,
            "%d 条" % count_entries(text),
            "%d 源" % count_sources(text),
            _lib.format_conf(conf),
            _lib.truncate(" ".join(findings), W[4] - 2) if findings else "—",
        ))
        for line in text.splitlines():
            if CONTRADICTION_RE.search(line) and len(contradictions) < 5:
                s = line.strip().lstrip("-*># ").strip()
                if s and len(s) > 6:
                    contradictions.append(s[:70])

    src_total = len(manifest.get("sources", []) or [])
    primary = manifest.get("sources_primary")
    if _lib.is_null(primary):
        pct = " (一手占比 未回填)"
    elif isinstance(primary, int) and src_total:
        pct = " (一手占比 %d/%d)" % (primary, src_total)
    else:
        pct = ""
    footer.append(("素材总量", "%d 个" % src_total, "", _lib.format_conf(all_conf),
                   _lib.truncate("字数 %s%s" % (manifest.get("source_words") or "—", pct),
                                 W[4] - 2)))
    footer.append(("矛盾点", "%d 处" % len(contradictions), "", "",
                   _lib.truncate(contradictions[0], W[4] - 2) if contradictions else "无"))
    footer.append(("信息不足维度", "%d 个" % len(missing), "", "",
                   _lib.truncate("、".join(missing), W[4] - 2) if missing else "无"))

    title = manifest.get("title") or os.path.basename(root)
    print("蒸馏检查点摘要: %s" % title)
    for line in _lib.render_table(("维度", "条目", "来源", "信度分布", "关键发现"),
                                  [rows, footer], W):
        print(line)

    if len(contradictions) > 1:
        print("")
        print("矛盾点明细:")
        for c in contradictions:
            print("  - " + c)

    d_total = _lib.conf_total(all_conf)
    warnings = []
    if missing:
        warnings.append("缺失维度: " + "、".join(missing))
    if src_total < 10:
        warnings.append("素材总数 <10，档案质量会受限（framework §九）")
    if unfilled_cov:
        warnings.append("coverage 未回填: " + "、".join(unfilled_cov)
                        + "（Phase 3 应由 agent 判定后回填）")
    if d_total and all_conf["D"] / d_total > 0.20:
        warnings.append("D 级（推断）占比 %.0f%% > 20%%，素材不足，应标注缺口而非靠推断填充"
                        % (100.0 * all_conf["D"] / d_total))
    if rows and not contradictions:
        warnings.append("未检出矛盾点——确认是真的无矛盾，还是被调和掉了（framework §五）")

    print("")
    if warnings:
        for w in warnings:
            print("  ⚠️  " + w)
    else:
        print("  ✅ 未检出结构性问题")

    print("")
    print("  提示：本表只做静态检查。生成力与诚实度须由独立 agent 跑 quality-scorecard.md。")


if __name__ == "__main__":
    main()
