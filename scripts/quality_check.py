#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 档案静态质检（契约的可执行形式）

对一份蒸馏档案做 **7 项结构检查** + 一组**软诊断**。
这是 Phase 5 的第一道关，之后还必须由**独立 agent** 跑 `references/quality-scorecard.md`。

用法:
    python3 quality_check.py <档案目录 或 DISTILLATE.md 路径> [--json]

七项硬检查（任一不过 → 退出码 1）:
    1. frontmatter 完整性      必填字段 + schema 枚举 + schema_version 受支持
    2. 核心骨架数量            3-10 条（<3 没提炼，>10 没取舍）
    3. 信度标记与 D 级占比      正文须有信度标记；D 级 <20%
    4. 矛盾保留与分类          有类型标注；**无和稀泥式调和**（铁律 2）
    5. 缺口诚实                gaps 字段存在且已回填；gaps 空但 coverage<40 → 装懂
    6. 浓度                    每千字 5-20 条独立条目
    7. manifest 契约与哈希封存  契约字段齐备；distillate_sha256 与档案一致

软诊断（只提示，不影响通过判定）:
    前后端信度分布不一致、骨架条目缺信度/缺出处、coverage 未回填、
    字数与压缩比自报值与实测值偏差、manifest 与正文 version 不一致等。

退出码:
    0 = 7 项全过
    1 = 有未通过项，或参数/文件有误

注意:
    本脚本只做**静态结构检查**——它能发现「缺段落」「信度没标」「缺口没写」
    「哈希没封存」，但发现不了「推断编得像真的」。
    生成力与诚实度必须由独立 agent 跑 `references/quality-scorecard.md`，
    **绝不能用本脚本代替**。

契约同步:
    规则的权威定义在 `references/artifact-format.md`，本文件是它的可执行形式。
    改契约必须同步改本文件，反之亦然——两边不得漂移。
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

USAGE = "python3 quality_check.py <档案目录 或 DISTILLATE.md> [--json]"

#: manifest.json 必须齐备的字段（契约 §三）。
MANIFEST_REQUIRED = [
    "schema_version", "slug", "schema", "title", "created", "updated", "version",
    "sources", "source_words", "sources_primary", "sources_secondary",
    "dimensions", "gaps", "meta_sources", "source_overlap", "changes",
    "distillate_sha256",
]

DENSITY_MIN, DENSITY_MAX = 5.0, 20.0


# --------------------------------------------------------------------------
# 硬检查
# --------------------------------------------------------------------------


def check_frontmatter(fm):
    if fm is None:
        return False, "未找到 frontmatter（文件须以 --- 开头）"
    missing = [f for f in _lib.REQUIRED_FIELDS if f not in fm]
    if missing:
        return False, "缺少字段: " + "、".join(missing)

    sv = fm.get("schema_version")
    if _lib.is_null(sv):
        return False, "schema_version 未回填"
    try:
        sv = int(sv)
    except (TypeError, ValueError):
        return False, "schema_version 不是整数: %r" % (sv,)
    if sv > _lib.SUPPORTED_SCHEMA_VERSION:
        return False, ("schema_version=%d 高于本 skill 支持的 %d —— "
                       "请升级 skill，不要猜测解析" % (sv, _lib.SUPPORTED_SCHEMA_VERSION))

    schema = fm.get("schema")
    if schema not in _lib.SCHEMAS:
        return False, "schema 取值非法: %r（应为 %s）" % (schema, " / ".join(_lib.SCHEMAS))

    return True, "%d 个必填字段齐全 · schema=%s · schema_version=%s ✅" % (
        len(_lib.REQUIRED_FIELDS), schema, sv)


def check_skeleton(body):
    items = _lib.skeleton_items(body)
    n = len(items)
    if n < 3:
        return False, "核心骨架仅 %d 条（需 ≥3，说明没提炼）" % n
    if n > 10:
        return False, "核心骨架 %d 条（>10，说明没取舍）" % n
    return True, "%d 条核心骨架 ✅" % n


