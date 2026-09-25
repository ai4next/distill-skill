#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 素材归集与清点

把散落的素材按类型归入 `distilled/<slug>/sources/`，统计字数与哈希，
生成 / 增量更新 `manifest.json`（蒸馏档案契约的素材清单）。

用法:
    python3 ingest.py <素材路径...> --out distilled/<slug>/ [选项]

选项:
    --out DIR          档案目录（必填），不存在则创建
    --schema NAME      person | topic | document | custom（默认 person）
    --slug SLUG        档案 slug（默认取 --out 的末级目录名）
    --title TITLE      档案标题（默认取 slug）
    --dimensions STR   custom schema 用，逗号分隔，如 "论点,证据,缺口"

示例:
    python3 ingest.py ~/Downloads/munger/ --out distilled/munger --schema person
    python3 ingest.py a.pdf b.srt c.md --out distilled/munger

说明:
    - 二进制素材（PDF/EPUB 等）无法用标准库抽文本，words 记 null 并在末尾提示，
      由 agent 在 Phase 1 用 pdf/文档读取工具提取后回填。
    - 已存在 manifest.json 时走增量：sha256 相同的素材跳过，不重复计入。
    - **脚本不做语义判定**：`coverage` / `sources_primary` / `sources_secondary` /
      `dimensions[].sources` 无法机械得出，一律写 **null（未回填）**，
      由 agent 在 Phase 3 判定后回填。**null ≠ 0**：0 是判定结果，null 是没判。
      （SKILL.md 反模式 #16：让脚本做语义判定。）
    - 本脚本**不**计算 `distillate_sha256`——那是 `seal.py` 的职责（档案定型后才封存）。
