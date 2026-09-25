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
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import _lib  # noqa: E402


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


SOURCE_TEXT = ("反过来想。可逆性判断在产品与人事两处都出现。\n"
               "激励机制错，人就做错事。早期更看重低价，后期转向质量。\n")


class ArchiveFixture:
    """构建一份**合法**档案，供各测试按需改坏某一点。"""

    def __init__(self, tmp, slug="munger", schema="person", body=DEFAULT_BODY,
                 seal=True, sources=("note1.md", "note2.md")):
        self.tmp = tmp
        self.slug = slug
        self.schema = schema
        self.body = body
        self.root = os.path.join(tmp, "distilled", slug)
        self.src_dir = os.path.join(tmp, "raw-" + slug)
        for name in sources:
            write(os.path.join(self.src_dir, name), SOURCE_TEXT)

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

        self.write_distillate()
        if seal:
            r = run("seal.py", self.root)
            assert r.returncode == 0, r.stdout + r.stderr

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
            fm = fm.replace("%s: " % k, "%s: " % k, 1)  # 占位，实际替换见下
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

    def test_count_confidence_both_syntaxes(self):
        c = _lib.count_confidence("a（A） b [B] c 信度: C")
        self.assertEqual(c, {"A": 1, "B": 1, "C": 1, "D": 0})
        self.assertEqual(_lib.conf_total(c), 3)
        self.assertEqual(_lib.d_ratio(c), 0.0)
        self.assertEqual(_lib.format_conf(c), "A1 B1 C1 D0")

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


# --------------------------------------------------------------------------
# 3. quality_check：七项硬检查 + 缺陷回归
# --------------------------------------------------------------------------


class TestQualityCheck(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fx = ArchiveFixture(self.tmp)

    def qc(self, *args):
        return run("quality_check.py", self.fx.root, *args)

    def test_valid_archive_passes_all_seven(self):
        r = self.qc()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("7/7 通过", r.stdout)

    def test_harmony_contradiction_is_rejected(self):
        """回归：原实现里 `and not found` 让和稀泥检测成为死代码，
        含「虽然…但是」的档案照样 PASS —— 直接违反铁律 2。"""
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
        self.assertEqual(len(data["checks"]), 7)
        self.assertTrue(data["ok"])
        self.assertEqual(data["passed"], 7)

    def test_diagnostics_flag_missing_source_pointer(self):
        self.fx.write_distillate(body=DEFAULT_BODY.replace(
            "（A · sources/notes/note1.md）", "（A）"))
        r = self.qc()
        self.assertIn("没有可回查的出处指针", r.stdout)

    def test_accepts_distillate_path_as_well_as_dir(self):
        r = run("quality_check.py", self.fx.distillate_path())
        self.assertEqual(r.returncode, 0, r.stdout)


# --------------------------------------------------------------------------
# 4. ingest：契约字段、判重、null 语义、旧数据迁移
# --------------------------------------------------------------------------


class TestIngest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_writes_contract_fields_and_null_defaults(self):
        fx = ArchiveFixture(self.tmp)
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
        r = run("distill_report.py", self.fx.root)
        self.assertIn("coverage 未回填", r.stdout)

    def test_reports_unfilled_primary_counts(self):
        r = run("distill_report.py", self.fx.root)
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

    def test_required_fields_documented(self):
        text = _lib.read_text(os.path.join(ROOT, "references", "artifact-format.md"))
        for f in _lib.REQUIRED_FIELDS:
            self.assertIn(f, text, "契约文档缺少字段 %s" % f)

    def test_every_script_compiles_and_has_help(self):
        import glob
        for path in sorted(glob.glob(os.path.join(SCRIPTS, "*.py"))):
            name = os.path.basename(path)
            if name == "_lib.py":
                continue
            r = run(name, "--help")
            self.assertIn(r.returncode, (0, 1), name)
            self.assertTrue(r.stdout.strip(), "%s --help 无输出" % name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
