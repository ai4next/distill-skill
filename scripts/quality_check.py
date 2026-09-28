#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 档案**结构**检查（契约的可执行形式）

对一份蒸馏档案做 **12 项结构检查** + 一组**软诊断**。
这是 Phase 5 的第一道关，之后还必须由**独立 agent** 跑 `references/quality-scorecard.md`。

用法:
    python3 quality_check.py <档案目录 或 DISTILLATE.md 路径> [--json]

十二项结构检查（任一不过 → 退出码 1）:
    1. frontmatter 完整性      必填字段 + schema 枚举 + schema_version 受支持
    2. frontmatter 交叉校验    dimensions 与 schema 匹配 / slug 与目录名一致 /
                              sources_total == 一手 + 二手 / confidence 形如 {A:n,…}
    3. 核心骨架数量            3-10 条（<3 没提炼，>10 没取舍）
    4. 骨架条目元数据          每条骨架都要带信度标记 + 出处指针（铁律 3 / 契约 §2.3）
    5. 信度标记与 D 级占比      正文须有信度标记；D 级 ≤20%
    6. 矛盾保留与分类          有类型标注，或显式声明「未发现矛盾」；**无否认对立式调和**
    7. 缺口诚实                gaps 字段已回填；缺口段非空；gaps 空但 coverage<40 → 装懂
    8. 素材清单                manifest.sources 非空（档案必须有素材依据）
    9. 维度底稿齐备            非 missing 的维度都要有 research/ 底稿
   10. 元数据已回填            coverage / 一手二手计数不得停在 null（Phase 3 的活）
   11. 浓度                    每千字 5-20 条独立条目
   12. manifest 契约与哈希封存  契约字段齐备；distillate_sha256 与档案一致

**这十二项拦的是结构缺陷，不是内容真伪。** 它们能发现「缺段落」「信度没标」
「缺口没写」「哈希没封存」，但发现不了「推断编得像真的」——一份字段齐全、
标记规范的档案完全可能是编造的。**过了这十二项 ≠ 质量合格**，
只等于「没有结构性缺陷，值得花一次评分」。
生成力与诚实度必须由独立 agent 跑 `references/quality-scorecard.md`，绝不能用本脚本代替。

软诊断（只提示，不影响通过判定）:
    前后端信度分布不一致、字数与压缩比自报值与实测值偏差、manifest 与正文 version 不一致、
    矛盾段用了转折句式但未标类型（疑似抹平）、声明「未发现矛盾」等。

退出码:
    0 = 12 项全过
    1 = 有未通过项，或参数/文件有误

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

#: 一个 `###` 小节要算作「独立条目」，它下面至少得有这么多字的内容。
#: 空的或只有一行标题的小节是免费的分子，不算条目。
DENSITY_ITEM_MIN_WORDS = 20

#: 信息缺口段的最小长度。只判「段落存在」的话，写一句「（本节待补）」就能过——
#: 那是留空换了个写法，而留空正是本节要拦的东西（沉默不能替代声明）。
GAPS_MIN_CHARS = 10

#: 日期字段的形态（契约 §2.2：`YYYY-MM-DD`）。
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def check_frontmatter_xref(fm, root):
    """frontmatter 内部与对外的**交叉**一致性。

    这些字段单看都合法，凑在一起却可能自相矛盾——而矛盾的数据会让下游
    静默地得出错误结论（比如把 `dimensions: []` 当成「这份档案没有维度」）。
    """
    if fm is None:
        return False, "未找到 frontmatter"
    errs = []

    schema = fm.get("schema")
    dims = fm.get("dimensions")
    if not isinstance(dims, list) or not dims:
        errs.append("dimensions 必须是非空列表")
    elif schema in _lib.SCHEMA_DIMENSIONS:
        expect = [d[1] for d in _lib.SCHEMA_DIMENSIONS[schema]]
        if list(dims) != expect:
            errs.append("%s 的 dimensions 应为 %s，实际 %s"
                        % (schema, expect, list(dims)))

    slug = fm.get("slug")
    if isinstance(slug, str) and os.path.basename(root) != slug:
        errs.append("slug=%r 与目录名 %r 不一致" % (slug, os.path.basename(root)))

    conf = fm.get("confidence")
    if not isinstance(conf, dict) or not all(k in "ABCD" for k in conf):
        errs.append("confidence 须为行内映射 {A: n, B: n, C: n, D: n}，实际 %r" % (conf,))

    total, pri, sec = (fm.get("sources_total"), fm.get("sources_primary"),
                       fm.get("sources_secondary"))
    if all(isinstance(v, int) and not isinstance(v, bool) for v in (total, pri, sec)):
        if total != pri + sec:
            errs.append("sources_total=%d ≠ 一手 %d + 二手 %d" % (total, pri, sec))

    for key in ("created", "updated"):
        v = fm.get(key)
        if isinstance(v, str) and not DATE_RE.match(v):
            errs.append("%s=%r 不是 YYYY-MM-DD" % (key, v))

    if errs:
        return False, "；".join(errs)
    return True, "dimensions/slug/confidence/计数/日期 相互一致 ✅"


