#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 跨档案扫描（综合档案的前置工具）

读 N 份蒸馏档案，输出：
  1. **来源重叠检测** —— 哪几份档案共享素材（重叠者不构成独立佐证）
  2. **slug 碰撞检测** —— 同名档案（会导致综合结果自相矛盾）
  3. **候选对照矩阵** —— 各档案的主张/心智模型并列，供 agent 做语义判定
  4. **互补缺口候选** —— A 的缺口落在 B 的强项维度上
  5. **信度概览** —— 各档案的信度分布

用法:
    python3 meta_scan.py <档案目录...> [--out <综合档案目录>] [--json]

示例:
    python3 meta_scan.py distilled/munger distilled/buffett --out distilled/value-investing
    python3 meta_scan.py distilled/*/ --json > matrix.json

只读不写（除 --out 时写一份 meta_scan.json 供后续引用）。

重要:
    本脚本只做**机械抽取与候选聚合**。
    「这两条是不是在回答同一个问题」「是不是真的对立」是**语义判断**，
    必须由 agent 完成 —— 脚本不猜（SKILL.md 反模式 #16）。
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

USAGE = "python3 meta_scan.py <档案目录...> [--out <综合档案目录>] [--json]"


def load_archive(path):
    """读一份档案，抽出名册所需的全部字段。无效档案返回 None。"""
    d = _lib.resolve_archive_dir(path)
    dpath = os.path.join(d, "DISTILLATE.md")
    if not os.path.isfile(dpath):
        return None
    fm, body = _lib.parse_frontmatter(_lib.read_text(dpath))
    if fm is None:
        return None

    claims = [{"text": t, "conf": c or "?"} for t, c, _ in _lib.skeleton_items(body)]
    models = re.findall(
        r"^###\s+(.+)$",
        _lib.section(body, "心智模型 / 核心框架", "核心框架") or "", re.M)

    # 信度统计：优先用 frontmatter，缺失则从正文数
    conf = fm.get("confidence")
    if not isinstance(conf, dict) or not _lib.conf_total(conf):
        conf = _lib.count_confidence(body)

    dims, sources, overlap_keys = {}, [], set()
    manifest = _lib.load_json(os.path.join(d, "manifest.json"))
    if manifest:
        for dim in manifest.get("dimensions", []) or []:
            dims[dim.get("name")] = dim.get("coverage")
        for s in manifest.get("sources", []) or []:
            sources.append(s)
            # 重叠判定的键：优先内容哈希，其次路径
            key = s.get("sha256") or s.get("path")
            if key:
                overlap_keys.add(key)

    return {
        "slug": fm.get("slug") or os.path.basename(d),
        "title": fm.get("title", ""),
        "schema": fm.get("schema", "?"),
        "version": fm.get("version"),
        "dir": d,
        "claims": claims,
        "models": models,
        "confidence": conf,
        "gaps": fm.get("gaps") or [],
        "dimensions": dims,
        "n_sources": len(sources),
        "overlap_keys": overlap_keys,
        "source_paths": {s.get("sha256") or s.get("path"): s.get("path")
                         for s in sources if (s.get("sha256") or s.get("path"))},
    }


def _cov(v):
    """把 coverage 收敛成数字；未回填（null）返回 None。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return v


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if argv else 1)

    paths, out_dir, as_json = [], None, False
    i = 0
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out_dir = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            as_json = True
            i += 1
        elif argv[i].startswith("--"):
            _lib.usage_error("未知参数: " + argv[i], USAGE)
        else:
            paths.append(argv[i])
            i += 1

    if len(paths) < 2:
        _lib.usage_error("至少需要 2 份档案才能综合（收到 %d 个）" % len(paths), USAGE)

    archives = []
    for p in paths:
        a = load_archive(p)
        if a is None:
            print("⚠️  跳过（不是有效档案目录）: %s" % p)
        else:
            archives.append(a)

    if len(archives) < 2:
        print("❌ 有效档案不足 2 份，无法综合")
        sys.exit(1)

    # ---- 来源重叠检测（本工具的核心价值） ----
    overlaps = []
    for x in range(len(archives)):
        for y in range(x + 1, len(archives)):
            a, b = archives[x], archives[y]
            shared = a["overlap_keys"] & b["overlap_keys"]
            if shared:
                overlaps.append({
                    "archives": [a["slug"], b["slug"]],
                    "shared": sorted(a["source_paths"].get(k, k) for k in shared),
                    "verdict": "不构成独立佐证",
                })

    # ---- slug 碰撞检测（同名档案会让综合结果自相矛盾） ----
    seen, collisions = {}, []
    for a in archives:
        if a["slug"] in seen:
            collisions.append({
                "slug": a["slug"],
                "dirs": [seen[a["slug"]], a["dir"]],
                "verdict": "同名档案不可综合——先给其中一份改 slug",
            })
        else:
            seen[a["slug"]] = a["dir"]

    # ---- 互补缺口候选：A 的 gap 落在 B 的强项维度 ----
    comp, cov_unfilled = [], []
    for a in archives:
        for dim, cov in a["dimensions"].items():
            if _cov(cov) is None:
                cov_unfilled.append("%s/%s" % (a["slug"], dim))
        for b in archives:
            if a["slug"] == b["slug"] and a["dir"] == b["dir"]:
                continue
            for g in a["gaps"]:
                if not isinstance(g, str):
                    continue
                for dim, cov in b["dimensions"].items():
                    c = _cov(cov)
                    if c is not None and c >= 70 and (dim in g or (g[:4] and g[:4] in dim)):
                        comp.append({"gap_of": a["slug"], "gap": g,
                                     "strong_in": b["slug"], "dimension": dim,
                                     "coverage": c})

    result = {
        "archives": [{k: v for k, v in a.items() if k != "overlap_keys"}
                     for a in archives],
        "source_overlap": overlaps,
        "slug_collisions": collisions,
        "complementary_gaps": comp,
        "coverage_unfilled": cov_unfilled,
    }

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        _lib.write_json(os.path.join(out_dir, "meta_scan.json"), result)

    if as_json:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # ---- 人类可读输出 ----
    print("跨档案扫描: %d 份档案" % len(archives))
    print("=" * 70)
    for a in archives:
        c = a["confidence"]
        print("  %-18s %-9s v%-3s 主张 %2d · 模型 %2d · 来源 %2d · 信度 %s"
              % (a["slug"], a["schema"], a["version"] if a["version"] is not None else "?",
                 len(a["claims"]), len(a["models"]), a["n_sources"],
                 _lib.format_conf(c) if isinstance(c, dict) else "—"))
    print("=" * 70)

    # slug 碰撞（先报，因为它会让后面所有结论失效）
    if collisions:
        print("")
        print("❌ slug 碰撞 —— 以下档案同名，**不可综合**：")
        for c in collisions:
            print("   %s: %s" % (c["slug"], " ↔ ".join(c["dirs"])))
        print("   同名档案在综合结果里无法区分出处，先给其中一份改 slug。")

    # 重叠警告（最重要）
    print("")
    if overlaps:
        print("⚠️  来源重叠检测 —— 以下档案共享素材，**不构成独立佐证**：")
        for o in overlaps:
            print("   %s ↔ %s" % (o["archives"][0], o["archives"][1]))
            for s in o["shared"][:5]:
                print("      共享: %s" % s)
            if len(o["shared"]) > 5:
                print("      ... 另有 %d 个" % (len(o["shared"]) - 5))
        print("")
        print("   影响：这些档案之间的「共识」可能只是**一份素材数了两次**。")
        print("   共识判定必须满足「≥2 份来源不重叠的档案」（见 meta-synthesis.md §三）。")
    else:
        print("✅ 来源重叠检测：未发现共享素材，所有档案互为独立佐证")

    # 候选对照矩阵
    W = (18, 46, 6)
    rows = []
    for a in archives:
        if not a["claims"]:
            rows.append((a["slug"], "（无核心骨架）", "—"))
            continue
        for j, c in enumerate(a["claims"][:3]):
            rows.append((a["slug"] if j == 0 else "", c["text"], c["conf"]))
    print("")
    print("候选对照矩阵（机械聚合，**语义判定归 agent**）")
    for line in _lib.render_table(("档案", "核心主张（前 3 条）", "信度"), [rows], W):
        print(line)

    # 心智模型并列
    print("")
    print("心智模型并列（找跨档案复现的框架）")
    for a in archives:
        print("  %-18s %s" % (a["slug"], "、".join(a["models"]) if a["models"] else "（无）"))

    # 互补缺口
    print("")
    if comp:
        print("互补缺口候选（A 的缺口落在 B 的强项维度上）")
        for c in comp[:10]:
            print("  %s 缺「%s」 → %s 的「%s」覆盖 %s%%"
                  % (c["gap_of"], _lib.truncate(c["gap"], 24), c["strong_in"],
                     c["dimension"], c["coverage"]))
    else:
        print("互补缺口候选：无（无档案的 gaps 落在他人强项维度上）")

    if cov_unfilled:
        print("")
        print("⚠️  以下维度 coverage 未回填，互补缺口判定会漏（Phase 3 应回填）：")
        print("   " + _lib.truncate("、".join(cov_unfilled), 66))

    if out_dir:
        print("")
        print("  📄 完整数据已写入: %s"
              % os.path.relpath(os.path.join(out_dir, "meta_scan.json"), os.getcwd()))

    print("")
    print("  下一步（agent 做语义判定）：")
    print("    1. 判定哪些主张在回答**同一个问题**（脚本不猜）")
    print("    2. 判定哪些是**真对立**（各自信度 ≥B）")
    print("    3. 区分**事实分歧**与**价值观分歧**（后者才是断层线）")
    print("    4. 按 meta-synthesis.md 合成 topic schema 档案 + 「## 综合」段")


if __name__ == "__main__":
    main()