"""

import argparse
import os
import re
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

SCHEMA_VERSION = _lib.SUPPORTED_SCHEMA_VERSION
SCHEMA_DIMENSIONS = _lib.SCHEMA_DIMENSIONS
TYPE_BY_EXT = _lib.TYPE_BY_EXT
BINARY_EXTS = _lib.BINARY_EXTS

USAGE = "python3 ingest.py <素材路径...> --out distilled/<slug>/ [--schema person]"


def classify(path):
    """按扩展名判定素材类型。"""
    ext = os.path.splitext(path)[1].lower()
    for type_name, exts in TYPE_BY_EXT.items():
        if ext in exts:
            return type_name
    return "other"


def read_text(path):
    """尽力解码为文本；二进制或解码失败返回 None。"""
    if os.path.splitext(path)[1].lower() in BINARY_EXTS:
        return None
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def iter_files(paths):
    """展开文件与目录，跳过隐藏文件与常见噪音。"""
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
                for name in sorted(files):
                    if name.startswith(".") or name == ".DS_Store":
                        continue
                    yield os.path.join(root, name)
        else:
            print("⚠️  路径不存在，跳过: " + p)


def next_source_id(sources):
    """下一个素材编号。取现有最大编号 +1，避免删过素材后编号撞车。"""
    mx = 0
    for s in sources:
        m = re.match(r"S(\d+)$", str(s.get("id", "")))
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


def migrate_unfilled_dim(prev):
    """把旧版 ingest 写的「默认 0」迁移为「未回填 null」。

    旧版把脚本无法判定的字段一律写 0，于是「未回填」与「判定为 0」无法区分。
    只在**无歧义**时迁移：coverage 为 0 **且** sources 为 0/null **且** confidence
    为空/全 0 —— 不存在一个 agent 在判定 coverage=0 的同时把来源数与信度全留空。
    迁移后 quality_check 会提示回填；误迁移的代价只是多一次提示，不会丢真数据。
    """
    if prev.get("coverage") != 0:
        return prev
    conf = prev.get("confidence")
    conf_empty = (not isinstance(conf, dict)) or not _lib.conf_total(conf)
    if prev.get("sources") in (0, None) and conf_empty:
        prev = dict(prev)
        prev["coverage"] = None
        prev["sources"] = None
        prev["confidence"] = None
    return prev


def migrate_unfilled_counts(manifest):
    """同理迁移 manifest 顶层的「一手/二手」默认 0。

    两者同时为 0 且有素材 → 是旧版默认值（未判定）。若真是一手为 0，
    二手必然 >0，不会被误迁移。
    """
    if manifest.get("sources_primary") == 0 and manifest.get("sources_secondary") == 0 \
            and manifest.get("sources"):
        manifest["sources_primary"] = None
        manifest["sources_secondary"] = None
    return manifest


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("paths", nargs="*", help="素材文件或目录")
    ap.add_argument("--out", required=False, help="档案目录，如 distilled/munger/")
    ap.add_argument("--schema", default="person", choices=list(_lib.SCHEMAS))
    ap.add_argument("--slug", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--dimensions", default=None, help="custom schema 的维度，逗号分隔")
    args = ap.parse_args()

    if not args.paths:
        _lib.usage_error("缺少素材路径", USAGE)
    if not args.out:
        _lib.usage_error("缺少 --out 档案目录", USAGE)

    out_dir = os.path.abspath(os.path.expanduser(args.out))
    slug = args.slug or os.path.basename(out_dir.rstrip(os.sep))
    if not slug:
        _lib.usage_error("无法推断 slug，请显式传 --slug", USAGE)

    # 维度定义
    if args.schema == "custom":
        if not args.dimensions:
            _lib.usage_error("schema=custom 时必须用 --dimensions 指定维度（逗号分隔）", USAGE)
        names = [s.strip() for s in args.dimensions.split(",") if s.strip()]
        if not 2 <= len(names) <= 8:
            _lib.usage_error("custom 维度数量需在 2-8 之间，当前 %d 个" % len(names), USAGE)
        dims = [("%02d" % (i + 1), n,
                 "%02d-%s.md" % (i + 1, re.sub(r"\W+", "-", n).strip("-").lower() or "dim"))
                for i, n in enumerate(names)]
    else:
        dims = SCHEMA_DIMENSIONS[args.schema]

    for sub in ("", "research", "sources"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    for t in _lib.SOURCES_SUBDIRS:
        os.makedirs(os.path.join(out_dir, "sources", t), exist_ok=True)

    old = _lib.load_json(os.path.join(out_dir, "manifest.json"))
    if old is not None and not isinstance(old, dict):
        print("⚠️  现有 manifest.json 结构异常，将重建")
        old = None
    old = old or {}
    old_sources = {s.get("sha256"): s for s in old.get("sources", []) if s.get("sha256")}
    sources = list(old.get("sources", []))
    sid = next_source_id(sources)

    added, skipped, need_text = [], [], []
    today = date.today().isoformat()

    for path in iter_files(args.paths):
        try:
            digest = _lib.sha256_file(path)
        except OSError as e:
            print("⚠️  读取失败，跳过: %s (%s)" % (path, e))
            continue

        if digest in old_sources:
            skipped.append(old_sources[digest].get("path", path))
            continue

        type_name = classify(path)
        dest_dir = os.path.join(out_dir, "sources", type_name)
        dest = os.path.join(dest_dir, os.path.basename(path))
        # 避免把已在 sources/ 下的文件再复制一次
        if os.path.abspath(os.path.dirname(path)) != os.path.abspath(dest_dir):
            base, n = os.path.basename(path), 1
            stem, ext = os.path.splitext(base)
            while os.path.exists(dest):
                dest = os.path.join(dest_dir, "%s-%d%s" % (stem, n, ext))
                n += 1
            try:
                shutil.copy2(path, dest)
            except OSError as e:
                print("⚠️  复制失败，跳过: %s (%s)" % (path, e))
                continue

        text = read_text(dest)
        words = None if text is None else _lib.count_words(text)
        if words is None:
            need_text.append(os.path.relpath(dest, out_dir))

        rel = os.path.relpath(dest, out_dir)
        sources.append({
            "id": "S%03d" % sid,
            "path": rel,
            "origin": "local",
            "type": type_name,
            "title": os.path.splitext(os.path.basename(path))[0],
            "url": None,
            "words": words,
            "sha256": digest,
            "added": today,
            "dimensions": [],
        })
        added.append((rel, type_name, words))
        sid += 1

    # 维度状态：research/ 下有对应文件即 partial/complete
    old_dims = {d.get("name"): d for d in old.get("dimensions", [])}
    dimensions = []
    for did, name, fname in dims:
        fpath = os.path.join(out_dir, "research", fname)
        if os.path.isfile(fpath):
            body = _lib.read_text(fpath)
            status = "complete" if len(body) > 800 else "partial"
        else:
            status = "missing"
        prev = migrate_unfilled_dim(old_dims.get(name, {}))
        dimensions.append({
            "id": did,
            "name": name,
            "file": "research/" + fname,
            "status": status,
            # 以下三项脚本无法判定 → 未回填写 null（**null ≠ 0**），由 agent 在 Phase 3 回填
            "sources": prev.get("sources"),
            "confidence": prev.get("confidence"),
            "coverage": prev.get("coverage"),
        })

    total_words = sum(s["words"] or 0 for s in sources)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "schema": args.schema,
        "title": args.title or old.get("title") or slug,
        "created": old.get("created", today),
        "updated": today,
        "version": (old.get("version", 0) + (1 if added else 0)) or 1,
        "sources": sources,
        "source_words": total_words,
        "sources_primary": old.get("sources_primary"),
        "sources_secondary": old.get("sources_secondary"),
        "dimensions": dimensions,
        "gaps": old.get("gaps", []),
        # 综合档案专用字段：普通档案为 null / []
        "meta_sources": old.get("meta_sources"),
        "source_overlap": old.get("source_overlap", []),
        "changes": old.get("changes", []) + ([{
            "date": today,
            "action": "ingest",
            "note": "新增素材 %d 个，跳过重复 %d 个" % (len(added), len(skipped)),
            "sources_added": len(added),
        }] if added else []),
        "distillate_sha256": old.get("distillate_sha256"),
    }
    migrate_unfilled_counts(manifest)
    if not manifest["changes"]:
        manifest["changes"] = [{
            "date": today, "action": "initial", "note": "首次建库",
            "sources_added": len(added),
        }]

    mpath = os.path.join(out_dir, "manifest.json")
    _lib.write_json(mpath, manifest)

    # 报告
    print("素材归集: %s" % out_dir)
    print("=" * 62)
    if added:
        for rel, t, w in added:
            print("  ✅ %-42s %-11s %s" % (rel, t, ("%d 字" % w) if w else "待抽文本"))
    else:
        print("  （无新增素材）")
    if skipped:
        print("  ⏭️  跳过重复 %d 个（sha256 已存在）" % len(skipped))
    print("=" * 62)
    print("  素材总数: %d 个 · 可计字数: %d 字" % (len(sources), total_words))
    print("  schema: %s · slug: %s" % (args.schema, slug))
    print("  维度状态: " + " · ".join(
        "%s=%s" % (d["name"], {"complete": "✅", "partial": "🟡", "missing": "❌"}[d["status"]])
        for d in dimensions))
    print("  清单已写入: %s" % os.path.relpath(mpath, os.getcwd()))

    if need_text:
        print("")
        print("  ⚠️  以下 %d 个二进制素材未能统计字数，请在 Phase 1 用文档读取工具抽取后回填:"
              % len(need_text))
        for p in need_text[:10]:
            print("     - " + p)
        if len(need_text) > 10:
            print("     ... 另有 %d 个" % (len(need_text) - 10))

    if len(sources) < 10:
        print("")
        print("  ⚠️  素材不足 10 条，档案质量会受限（见 distillation-framework.md §九）")

    print("")
    print("  提示：coverage / 一手二手计数脚本不判定，写为 null（未回填），Phase 3 由 agent 回填；")
    print("        档案正文写完后跑 seal.py 封存 distillate_sha256。")


if __name__ == "__main__":
    main()
