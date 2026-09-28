#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 封存档案哈希（distillate_sha256）

把 `DISTILLATE.md` 的内容哈希写进 `manifest.json` 的 `distillate_sha256`。

为什么需要它:
    `distillate_sha256` 是**档案格式契约的字段**：下游消费者靠它判断
    「我手里的产物是否还基于当前这版档案」。在 seal 出现之前，没有任何脚本
    会计算这个字段——它永远是 null，「档案已漂移」这件事静默失效。
    （消费者若拿得到档案文件，可直接哈希比对；本字段是异地兜底与镜像。）

职责边界:
    本脚本只做**机械**动作：算哈希、写回一个字段。它**不**判断档案质量、
    **不**递增 version、**不**改 updated——那些是语义动作，由 agent 按流程做。
    档案内容一改，哈希就过期；改完档案必须重新 seal，`quality_check.py` 会检查。

用法:
    python3 seal.py <档案目录或 DISTILLATE.md 路径> [--check]

选项:
    --check    只校验不写入。一致退出 0，不一致/缺失退出 1（供 CI 或质检调用）

示例:
    python3 seal.py distilled/munger
    python3 seal.py distilled/munger/DISTILLATE.md
    python3 seal.py distilled/munger --check

退出码:
    0 = 已封存（或 --check 校验一致）
    1 = 参数/文件有误，或 --check 发现不一致
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

USAGE = "python3 seal.py <档案目录或 DISTILLATE.md> [--check]"


def derive_ratio(manifest):
    """从 `source_words` / `distillate_words` 派生 `compression_ratio` 字符串。

    两个数缺一不可、必须是整数、且档案字数 >0，否则返回 None（**不猜**）。
    契约要求 `compression_ratio` 必填，而它是纯派生值——让 agent 手算
    `"38:1"` 只是白送一个出错面，还会在软诊断里报出「自报值与实测值偏差」。
    素材是二进制、字数尚未回填时返回 None，由 agent 抽文本后回填再封存。
    """
    src = manifest.get("source_words")
    dst = manifest.get("distillate_words")
    for v in (src, dst):
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            return None
    return "%d:1" % max(1, round(src / float(dst)))


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if argv else 1)

    check_only = "--check" in argv
    paths = [a for a in argv if not a.startswith("--")]
    unknown = [a for a in argv if a.startswith("--") and a != "--check"]
    if unknown:
        _lib.usage_error("未知参数: " + "、".join(unknown), USAGE)
    if len(paths) != 1:
        _lib.usage_error("需要且仅需要一个档案路径", USAGE)

    root = _lib.resolve_archive_dir(paths[0])
    dpath = os.path.join(root, "DISTILLATE.md")
    mpath = os.path.join(root, "manifest.json")

    if not os.path.isfile(dpath):
        _lib.usage_error("未找到 DISTILLATE.md: " + dpath, USAGE)
    if not os.path.isfile(mpath):
        _lib.usage_error(
            "未找到 manifest.json（档案目录应由 ingest.py 建立）: " + mpath, USAGE)

    digest = _lib.sha256_file(dpath)
    if digest is None:
        _lib.usage_error("无法读取 DISTILLATE.md（权限或路径问题）: " + dpath, USAGE)
    manifest = _lib.load_manifest(mpath)
    if manifest is None:
        _lib.usage_error(
            "manifest.json 缺失、解析失败或顶层不是对象: " + mpath, USAGE)

    recorded = manifest.get("distillate_sha256")
    short = digest[:12]

    if check_only:
        if _lib.is_null(recorded):
            print("❌ 未封存：manifest.json 的 distillate_sha256 为空")
            print("   修法: python3 scripts/seal.py %s" % os.path.relpath(root))
            sys.exit(1)
        if recorded != digest:
            print("❌ 哈希过期：档案在封存后被改动过")
            print("   manifest: %s…" % str(recorded)[:12])
            print("   实际值:   %s…" % short)
            print("   修法: python3 scripts/seal.py %s" % os.path.relpath(root))
            sys.exit(1)
        print("✅ 哈希一致: %s…" % short)
        sys.exit(0)

    if recorded == digest:
        print("✅ 哈希已是最新，无需改动: %s…" % short)
        sys.exit(0)

    manifest["distillate_sha256"] = digest

    # 顺带派生 compression_ratio：它是 source_words / distillate_words 的商，
    # 让 agent 手算成 "38:1" 只是白送一个出错面。只在两个数都是整数时派生，
    # 且**不覆盖**已有的合法值之外的东西——测不到就留 null，不猜。
    derived = derive_ratio(manifest)
    if derived:
        manifest["compression_ratio"] = derived

    _lib.write_json(mpath, manifest)

    # version 不一致是常见的人为疏漏（改了档案忘了递增），如实提示但不代改
    fm, _ = _lib.parse_frontmatter(_lib.read_text(dpath))
    fm_version = (fm or {}).get("version")
    man_version = manifest.get("version")
    if fm_version is not None and man_version is not None and fm_version != man_version:
        print("⚠️  版本不一致：DISTILLATE.md version=%s，manifest.json version=%s"
              % (fm_version, man_version))
        print("   version 递增是语义动作（增量蒸馏时 +1），seal 不代改。")

    print("🔒 已封存: %s…" % short)
    print("   写入 %s" % os.path.relpath(mpath))
    if derived:
        print("   派生 compression_ratio=%s（源 %s 字 : 档 %s 字）"
              % (derived, manifest["source_words"], manifest["distillate_words"]))
    print("   下游消费者据此判断产物是否基于当前档案；档案改动后须重新 seal。")


if __name__ == "__main__":
    main()
