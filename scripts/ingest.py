#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 素材归集与清点

把散落的素材按类型归入 distilled/<slug>/sources/，统计字数与哈希，
生成 / 增量更新 manifest.json（蒸馏档案契约的素材清单）。

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
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import date

SCHEMA_VERSION = 1

# 维度定义：与 references/schema-*.md 保持一致
SCHEMA_DIMENSIONS = {
    "person": [
        ("01", "著作", "01-writings.md"),
        ("02", "对话", "02-conversations.md"),
        ("03", "表达", "03-expression-dna.md"),
        ("04", "他者", "04-external-views.md"),
        ("05", "决策", "05-decisions.md"),
        ("06", "时间线", "06-timeline.md"),
    ],
    "topic": [
        ("01", "领域共识", "01-consensus.md"),
        ("02", "流派分歧", "02-schools.md"),
        ("03", "关键概念", "03-concepts.md"),
        ("04", "经典案例", "04-cases.md"),
        ("05", "争议前沿", "05-frontier.md"),
        ("06", "演进脉络", "06-evolution.md"),
    ],
    "document": [
        ("01", "论点树", "01-argument-tree.md"),
        ("02", "证据链", "02-evidence-chain.md"),
        ("03", "术语表", "03-glossary.md"),
        ("04", "隐含假设", "04-assumptions.md"),
        ("05", "内部矛盾", "05-contradictions.md"),
        ("06", "信息缺口", "06-gaps.md"),
    ],
}

