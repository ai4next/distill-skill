#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 测试套件

跑法（在 skill 根目录）:
    python3 -m unittest discover -s test -v

覆盖三件事:
  1. `scripts/_lib.py` 的解析/统计/渲染契约（frontmatter 子集、null 语义、信度统计）
  2. **已修复缺陷的回归测试** —— 每条对应一个真实踩过的坑，注释里写了原缺陷
  3. 端到端流程 —— ingest → seal → quality_check → distill_report → meta_scan → eval_record

约定：测试通过 subprocess 调真实 CLI（不是只测函数），
因为脚本之间的**接口**（参数、退出码、stdout 关键字）本身就是契约的一部分。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import _lib  # noqa: E402
import quality_check as qc_mod  # noqa: E402
import distill_report  # noqa: E402


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------


def run(script, *args, cwd=None):
    """跑一个真实脚本，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script)] + [str(a) for a in args],
        capture_output=True, text=True, cwd=cwd or ROOT)


DEFAULT_BODY = """# 测试人物 · 认知档案

## 一句话
用可逆性判断替代预测：不猜未来，只买下错了也不致命的选项。

## 核心骨架
- 用可逆性判断替代预测，只在错了也不致命时下注（A · sources/notes/note1.md）
- 反过来想：先问什么会导致失败，再倒推该做什么（A · sources/notes/note1.md）
- 激励机制错，人就做错事，先看激励再看人（B · sources/notes/note2.md）

## 身份与时间线
测试人物活跃于二十世纪后半叶，其判断横跨投资、人事与自我管理三个领域。
| 时期 | 主张 | 触发事件 | 信度 |
|------|------|---------|------|
| 早期 | 价格优先，强调安全边际 | 早期资金规模小 | A |
| 近期 | 质量优先，愿为确定性付溢价 | 规模变大后摩擦成本上升 | A |

## 心智模型
### 可逆性优先
**一句话**：决策前先问这一步能不能退回来，能退的才值得试。
**证据**：在产品选型与人事任免两处都先问可逆性（A）；在时间分配上同样保留冗余（B）。
**生成力**：可推断他对不可逆的公开承诺会异常谨慎，即使收益看起来很高。
**局限**：当机会窗口极短、可逆选项不存在时，该框架会退化为犹豫。

### 逆向排除法
**一句话**：不追求做对，先系统排除必然做错的路。
**证据**：多次用反过来想重述问题（A）；在评估同行时先列失败模式（B）。
**生成力**：可推断他面对新领域时会先收集失败案例而不是成功案例。
**局限**：排除法在全新领域缺少历史失败样本时会失灵。

## 决策启发式
| 场景 | 启发式 | 反例 / 失效条件 | 信度 |
|------|--------|----------------|------|
| 面对高收益承诺 | 先问最坏情况是否致命 | 收益本身不可验证时失效 | A |
| 评估合作者 | 看激励结构而非表态 | 激励被隐藏时失效 | B |

## 表达DNA
- 句式指纹：短断言句为主，类比密度高，平均句长偏短。
- 风格标签轴：冷、具象、断言、口语。
- 口癖：反过来想；禁忌：不用时髦管理术语。

## 价值观与反模式
**排序**：当确定性与收益率冲突时，优先牺牲收益率、保住确定性。
**反模式**：明确反对用事后结果反推决策质量，反对在没有可选项信息时评价决策。

## 智识谱系
- 受影响于：早期统计学训练（本人承认，A）。
- 影响了：一批以排除法为方法论的从业者（他人归类，C）。

## 矛盾与张力
**时间性矛盾**：早期更看重低价，后期转向质量；两者在同一时期的不同领域仍然并存（A）。

## 信息缺口
- 早期（1990 年前）决策记录稀少，无法判断其框架的形成顺序。
- 家庭生活维度本人主动不公开，标注为主动不公开而非信息缺失。

## 变更记录
| 日期 | 动作 | 说明 |
|------|------|------|
| 2026-09-22 | initial | 首次蒸馏 |
"""

FRONTMATTER = """---
schema_version: 1
schema: {schema}
slug: {slug}
title: {title}
created: 2026-09-22
updated: 2026-09-22
version: 1
sources_total: {n_sources}
sources_primary: {n_sources}
sources_secondary: 0
confidence: {{A: 8, B: 3, C: 1, D: 1}}
source_words: {source_words}
distillate_words: {distillate_words}
compression_ratio: "{ratio}"
dimensions: {dimensions}
gaps:
  - 早期（1990 年前）决策记录稀少