def check_confidence(fm, body):
    counts = _lib.count_confidence(body)
    total = _lib.conf_total(counts)
    if total == 0:
        return False, "正文未检出任何信度标记（A/B/C/D）——铁律 3：无信度标记的条目不合格"
    ratio = _lib.d_ratio(counts)
    if ratio > 20:
        return False, "D 级（推断）占 %.0f%%（需 <20%%），素材不足" % ratio
    return True, "%d 处信度标记，D 级占 %.0f%% ✅" % (total, ratio)


def check_tensions(body):
    sec = _lib.section(body, "矛盾与张力")
    if sec is None:
        return False, "缺少「## 矛盾与张力」段"
    found = [t for t in _lib.TENSION_TYPES if t in sec]
    harmony = _lib.HARMONY_RE.search(sec)
    if not found:
        return False, "矛盾段未标注类型（需含 时间性/领域性/本质张力 之一）"
    if harmony:
        return False, ("疑似和稀泥式调和（命中「%s」）——矛盾是信息不是 Bug，"
                       "必须保留并分类，禁止调和（铁律 2）" % harmony.group(0))
    return True, "矛盾已分类: " + "、".join(found) + " ✅"


def check_gaps(fm, body, manifest):
    if fm is None or "gaps" not in fm:
        return False, "frontmatter 缺少 gaps 字段"
    if _lib.is_null(fm.get("gaps")):
        return False, ("gaps 未回填——须显式写成列表（确实无缺口写 `gaps: []`，"
                       "不要留空；不知道就说不知道）")
    sec = _lib.section(body, "信息缺口")
    if sec is None:
        return False, "缺少「## 信息缺口」段"
    # scorecard 规则：gaps 为空但存在 coverage<40 的维度 = 装懂（0 分）
    if not fm.get("gaps") and manifest:
        low = []
        for d in manifest.get("dimensions", []) or []:
            cov = d.get("coverage")
            if isinstance(cov, (int, float)) and not isinstance(cov, bool) and cov < 40:
                low.append("%s(%s)" % (d.get("name", "?"), cov))
        if low:
            return False, ("gaps 为空，但以下维度 coverage<40：%s —— "
                           "这是装懂（评分卡判 0 分）" % "、".join(low))
    return True, "gaps 字段 + 信息缺口段齐备 ✅"


def check_density(body):
    words = _lib.count_words(body)
    if words < 200:
        return False, "正文仅 %d 字，样本太小无法评估浓度（真实档案通常 2000 字以上）" % words
    items = len(_lib.skeleton_items(body))
    items += len(re.findall(r"^###\s+\S", body, re.M))
    per_k = items * 1000.0 / words
    if per_k < DENSITY_MIN:
        return False, "每千字 %.1f 条（<%.0f，水太多，继续去水）" % (per_k, DENSITY_MIN)
    # 上限只在正文够长时才有意义：短文档天然条目密度高
    if per_k > DENSITY_MAX and words >= 800:
        return False, "每千字 %.1f 条（>%.0f，没展开，读者理解不了）" % (per_k, DENSITY_MAX)
    note = "（正文偏短，上限未判定）" if per_k > DENSITY_MAX else ""
    return True, "每千字 %.1f 条独立条目 ✅%s" % (per_k, note)