def check_skeleton(body):
    items = _lib.skeleton_items(body)
    n = len(items)
    if n < _lib.SKELETON_MIN:
        return False, "核心骨架仅 %d 条（需 ≥%d，说明没提炼）%s" % (
            n, _lib.SKELETON_MIN, _hint_skeleton_heading(body))
    if n > _lib.SKELETON_MAX:
        return False, "核心骨架 %d 条（>%d，说明没取舍）" % (n, _lib.SKELETON_MAX)
    return True, "%d 条核心骨架 ✅" % n


def _hint_skeleton_heading(body):
    """骨架数为 0 时，如果其实是标题写变形了，直接说出来。

    不说的话，agent 会拿到「没提炼」这个指向错误根因的结论，然后去改内容——
    而真正的问题在标题格式。检查失败信息指错方向，是自纠的最大障碍。
    """
    if _lib.section(body, "核心骨架") is not None:
        return ""
    near = _lib.near_miss_headings(body, "核心骨架")
    if near:
        return "（疑似标题写变形：%s）" % "；".join(near)
    return ""


def check_skeleton_meta(body):
    """每条骨架都要带信度标记与出处指针（铁律 3 + 契约 §2.3）。

    这条曾经只是**软诊断**，而 evals 的断言却承诺了它——承诺与执行对不上，
    评测就在说谎。现在落成硬检查：铁律 3 明写「无信度标记的条目视为不合格」，
    契约 §2.3 明写「每条主张都要能回答两个问题：多可信、从哪来」。
    """
    items = _lib.skeleton_items(body)
    if not items:
        return True, "（无骨架条目，根因见第 3 项）"
    no_conf = [t for t, c, _ in items if c is None]
    no_src = [t for t, _, s in items if not s]
    errs = []
    if no_conf:
        errs.append("%d/%d 条无信度标记：%s" % (
            len(no_conf), len(items),
            "；".join(_lib.truncate(t, 24) for t in no_conf[:3])))
    if no_src:
        errs.append("%d/%d 条无出处指针（反模式 #2）：%s" % (
            len(no_src), len(items),
            "；".join(_lib.truncate(t, 24) for t in no_src[:3])))
    if errs:
        return False, " · ".join(errs)
    return True, "%d 条骨架均带信度与出处 ✅" % len(items)


def check_confidence(body):
    counts = _lib.count_confidence(body)
    total = _lib.conf_total(counts)
    if total == 0:
        return False, ("正文未检出任何信度标记（A/B/C/D）——铁律 3：无信度标记的条目不合格。"
                       "行尾写 `（A · sources/x.md）`，或用带「信度」列的表格")
    ratio = _lib.d_ratio(counts)
    if ratio > 20:
        return False, "D 级（推断）占 %.0f%%（需 ≤20%%），素材不足" % ratio
    return True, "%d 处信度标记，D 级占 %.0f%% ✅" % (total, ratio)


