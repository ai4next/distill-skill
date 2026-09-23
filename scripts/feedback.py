#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 汇总人格使用反馈（只读）

读人格目录里的 FEEDBACK.jsonl，汇总「哪些缺口被反复命中」「哪些条目需要复核」。

用法:
    python3 feedback.py [<人格目录...>] [--skills-dir ~/.claude/skills] [--json]

选项:
    <人格目录...>        指定要读的人格目录；不给则扫描 --skills-dir 下的 *-persona
    --skills-dir DIR     默认 ~/.claude/skills
    --json               输出 JSON

只读不写:
    本脚本**只读**人格目录，绝不修改。档案归 distill 管，人格归 summon 管；
    distill 读反馈是为了发现缺口，不是去改人格。

关键语义:
    **faithful_silence（忠实沉默）不计入缺陷汇总。**
    拒答在本系统里常常是正确行为——gaps 映射、结构性沉默、伦理红线都要求拒答。
    若把它当缺陷，就会被推着去为刻意沉默的主体编造立场，违反 framework §九。
    本脚本把它单独统计，只报频率，不列为待修项。
"""

import json
import os
import sys
import unicodedata
from collections import Counter, defaultdict

DEFECT_TYPES = ("style_drift", "in_scope_gap", "wrong_stance")
SILENCE_TYPES = ("faithful_silence",)

TYPE_LABEL = {
    "style_drift": "表达不像",
    "in_scope_gap": "范围内没答好",
    "wrong_stance": "立场与档案矛盾",
    "faithful_silence": "忠实沉默（正确行为）",
}

SUGGESTION = {
    "style_drift": "表达DNA 需加强（加正/反例对照）",
    "in_scope_gap": "该维度底稿不够厚，建议补素材或补提炼",
    "wrong_stance": "档案对应条目可能出错 → 需复核该条目的信度与出处",
}


def usage_error(msg):
    print("❌ " + msg)
    print("用法: python3 feedback.py [<人格目录...>] [--skills-dir ~/.claude/skills] [--json]")
    sys.exit(1)


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


def load_feedback(pdir):
    path = os.path.join(pdir, "FEEDBACK.jsonl")
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                print("⚠️  %s 第 %d 行解析失败，跳过" % (path, n))
    return out


def main():
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    dirs, skills_dir, as_json = [], os.path.expanduser("~/.claude/skills"), False
    i = 0
    while i < len(argv):
        if argv[i] == "--skills-dir" and i + 1 < len(argv):
            skills_dir = os.path.expanduser(argv[i + 1])
            i += 2
        elif argv[i] == "--json":
            as_json = True
            i += 1
        elif argv[i].startswith("--"):
            usage_error("未知参数: " + argv[i])
        else:
            dirs.append(os.path.expanduser(argv[i]))
            i += 1

    if not dirs:
        if not os.path.isdir(skills_dir):
            usage_error("目录不存在: " + skills_dir)
        dirs = [os.path.join(skills_dir, d) for d in sorted(os.listdir(skills_dir))
                if d.endswith("-persona") and os.path.isdir(os.path.join(skills_dir, d))]
        if not dirs:
            print("（%s 下没有 *-persona 目录，也没有反馈可汇总）" % skills_dir)
            return

    records, per_persona = [], {}
    for d in dirs:
        recs = load_feedback(d)
        per_persona[os.path.basename(d.rstrip(os.sep))] = recs
        records.extend(recs)

    if not records:
        print("（%d 个人格目录，均无 FEEDBACK.jsonl）" % len(dirs))
        return

    defects = [r for r in records if r.get("failure") in DEFECT_TYPES]
    silences = [r for r in records if r.get("failure") in SILENCE_TYPES]
    unknown = [r for r in records if r.get("failure") not in DEFECT_TYPES + SILENCE_TYPES]
    no_evidence = [r for r in defects if not r.get("evidence")]

    by_type = Counter(r.get("failure") for r in defects)
    by_persona = Counter(r.get("persona") for r in defects)
    # 被反复命中的问题（缺陷类）
    q_counter = Counter(r.get("question", "").strip() for r in defects if r.get("question"))
    dim_counter = Counter()
    for r in defects:
        ev = (r.get("evidence") or "")
        if "§" in ev:
            dim_counter[ev.split("§")[-1].strip()[:20]] += 1

    result = {
        "total_records": len(records),
        "defects": len(defects),
        "faithful_silence": len(silences),
        "by_type": dict(by_type),
        "by_persona": dict(by_persona),
        "top_questions": q_counter.most_common(10),
        "top_evidence": dim_counter.most_common(10),
        "records_without_evidence": len(no_evidence),
        "per_persona": {k: len(v) for k, v in per_persona.items()},
    }

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("人格使用反馈汇总（只读）")
    print("=" * 66)
    print("  总记录 %d 条 · 人格缺陷 %d 条 · 忠实沉默 %d 条"
          % (len(records), len(defects), len(silences)))
    print("=" * 66)

    if defects:
        print("")
        print("人格缺陷（计入汇总）")
        for t, n in by_type.most_common():
            print("  %-16s %2d 条 —— %s" % (TYPE_LABEL.get(t, t), n, SUGGESTION.get(t, "")))

        if len(by_persona) > 1 or True:
            print("")
            print("按人格分布")
            for p, n in by_persona.most_common():
                print("  %-24s %d 条" % (p, n))

        if q_counter:
            print("")
            print("被反复命中的问题（Top 5）—— 这些是真缺口")
            for q, n in q_counter.most_common(5):
                print("  %2d× %s" % (n, truncate(q, 52)))

        if dim_counter:
            print("")
            print("涉及最多的档案位置（Top 5）")
            for d, n in dim_counter.most_common(5):
                print("  %2d× §%s" % (n, d))
    else:
        print("")
        print("  ✅ 无人格缺陷记录")

    print("")
    if silences:
        print("忠实沉默（**不计入缺陷**）")
        print("  %d 条 —— 这是**正确行为**，不要为此去补缺口。" % len(silences))
        print("  拒答在 gaps 映射、结构性沉默、伦理红线场景下都是对的；")
        print("  若当成缺陷去修，就会被推着为刻意沉默的主体编造立场（违反 framework §九）。")
        for r in silences[:3]:
            print("    · [%s] %s" % (r.get("persona", "?"), truncate(r.get("question", ""), 44)))
    else:
        print("忠实沉默：无记录")

    if unknown:
        print("")
        print("  ⚠️  %d 条记录的 failure 类型无法识别（可能是旧版本写入）" % len(unknown))
    if no_evidence:
        print("")
        print("  ⚠️  %d 条缺陷记录**缺少证据指针** —— 按铁律3 视为意见，"
              "不要据此修改档案" % len(no_evidence))

    print("")
    print("  下一步（由用户发起）：")
    print("    · 有真缺口 → 补素材后跑「补充蒸馏」，gaps 更新 → version++")
    print("    · 档案更新后 DISTILLATE.md 哈希变 → roster 会报 stale → 重铸人格")
    print("    · 重铸后用 eval_record.py compare 验证是否真的变好")


if __name__ == "__main__":
    main()