---
"""


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def patch_json(path, mutate):
    data = _lib.load_json(path)
    mutate(data)
    _lib.write_json(path, data)
    return data


def count_density_items(body):
    """浓度公式里的「独立条目数」（直接测函数，避免只靠 CLI 输出反推）。"""
    return qc_mod.count_density_items(body)


SOURCE_TEXT = ("反过来想。可逆性判断在产品与人事两处都出现。\n"
               "激励机制错，人就做错事。早期更看重低价，后期转向质量。\n")
#: 第二份素材用**不同**内容：内容相同的话会被 sha256 判重跳过（那是正确的行为，
#: 见 TestIngest 的去重用例），但这里要的是一份有两份独立素材的档案。
SOURCE_TEXT_2 = ("反过来想，先问什么会导致失败，再倒推该做什么。\n"
                 "激励机制决定行为，看人先看激励结构。可逆性贯穿其决策。\n")


class ArchiveFixture:
    """构建一份**合法**档案，供各测试按需改坏某一点。"""

    def __init__(self, tmp, slug="munger", schema="person", body=DEFAULT_BODY,
                 seal=True, sources=("note1.md", "note2.md"), backfill=True):
        self.tmp = tmp
        self.slug = slug
        self.schema = schema
        self.body = body
        self.root = os.path.join(tmp, "distilled", slug)
        self.src_dir = os.path.join(tmp, "raw-" + slug)
        for i, name in enumerate(sources):
            write(os.path.join(self.src_dir, name),
                  SOURCE_TEXT if i == 0 else SOURCE_TEXT_2)

        r = run("ingest.py", self.src_dir, "--out", self.root,
                "--schema", schema, "--title", "测试人物 · 认知档案")
        assert r.returncode == 0, r.stdout + r.stderr
        self.manifest_path = os.path.join(self.root, "manifest.json")
        self.manifest = _lib.load_json(self.manifest_path)

        # research/ 底稿：>800 字才算 complete
        dims = _lib.SCHEMA_DIMENSIONS.get(schema, [])
        for _, _, fname in dims:
            write(os.path.join(self.root, "research", fname),
                  "### 条目一\n" + "素材内容，带信度标记（A）。" * 80 +
                  "\n\n### 条目二\n更多内容（B）。\n")

        # 重跑 ingest，让维度状态变成 complete（底稿已存在）
        run("ingest.py", self.src_dir, "--out", self.root,
            "--schema", schema, "--title", "测试人物 · 认知档案")
        self.manifest = _lib.load_json(self.manifest_path)

        if backfill:
            self.backfill()
        self.write_distillate()
        if seal:
            r = run("seal.py", self.root)
            assert r.returncode == 0, r.stdout + r.stderr

    def backfill(self, coverage=85):
        """模拟 Phase 3 的元数据回填：`coverage` 与一手/二手计数。

        脚本判不出这些值（那是语义判断），但**未回填是中间态，不是交付态**。
        `quality_check.py` 的「元数据已回填」是硬检查，所以一份「合法档案」
        的夹具必须是回填过的——否则它模拟的是半成品，不是交付品。
        """
        def mutate(m):
            for d in m.get("dimensions", []):
                if d.get("status") != "missing":
                    d["coverage"] = coverage
            n = len(m.get("sources", []))
            m["sources_primary"] = n
            m["sources_secondary"] = 0
        self.manifest = patch_json(self.manifest_path, mutate)
        return self.manifest

    def write_distillate(self, body=None, **fm_over):
        body = self.body if body is None else body
        dims = [n for _, n, _ in _lib.SCHEMA_DIMENSIONS.get(self.schema, [])]
        sw = self.manifest.get("source_words") or 100
        dw = _lib.count_words(body)
        fm = FRONTMATTER.format(
            schema=self.schema, slug=self.slug, title="测试人物 · 认知档案",
            n_sources=len(self.manifest.get("sources", [])),
            source_words=sw, distillate_words=dw,
            ratio="%d:1" % max(1, round(sw / max(1, dw))),
            dimensions="[%s]" % ", ".join(dims))
        for k, v in fm_over.items():
            # 回归：这里原先写的是 `fm.replace("%s: " % k, "%s: " % k, 1)`
            # ——用 X 替换 X 的恒等操作，`**fm_over` 参数被整个吞掉，
            # 调用方以为改了 frontmatter，实际什么都没发生。
            fm = re.sub(r"(?m)^%s:.*$" % re.escape(k), "%s: %s" % (k, v), fm, count=1)
        write(os.path.join(self.root, "DISTILLATE.md"), fm + "\n" + body)

    def distillate_path(self):
        return os.path.join(self.root, "DISTILLATE.md")


# --------------------------------------------------------------------------
# 1. _lib：frontmatter 子集解析
# --------------------------------------------------------------------------


class TestFrontmatterParsing(unittest.TestCase):

    def test_scalars_lists_maps_and_null(self):
        fm, body = _lib.parse_frontmatter(
            "---\n"
            "schema_version: 1\n"
            "sources_primary: null\n"
            "title: \"反脆弱：从不确定性中获益\"\n"
            "dimensions: [著作, 对话, 表达]\n"
            "confidence: {A: 22, B: 18, C: 8, D: 2}\n"
            "gaps:\n"
            "  - 早期记录稀少\n"
            "  - 家庭维度不公开\n"
            "---\n"
            "正文\n")
        self.assertEqual(fm["schema_version"], 1)          # 整数收敛
        self.assertIsNone(fm["sources_primary"])            # null → None
        self.assertEqual(fm["title"], "反脆弱：从不确定性中获益")  # 引号内冒号不截断
        self.assertEqual(fm["dimensions"], ["著作", "对话", "表达"])
        self.assertEqual(fm["confidence"], {"A": 22, "B": 18, "C": 8, "D": 2})
        self.assertEqual(fm["gaps"], ["早期记录稀少", "家庭维度不公开"])
        self.assertEqual(body, "正文")

    def test_empty_key_without_items_is_null_not_empty_list(self):
        """空值应表示「未回填」= null；显式 [] 才表示「确实为空」。"""
        fm, _ = _lib.parse_frontmatter("---\nsources_primary:\ngaps: []\n---\n")
        self.assertIsNone(fm["sources_primary"])
        self.assertEqual(fm["gaps"], [])

    def test_quoted_number_stays_string(self):
        fm, _ = _lib.parse_frontmatter('---\nslug: "2026"\n---\n')
        self.assertEqual(fm["slug"], "2026")
        self.assertIsInstance(fm["slug"], str)

    def test_missing_or_unclosed_frontmatter(self):
        self.assertEqual(_lib.parse_frontmatter("no fm here")[0], None)
        self.assertEqual(_lib.parse_frontmatter("---\na: 1\n")[0], None)

    def test_bom_tolerated(self):
        fm, _ = _lib.parse_frontmatter("\ufeff---\nslug: x\n---\nbody")
        self.assertEqual(fm["slug"], "x")

    def test_is_null_distinguishes_zero_from_unknown(self):
        """**null ≠ 0**：0 是判定结果，null 是没判。"""
        self.assertTrue(_lib.is_null(None))
        self.assertTrue(_lib.is_null("null"))
        self.assertFalse(_lib.is_null(0))
        self.assertFalse(_lib.is_null("0"))


# --------------------------------------------------------------------------
# 2. _lib：统计与渲染
# --------------------------------------------------------------------------


class TestLibStats(unittest.TestCase):

    def test_count_confidence_counts_recommended_form(self):
        """回归：`（A · 出处）` 是契约推荐的写法，必须被统计到。

        历史缺陷：`count_confidence` 自己写了一条正则，要求闭合括号紧跟在
        字母之后，于是只认裸的 `（A）`，反而不认 SKILL.md 与 artifact-format
        §2.3 推荐的 `（A · sources/x.md）`。后果是照契约写出来的档案在
        铁律 3 上判 FAIL（「正文未检出任何信度标记」），而 D 级占比因为
        分母恒为 0 而**永不触发**。
        """
        body = ("- 主张一（A · sources/notes/note1.md）\n"
                "- 主张二（B | §决策启发式）\n"
                "- 主张三（A）\n")
        c = _lib.count_confidence(body)
        self.assertEqual(c, {"A": 2, "B": 1, "C": 0, "D": 0})
        self.assertEqual(_lib.conf_total(c), 3)
        self.assertEqual(_lib.format_conf(c), "A2 B1 C0 D0")

    def test_count_confidence_ignores_mid_line_markers(self):
        """只认行尾——契约 §2.3 把「行中间出现（A）」定义为非元数据。

        宽松匹配会把 `（A 方案）` 这类正文括号算成信度，虚增分母并稀释 D 级占比。

        已知局限：行尾的 `见附录（B）` 与信度标记在语法上无法区分，会被计入。
        这是格式本身的歧义，契约选择「行尾即元数据」；档案正文用 `sources/`
        路径与 `§段名` 作出处，因此实际很少撞上。
        """
        c = _lib.count_confidence("某方案（A 方案）胜出，另见（B）附录")
        self.assertEqual(c, {"A": 0, "B": 0, "C": 0, "D": 0})

    def test_count_confidence_label_form(self):
        c = _lib.count_confidence("| 时期 | 主张 | 信度: A |")
        self.assertEqual(c, {"A": 1, "B": 0, "C": 0, "D": 0})

    def test_count_confidence_tolerates_trailing_punctuation(self):
        """行尾元数据后跟句末标点，仍应被认出。"""
        self.assertEqual(_lib.count_confidence("主张（A · sources/x.md）。"),
                         {"A": 1, "B": 0, "C": 0, "D": 0})

    def test_count_confidence_does_not_double_count_same_line(self):
        """同一行同时出现两种写法时只计一次。

        回归：`count_confidence` 先取行尾元数据、再无条件扫一遍 `信度: X` 标签，
        于是一行 `信度: D 的推断（D）` 会把 D 数成 2。分母虚高会直接扭曲
        铁律 3 的 D 级占比：重复的是 A 就低估、重复的是 D 就高估。
        """
        self.assertEqual(_lib.count_confidence("- 信度: A 主张（A）"),
                         {"A": 1, "B": 0, "C": 0, "D": 0})
        self.assertEqual(_lib.count_confidence("信度：D 的推断（D）"),
                         {"A": 0, "B": 0, "C": 0, "D": 1})
        # 两种写法各自的单独路径仍然有效
        self.assertEqual(_lib.count_confidence("| 时期 | 信度: B |"),
                         {"A": 0, "B": 1, "C": 0, "D": 0})
        self.assertEqual(_lib.count_confidence("主张（C）"),
                         {"A": 0, "B": 0, "C": 1, "D": 0})

    def test_d_ratio_is_actually_enforced(self):
        """回归：D 级占比必须真的算得出来。

        历史缺陷下，全 D 的档案（用推荐写法）算出的 d_ratio 是 0.0，
        等于铁律 3 的「D <20%」规则处于永不触发的死状态。
        """
        all_d = "".join("- 断言%d（D · sources/a.md）\n" % i for i in range(10))
        c = _lib.count_confidence(all_d)
        self.assertEqual(_lib.conf_total(c), 10)
        self.assertEqual(_lib.d_ratio(c), 100.0)

    def test_d_ratio(self):
        self.assertEqual(_lib.d_ratio({"A": 8, "B": 0, "C": 0, "D": 2}), 20.0)
        self.assertEqual(_lib.d_ratio({"A": 0, "B": 0, "C": 0, "D": 0}), 0.0)

    def test_skeleton_items_strips_marker_and_detects_pointer(self):
        body = ("## 核心骨架\n"
                "- 有出处的主张（A · sources/notes/x.md）\n"
                "- 没出处的主张（B）\n"
                "- 完全没标的主张\n")
        items = _lib.skeleton_items(body)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0], ("有出处的主张", "A", True))
        self.assertEqual(items[1], ("没出处的主张", "B", False))
        self.assertEqual(items[2], ("完全没标的主张", None, False))

    def test_skeleton_items_ignores_mid_line_letters(self):
        """只认行尾信度标记——正文中间的（A）不算。"""
        body = "## 核心骨架\n- 某方案（A 方案）胜出\n"
        self.assertIsNone(_lib.skeleton_items(body)[0][1])

    def test_has_source_pointer_variants(self):
        for s in ("见 sources/books/a.pdf", "见 a.pdf", "https://x.com/y",
                  "见 §决策启发式", "见 [S003]"):
            self.assertTrue(_lib.has_source_pointer(s), s)
        self.assertFalse(_lib.has_source_pointer("只是一句话"))

    def test_truncate_by_display_width(self):
        self.assertEqual(_lib.truncate("abcdef", 4), "abc…")
        self.assertEqual(_lib.truncate("中文字", 6), "中文字")
        self.assertEqual(_lib.dw("中文"), 4)
        self.assertEqual(_lib.dw("ab"), 2)

    def test_render_table_groups_and_widths(self):
        lines = _lib.render_table(("a", "b"), [[("1", "2")], [("3", "4")]], (5, 5))
        self.assertTrue(lines[0].startswith("┌"))
        self.assertTrue(lines[-1].startswith("└"))
        # 顶 + 表头 + 分隔 + 组1行 + 组分隔 + 组2行 + 底
        self.assertEqual(len(lines), 7)
        self.assertTrue(all(_lib.dw(x) == _lib.dw(lines[0]) for x in lines))

    def test_split_trailing_meta_variants(self):
        self.assertEqual(_lib.split_trailing_meta("主张（A）"), ("主张", "A"))
        self.assertEqual(_lib.split_trailing_meta("主张（A · sources/x.md）"),
                         ("主张", "A"))
        self.assertEqual(_lib.split_trailing_meta("主张（B | §决策启发式）"),
                         ("主张", "B"))
        # 正文括号不能被当成元数据
        self.assertEqual(_lib.split_trailing_meta("某方案（A 方案）"), ("某方案（A 方案）", None))
        # 括号里有两个字母 → 不是信度标记
        self.assertEqual(_lib.split_trailing_meta("对比（A 与 B）"), ("对比（A 与 B）", None))

    # ---- 表格信度列（回归：契约内部自相矛盾） ----

    def test_count_confidence_reads_table_confidence_column(self):
        """回归：schema-*.md 规定专属段用带「信度」列的表格，而
        `count_confidence` 只认行尾括号——照契约写的档案会被系统性少计，
        一份主要靠表格承载主张的档案甚至直接 FAIL「正文未检出任何信度标记」。
        检查在惩罚正确输出，且契约自己跟自己打架。
        """
        body = ("| 场景 | 启发式 | 反例 | 信度 |\n"
                "|------|--------|------|------|\n"
                "| 定价 | 先做减法 | 功能多时 | A |\n"
                "| 招聘 | 招慢一点 | 紧急时 | B |\n"
                "| 合作 | 看激励结构 | 激励隐藏时 | A 级 |\n")
        self.assertEqual(_lib.count_confidence(body), {"A": 2, "B": 1, "C": 0, "D": 0})

    def test_count_confidence_ignores_tables_without_confidence_column(self):
        """没有「信度」列名的表格不算——列名给了语义，不靠猜单元格内容。"""
        body = ("| 术语 | 本文档定义 | 出现位置 |\n"
                "|------|-----------|--------|\n"
                "| A | 某个概念 | §2 |\n")
        self.assertEqual(_lib.conf_total(_lib.count_confidence(body)), 0)

    def test_table_confidence_does_not_double_count_line_meta(self):
        """同一行既有 `信度: X` 标签又在信度列里时只计一次，避免分母虚高。

        表格行以 `|` 结尾，行尾元数据正则匹配不到，所以真正会撞车的是
        「标签 vs 信度列」。优先级：行尾元数据 > 表格信度列 > `信度: X` 标签。
        """
        body = ("| 项 | 信度 |\n|----|----|\n"
                "| 主张一 信度: B | A |\n")
        self.assertEqual(_lib.count_confidence(body), {"A": 1, "B": 0, "C": 0, "D": 0})

    # ---- 和稀泥：引用与提及不是主张 ----

    def test_quoted_mention_of_harmony_is_not_harmony(self):
        """回归：HARMONY_RE 是纯字符串匹配，分不清「主张」与「提及」——
        一份**明确否定**抹平写法的档案会被原样判成和稀泥并硬性 FAIL。
        这与曾经把「虽然…但是」当罪证是同一类错误。
        """
        self.assertFalse(_lib.has_harmony(
            "本节刻意未使用「其实两者并不冲突」这类抹平表述。"))
        self.assertFalse(_lib.has_harmony("禁止写成「殊途同归」式的结论。"))

    def test_real_denial_of_opposition_is_still_harmony(self):
        """剥离引用不能把真抹平一起放过。"""
        self.assertTrue(_lib.has_harmony("早期重低价、后期重质量，其实两者并不冲突。"))
        self.assertTrue(_lib.has_harmony("两派观点殊途同归。"))

    # ---- 张力类型必须成标签 ----

    def test_labeled_tension_types_requires_a_label(self):
        """回归：只做 `"时间性" in sec` 的子串匹配时，一句「按要求写出
        『时间性』这个词」就能让占位档案白拿「矛盾已分类」。"""
        self.assertEqual(_lib.labeled_tension_types("**时间性张力**：早期…"), ["时间性张力"])
        self.assertEqual(_lib.labeled_tension_types("还有**本质性张力**一处"), ["本质性张力"])
        self.assertEqual(_lib.labeled_tension_types("本节写出「时间性」这个词"), [])

    # ---- 「未发现矛盾」的长度量在声明句上 ----

    def test_declaration_sentence_is_the_sentence_not_the_section(self):
        """回归：长度门槛原先量的是整段（`len(sec)`），于是
        「未发现矛盾。」后面补 30 个「哈」就能过。"""
        self.assertEqual(len(_lib.declaration_sentence("未发现矛盾。")), 6)
        self.assertEqual(len(_lib.declaration_sentence("未发现矛盾。" + "哈" * 60)), 6)
        self.assertEqual(
            len(_lib.declaration_sentence("已比对全文各章节的立场陈述，未发现前后不一致。")), 23)

    # ---- 骨架条目符号与标题 near miss ----

    def test_skeleton_items_accepts_all_list_markers(self):
        """回归：只认 `-` `*` `1.` 时，`+` 与 `1)` `1、` 写的骨架会被静默丢弃，
        3 条变 2 条直接撞上下限 FAIL。顿号列表（`1、内容`）在中文里最常见，
        且**不带空格**。
        """
        body = ("## 核心骨架\n"
                "+ a（A · sources/x.md）\n"
                "1) b（A · sources/y.md）\n"
                "2、c（A · sources/z.md）\n"
                "- d（A · sources/w.md）\n")
        self.assertEqual(len(_lib.skeleton_items(body)), 4)

    def test_skeleton_items_does_not_eat_decimals(self):
        """`.` 分支要求空格，否则 `1.5 倍` 会被当成「第 1 条：5 倍」。"""
        body = "## 核心骨架\n1.5 倍增长（A · sources/x.md）\n"
        self.assertEqual(len(_lib.skeleton_items(body)), 0)

    def test_near_miss_headings_explains_a_malformed_heading(self):
        """回归：`section()` 严格匹配是契约，但 miss 时必须说清原因——
        否则 agent 拿到「没提炼」这个错误根因，会去改内容，而问题在标题格式。
        """
        self.assertEqual(_lib.near_miss_headings("## 核心骨架\n- a\n", "核心骨架"), [])
        self.assertIn("不能带后缀",
                      "".join(_lib.near_miss_headings("## 核心骨架（3-10 条）\n", "核心骨架")))
        self.assertIn("层级写错了",
                      "".join(_lib.near_miss_headings("### 核心骨架\n", "核心骨架")))

    # ---- 畸形嵌套 manifest 不该让诊断工具崩掉 ----

    def test_manifest_accessors_tolerate_malformed_nesting(self):
        """回归：`load_manifest` 只保证顶层是对象，嵌套畸形
        （`dimensions: ["著作"]`）会让 4 个脚本同时 traceback。"""
        m = {"dimensions": ["著作", {"name": "对话"}], "sources": ["a", {"id": "S001"}]}
        self.assertEqual(_lib.manifest_dimensions(m), [{"name": "对话"}])
        self.assertEqual(_lib.manifest_sources(m), [{"id": "S001"}])
        self.assertEqual(_lib.manifest_dimensions({"dimensions": "x"}), [])
        self.assertEqual(_lib.manifest_sources(None), [])

    def test_sha256_file_returns_none_when_unreadable(self):
        """读不到返回 None，而不是抛异常——调用方全是诊断工具，崩掉比报错更糟。
        但也**不能**返回空串：那会让「读不到」伪装成「哈希一致」。"""
        self.assertIsNone(_lib.sha256_file("/nonexistent/path/xyz"))
        self.assertIsNone(_lib.sha256_file(tempfile.mkdtemp()))


# --------------------------------------------------------------------------
# 3. quality_check：十二项结构检查 + 缺陷回归
# --------------------------------------------------------------------------


class TestQualityCheck(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fx = ArchiveFixture(self.tmp)

    def qc(self, *args):
        return run("quality_check.py", self.fx.root, *args)

    def test_valid_archive_passes_all_checks(self):
        r = self.qc()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("12/12 通过", r.stdout)
        # 通过文案必须说清「这只是结构过关」，不能给虚假的质量保证
        self.assertIn("不代表内容可信", r.stdout)

    def test_harmony_contradiction_is_rejected(self):
        """回归：原实现里 `and not found` 让和稀泥检测成为死代码，
        含「虽然…但是」的档案照样 PASS —— 直接违反铁律 2。

        注意这条用例真正致命的是「本质上统一」这个**否认对立**的断言；
        转折句式本身已不再是罪证（见 test_turn_of_phrase_is_not_harmony）。
        """
        self.fx.write_distillate(body=DEFAULT_BODY.replace(
            "**时间性矛盾**：早期更看重低价，后期转向质量；两者在同一时期的不同领域仍然并存（A）。",
            "**时间性矛盾**：虽然早期更看重低价，但是后期转向质量，本质上统一。（A）"))
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("和稀泥", r.stdout)
        self.assertIn("矛盾保留与分类", r.stdout)

    def test_typed_contradiction_without_harmony_passes(self):
        r = self.qc()
        self.assertIn("矛盾已分类", r.stdout)

    # ---- 和稀泥的判据是「信息量净减少」，不是句式 ----

    def test_turn_of_phrase_is_not_harmony(self):
        """「虽然…但是」本身合法——它是描述张力的正确写法之一。

        回归：HARMONY_RE 曾把 30 字内的任何「虽然…但是」判为和稀泥，且和稀泥
        检查排在类型标注之前，于是一条**标注齐全的时间性张力**只要用了转折句式
        就被硬性 FAIL。作者为了过检只能删掉真实矛盾或改写成别扭的句子——
        检查在惩罚正确输出，并诱导违反铁律 2。
        """
        self.rewrite_tension(
            "**时间性张力**：他早期虽然在多个场合强调多元化，"
            "但是 2019 年后转向聚焦单一主线（A · sources/notes/note1.md）。")
        r = self.qc()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("矛盾已分类", r.stdout)

    def test_denial_of_opposition_fails_even_with_type_label(self):
        """标了类型不等于可以抹平——「并不冲突」仍然直接 FAIL。

        类型标注不能给和稀泥洗白：分类是对张力的描述，抹平是对张力的删除，
        两件事。这条守的是「和稀泥检查必须排在类型检查之前」。
        """
        self.rewrite_tension(
            "**时间性张力**：早期主张低价优先，后期转向质量优先，"
            "其实两者并不冲突（A）。")
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("和稀泥", r.stdout)

    def test_comprehensive_rewrite_is_not_harmony(self):
        """正确的综合（信息量增加）不该被判成和稀泥。

        补上条件差异的转折是**综合**——两条主张都在，还多出了归因。
        抹平的对立面不是「并列摆着」，是「正确地综合」。
        """
        self.rewrite_tension(
            "**领域性张力**：他在工作中虽然主张放权，但是在家庭里事无巨细——"
            "因为他对「可控性」的权重随场景不同（A · sources/notes/note1.md）。")
        r = self.qc()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_turn_phrase_without_type_label_is_soft_only(self):
        """转折句式 + 无类型标注 → 软诊断提示，但失败原因是「未分类」而非「和稀泥」。

        缺标注的转折多半是把对立揉平了，值得复核一眼；但它不能被硬判成和稀泥，
        否则又会回到「句式当罪证」。硬 FAIL 的理由必须是「二选一」。
        """
        self.rewrite_tension("他虽然在公开场合推崇长期主义，但是在内部信里反复强调季度数字。")
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("二选一", r.stdout)
        self.assertNotIn("和稀泥", r.stdout)

    # ---- 「确实没有矛盾」的合法出口（回归：曾与评分卡口径冲突）----

    TENSION_LINE = ("**时间性矛盾**：早期更看重低价，后期转向质量；"
                    "两者在同一时期的不同领域仍然并存（A）。")

    def rewrite_tension(self, replacement):
        """换掉矛盾段正文并重新封存，让失败原因可归因到矛盾检查本身。"""
        self.fx.write_distillate(body=DEFAULT_BODY.replace(self.TENSION_LINE, replacement))
        run("seal.py", self.fx.root)

    def test_explicit_no_tension_declaration_passes(self):
        """确实核查过而无矛盾时，显式声明「未发现矛盾」应当通过。

        回归：硬检查此前要求矛盾段必须含类型词，于是一份内部自洽的材料只有
        两条路——编一条矛盾出来（违反铁律 1），或永远过不了静态关。而评分卡
        本来就写着「素材确实无矛盾 = 8/15 分」。两边口径必须一致，否则
        「诚实」在静态关被惩罚、在评分卡被奖励。
        """
        self.rewrite_tension("已比对全文各章节的立场陈述与三份素材的时间线，"
                             "未发现前后不一致之处。")
        r = self.qc()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("未发现矛盾", r.stdout)
        # 合法但该被看见：声明无矛盾会进软诊断提示复核（不拦截）
        self.assertIn("确认是核查过而不是漏读", r.stdout)

    def test_empty_tension_section_still_fails(self):
        """留空不算「没有矛盾」——沉默区分不了「真的没有」与「没看」。"""
        self.rewrite_tension("（本节待补）")
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("二选一", r.stdout)

    def test_too_short_no_tension_declaration_fails(self):
        """一句「未发现矛盾。」就交差，大概率是漏读——声明句不足最小长度不认。

        回归：长度门槛原先量的是**整段**长度（`len(sec)`），于是
        「未发现矛盾。」后面补 30 个「哈」就能过——契约要的是「显式声明
        **并说明核查范围**」，量整段等于没量。
        """
        self.rewrite_tension("未发现矛盾。")
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("声明句只有", r.stdout)

    def test_no_tension_length_is_measured_on_the_sentence(self):
        """回归：整段凑字不该让一句空洞的声明过关。"""
        self.rewrite_tension("未发现矛盾。" + "哈" * 60)
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("声明句只有", r.stdout)

    def test_no_tension_declaration_cannot_launder_harmony(self):
        """声明「未发现矛盾」不能给和稀泥洗白——和稀泥仍然直接 0 分。

        和稀泥检查必须排在「没标类型」之前，否则同时命中时会被报成
        「未标注类型」，把真正的问题（抹平）藏起来。
        """
        self.rewrite_tension("已比对全文各章节，未发现矛盾——其实两者是互补的，并不冲突。")
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("和稀泥", r.stdout)

    def test_d_ratio_over_20_percent_fails(self):
        self.fx.write_distillate(body=DEFAULT_BODY.replace(
            "## 核心骨架", "## 核心骨架\n- 一条（D）\n- 两条（D）\n- 三条（D）\n- 四条（D）\n"))
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("D 级", r.stdout)

    def test_unsealed_hash_fails(self):
        """回归：此前没有任何脚本会计算 distillate_sha256，它永远是 null。"""
        patch_json(self.fx.manifest_path,
                   lambda m: m.update({"distillate_sha256": None}))
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("未封存", r.stdout)

    def test_stale_hash_fails(self):
        with open(self.fx.distillate_path(), "a", encoding="utf-8") as f:
            f.write("\n改了一行\n")
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("已过期", r.stdout)

    def test_missing_manifest_field_fails(self):
        patch_json(self.fx.manifest_path, lambda m: m.pop("meta_sources"))
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("meta_sources", r.stdout)

    def test_unsupported_schema_version_fails(self):
        txt = _lib.read_text(self.fx.distillate_path()).replace(
            "schema_version: 1", "schema_version: 99", 1)
        write(self.fx.distillate_path(), txt)
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("高于本 skill 支持", r.stdout)

    def test_gaps_null_fails(self):
        txt = _lib.read_text(self.fx.distillate_path()).replace(
            "gaps:\n  - 早期（1990 年前）决策记录稀少\n", "gaps:\n", 1)
        write(self.fx.distillate_path(), txt)
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("gaps 未回填", r.stdout)

    def test_empty_gaps_with_low_coverage_fails(self):
        """scorecard 规则：gaps 为空但存在 coverage<40 的维度 = 装懂。"""
        txt = _lib.read_text(self.fx.distillate_path()).replace(
            "gaps:\n  - 早期（1990 年前）决策记录稀少\n", "gaps: []\n", 1)
        write(self.fx.distillate_path(), txt)
        patch_json(self.fx.manifest_path, lambda m: m["dimensions"][0].update({"coverage": 10}))
        run("seal.py", self.fx.root)
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("装懂", r.stdout)

    def test_too_few_skeleton_items_fails(self):
        self.fx.write_distillate(body=DEFAULT_BODY.replace(
            "- 用可逆性判断替代预测，只在错了也不致命时下注（A · sources/notes/note1.md）\n", "")
            .replace("- 反过来想：先问什么会导致失败，再倒推该做什么（A · sources/notes/note1.md）\n", ""))
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("核心骨架仅", r.stdout)

    def test_json_output_shape(self):
        r = self.qc("--json")
        data = json.loads(r.stdout)
        self.assertEqual(len(data["checks"]), 12)
        self.assertTrue(data["ok"])
        self.assertEqual(data["passed"], 12)

    def test_missing_source_pointer_is_now_a_hard_check(self):
        """回归：骨架缺出处指针原先只是**软诊断**，而技能级评测的断言
        却承诺了「每条核心骨架都带出处指针」——承诺与执行对不上，
        评测就在说谎。现在落成硬检查（契约 §2.3 本就要求「每条主张都要能
        回答两个问题：多可信、从哪来」）。
        """
        self.fx.write_distillate(body=DEFAULT_BODY.replace(
            "（A · sources/notes/note1.md）", "（A）"))
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("无出处指针", r.stdout)

    def test_accepts_distillate_path_as_well_as_dir(self):
        r = run("quality_check.py", self.fx.distillate_path())
        self.assertEqual(r.returncode, 0, r.stdout)

    # ---- 新增硬检查（原先只是软诊断，而 evals 的断言却承诺了它们） ----

    def test_empty_placeholder_archive_is_rejected(self):
        """回归：一份零提炼的占位档案曾能拿「7/7 通过 · 退出码 0 · 🎉 全部通过」。

        当时那 7 项检查全是结构/正则，没有一项读内容：3 个空骨架、矛盾段写「时间性」
        这个词、缺口段写「（本节待补）」、填充句 + 空 `###` 凑浓度 —— 全部通过。
        **虚假的通过比缺失的功能危险，因为不可见。**
        """
        body = ("\n# 占位档案\n\n## 一句话\n占位。\n\n## 核心骨架\n"
                "- 占位一（A）\n- 占位二（A）\n- 占位三（A）\n\n"
                "## 心智模型\n")
        body += "这是占位句子，不含任何主张或证据，仅用于凑字数。" * 40 + "\n"
        for i in range(7):
            body += "### 占位小节%d\n\n" % i
        body += ("\n## 矛盾与张力\n本节尚无内容，但按要求写出「时间性」这个词。\n\n"
                 "## 信息缺口\n（本节待补）\n\n## 变更记录\n| 日期 | 动作 | 说明 |\n")
        dims = [n for _, n, _ in _lib.SCHEMA_DIMENSIONS["person"]]
        head = ("---\nschema_version: 1\nschema: person\nslug: %s\n"
                "title: 占位档案\ncreated: 2026-09-22\nupdated: 2026-09-22\nversion: 1\n"
                "sources_total: 2\nsources_primary: 2\nsources_secondary: 0\n"
                "confidence: {A: 3, B: 0, C: 0, D: 0}\n"
                "source_words: 100\ndistillate_words: 900\ncompression_ratio: \"1:9\"\n"
                "dimensions: [%s]\ngaps: []\n---\n" % (self.fx.slug, ", ".join(dims)))
        write(self.fx.distillate_path(), head + body)
        run("seal.py", self.fx.root)
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        # 骨架无出处、矛盾段没真分类、缺口段是空壳、浓度靠空 ### 凑 —— 全被拦下
        self.assertIn("无出处指针", r.stdout)
        self.assertIn("矛盾段既未标注类型", r.stdout)
        self.assertIn("等于没写", r.stdout)
        self.assertIn("水太多", r.stdout)

    def test_tension_type_word_alone_is_not_a_classification(self):
        """回归：只做子串匹配时，写「时间性」三个字就算「矛盾已分类」。"""
        self.rewrite_tension("本节按模板要求写出「时间性」这个词。")
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("二选一", r.stdout)

    def test_empty_h3_sections_do_not_count_toward_density(self):
        """回归：`###` 标题曾无条件计入条目数，加空小节就是免费分子——
        一份零提炼的档案能靠 7 个空 `###` 算出「每千字 10.7 条」的健康浓度。
        """
        with_empty = DEFAULT_BODY + "\n" + "### 空小节\n\n" * 8
        self.assertEqual(count_density_items(DEFAULT_BODY),
                         count_density_items(with_empty))
        # 有内容的小节仍然算数（夹具里「心智模型」下的两个 ### 都有正文）
        self.assertEqual(count_density_items(DEFAULT_BODY), 5)

    def test_research_draft_missing_fails(self):
        os.remove(os.path.join(self.fx.root, "research", "01-writings.md"))
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("没有 research/ 底稿", r.stdout)

    def test_empty_sources_list_fails(self):
        patch_json(self.fx.manifest_path, lambda m: m.update({"sources": []}))
        run("seal.py", self.fx.root)
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("没有素材依据", r.stdout)

    def test_unfilled_metadata_fails(self):
        """交付时元数据还停在 null，评分卡的覆盖度与装懂检测都会静默失效。"""
        patch_json(self.fx.manifest_path, lambda m: m.update({"sources_primary": None}))
        run("seal.py", self.fx.root)
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("未回填", r.stdout)

    # ---- frontmatter 交叉校验 ----

    def test_frontmatter_xref_catches_inconsistencies(self):
        cases = [
            ("dimensions: [著作, 对话, 表达, 他者, 决策, 时间线]",
             "dimensions: [著作, 对话]", "dimensions 应为"),
            ("slug: munger", "slug: someone-else", "与目录名"),
            ("sources_total: 2", "sources_total: 99", "≠ 一手"),
            ("confidence: {A: 8, B: 3, C: 1, D: 1}", "confidence: 8", "confidence 须为行内映射"),
            ("created: 2026-09-22", "created: 2026/09/22", "YYYY-MM-DD"),
        ]
        for old, new, expect in cases:
            with self.subTest(new=new):
                self.fx.write_distillate()
                txt = _lib.read_text(self.fx.distillate_path()).replace(old, new, 1)
                write(self.fx.distillate_path(), txt)
                r = self.qc()
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(expect, r.stdout)

    def test_too_many_skeleton_items_fails(self):
        extra = "".join("- 补充条目%d（A · sources/notes/note1.md）\n" % i for i in range(9))
        self.fx.write_distillate(body=DEFAULT_BODY.replace(
            "## 核心骨架\n", "## 核心骨架\n" + extra))
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("没取舍", r.stdout)

    def test_frontmatter_missing_field_and_bad_enum(self):
        for old, new, expect in (("title: 测试人物 · 认知档案", "x: y", "缺少字段"),
                                 ("schema: person", "schema: blog", "schema 取值非法")):
            with self.subTest(new=new):
                self.fx.write_distillate()
                txt = _lib.read_text(self.fx.distillate_path()).replace(old, new, 1)
                write(self.fx.distillate_path(), txt)
                r = self.qc()
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(expect, r.stdout)

    def test_malformed_skeleton_heading_gives_actionable_error(self):
        """回归：标题写成 `## 核心骨架（3-10 条）` 时，失败信息只会说
        「没提炼」——指向错误根因，agent 会去改内容。"""
        self.fx.write_distillate(body=DEFAULT_BODY.replace(
            "## 核心骨架\n", "## 核心骨架（3-10 条）\n"))
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("疑似标题写变形", r.stdout)

    def test_density_upper_bound_fails_only_for_long_bodies(self):
        """上限只在正文 ≥800 字时才判——短文档天然密度高。

        回归：`check_density` 此前零测试，5/20 上下限、`<200` 字分支、
        `>=800` 才判上限的分支一条都没跑过。
        """
        skel = "## 核心骨架\n" + "".join(
            "- 条目%d（A · sources/notes/note1.md）\n" % i for i in range(8))
        section = ("### 模型%d\n这是该模型的展开说明，含证据与局限，"
                   "也交代了适用边界。另有一条注意事项。\n\n")

        # 短正文：密度必然超上限，但不应判 FAIL
        short = skel + "\n## 心智模型\n" + "".join(section % i for i in range(4))
        self.assertLess(_lib.count_words(short), 800)
        self.assertGreaterEqual(_lib.count_words(short), 200)
        self.assertGreater(count_density_items(short) * 1000.0 / _lib.count_words(short), 20)
        self.fx.write_distillate(body=short)
        r = self.qc()
        self.assertIn("上限未判定", r.stdout)

        # 长正文（≥800 字）却条目过密 → 判 FAIL
        long_body = skel + "\n## 心智模型\n" + "".join(section % i for i in range(25))
        words = _lib.count_words(long_body)
        self.assertGreaterEqual(words, 800)
        self.assertGreater(count_density_items(long_body) * 1000.0 / words, 20)
        self.fx.write_distillate(body=long_body)
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("没展开", r.stdout)

    def test_density_rejects_too_short_body(self):
        self.fx.write_distillate(body="## 核心骨架\n- 一（A · s/x.md）\n")
        r = self.qc()
        self.assertEqual(r.returncode, 1)
        self.assertIn("样本太小", r.stdout)


# --------------------------------------------------------------------------
# 4. ingest：契约字段、判重、null 语义、旧数据迁移
# --------------------------------------------------------------------------


class TestIngest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_writes_contract_fields_and_null_defaults(self):
        """ingest 自己产出的 manifest：语义字段一律 null（**不是 0**）。

        用 `backfill=False` 拿的是 **ingest 刚写完、agent 还没判定**的状态——
        那正是这条用例要断言的东西。交付态必须已回填（见
        TestQualityCheck 的「元数据已回填」硬检查）。
        """
        fx = ArchiveFixture(self.tmp, backfill=False)
        m = fx.manifest
        for key in ("meta_sources", "source_overlap", "changes",
                    "distillate_sha256", "sources_primary", "sources_secondary"):
            self.assertIn(key, m)
        self.assertIsNone(m["meta_sources"])
        self.assertEqual(m["source_overlap"], [])
        # 脚本不做语义判定 → 未回填一律 null（**不是 0**）
        self.assertIsNone(m["sources_primary"])
        self.assertIsNone(m["sources_secondary"])
        for d in m["dimensions"]:
            self.assertIsNone(d["coverage"])
            self.assertIsNone(d["sources"])

    def test_dedupes_by_sha256_and_bumps_version(self):
        fx = ArchiveFixture(self.tmp)
        v1 = fx.manifest["version"]
        r = run("ingest.py", fx.src_dir, "--out", fx.root)
        self.assertIn("跳过重复", r.stdout)
        self.assertEqual(_lib.load_json(fx.manifest_path)["version"], v1)

    def test_assigns_unique_source_ids_after_deletion(self):
        fx = ArchiveFixture(self.tmp)
        patch_json(fx.manifest_path, lambda m: m["sources"].pop(0))
        write(os.path.join(fx.src_dir, "note3.md"), "全新内容，哈希不同。\n")
        run("ingest.py", fx.src_dir, "--out", fx.root)
        ids = [s["id"] for s in _lib.load_json(fx.manifest_path)["sources"]]
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_migrates_legacy_zero_defaults_to_null(self):
        """旧版 ingest 把「未回填」写成 0，与「判定为 0」无法区分。
        ingest 必须把这种无歧义的旧默认值迁移成 null。"""
        fx = ArchiveFixture(self.tmp)
        def degrade(m):
            for d in m["dimensions"]:
                d.update({"coverage": 0, "sources": 0,
                          "confidence": {"A": 0, "B": 0, "C": 0, "D": 0}})
            m["sources_primary"] = 0
            m["sources_secondary"] = 0
        patch_json(fx.manifest_path, degrade)
        run("ingest.py", fx.src_dir, "--out", fx.root)
        m = _lib.load_json(fx.manifest_path)
        self.assertIsNone(m["dimensions"][0]["coverage"])
        self.assertIsNone(m["sources_primary"])
        self.assertIsNone(m["sources_secondary"])

    def test_keeps_real_judgements(self):
        """真判定（一手 0、二手 5）不能被迁移掉。"""
        fx = ArchiveFixture(self.tmp)
        patch_json(fx.manifest_path,
                   lambda m: m.update({"sources_primary": 0, "sources_secondary": 5}))
        run("ingest.py", fx.src_dir, "--out", fx.root)
        m = _lib.load_json(fx.manifest_path)
        self.assertEqual(m["sources_primary"], 0)
        self.assertEqual(m["sources_secondary"], 5)

    def test_binary_source_gets_null_words(self):
        write(os.path.join(self.tmp, "raw", "book.pdf"), "%PDF-1.4 fake\n")
        out = os.path.join(self.tmp, "distilled", "bin")
        r = run("ingest.py", os.path.join(self.tmp, "raw"), "--out", out)
        self.assertIn("待抽文本", r.stdout)
        s = _lib.load_json(os.path.join(out, "manifest.json"))["sources"][0]
        self.assertIsNone(s["words"])

    def test_dedupes_within_a_single_run(self):
        """回归：判重表只取**运行前**的快照，本次新增的摘要从不加进去——
        同一批里两个内容相同的文件会被各记一条（sha256 完全相同），
        要再跑一次才去重。这与脚本自己承诺的「sha256 相同的素材跳过，
        不重复计入」直接矛盾，并让 sources_total / source_words 虚高。
        """
        write(os.path.join(self.tmp, "raw", "a.md"), "同一份内容。\n")
        write(os.path.join(self.tmp, "raw", "sub", "b.md"), "同一份内容。\n")
        out = os.path.join(self.tmp, "distilled", "dup")
        r = run("ingest.py", os.path.join(self.tmp, "raw"), "--out", out)
        self.assertEqual(r.returncode, 0, r.stdout)
        srcs = _lib.load_json(os.path.join(out, "manifest.json"))["sources"]
        self.assertEqual(len(srcs), 1, "单次运行内未去重：%s" % [s["path"] for s in srcs])

    def test_ingesting_the_archive_dir_does_not_eat_the_archive(self):
        """回归：`ingest.py <档案目录> --out <同一目录>` 会把 DISTILLATE.md /
        manifest.json / research/ 当成素材复制进 sources/ —— 清单凭空膨胀，
        而且 `manifest.json` 因 `.json` 在 TYPE_BY_EXT 里被归类成 **chat**。
        用户很自然会这么敲（想把新丢进 sources/ 的文件补进来）。
        """
        fx = ArchiveFixture(self.tmp)
        before = len(fx.manifest["sources"])
        r = run("ingest.py", fx.root, "--out", fx.root)
        self.assertEqual(r.returncode, 0, r.stdout)
        m = _lib.load_json(fx.manifest_path)
        self.assertEqual(len(m["sources"]), before, "档案本体被当成素材吃进去了")
        types = {s["type"] for s in m["sources"]}
        self.assertNotIn("chat", types, "manifest.json 被归类成 chat 素材")

    def test_dimension_status_uses_word_count_not_char_count(self):
        """回归：维度状态用 `len(body) > 800`（字符数）判定，而库里所有字数
        口径都是「CJK 按字、拉丁按词」。900 字符的英文底稿 count_words 只有
        约 150 词，会被误判成 complete。
        """
        out = os.path.join(self.tmp, "distilled", "en")
        run("ingest.py", os.path.join(self.tmp, "raw"), "--out", out)
        # 900 个字符的英文，实际只有 ~150 个词
        write(os.path.join(out, "research", "01-writings.md"),
              "word " * 180)
        run("ingest.py", os.path.join(self.tmp, "raw"), "--out", out)
        d = _lib.load_json(os.path.join(out, "manifest.json"))["dimensions"][0]
        self.assertEqual(d["status"], "partial")


# --------------------------------------------------------------------------
# 5. seal
# --------------------------------------------------------------------------


class TestSeal(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fx = ArchiveFixture(self.tmp, seal=False)

    def test_seal_then_check_then_edit_then_reseal(self):
        r = run("seal.py", self.fx.root)
        self.assertEqual(r.returncode, 0, r.stdout)
        digest = _lib.sha256_file(self.fx.distillate_path())
        self.assertEqual(_lib.load_json(self.fx.manifest_path)["distillate_sha256"], digest)

        self.assertEqual(run("seal.py", self.fx.root, "--check").returncode, 0)

        with open(self.fx.distillate_path(), "a", encoding="utf-8") as f:
            f.write("\n新增一行\n")
        self.assertEqual(run("seal.py", self.fx.root, "--check").returncode, 1)
        self.assertEqual(run("seal.py", self.fx.root).returncode, 0)
        self.assertEqual(run("seal.py", self.fx.root, "--check").returncode, 0)

    def test_seal_uses_sha256_of_raw_file_bytes(self):
        """哈希算法是契约的一部分：改算法 = 让所有基于旧哈希的下游产物误报漂移。
        用 sha256("abc") 的公开黄金值把算法钉死。"""
        p = os.path.join(self.tmp, "abc.txt")
        write(p, "abc")
        self.assertEqual(
            _lib.sha256_file(p),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_seal_without_manifest_errors(self):
        os.remove(self.fx.manifest_path)
        self.assertEqual(run("seal.py", self.fx.root).returncode, 1)

    def test_seal_does_not_bump_version(self):
        before = _lib.load_json(self.fx.manifest_path)["version"]
        run("seal.py", self.fx.root)
        self.assertEqual(_lib.load_json(self.fx.manifest_path)["version"], before)


# --------------------------------------------------------------------------
# 6. distill_report（含回归）
# --------------------------------------------------------------------------


class TestDistillReport(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fx = ArchiveFixture(self.tmp)

    def test_renders_table(self):
        r = run("distill_report.py", self.fx.root)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("蒸馏检查点摘要", r.stdout)
        self.assertIn("信度分布", r.stdout)

    def test_title_fallback_does_not_print_none(self):
        """回归：原实现 `"…%s" % manifest.get("title") or root` 因 % 优先级高于 or，
        title 缺失时打印「None」而不是回落到目录名。"""
        patch_json(self.fx.manifest_path, lambda m: m.pop("title", None))
        r = run("distill_report.py", self.fx.root)
        self.assertNotIn("None", r.stdout)
        self.assertIn(os.path.basename(self.fx.root), r.stdout)

    def test_reports_unfilled_coverage(self):
        """未回填是**中间态**，检查点表必须把它显式指出来（不能当成 0 或满分）。

        用独立 slug：setUp 里那份夹具是已回填的交付态，而 ingest 会沿用
        旧 manifest 里已有的判定值——共用目录就拿不到「未回填」这个状态。
        """
        fx = ArchiveFixture(self.tmp, slug="unfilled", backfill=False)
        r = run("distill_report.py", fx.root)
        self.assertIn("coverage 未回填", r.stdout)

    def test_reports_unfilled_primary_counts(self):
        fx = ArchiveFixture(self.tmp, slug="unfilled2", backfill=False)
        r = run("distill_report.py", fx.root)
        self.assertIn("一手占比 未回填", r.stdout)


# --------------------------------------------------------------------------
# 7. meta_scan
# --------------------------------------------------------------------------


class TestMetaScan(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _two(self, shared_source=False, same_slug=False):
        a = ArchiveFixture(self.tmp, slug="alpha", sources=("a.md",))
        b_slug = "alpha" if same_slug else "beta"
        # beta 的素材目录不同；**内容**相同才会被判为「来源重叠」（判重依据是 sha256）
        src = os.path.join(self.tmp, "raw-beta")
        content = SOURCE_TEXT if shared_source else SOURCE_TEXT + "beta 独有的一段内容。\n"
        write(os.path.join(src, "a.md" if shared_source else "b.md"), content)
        b_root = os.path.join(self.tmp, "distilled2", b_slug)
        run("ingest.py", src, "--out", b_root, "--title", "B")
        dims = _lib.SCHEMA_DIMENSIONS["person"]
        for _, _, fname in dims:
            write(os.path.join(b_root, "research", fname), "### x\n" + "内容（A）。" * 100)
        run("ingest.py", src, "--out", b_root, "--title", "B")
        body = DEFAULT_BODY.replace("slug: munger", "slug: " + b_slug)
        write(os.path.join(b_root, "DISTILLATE.md"),
              FRONTMATTER.format(schema="person", slug=b_slug, title="B", n_sources=1,
                                 source_words=100, distillate_words=_lib.count_words(body),
                                 ratio="1:1",
                                 dimensions="[%s]" % ", ".join(n for _, n, _ in dims))
              + "\n" + body)
        run("seal.py", b_root)
        return a, b_root

    def test_detects_shared_source(self):
        a, b = self._two(shared_source=True)
        r = run("meta_scan.py", a.root, b)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("不构成独立佐证", r.stdout)

    def test_no_overlap_when_sources_differ(self):
        a, b = self._two(shared_source=False)
        r = run("meta_scan.py", a.root, b)
        self.assertIn("互为独立佐证", r.stdout)

    def test_detects_slug_collision(self):
        """同名档案在综合结果里无法区分出处，必须显式报错。"""
        a, b = self._two(same_slug=True)
        r = run("meta_scan.py", a.root, b)
        self.assertIn("slug 碰撞", r.stdout)

    def test_json_has_overlap_and_collision_keys(self):
        a, b = self._two(shared_source=True)
        r = run("meta_scan.py", a.root, b, "--json")
        data = json.loads(r.stdout)
        for key in ("source_overlap", "slug_collisions", "complementary_gaps",
                    "coverage_unfilled", "archives"):
            self.assertIn(key, data)
        self.assertTrue(data["source_overlap"])

    def test_requires_two_archives(self):
        a, _ = self._two()
        self.assertEqual(run("meta_scan.py", a.root).returncode, 1)

    def test_null_coverage_does_not_crash(self):
        a, b = self._two(shared_source=False)
        r = run("meta_scan.py", a.root, b)
        self.assertEqual(r.returncode, 0, r.stdout)


# --------------------------------------------------------------------------
# 8. eval_record
# --------------------------------------------------------------------------


def rec(version, sha, total, scorers=2, questions=None, scores=None):
    return {
        "version": version, "artifact_sha256": sha, "total": total,
        "grade": "B", "scorers": scorers,
        "models": {"answer": "m-a", "score": "m-b"},
        "questions": questions if questions is not None else [
            {"id": "q1", "kind": "known", "text": "t", "status": "active"}],
        "scores": scores if scores is not None else {"覆盖度": 18, "信度": 16},
    }


class TestEvalRecord(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fx = ArchiveFixture(self.tmp)
        self.evals = os.path.join(self.fx.root, "EVALS.jsonl")

    def test_artifact_flag_fills_hash_and_version(self):
        """回归：artifact_sha256 此前只能手抄，抄错整条记录失去意义。"""
        payload = {"models": {"answer": "a", "score": "b"}, "scorers": 2,
                   "scores": {"覆盖度": 18}, "total": 82, "grade": "B",
                   "questions": [{"id": "q1", "kind": "known", "text": "t",
                                  "status": "active"}]}
        r = run("eval_record.py", "record", "--file", self.evals,
                "--json", json.dumps(payload), "--artifact", self.fx.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = _lib.load_jsonl(self.evals)[0]
        self.assertEqual(got["artifact_sha256"], _lib.sha256_file(self.fx.distillate_path()))
        self.assertEqual(got["version"], 1)

    def test_artifact_conflict_is_reported(self):
        payload = {"version": 1, "artifact_sha256": "deadbeef", "models": {"answer": "a", "score": "b"},
                   "scorers": 2, "scores": {"覆盖度": 18}, "total": 82,
                   "questions": [{"id": "q1", "kind": "known", "text": "t", "status": "active"}]}
        r = run("eval_record.py", "record", "--file", self.evals,
                "--json", json.dumps(payload), "--artifact", self.fx.root)
        self.assertIn("与档案不符", r.stdout)

    def test_missing_required_fields_rejected(self):
        r = run("eval_record.py", "record", "--file", self.evals,
                "--json", json.dumps({"total": 50}))
        self.assertEqual(r.returncode, 1)

    def test_models_must_include_score_model(self):
        payload = {"version": 1, "artifact_sha256": "x", "models": {"answer": "a"},
                   "scorers": 2, "scores": {}, "total": 1}
        r = run("eval_record.py", "record", "--file", self.evals,
                "--json", json.dumps(payload))
        self.assertEqual(r.returncode, 1)
        self.assertIn("评分必须独立于答题", r.stdout)

    def _seed(self, a, b):
        for r_ in (a, b):
            run("eval_record.py", "record", "--file", self.evals,
                "--json", json.dumps(r_))

    def test_compare_refuses_same_artifact(self):
        self._seed(rec(1, "same", 70), rec(2, "same", 85))
        r = run("eval_record.py", "compare", "--file", self.evals)
        self.assertIn("不构成有效对比", r.stdout)
        self.assertIn("同一个", r.stdout)

    def test_compare_refuses_single_scorer(self):
        self._seed(rec(1, "aaa", 70, scorers=1), rec(2, "bbb", 90, scorers=1))
        r = run("eval_record.py", "compare", "--file", self.evals)
        self.assertIn("不构成有效对比", r.stdout)
        self.assertIn("评分 agent 少于 2 个", r.stdout)

    def test_compare_refuses_retired_question_set(self):
        q_old = [{"id": "q1", "kind": "known", "text": "t", "status": "active"},
                 {"id": "q4", "kind": "gap", "text": "g", "status": "active"}]
        q_new = [{"id": "q1", "kind": "known", "text": "t", "status": "active"},
                 {"id": "q4", "kind": "gap", "text": "g", "status": "retired"}]
        self._seed(rec(1, "aaa", 70, questions=q_old), rec(2, "bbb", 90, questions=q_new))
        r = run("eval_record.py", "compare", "--file", self.evals)
        self.assertIn("题目集已变化", r.stdout)
        self.assertIn("越完整分越低", r.stdout)

    def test_compare_flags_noise_band(self):
        self._seed(rec(1, "aaa", 80), rec(2, "bbb", 85))
        r = run("eval_record.py", "compare", "--file", self.evals)
        self.assertIn("噪声带", r.stdout)

    def test_compare_accepts_real_improvement(self):
        self._seed(rec(1, "aaa", 70), rec(2, "bbb", 90))
        r = run("eval_record.py", "compare", "--file", self.evals)
        self.assertIn("对比有效", r.stdout)
        self.assertIn("提升", r.stdout)

    def test_history_renders(self):
        self._seed(rec(1, "aaa", 70), rec(2, "bbb", 90))
        r = run("eval_record.py", "history", "--file", self.evals)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("评测历史", r.stdout)


# --------------------------------------------------------------------------
# 9. 跨脚本：契约常量与文档同步
# --------------------------------------------------------------------------


class TestContractSync(unittest.TestCase):

    def test_schema_sections_match_reference_files(self):
        """`_lib.SCHEMA_SECTIONS` 必须与 references/schema-*.md 的专属段标题逐字一致。

        schema 专属段是各 schema 相对通用骨架的**独有交付物**（document 的
        「可执行结论」、person 的「表达DNA」、topic 的「流派对比表」）。
        标题一变，`section()` 的严格匹配就 miss，而评测断言会静默失效——
        断言写了却永远不通过，或更糟：永远通过。
        """
        for schema, sections in _lib.SCHEMA_SECTIONS.items():
            text = _lib.read_text(os.path.join(ROOT, "references",
                                               "schema-%s.md" % schema))
            self.assertTrue(text, "schema-%s.md 读不到" % schema)
            for s in sections:
                self.assertIn("## " + s, text,
                              "schema-%s.md 缺少专属段「%s」（或标题被改了）" % (schema, s))

    def test_schema_dimensions_match_reference_files(self):
        """`_lib.SCHEMA_DIMENSIONS` 必须与 references/schema-*.md 的维度名一致——
        契约文档是权威定义，脚本是它的可执行形式，两边不得漂移。"""
        expected = {
            "schema-person.md": ["著作", "对话", "表达", "他者", "决策", "时间线"],
            "schema-topic.md": ["领域共识", "流派分歧", "关键概念", "经典案例", "争议前沿", "演进脉络"],
            "schema-document.md": ["论点树", "证据链", "术语表", "隐含假设", "内部矛盾", "信息缺口"],
        }
        for fname, dims in expected.items():
            text = _lib.read_text(os.path.join(ROOT, "references", fname))
            self.assertTrue(text, fname)
            for d in dims:
                self.assertIn(d, text, "%s 缺少维度 %s" % (fname, d))
        self.assertEqual([n for _, n, _ in _lib.SCHEMA_DIMENSIONS["person"]], expected["schema-person.md"])
        self.assertEqual([n for _, n, _ in _lib.SCHEMA_DIMENSIONS["topic"]], expected["schema-topic.md"])
        self.assertEqual([n for _, n, _ in _lib.SCHEMA_DIMENSIONS["document"]], expected["schema-document.md"])

    def test_sources_subdirs_match_artifact_format(self):
        """`sources/` 子目录名必须出现在契约文档里（目录名 == 素材类型）。"""
        text = _lib.read_text(os.path.join(ROOT, "references", "artifact-format.md"))
        for sub in _lib.SOURCES_SUBDIRS:
            self.assertIn(sub, text, "契约文档缺少 sources/%s" % sub)

    def test_sources_type_enum_is_plural(self):
        """`sources[].type` 的枚举必须与 `sources/` 子目录名一致（复数）。

        回归：契约 §三 曾把枚举写成单数 `book / transcript / article`，
        而 §一 与 `_lib.TYPE_BY_EXT` 用复数。agent 照 §三 手写 manifest 时
        会写出与所在子目录不匹配的 type，破坏 §一 自己声明的「一一对应」。
        旧的 `assertIn` 断言挡不住这个——子串在文档里出现就算过。
        """
        text = _lib.read_text(os.path.join(ROOT, "references", "artifact-format.md"))
        rows = [l for l in text.splitlines() if "`sources[].type`" in l]
        self.assertTrue(rows, "契约未定义 sources[].type")
        # 契约在两处声明这个枚举（§一 的「一一对应」说明、§三 的字段表）。
        # 两处都必须用复数——只要有一处退回单数，agent 就可能照它写错。
        for row in rows:
            for sub in _lib.SOURCES_SUBDIRS:
                self.assertIn("`%s`" % sub, row,
                              "sources[].type 枚举缺 `%s`（须与子目录名同形）" % sub)

    def test_skeleton_bound_documented_consistently(self):
        """骨架条目上下限必须三处一致：方法论、契约文档、可执行检查。

        回归：framework §十 曾写「3-7 条之间？」，同一行的括号却写
        「多于 10 = 没取舍」——自相矛盾；而 artifact-format §八 又引用 §十
        作为「3-10」的依据，被引用的源不支持该规则。照 §十 自检的 agent
        会把 8-10 条合法骨架删掉。
        """
        bound = "%d-%d" % (_lib.SKELETON_MIN, _lib.SKELETON_MAX)
        for rel in ("references/distillation-framework.md",
                    "references/artifact-format.md"):
            text = _lib.read_text(os.path.join(ROOT, rel))
            self.assertIn(bound, text, "%s 未写骨架上下限 %s" % (rel, bound))

    def test_required_fields_documented(self):
        text = _lib.read_text(os.path.join(ROOT, "references", "artifact-format.md"))
        for f in _lib.REQUIRED_FIELDS:
            self.assertIn(f, text, "契约文档缺少字段 %s" % f)

    def test_scorecard_dimensions_match_docs(self):
        """评分卡维度与分值必须三处一致：`_lib` 常量、评分卡文档、SKILL.md。

        回归背景：生成力（判定线）此前只以「3 道题」的形式出现、**不占任何分值**，
        于是流程里最锋利的那句话——「拿产物去回答素材没出现过的新问题」——在度量上
        等于不存在，一份完美的摘要能拿满分。把它变成有分的维度之后，必须钉住它
        不会在某次编辑里又悄悄消失。
        """
        self.assertEqual(_lib.SCORECARD_TOTAL, 100,
                         "评分卡总分必须为 100，当前 %d" % _lib.SCORECARD_TOTAL)

        sc = _lib.read_text(os.path.join(ROOT, "references", "quality-scorecard.md"))
        for i, (name, score) in enumerate(_lib.SCORECARD_DIMENSIONS, 1):
            self.assertIn("| %d | %s | %d |" % (i, name, score), sc,
                          "评分卡表格缺少行 `| %d | %s | %d |`" % (i, name, score))

        skill = _lib.read_text(os.path.join(ROOT, "SKILL.md"))
        for name, _ in _lib.SCORECARD_DIMENSIONS:
            self.assertIn(name, skill, "SKILL.md 未提及评分卡维度 %s" % name)

    def test_harmony_is_not_a_sentence_pattern(self):
        """和稀泥的判据是「信息量净减少」，不是句式。

        回归：`HARMONY_RE` 曾把 30 字内的任何「虽然…但是」判为和稀泥，
        于是**标注齐全的时间性张力**只要用了转折句式就被硬性 FAIL ——
        检查在惩罚正确输出，并诱导作者删掉真实矛盾（反而违反铁律 2）。
        """
        legit = [
            "早期他虽然在多个场合强调多元化，但是 2019 年后转向聚焦单一主线",
            "他虽然在公开场合推崇长期主义，但是在内部信里反复强调季度数字",
            "他在工作中虽然主张放权，但是在家庭里事无巨细",
        ]
        for text in legit:
            with self.subTest(text=text[:16]):
                self.assertIsNone(_lib.HARMONY_RE.search(text),
                                  "转折句式被误判为和稀泥: %s" % text)
        # 但「否认对立」的断言必须继续被拦住——它才是抹平的实质
        for text in ("其实两者并不冲突", "两者并不矛盾", "本质上统一",
                     "殊途同归", "说到底是同一回事", "其实两者是互补的"):
            with self.subTest(text=text):
                self.assertIsNotNone(_lib.HARMONY_RE.search(text),
                                     "否认对立的断言漏检: %s" % text)

    def test_d_ratio_threshold_documented_consistently(self):
        """D 级阈值必须全库同口径（≤20%）——代码是 `ratio > 20` 才 FAIL。

        回归：契约文档 §8.1 与 framework/README/三份 schema 的质检清单写 `<20%`，
        而 `quality_check.py` 是「>20 才 FAIL」。恰好卡在 20.0% 时，契约说 FAIL、
        代码说 PASS。
        """
        stale = []
        for rel in ("references/artifact-format.md",
                    "references/distillation-framework.md",
                    "references/quality-scorecard.md",
                    "references/meta-synthesis.md",
                    "references/schema-person.md",
                    "references/schema-topic.md",
                    "references/schema-document.md",
                    "README.md"):
            text = _lib.read_text(os.path.join(ROOT, rel))
            for line in text.splitlines():
                if "D 级" in line and "<20%" in line:
                    stale.append("%s: %s" % (rel, line.strip()))
        self.assertEqual(stale, [], "D 级阈值写法与代码不一致（应为 ≤20%）：\n" + "\n".join(stale))

    def test_every_script_compiles_and_has_help(self):
        import glob
        for path in sorted(glob.glob(os.path.join(SCRIPTS, "*.py"))):
            name = os.path.basename(path)
            if name == "_lib.py":
                continue
            r = run(name, "--help")
            self.assertIn(r.returncode, (0, 1), name)
            self.assertTrue(r.stdout.strip(), "%s --help 无输出" % name)


class TestRobustness(unittest.TestCase):
    """坏输入不该让诊断工具带 traceback 退出。

    这些脚本的定位是「告诉用户哪里坏了」。它们自己崩掉时，
    连「哪份档案有问题」都说不出来——比报错更糟。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fx = ArchiveFixture(self.tmp)

    def test_non_object_manifest_does_not_crash(self):
        """JSON 合法但顶层不是对象（[] / "x" / 123）时，必须给人话错误。"""
        for payload in ("[]", '"x"', "123", "null"):
            with self.subTest(payload=payload):
                write(self.fx.manifest_path, payload)
                for script, args in (("seal.py", (self.fx.root,)),
                                     ("quality_check.py", (self.fx.root,)),
                                     ("distill_report.py", (self.fx.root,)),
                                     ("meta_scan.py", (self.fx.root, self.fx.root))):
                    r = run(script, *args)
                    self.assertNotIn("Traceback", r.stderr, "%s 崩了" % script)
                    self.assertNotEqual(r.returncode, 0, "%s 应非零退出" % script)

    def test_non_utf8_distillate_does_not_crash(self):
        """GBK 编码的档案不能让 quality_check 崩掉。"""
        dpath = os.path.join(self.fx.root, "DISTILLATE.md")
        with open(dpath, "wb") as f:
            f.write("# 测试\n\n## 核心骨架\n- 主张（A）\n".encode("gb18030"))
        r = run("quality_check.py", self.fx.root)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 1)   # 结构不完整 → 正常判 FAIL

    def test_nested_malformed_manifest_does_not_crash(self):
        """回归：`load_manifest` 只保证**顶层**是对象，嵌套畸形
        （`"dimensions": ["著作"]`、`"sources": ["a"]`）会让 quality_check /
        distill_report / meta_scan / ingest **同时** traceback——而这几个脚本
        的定位是「诊断工具」，崩掉比报错更糟：它连「哪份档案有问题」都说不出来。
        顶层用例（上面那条）恰好把这类漏在网外。
        """
        payloads = ('{"dimensions": ["著作"], "sources": []}',
                    '{"dimensions": [], "sources": ["a"]}',
                    '{"dimensions": {"a": 1}, "sources": {"b": 2}}')
        for payload in payloads:
            with self.subTest(payload=payload):
                write(self.fx.manifest_path, payload)
                for script, args in (("quality_check.py", (self.fx.root,)),
                                     ("distill_report.py", (self.fx.root,)),
                                     ("meta_scan.py", (self.fx.root, self.fx.root)),
                                     ("ingest.py", (self.fx.root, "--out", self.fx.root))):
                    r = run(script, *args)
                    self.assertNotIn("Traceback", r.stderr,
                                     "%s 在 %s 下崩了" % (script, payload))

    def test_unreadable_distillate_does_not_crash(self):
        """回归：`sha256_file` 没有异常兜底，权限错误会直接冒泡成 traceback。
        更要紧的是它**不能返回空串**——那会让「读不到」伪装成「哈希一致」。
        """
        dpath = os.path.join(self.fx.root, "DISTILLATE.md")
        os.chmod(dpath, 0o000)
        self.addCleanup(os.chmod, dpath, 0o644)
        for script in ("seal.py", "quality_check.py"):
            r = run(script, self.fx.root)
            self.assertNotIn("Traceback", r.stderr, "%s 崩了" % script)
            self.assertNotEqual(r.returncode, 0)

    def test_eval_record_compare_survives_a_hand_written_bad_row(self):
        """回归：`EVALS.jsonl` 是**只增不改**的流水。一条手写的、分数写成
        字符串或 `scorers: null` 的记录会让 `compare` 永久 TypeError——
        而「拒绝过度断言」这个核心价值的前提是它一直跑得起来。
        """
        path = os.path.join(self.tmp, "EVALS.jsonl")
        base = {"schema_version": 1, "version": 1, "artifact_sha256": "a" * 64,
                "models": {"answer": "m", "score": "m"}, "scorers": 2,
                "questions": [{"id": "q1", "kind": "known", "text": "x", "status": "active"}],
                "scores": {"生成力": 10}, "total": 50, "grade": "D"}
        newer = dict(base, version=2, artifact_sha256="b" * 64,
                     scores={"生成力": "13"}, total="70")   # 分数写成字符串
        with open(path, "w", encoding="utf-8") as f:
            for rec in (base, newer):
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        r = run("eval_record.py", "compare", "--file", path)
        self.assertNotIn("Traceback", r.stderr, r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

        # scorers 为 null 时也不能崩
        newer["scorers"] = None
        with open(path, "w", encoding="utf-8") as f:
            for rec in (base, newer):
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        r = run("eval_record.py", "compare", "--file", path)
        self.assertNotIn("Traceback", r.stderr, r.stdout)

    def test_distill_report_does_not_double_count_url_sources(self):
        """回归：URL 正则与路径正则分别 findall 再相加，
        `见 https://example.com/a.pdf` 会被算成 2 个来源——
        检查点表的「N 源」对含链接的底稿系统性虚高。
        """
        self.assertEqual(distill_report.count_sources(
            "见 https://example.com/a.pdf"), 1)
        self.assertEqual(distill_report.count_sources(
            "见 https://example.com/a.pdf 与 sources/notes/b.md"), 2)

    def test_meta_scan_extracts_schema_specific_model_section(self):
        """回归：各 schema 把「心智模型」具体化成了不同标题。

        person 写「心智模型」，topic 写「框架总览」，document 写「论点树」。
        只认通用名会让「找跨档案复现的框架」对所有真实档案都返回空——
        而综合档案按契约恒为 topic schema，正好是这个功能唯一要服务的场景。
        """
        for title in ("心智模型", "心智模型 / 核心框架", "核心框架",
                      "框架总览", "论点树"):
            with self.subTest(section=title):
                body = self.fx.body.replace("## 心智模型", "## " + title)
                self.fx.write_distillate(body=body)
                other = ArchiveFixture(self.tmp, slug="other")
                other.write_distillate(body=body)
                r = run("meta_scan.py", self.fx.root, other.root, "--json")
                self.assertIn("可逆性优先", r.stdout,
                              "未从「%s」段提取到模型" % title)

    def test_meta_scan_warns_when_manifest_unreadable(self):
        """没有 manifest 就没有 sha256 判重键，重叠结论不可信——必须说出来。"""
        os.remove(self.fx.manifest_path)
        other = ArchiveFixture(self.tmp, slug="other")
        os.remove(other.manifest_path)
        r = run("meta_scan.py", self.fx.root, other.root)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("manifest", r.stdout)
        self.assertIn("不可信", r.stdout)

    def test_meta_scan_exits_nonzero_on_slug_collision(self):
        """同名档案不可综合——CI 里必须能被 && 拦住。"""
        same = ArchiveFixture(self.tmp, slug="munger")
        r = run("meta_scan.py", self.fx.root, same.root)
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_ingest_survives_null_version(self):
        """version 被手改成 null 时，「补素材」这条主路径不能挂。"""
        patch_json(self.fx.manifest_path, lambda m: m.__setitem__("version", None))
        r = run("ingest.py", self.fx.src_dir, "--out", self.fx.root,
                "--schema", "person", "--title", "测试人物 · 认知档案")
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_frontmatter_accepts_full_width_comma(self):
        """中文全角逗号很常见，不能让它静默解析失败。"""
        self.assertEqual(_lib.parse_scalar("{A: 8，B: 3}"), {"A": 8, "B": 3})
        self.assertEqual(_lib.parse_scalar("[著作，对话]"), ["著作", "对话"])
        c = _lib.parse_scalar("{A: 8，B: 3}")
        self.assertEqual(_lib.conf_total(c), 11)

    def test_skeleton_items_ignores_indented_sub_bullets(self):
        """缩进的子条目是对上一条的展开，不是并列骨架条目。

        算进来会让骨架数量虚高，进而撞上 >10 的上限。
        """
        body = ("## 核心骨架\n"
                "- 主张一（A）\n"
                "  - 展开说明（A）\n"
                "  - 又一个展开（B）\n"
                "- 主张二（B）\n")
        self.assertEqual(len(_lib.skeleton_items(body)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