def check_tensions(body):
    sec = _lib.section(body, "矛盾与张力")
    if sec is None:
        return False, "缺少「## 矛盾与张力」段"
    # 和稀泥先判：它比「没标类型」严重，报错也要报得准（两者同时命中时，
    # 说「没标类型」会把真正的问题——抹平——藏起来）。
    #
    # 判的是**信息量净减少**（否认对立的断言），不是「虽然…但是」句式。
    # 转折句式是描述张力的合法形式；把它当罪证会硬性 FAIL 一条标注齐全的时间性
    # 张力，逼作者删掉真实矛盾——检查在惩罚正确输出，反而违反铁律 2。
    # 转折句式只在缺类型标注时进软诊断（见 collect_diagnostics）。
    #
    # `harmony_matches` 还会剥掉引号内的引用与「禁止/避免…」式的提及：
    # 一份**否定**抹平写法的档案（「本节刻意未使用『其实两者并不冲突』这类表述」）
    # 不该被判成和稀泥。
    hits = _lib.harmony_matches(sec)
    if hits:
        return False, ("疑似和稀泥式调和（命中「%s」）——这类断言抹掉了对立本身，"
                       "读者再也取不出原来的两条主张。矛盾是信息不是 Bug，"
                       "必须保留并分类（铁律 2）" % hits[0])
    # 类型必须**成标签**（`时间性张力`）才算分类。只做子串匹配的话，
    # 一句「按要求写出『时间性』这个词」就能让占位档案白拿这一项。
    found = _lib.labeled_tension_types(sec)
    if found:
        return True, "矛盾已分类: " + "、".join(found) + " ✅"
    # 允许「查过了，确实没有」。没有这条出口，一份内部自洽的材料会被逼着
    # 编造一条矛盾出来——那正是铁律 1 禁止的。
    sentence = _lib.declaration_sentence(sec)
    if len(sentence) >= _lib.NO_TENSION_MIN_CHARS:
        return True, "已显式声明「未发现矛盾」并交代核查范围 ✅"
    if _lib.NO_TENSION_RE.search(sec):
        return False, ("「未发现矛盾」的声明句只有 %d 字（需 ≥%d）——"
                       "必须说明**核查范围**（比对了哪些章节/哪几组立场），"
                       "一行「无矛盾。」区分不了「真的没有」与「没看」"
                       % (len(sentence), _lib.NO_TENSION_MIN_CHARS))
    return False, ("矛盾段既未标注类型（需含 时间性/领域性/本质性张力 之一），"
                   "也未显式声明「未发现矛盾」——二选一，不许留空")


def check_gaps(fm, body, manifest):
    if fm is None or "gaps" not in fm:
        return False, "frontmatter 缺少 gaps 字段"
    if _lib.is_null(fm.get("gaps")):
        return False, ("gaps 未回填——须显式写成列表（确实无缺口写 `gaps: []`，"
                       "不要留空；不知道就说不知道）")
    sec = _lib.section(body, "信息缺口")
    if sec is None:
        return False, "缺少「## 信息缺口」段"
    if len(sec.strip()) < GAPS_MIN_CHARS:
        return False, ("「## 信息缺口」段只有 %d 字，等于没写——"
                       "留空与「（本节待补）」都无法区分「真的没有」与「没看」。"
                       "确实无缺口时，写清核查范围与 `gaps: []` 的依据"
                       % len(sec.strip()))
    # scorecard 规则：gaps 为空但存在 coverage<40 的维度 = 装懂（0 分）
    if not fm.get("gaps") and manifest:
        low = []
        for d in _lib.manifest_dimensions(manifest):
            cov = d.get("coverage")
            if isinstance(cov, (int, float)) and not isinstance(cov, bool) and cov < 40:
                low.append("%s(%s)" % (d.get("name", "?"), cov))
        if low:
            return False, ("gaps 为空，但以下维度 coverage<40：%s —— "
                           "这是装懂（评分卡判 0 分）" % "、".join(low))
    return True, "gaps 字段 + 信息缺口段齐备 ✅"


def check_sources(manifest):
    """档案必须有素材依据：`manifest.sources` 非空。

    空的 sources 意味着这份档案没有可回查的来源——而「每条断言可溯源」是
    铁律 3 的落点。网络来源只记 URL 不落盘是允许的（契约 §三），
    但清单本身不能是空的。
    """
    if manifest is None:
        return True, "（无 manifest，根因见第 12 项）"
    srcs = _lib.manifest_sources(manifest)
    if not srcs:
        return False, ("manifest.sources 为空——档案没有素材依据。"
                       "跑 ingest.py 归集素材，或确认 sources[] 没被写坏")
    primary = [s for s in srcs if s.get("origin") == "local"]
    return True, "%d 条素材（本地 %d）✅" % (len(srcs), len(primary))


def check_dimension_drafts(root, manifest):
    """非 missing 的维度都要有 `research/` 底稿。

    底稿是「结论从哪来」的中间证据。manifest 说某维度 complete 却找不到底稿，
    意味着这个状态是空口填的——评分卡的覆盖度也就无从核对。
    """
    if manifest is None:
        return True, "（无 manifest，根因见第 12 项）"
    dims = _lib.manifest_dimensions(manifest)
    if not dims:
        return False, "manifest.dimensions 为空——维度划分是蒸馏的骨架，不能省"
    missing = []
    for d in dims:
        if d.get("status") == "missing":
            continue
        fname = os.path.basename(str(d.get("file") or ""))
        if not fname or not os.path.isfile(os.path.join(root, "research", fname)):
            missing.append("%s→research/%s" % (d.get("name", "?"), fname or "?"))
    if missing:
        return False, "以下维度没有 research/ 底稿：%s" % "、".join(missing)
    return True, "%d 个维度均有底稿 ✅" % len(dims)