def check_manifest(root, dpath):
    mpath = os.path.join(root, "manifest.json")
    if not os.path.isfile(mpath):
        return False, "缺少 manifest.json（档案目录应由 ingest.py 建立）"
    manifest = _lib.load_json(mpath)
    if manifest is None:
        return False, "manifest.json 无法解析: " + mpath

    sv = manifest.get("schema_version")
    try:
        sv = int(sv)
    except (TypeError, ValueError):
        return False, "manifest.schema_version 不是整数: %r" % (sv,)
    if sv > _lib.SUPPORTED_SCHEMA_VERSION:
        return False, "manifest.schema_version=%d 高于本 skill 支持的 %d" % (
            sv, _lib.SUPPORTED_SCHEMA_VERSION)

    missing = [k for k in MANIFEST_REQUIRED if k not in manifest]
    if missing:
        return False, ("manifest 缺少契约字段: %s（重跑 ingest.py 或补齐）"
                       % "、".join(missing))

    recorded = manifest.get("distillate_sha256")
    actual = _lib.sha256_file(dpath)
    if _lib.is_null(recorded):
        return False, ("distillate_sha256 未封存（跑 seal.py）——"
                       "缺它则下游的漂移检测静默失效")
    if recorded != actual:
        return False, ("distillate_sha256 已过期：档案在封存后被改动过（跑 seal.py 重新封存）"
                       " · manifest=%s… 实际=%s…" % (str(recorded)[:12], actual[:12]))
    return True, "契约字段齐备 · 哈希已封存 %s… ✅" % actual[:12]


# --------------------------------------------------------------------------
# 软诊断（只提示，不影响通过判定）
# --------------------------------------------------------------------------


def _ratio_value(text):
    """把 `38:1` 解析成 38.0；解析不出返回 None。"""
    if not isinstance(text, str):
        return None
    m = re.match(r"^\s*([\d.]+)\s*[:：]\s*([\d.]+)\s*$", text)
    if not m:
        return None
    try:
        a, b = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None
    return a / b if b else None