# 扩展名 → 素材类型（类型名 == sources/ 子目录名）
TYPE_BY_EXT = {
    "books": {".pdf", ".epub", ".mobi", ".azw3", ".djvu"},
    "transcripts": {".srt", ".vtt"},
    "articles": {".html", ".htm", ".mhtml", ".mht"},
    "notes": {".txt", ".md", ".markdown", ".rst", ".org", ".docx", ".doc"},
    "chat": {".jsonl", ".json"},
    "code": {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".kt", ".rs",
        ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".scala",
        ".sh", ".bash", ".zsh", ".sql", ".yaml", ".yml", ".toml", ".ini",
    },
    "video": {".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".m4a", ".wav", ".flac"},
}

# 已知二进制：不做文本解码，words 记 null
BINARY_EXTS = {
    ".pdf", ".epub", ".mobi", ".azw3", ".djvu", ".docx", ".doc",
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".m4a", ".wav", ".flac",
}

CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")
LATIN_RE = re.compile(r"[A-Za-z0-9]+")


def usage_error(msg):
    print("❌ " + msg)
    print("用法: python3 ingest.py <素材路径...> --out distilled/<slug>/ [--schema person]")
    print("     详细说明见文件头部 docstring")
    sys.exit(1)


def classify(path):
    """按扩展名判定素材类型。"""
    ext = os.path.splitext(path)[1].lower()
    for type_name, exts in TYPE_BY_EXT.items():
        if ext in exts:
            return type_name
    return "other"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    """尽力解码为文本；二进制或解码失败返回 None。"""
    if os.path.splitext(path)[1].lower() in BINARY_EXTS:
        return None
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def count_words(text):
    """CJK 按字计，拉丁按词计。"""
    if text is None:
        return None
    return len(CJK_RE.findall(text)) + len(LATIN_RE.findall(text))


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


def load_manifest(out_dir):
    mpath = os.path.join(out_dir, "manifest.json")
    if not os.path.isfile(mpath):
        return None
    try:
        with open(mpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError) as e:
        print("⚠️  现有 manifest.json 无法解析（%s），将重建" % e)
        return None


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("paths", nargs="*", help="素材文件或目录")
    ap.add_argument("--out", required=False, help="档案目录，如 distilled/munger/")
    ap.add_argument("--schema", default="person",
                    choices=["person", "topic", "document", "custom"])
    ap.add_argument("--slug", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--dimensions", default=None, help="custom schema 的维度，逗号分隔")
    args = ap.parse_args()

    if not args.paths:
        usage_error("缺少素材路径")
    if not args.out:
        usage_error("缺少 --out 档案目录")

    out_dir = os.path.abspath(os.path.expanduser(args.out))
    slug = args.slug or os.path.basename(out_dir.rstrip(os.sep))
    if not slug:
        usage_error("无法推断 slug，请显式传 --slug")

    # 维度定义
    if args.schema == "custom":
        if not args.dimensions:
            usage_error("schema=custom 时必须用 --dimensions 指定维度（逗号分隔）")
        names = [s.strip() for s in args.dimensions.split(",") if s.strip()]
        if not 2 <= len(names) <= 8:
            usage_error("custom 维度数量需在 2-8 之间，当前 %d 个" % len(names))
        dims = [("%02d" % (i + 1), n, "%02d-%s.md" % (i + 1, re.sub(r"\W+", "-", n).strip("-").lower() or "dim"))
                for i, n in enumerate(names)]
    else:
        dims = SCHEMA_DIMENSIONS[args.schema]

    for sub in ("", "research", "sources"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    for t in list(TYPE_BY_EXT.keys()) + ["other"]:
        os.makedirs(os.path.join(out_dir, "sources", t), exist_ok=True)

    old = load_manifest(out_dir)
    old_sources = {s.get("sha256"): s for s in (old or {}).get("sources", []) if s.get("sha256")}
    sources = list((old or {}).get("sources", []))
    next_id = len(sources) + 1

    added, skipped, need_text = [], [], []
    today = date.today().isoformat()

    for path in iter_files(args.paths):
        try:
            digest = sha256_of(path)
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

        words = count_words(read_text(dest))
        if words is None:
            need_text.append(os.path.relpath(dest, out_dir))

        rel = os.path.relpath(dest, out_dir)
        sources.append({
            "id": "S%03d" % next_id,
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
        next_id += 1

    # 维度状态：research/ 下有对应文件即 partial/complete
    old_dims = {d.get("name"): d for d in (old or {}).get("dimensions", [])}
    dimensions = []
    for did, name, fname in dims:
        fpath = os.path.join(out_dir, "research", fname)
        if os.path.isfile(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    body = f.read()
            except OSError:
                body = ""
            status = "complete" if len(body) > 800 else "partial"
        else:
            status = "missing"
        prev = old_dims.get(name, {})
        dimensions.append({
            "id": did,
            "name": name,
            "file": "research/" + fname,
            "status": status,
            "sources": prev.get("sources", 0),
            "confidence": prev.get("confidence", {"A": 0, "B": 0, "C": 0, "D": 0}),
            "coverage": prev.get("coverage", 0),
        })

    total_words = sum(s["words"] or 0 for s in sources)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "schema": args.schema,
        "title": args.title or (old or {}).get("title") or slug,
        "created": (old or {}).get("created", today),
        "updated": today,
        "version": ((old or {}).get("version", 0) + (1 if added else 0)) or 1,
        "sources": sources,
        "source_words": total_words,
        # 一手/二手需判断，脚本无法自动判定，默认 0，由 agent 在 Phase 3 回填
        "sources_primary": (old or {}).get("sources_primary", 0),
        "sources_secondary": (old or {}).get("sources_secondary", 0),
        "dimensions": dimensions,
        "gaps": (old or {}).get("gaps", []),
        "changes": (old or {}).get("changes", []) + ([{
            "date": today,
            "action": "ingest",
            "note": "新增素材 %d 个，跳过重复 %d 个" % (len(added), len(skipped)),
            "sources_added": len(added),
        }] if added else []),
        "distillate_sha256": (old or {}).get("distillate_sha256"),
    }
    if not manifest["changes"]:
        manifest["changes"] = [{
            "date": today, "action": "initial", "note": "首次建库", "sources_added": len(added),
        }]

    mpath = os.path.join(out_dir, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

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
        print("  ⚠️  以下 %d 个二进制素材未能统计字数，请在 Phase 1 用文档读取工具抽取后回填:" % len(need_text))
        for p in need_text[:10]:
            print("     - " + p)
        if len(need_text) > 10:
            print("     ... 另有 %d 个" % (len(need_text) - 10))

    if len(sources) < 10:
        print("")
        print("  ⚠️  素材不足 10 条，档案质量会受限（见 distillation-framework.md §九）")


if __name__ == "__main__":
    main()
