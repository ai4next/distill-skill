#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蒸馏.skill · 评测记录与对比

维护 `EVALS.jsonl`（追加式评测历史），并提供**拒绝过度断言**的版本对比。

背景:
    QUALITY.md 每次重跑评分都被覆盖，分数历史随之销毁。EVALS.jsonl 只增不改，
    让「这版比上版好在哪」这个问题第一次变得可回答。

用法:
    python3 eval_record.py record  --file distilled/<slug>/EVALS.jsonl --json '<记录 JSON>'
    python3 eval_record.py record  --file <path> --from-file <json文件>
    python3 eval_record.py record  --file <path> --json '<记录 JSON>' --artifact distilled/<slug>
    python3 eval_record.py history --file <path>
    python3 eval_record.py compare --file <path> [--noise 10]

选项:
    --artifact PATH   指定被评测的档案（目录或 DISTILLATE.md）。
                      **强烈建议使用**：它自动填入 artifact_sha256 与 version，
                      消除手抄哈希/版本号出错的可能。与记录里已有的值冲突时会告警。

对比的有效性检查（关键）:
    compare **拒绝**在下列情况下给出趋势结论，只如实说明原因：
      1. 题目集变了（含题目退役）—— 缺口被补上后题目失效，直接比会得出「越完整分越低」的假退步
      2. 评分 agent < 2 个 —— 单次 LLM 评分噪声 ±5-10 分，不足以支撑趋势
      3. 分数差落在噪声带内 —— 分不出是真变化还是抖动
      4. 两次评的是同一份档案（artifact_sha256 相同）—— 没有变化可比

只读不写（record 除外，它只追加）。
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

NOISE_BAND = 10  # 与两份评分卡的「分差>10分需复核」保持一致
USAGE = "python3 eval_record.py {record|history|compare} --file <EVALS.jsonl> [--json ...]"


def q_sig(rec):
    """题目集签名：id + status。任何变化都意味着两次评测不可直接比较。"""
    return tuple(sorted((q.get("id"), q.get("status")) for q in rec.get("questions", [])))


def apply_artifact(rec, artifact_path):
    """用档案的真实哈希与 version 校正记录，返回告警列表。

    这是防呆：手抄 64 位哈希或版本号必然出错，而 artifact_sha256 是
    「这次评的到底是哪一版」的唯一依据——错了整条记录就失去意义。
    """
    warnings = []
    root = _lib.resolve_archive_dir(artifact_path)
    dpath = os.path.join(root, "DISTILLATE.md")
    if not os.path.isfile(dpath):
        _lib.usage_error("--artifact 下未找到 DISTILLATE.md: " + dpath, USAGE)
    digest = _lib.sha256_file(dpath)
    fm, _ = _lib.parse_frontmatter(_lib.read_text(dpath))
    version = (fm or {}).get("version")

    for key, actual in (("artifact_sha256", digest), ("version", version)):
        if actual is None:
            continue
        if key not in rec or _lib.is_null(rec.get(key)):
            rec[key] = actual
        elif rec.get(key) != actual:
            warnings.append("%s 与档案不符：记录里是 %r，档案实际是 %r"
                            % (key, rec.get(key), actual))
    return warnings


