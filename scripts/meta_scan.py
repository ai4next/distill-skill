#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 跨档案扫描（综合档案的前置工具）

读 N 份蒸馏档案，输出：
  1. **来源重叠检测** —— 哪几份档案共享素材（重叠者不构成独立佐证）
  2. **候选对照矩阵** —— 各档案的主张/心智模型并列，供 agent 做语义判定
  3. **互补缺口候选** —— A 的缺口落在 B 的强项维度上
  4. **信度概览** —— 各档案的信度分布

用法:
    python3 meta_scan.py <档案目录...> [--out <综合档案目录>] [--json]

示例:
    python3 meta_scan.py distilled/munger distilled/buffett --out distilled/value-investing
    python3 meta_scan.py distilled/*/ --json > matrix.json

只读不写（除 --out 时写一份 meta_scan.json 供后续引用）。

重要:
    本脚本只做**机械抽取与候选聚合**。
    「这两条是不是在回答同一个问题」「是不是真的对立」是**语义判断**，
    必须由 agent 完成 —— 脚本不猜。
"""

import hashlib
import json
import os
import re
import sys
import unicodedata

CONF_MARKER_RE = re.compile(r"[（(【\[]\s*([ABCD])\s*[）)】\]]")
CONF_LABEL_RE = re.compile(r"信度\s*[:：]\s*([ABCD])")


def usage_error(msg):
    print("❌ " + msg)
    print("用法: python3 meta_scan.py <档案目录...> [--out <综合档案目录>] [--json]")
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
        return [strip_quotes(x) for x in inner.split(",")] if inner else []
    if val.startswith("{") and val.endswith("}"):
        out = {}
        for part in val[1:-1].split(","):
            if ":" in part:
                k, _, v = part.partition(":")
                out[strip_quotes(k)] = strip_quotes(v)
        return out
    return strip_quotes(val)


def parse_frontmatter(text):
    if not text.lstrip().startswith("---"):
        return None, text
    start = text.index("---") + 3
    end = text.find("\n---", start)
    if end == -1:
        return None, text
    data, current_key = {}, None
    for line in text[start:end].splitlines():
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
    return data, text[end + 4:]


def section(body, *titles):
    for t in titles:
        m = re.search(r"^##\s+" + re.escape(t) + r"\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
        if m:
            return m.group(1)
    return ""


def dw(s):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in str(s))


def truncate(s, width):
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


def load_archive(path):
    """读一份档案，抽出名册所需的全部字段。"""
    if os.path.isdir(path):
        d = os.path.abspath(path)
    else:
        d = os.path.abspath(os.path.dirname(path))
        path = os.path.join(d, "DISTILLATE.md")
    dpath = os.path.join(d, "DISTILLATE.md")
    if not os.path.isfile(dpath):
        return None
    try:
        text = open(dpath, encoding="utf-8").read()
    except OSError:
        return None
    fm, body = parse_frontmatter(text)
    if fm is None:
        return None

    # 核心骨架条目 + 信度
    claims = []
    for line in (section(body, "核心骨架") or "").splitlines():
        m = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if not m:
            continue
        txt = m.group(1)
        c = re.search(r"[（(]([ABCD])[）)]\s*$", txt)
        claims.append({
            "text": re.sub(r"[（(][ABCD][）)]\s*$", "", txt).strip(),
            "conf": c.group(1) if c else "?",
        })

    models = re.findall(r"^###\s+(.+)$", section(body, "心智模型 / 核心框架", "核心框架"), re.M)

    # 信度统计：优先用 frontmatter，缺失则从正文数
    conf = fm.get("confidence") or {}
    if not conf:
        conf = {"A": 0, "B": 0, "C": 0, "D": 0}
        for m in CONF_MARKER_RE.finditer(body):
            conf[m.group(1)] = conf.get(m.group(1), 0) + 1
        for m in CONF_LABEL_RE.finditer(body):
            conf[m.group(1)] = conf.get(m.group(1), 0) + 1

    # 维度覆盖（用于互补缺口候选）
    dims = {}
    mpath = os.path.join(d, "manifest.json")
    sources = []
    overlap_keys = set()
    if os.path.isfile(mpath):
        try:
            man = json.load(open(mpath, encoding="utf-8"))
            for dim in man.get("dimensions", []):
                dims[dim.get("name")] = dim.get("coverage", 0)
            for s in man.get("sources", []):
                sources.append(s)
                # 重叠判定的键：优先内容哈希，其次路径
                key = s.get("sha256") or s.get("path")
                if key:
                    overlap_keys.add(key)
        except (OSError, ValueError):
            pass

    return {
        "slug": fm.get("slug") or os.path.basename(d),
        "title": fm.get("title", ""),
        "schema": fm.get("schema", "?"),
        "dir": d,
        "claims": claims,
        "models": models,
        "confidence": conf,
        "gaps": fm.get("gaps", []) or [],
        "dimensions": dims,
        "n_sources": len(sources),
        "overlap_keys": overlap_keys,
        "source_paths": {s.get("sha256") or s.get("path"): s.get("path")
                         for s in sources if (s.get("sha256") or s.get("path"))},
    }


def main():
    argv = sys.argv[1:]
    if not argv:
        usage_error("缺少档案目录参数")
    if argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    paths, out_dir, as_json = [], None, False
    i = 0
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out_dir = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            as_json = True
            i += 1
        else:
            paths.append(argv[i])
            i += 1

    if len(paths) < 2:
        usage_error("至少需要 2 份档案才能综合（收到 %d 个）" % len(paths))

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

    # ---- 互补缺口候选：A 的 gap 落在 B 的强项维度 ----
    comp = []
    for a in archives:
        for b in archives:
            if a["slug"] == b["slug"]:
                continue
            for g in a["gaps"]:
                for dim, cov in b["dimensions"].items():
                    if cov and cov >= 70 and (dim in g or g[:4] in dim):
                        comp.append({"gap_of": a["slug"], "gap": g,
                                     "strong_in": b["slug"], "dimension": dim, "coverage": cov})

    result = {
        "archives": [{k: v for k, v in a.items() if k != "overlap_keys"} for a in archives],
        "source_overlap": overlaps,
        "complementary_gaps": comp,
    }

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        op = os.path.join(out_dir, "meta_scan.json")
        with open(op, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # ---- 人类可读输出 ----
    print("跨档案扫描: %d 份档案" % len(archives))
    print("=" * 70)
    for a in archives:
        c = a["confidence"]
        print("  %-18s %-9s 主张 %2d · 模型 %2d · 来源 %2d · 信度 A%s B%s C%s D%s"
              % (a["slug"], a["schema"], len(a["claims"]), len(a["models"]),
                 a["n_sources"], c.get("A", 0), c.get("B", 0), c.get("C", 0), c.get("D", 0)))
    print("=" * 70)

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
    line = "┌" + "┬".join("─" * w for w in W) + "┐"
    sep = "├" + "┼".join("─" * w for w in W) + "┤"
    end = "└" + "┴".join("─" * w for w in W) + "┘"

    def row(cells):
        o = "│"
        for c, w in zip(cells, W):
            s = truncate(c, w - 1)
            pad = w - dw(s) - 1
            o += " " + s + " " * (pad if pad > 0 else 0) + "│"
        return o

    print("")
    print("候选对照矩阵（机械聚合，**语义判定归 agent**）")
    print(line)
    print(row(("档案", "核心主张（前 3 条）", "信度")))
    print(sep)
    for a in archives:
        if not a["claims"]:
            print(row((a["slug"], "（无核心骨架）", "—")))
            continue
        for j, c in enumerate(a["claims"][:3]):
            print(row((a["slug"] if j == 0 else "", c["text"], c["conf"])))
    print(end)

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
                  % (c["gap_of"], truncate(c["gap"], 24), c["strong_in"], c["dimension"], c["coverage"]))
    else:
        print("互补缺口候选：无（无档案的 gaps 落在他人强项维度上）")

    if out_dir:
        print("")
        print("  📄 完整数据已写入: %s" % os.path.relpath(os.path.join(out_dir, "meta_scan.json"), os.getcwd()))

    print("")
    print("  下一步（agent 做语义判定）：")
    print("    1. 判定哪些主张在回答**同一个问题**（脚本不猜）")
    print("    2. 判定哪些是**真对立**（各自信度 ≥B）")
    print("    3. 区分**事实分歧**与**价值观分歧**（后者才是断层线）")
    print("    4. 按 meta-synthesis.md 合成 topic schema 档案 + 「## 综合」段")


if __name__ == "__main__":
    main()