def check_backfilled(manifest):
    """Phase 3 该回填的元数据不能停在 `null`。

    `null` 是「未回填」，`0` 是「判定为零」——这个区分是本契约诚实性的基石
    （契约 §2.2）。但区分的前提是它**最终会被填上**：交付时仍是 `null`，
    评分卡的覆盖度与一手占比就无法计算，装懂检测（gaps 空 + coverage<40）
    也会静默失效——规则写着却永不触发，比没有规则更糟。
    """
    if manifest is None:
        return True, "（无 manifest，根因见第 12 项）"
    unfilled = []
    for d in _lib.manifest_dimensions(manifest):
        if d.get("status") == "missing":
            continue
        if _lib.is_null(d.get("coverage")):
            unfilled.append("维度「%s」的 coverage" % d.get("name", "?"))
    for key, label in (("sources_primary", "一手来源计数"),
                       ("sources_secondary", "二手来源计数")):
        if _lib.is_null(manifest.get(key)):
            unfilled.append(label)
    if unfilled:
        return False, ("以下元数据仍是 null（未回填）：%s —— "
                       "交付前必须由 agent 判定后回填（Phase 3 的活）"
                       % "、".join(unfilled[:5]))
    return True, "coverage 与一手/二手计数均已回填 ✅"


def count_density_items(body):
    """浓度公式里的「独立条目数」：骨架条数 + **有内容的** `###` 小节数。

    `###` 标题曾经是无条件计入的，于是「加 7 个空的 `### 占位小节`」就是
    免费条目——分母不变、分子 +7，一份零提炼的档案能算出「每千字 10.7 条」
    的健康浓度。小节要算数，它下面得真有内容。
    """
    n = len(_lib.skeleton_items(body))
    for m in re.finditer(r"^###\s+\S.*$", body, re.M):
        rest = body[m.end():]
        nxt = re.search(r"^#{1,3}\s+\S", rest, re.M)
        block = rest[:nxt.start()] if nxt else rest
        if _lib.count_words(block) >= DENSITY_ITEM_MIN_WORDS:
            n += 1
    return n


def check_density(body):
    words = _lib.count_words(body)
    if words < 200:
        return False, "正文仅 %d 字，样本太小无法评估浓度（真实档案通常 2000 字以上）" % words
    items = count_density_items(body)
    per_k = items * 1000.0 / words
    if per_k < DENSITY_MIN:
        return False, "每千字 %.1f 条（<%.0f，水太多，继续去水）" % (per_k, DENSITY_MIN)
    # 上限只在正文够长时才有意义：短文档天然条目密度高
    if per_k > DENSITY_MAX and words >= 800:
        return False, "每千字 %.1f 条（>%.0f，没展开，读者理解不了）" % (per_k, DENSITY_MAX)
    note = "（正文偏短，上限未判定）" if per_k > DENSITY_MAX else ""
    return True, "每千字 %.1f 条独立条目（%d 条 / %d 字）✅%s" % (
        per_k, items, words, note)