def cmd_record(args):
    path = args.get("--file")
    if not path:
        _lib.usage_error("record 需要 --file", USAGE)

    raw = args.get("--json")
    if not raw and args.get("--from-file"):
        raw = _lib.read_text(args["--from-file"])
    if not raw:
        _lib.usage_error("record 需要 --json 或 --from-file", USAGE)

    try:
        rec = json.loads(raw)
    except ValueError as e:
        _lib.usage_error("记录不是合法 JSON: %s" % e, USAGE)

    if not isinstance(rec, dict):
        _lib.usage_error("记录必须是 JSON 对象", USAGE)

    artifact_warnings = []
    if args.get("--artifact"):
        artifact_warnings = apply_artifact(rec, args["--artifact"])

    missing = [k for k in ("version", "artifact_sha256", "models", "scorers", "scores", "total")
               if k not in rec or _lib.is_null(rec.get(k))]
    if missing:
        _lib.usage_error("记录缺少必填字段: " + "、".join(missing)
                         + "（可用 --artifact 自动填入 version / artifact_sha256）", USAGE)
    if not isinstance(rec.get("models"), dict) or "score" not in rec["models"]:
        _lib.usage_error("models 必须是含 answer/score 的对象（评分必须独立于答题）", USAGE)
    if not rec.get("questions"):
        print("⚠️  记录未内嵌题目集（questions）—— compare 将无法判断可比性")

    rec.setdefault("schema_version", _lib.SUPPORTED_SCHEMA_VERSION)
    rec.setdefault("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    rec.setdefault("run_id", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    _lib.append_jsonl(path, rec)

    print("✅ 已追加评测记录: %s" % path)
    print("   version=%s total=%s grade=%s scorers=%s"
          % (rec.get("version"), rec.get("total"), rec.get("grade", "—"), rec.get("scorers")))
    print("   artifact_sha256=%s…" % str(rec.get("artifact_sha256"))[:12])
    for w in artifact_warnings:
        print("   ⚠️  " + w)
    if rec.get("scorers", 0) < 2:
        print("   ⚠️  评分 agent 仅 %s 个 —— compare 不会给出趋势结论（噪声大于信号）"
              % rec.get("scorers"))


def cmd_history(args):
    path = args.get("--file")
    if not path:
        _lib.usage_error("history 需要 --file", USAGE)
    recs = _lib.load_jsonl(path)
    if not recs:
        print("（无评测记录: %s）" % path)
        return

    dims = []
    for r in recs:
        for d in (r.get("scores") or {}):
            if d not in dims:
                dims.append(d)

    W = [8, 12, 8, 8] + [max(8, _lib.dw(d) + 2) for d in dims]
    rows = []
    for r in recs:
        sc = r.get("scores") or {}
        rows.append([r.get("version", "?"), r.get("date", "?"), r.get("total", "?"),
                     r.get("grade", "—")] + [sc.get(d, "—") for d in dims])

    print("评测历史: %s（%d 次）" % (path, len(recs)))
    for line in _lib.render_table(["ver", "date", "total", "grade"] + dims, [rows], W):
        print(line)


def cmd_compare(args):
    path = args.get("--file")
    if not path:
        _lib.usage_error("compare 需要 --file", USAGE)
    try:
        noise = int(args.get("--noise", NOISE_BAND))
    except (TypeError, ValueError):
        _lib.usage_error("--noise 必须是整数", USAGE)

    recs = _lib.load_jsonl(path)
    if len(recs) < 2:
        print("⚠️  只有 %d 次记录，无法对比。至少需要 2 次。" % len(recs))
        return

    prev, cur = recs[-2], recs[-1]
    print("对比: version %s → %s" % (prev.get("version"), cur.get("version")))
    print("=" * 62)

    # ---- 有效性检查（这是本命令的核心价值：拒绝过度断言） ----
    blockers = []

    if prev.get("artifact_sha256") == cur.get("artifact_sha256"):
        blockers.append("两次评的是**同一个**档案版本（artifact_sha256 相同）——没有变化可比")

    sp, sc_ = q_sig(prev), q_sig(cur)
    if sp != sc_:
        pp = {q.get("id"): q.get("status") for q in prev.get("questions", [])}
        cc = {q.get("id"): q.get("status") for q in cur.get("questions", [])}
        retired = [i for i in pp if i not in cc or cc[i] == "retired"]
        added = [i for i in cc if i not in pp]
        detail = []
        if retired:
            detail.append("退役 %d 题（%s）" % (len(retired), "、".join(retired[:3])))
        if added:
            detail.append("新增 %d 题（%s）" % (len(added), "、".join(added[:3])))
        if not detail:
            detail.append("题目状态有变动")
        blockers.append("题目集已变化：" + "，".join(detail) +
                        "\n      缺口被补上后原题失效，直接比会得出「越完整分越低」的假退步")

    if min(prev.get("scorers", 1), cur.get("scorers", 1)) < 2:
        blockers.append("评分 agent 少于 2 个（%s / %s）—— 单次 LLM 评分噪声 ±5-10 分，"
                        "不足以支撑趋势结论" % (prev.get("scorers"), cur.get("scorers")))

    # 逐维 delta
    dims = [d for d in (cur.get("scores") or {}) if d in (prev.get("scores") or {})]
    deltas = {d: cur["scores"][d] - prev["scores"][d] for d in dims}
    total_delta = (cur.get("total") or 0) - (prev.get("total") or 0)

    W = [22, 8, 8, 8]
    dim_rows = [(d, prev["scores"][d], cur["scores"][d], ("%+d" % deltas[d]) if deltas[d] else "0")
                for d in dims]
    total_row = [("总分", prev.get("total"), cur.get("total"), "%+d" % total_delta)]
    for line in _lib.render_table(("维度", "上版", "本版", "Δ"), [dim_rows, total_row], W):
        print(line)

    # ---- 结论 ----
    print("")
    if blockers:
        print("❌ 本次对比不构成有效对比：")
        for b in blockers:
            print("   - " + b)
        print("")
        print("   建议：修好上述问题后再比，或把它当作一次独立的分数记录（history 里仍可见）。")
        return

    if abs(total_delta) <= noise:
        print("⚠️  总分变化 %+d，落在噪声带（±%d）内 —— 分不出是真变化还是抖动。"
              % (total_delta, noise))
        print("   建议：加跑第二个评分 agent，看分差是否稳定。")
        return

    verdict = "提升" if total_delta > 0 else "退步"
    print("✅ 对比有效：总分 %+d，判定为**%s**。" % (total_delta, verdict))
    ups = [d for d in dims if deltas[d] > 0]
    downs = [d for d in dims if deltas[d] < 0]
    if ups:
        print("   上升维度: " + "、".join("%s %+d" % (d, deltas[d]) for d in ups))
    if downs:
        print("   下降维度: " + "、".join("%s %+d" % (d, deltas[d]) for d in downs))
    if verdict == "提升":
        print("   下一步：把这版设为新基线，继续下一次迭代。")


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if argv else 1)

    cmd = argv[0]
    if cmd not in ("record", "history", "compare"):
        _lib.usage_error("未知子命令: " + cmd, USAGE)

    args, i = {}, 1
    while i < len(argv):
        if argv[i].startswith("--"):
            key = argv[i]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                args[key] = argv[i + 1]
                i += 2
            else:
                args[key] = True
                i += 1
        else:
            i += 1

    {"record": cmd_record, "history": cmd_history, "compare": cmd_compare}[cmd](args)


if __name__ == "__main__":
    main()