def collect_diagnostics(fm, body, manifest, root, dpath):
    """收集非致命的一致性告警。每条都是「可机械发现」的，不含语义判断。"""
    out = []
    if fm is None:
        return out

    # 1) 前后端信度分布是否对得上
    body_conf = _lib.count_confidence(body)
    body_total = _lib.conf_total(body_conf)
    fm_conf = fm.get("confidence")
    if not isinstance(fm_conf, dict):
        out.append("frontmatter 的 confidence 不是行内映射（契约要求 {A: n, B: n, ...}）")
    elif not _lib.conf_total(fm_conf):
        out.append("frontmatter 的 confidence 未回填（全 0）")
    else:
        fm_total = _lib.conf_total(fm_conf)
        slack = max(2, int(0.2 * max(fm_total, body_total)))
        if abs(fm_total - body_total) > slack:
            out.append("信度分布不一致：frontmatter 共 %d 处（%s），正文实测 %d 处（%s）"
                       % (fm_total, _lib.format_conf(fm_conf), body_total,
                          _lib.format_conf(body_conf)))

    # 2) 骨架条目的信度与出处
    items = _lib.skeleton_items(body)
    if items:
        no_conf = [t for t, c, _ in items if c is None]
        no_src = [t for t, _, s in items if not s]
        if no_conf:
            out.append("%d/%d 条核心骨架没有信度标记（铁律 3）：%s"
                       % (len(no_conf), len(items),
                          "；".join(_lib.truncate(t, 28) for t in no_conf[:3])))
        if no_src:
            out.append("%d/%d 条核心骨架没有可回查的出处指针（反模式 #2）：%s"
                       % (len(no_src), len(items),
                          "；".join(_lib.truncate(t, 28) for t in no_src[:3])))

    # 3) manifest 未回填项
    if manifest:
        unfilled_cov = [d.get("name", "?") for d in manifest.get("dimensions", []) or []
                        if d.get("status") != "missing" and _lib.is_null(d.get("coverage"))]
        if unfilled_cov:
            out.append("coverage 未回填的维度：%s（Phase 3 应由 agent 判定后回填）"
                       % "、".join(unfilled_cov))
        if _lib.is_null(manifest.get("sources_primary")) or \
                _lib.is_null(manifest.get("sources_secondary")):
            out.append("sources_primary / sources_secondary 未回填（Phase 3 应由 agent 判定）")

        # 4) manifest 与正文的 version 是否一致
        fm_v, man_v = fm.get("version"), manifest.get("version")
        if fm_v is not None and man_v is not None and fm_v != man_v:
            out.append("version 不一致：DISTILLATE.md=%s，manifest.json=%s" % (fm_v, man_v))

        # 5) 维度状态与 research/ 底稿是否对得上（对不上说明 manifest 过期）
        for d in manifest.get("dimensions", []) or []:
            fname = os.path.basename(d.get("file", "") or "")
            if not fname:
                continue
            exists = os.path.isfile(os.path.join(root, "research", fname))
            if d.get("status") != "missing" and not exists:
                out.append("维度「%s」状态为 %s，但 research/%s 不存在（manifest 过期，重跑 ingest.py）"
                           % (d.get("name", "?"), d.get("status"), fname))
            elif d.get("status") == "missing" and exists:
                out.append("维度「%s」已有 research/%s，但状态仍是 missing（重跑 ingest.py）"
                           % (d.get("name", "?"), fname))

    # 6) 自报字数 / 压缩比与实测值
    actual_words = _lib.count_words(body)
    declared = fm.get("distillate_words")
    if isinstance(declared, int) and actual_words and abs(declared - actual_words) > 0.2 * actual_words:
        out.append("distillate_words 自报 %d，实测正文 %d（偏差 >20%%）" % (declared, actual_words))
    src_words = fm.get("source_words")
    if isinstance(src_words, int) and isinstance(declared, int) and declared and actual_words:
        expect = src_words / float(actual_words)
        got = _ratio_value(fm.get("compression_ratio"))
        if got is not None and abs(got - expect) > 0.2 * expect:
            out.append("compression_ratio 自报 %s（≈%.1f:1），按 source_words/distillate_words 应为 %.1f:1"
                       % (fm.get("compression_ratio"), got, expect))

    # 7) 人物档案极少真的无缺口
    if fm.get("schema") == "person" and fm.get("gaps") == []:
        out.append("人物档案的 gaps 为空——人物档案极少真的无缺口，确认不是漏标")

    return out


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if argv else 1)

    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]
    unknown = [a for a in argv if a.startswith("--") and a != "--json"]
    if unknown:
        _lib.usage_error("未知参数: " + "、".join(unknown), USAGE)
    if len(paths) != 1:
        _lib.usage_error("需要且仅需要一个档案路径", USAGE)

    root = _lib.resolve_archive_dir(paths[0])
    dpath = os.path.join(root, "DISTILLATE.md")
    if not os.path.isfile(dpath):
        _lib.usage_error("未找到 DISTILLATE.md: " + dpath, USAGE)

    text = _lib.read_text(dpath)
    fm, body = _lib.parse_frontmatter(text)
    manifest = _lib.load_json(os.path.join(root, "manifest.json"))

    checks = [
        ("frontmatter 完整性", check_frontmatter(fm)),
        ("核心骨架数量", check_skeleton(body)),
        ("信度标记与 D 级占比", check_confidence(fm, body)),
        ("矛盾保留与分类", check_tensions(body)),
        ("缺口诚实", check_gaps(fm, body, manifest)),
        ("浓度（每千字条目数）", check_density(body)),
        ("manifest 契约与哈希封存", check_manifest(root, dpath)),
    ]
    diagnostics = collect_diagnostics(fm, body, manifest, root, dpath)
    passed = sum(1 for _, (ok, _) in checks if ok)

    if as_json:
        print(json.dumps({
            "file": dpath,
            "passed": passed,
            "total": len(checks),
            "ok": passed == len(checks),
            "checks": [{"name": n, "ok": ok, "detail": d} for n, (ok, d) in checks],
            "diagnostics": diagnostics,
        }, ensure_ascii=False, indent=2))
        sys.exit(0 if passed == len(checks) else 1)

    print("质量检查: %s" % os.path.basename(dpath))
    print("=" * 62)
    for name, (ok, detail) in checks:
        print("  %-22s %s  %s" % (name, "✅ PASS" if ok else "❌ FAIL", detail))
    print("=" * 62)
    print("结果: %d/%d 通过" % (passed, len(checks)))

    if diagnostics:
        print("")
        print("软诊断（不影响通过判定，供 agent 判断）:")
        for d in diagnostics:
            print("  ⚠️  " + d)

    print("")
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