def check_manifest(root, dpath):
    mpath = os.path.join(root, "manifest.json")
    if not os.path.isfile(mpath):
        return False, "缺少 manifest.json（档案目录应由 ingest.py 建立）"
    manifest = _lib.load_manifest(mpath)
    if manifest is None:
        return False, "manifest.json 无法解析或顶层不是对象: " + mpath

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
    if actual is None:
        return False, "无法读取 DISTILLATE.md 计算哈希（权限或路径问题）: " + dpath
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
    """收集非致命的一致性告警。每条都是「可机械发现」的，不含语义判断。

    能进这里的东西有一条共同特征：**它不影响档案能否被消费**，只提示「值得看一眼」。
    骨架缺元数据、维度缺底稿、元数据未回填这些都不再属于软诊断——它们已经是硬检查。
    """
    out = []
    if fm is None:
        return out

    # 1) 前后端信度分布是否对得上
    body_conf = _lib.count_confidence(body)
    body_total = _lib.conf_total(body_conf)
    fm_conf = fm.get("confidence")
    if isinstance(fm_conf, dict) and _lib.conf_total(fm_conf):
        fm_total = _lib.conf_total(fm_conf)
        slack = max(2, int(0.2 * max(fm_total, body_total)))
        if abs(fm_total - body_total) > slack:
            out.append("信度分布不一致：frontmatter 共 %d 处（%s），正文实测 %d 处（%s）"
                       "——若正文主要用表格承载，确认表头列名写了「信度」"
                       % (fm_total, _lib.format_conf(fm_conf), body_total,
                          _lib.format_conf(body_conf)))

    if manifest:
        # 2) manifest 与正文的 version 是否一致
        fm_v, man_v = fm.get("version"), manifest.get("version")
        if fm_v is not None and man_v is not None and fm_v != man_v:
            out.append("version 不一致：DISTILLATE.md=%s，manifest.json=%s" % (fm_v, man_v))

        # 3) 维度状态与 research/ 底稿是否对得上（对不上说明 manifest 过期）
        for d in _lib.manifest_dimensions(manifest):
            fname = os.path.basename(str(d.get("file") or ""))
            if not fname:
                continue
            exists = os.path.isfile(os.path.join(root, "research", fname))
            if d.get("status") != "missing" and not exists:
                out.append("维度「%s」状态为 %s，但 research/%s 不存在（manifest 过期，重跑 ingest.py）"
                           % (d.get("name", "?"), d.get("status"), fname))
            elif d.get("status") == "missing" and exists:
                out.append("维度「%s」已有 research/%s，但状态仍是 missing（重跑 ingest.py）"
                           % (d.get("name", "?"), fname))

    # 4) 自报字数 / 压缩比与实测值
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

    # 5) 人物档案极少真的无缺口
    if fm.get("schema") == "person" and fm.get("gaps") == []:
        out.append("人物档案的 gaps 为空——人物档案极少真的无缺口，确认不是漏标")

    # 6) 矛盾段声明「未发现矛盾」——合法，但绝大多数素材确实有矛盾
    tsec = _lib.section(body, "矛盾与张力")
    if tsec is not None and _lib.NO_TENSION_RE.search(tsec) \
            and not _lib.labeled_tension_types(tsec):
        out.append("矛盾段声明「未发现矛盾」——确认是核查过而不是漏读（framework §五）。"
                   "评分卡按**核查记录的可信度**给分：指名比对了哪些章节/哪几组立场才能拿高分")

    # 7) 转折句式但整段没标类型——疑似抹平（软诊断，不拦截）
    #    「虽然…但是」本身合法（描述张力的正确写法之一），所以不能硬拦；
    #    但它确实是抹平的高发句式，缺类型标注时值得复核一眼。
    if tsec is not None and _lib.TURN_RE.search(tsec) \
            and not _lib.labeled_tension_types(tsec) \
            and not _lib.NO_TENSION_RE.search(tsec):
        out.append("矛盾段用了转折句式（「虽然…但是」）但未标注张力类型——"
                   "转折本身不是问题，缺类型标注才是：确认这是描述张力（合法，补类型词即可）"
                   "还是把对立揉平了（须改回并列）")

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
    manifest = _lib.load_manifest(root)

    checks = [
        ("frontmatter 完整性", check_frontmatter(fm)),
        ("frontmatter 交叉校验", check_frontmatter_xref(fm, root)),
        ("核心骨架数量", check_skeleton(body)),
        ("骨架条目元数据", check_skeleton_meta(body)),
        ("信度标记与 D 级占比", check_confidence(body)),
        ("矛盾保留与分类", check_tensions(body)),
        ("缺口诚实", check_gaps(fm, body, manifest)),
        ("素材清单", check_sources(manifest)),
        ("维度底稿齐备", check_dimension_drafts(root, manifest)),
        ("元数据已回填", check_backfilled(manifest)),
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

    print("结构检查: %s" % os.path.basename(dpath))
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
        print("✅ 结构检查通过。这只说明**没有结构性缺陷**，不代表内容可信——")
        print("   下一步必须由**独立 agent** 跑 references/quality-scorecard.md。")
        sys.exit(0)
    if passed >= len(checks) - 1:
        print("⚠️  基本通过，建议修复不通过项后交付")
    else:
        print("❌ 多项不通过，建议回到 Phase 2/3 迭代（迭代上限 2 轮）")
    sys.exit(1)


if __name__ == "__main__":
    main()
