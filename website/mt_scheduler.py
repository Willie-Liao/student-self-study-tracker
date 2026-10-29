#!/usr/bin/env python3
"""
MT (Mentor Time) Online Adaptive Scheduler
------------------------------------------
Reads:
  - MT/website/session-history.json  (per-session log + board photo filenames)
  - MT/website/student-records.json  (cumulative per-student record)

Does:
  1. Recomputes cumulative Praise (P) and Warning (W) counts from session-history.json
     and syncs MT/website/student-records.json.
  2. Runs the Online Adaptive Update across all 32 students (without row grouping):
       - Adaptive redemption weight alpha_t in [0.20, 0.60]
       - Next session's suggested Praise : Warning ratio & Quality/Backfill split
       - Class-wide Praise Backfill & Warning Watch priority order
  3. Writes the full table + Next Session Watchlist into MT/website/praise-warning.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
SESSION_HISTORY_PATH = BASE_DIR / "session-history.json"
STUDENT_RECORDS_PATH = BASE_DIR / "student-records.json"
MARKDOWN_PATH = BASE_DIR / "praise-warning.md"


def sync_records_from_history() -> tuple[dict[str, Any], dict[str, Any]]:
    with open(SESSION_HISTORY_PATH, encoding="utf-8") as f:
        history = json.load(f)
    with open(STUDENT_RECORDS_PATH, encoding="utf-8") as f:
        records = json.load(f)

    roster_map = {s["nickname"]: s for s in records["students"]}
    for s in records["students"]:
        s.pop("october_seat", None)
        s["praise"] = 0
        s["warning"] = 0
        s["last_praised_session"] = None
        s["last_warned_session"] = None

    unmatched: dict[str, dict[str, Any]] = {}
    reasons = {
        u["name"]: u.get("reason", "Not on E7-1 nickname roster.")
        for u in records.get("unmatched_or_ambiguous", [])
    }

    for sess in history["sessions"]:
        sid = sess["session_id"]
        for name in sess.get("praise", []):
            if name == "Olivia":
                name = "Seohyun"
            elif name in ("Mar", "Max"):
                name = "Max D"
            if name in roster_map:
                roster_map[name]["praise"] += 1
                roster_map[name]["last_praised_session"] = sid
            else:
                u = unmatched.setdefault(
                    name,
                    {
                        "name": name,
                        "praise": 0,
                        "warning": 0,
                        "last_praised_session": None,
                        "last_warned_session": None,
                        "reason": reasons.get(name, "Not on E7-1 nickname roster."),
                    },
                )
                u["praise"] += 1
                u["last_praised_session"] = sid

        for name in sess.get("warning", []):
            if name == "Olivia":
                name = "Seohyun"
            elif name in ("Mar", "Max"):
                name = "Max D"
            if name in roster_map:
                roster_map[name]["warning"] += 1
                roster_map[name]["last_warned_session"] = sid
            else:
                u = unmatched.setdefault(
                    name,
                    {
                        "name": name,
                        "praise": 0,
                        "warning": 0,
                        "last_praised_session": None,
                        "last_warned_session": None,
                        "reason": reasons.get(name, "Not on E7-1 nickname roster."),
                    },
                )
                u["warning"] += 1
                u["last_warned_session"] = sid

    history["total_sessions"] = len(history["sessions"])
    last_sid = history["sessions"][-1]["session_id"] if history["sessions"] else None
    p_matched = sum(s["praise"] for s in records["students"])
    w_matched = sum(s["warning"] for s in records["students"])
    p_unmatched = sum(u["praise"] for u in unmatched.values())
    w_unmatched = sum(u["warning"] for u in unmatched.values())

    records["updated_after_session"] = last_sid
    records["summary"] = {
        "roster_size": len(records["students"]),
        "total_praise_matched": p_matched,
        "total_warning_matched": w_matched,
        "total_praise_including_unmatched": p_matched + p_unmatched,
        "total_warning_including_unmatched": w_matched + w_unmatched,
    }
    records["unmatched_or_ambiguous"] = list(unmatched.values())

    with open(SESSION_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    with open(STUDENT_RECORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    return history, records


def compute_online_state(
    history: dict[str, Any],
    records: dict[str, Any],
    base_alpha: float = 0.25,
    learning_rate: float = 0.40,
) -> dict[str, Any]:
    """
    Class-Wide Online Adaptive Controller:
      1. d_t = sum(max(0, W_i - P_i)) / sum(W_i)
      2. alpha_t = clip(base_alpha + learning_rate * d_t, 0.20, 0.60)
      3. Chooses next session's suggested Praise : Warning ratio & Quality/Backfill split
      4. Orders all 32 students for Praise Backfill by (cooldown, P - alpha_t * W, P)
    """
    students = records["students"]
    sessions = history["sessions"]
    last_session = sessions[-1] if sessions else {"session_id": None, "praise": [], "warning": []}
    last_sid = last_session["session_id"]

    total_w = sum(s["warning"] for s in students)
    unredeemed_deficit = sum(max(0, s["warning"] - s["praise"]) for s in students)
    deficit_ratio = unredeemed_deficit / max(1, total_w)

    alpha_t = max(0.20, min(0.60, round(base_alpha + learning_rate * deficit_ratio, 2)))

    last_p = len(last_session.get("praise", []))
    last_w = len(last_session.get("warning", []))
    zero_praise_count = sum(1 for s in students if s["praise"] == 0)
    max_w_student = max(s["warning"] for s in students)

    if last_p <= last_w:
        target_praise, max_warning = 6, 2
        quality_m = 2
        reason = f"Last session was warning-heavy ({last_p}P : {last_w}W) — rebound to 6P : 2W (3:1)"
    elif zero_praise_count >= 8:
        target_praise, max_warning = 6, 3
        quality_m = 2
        reason = f"{zero_praise_count} students still at 0 praise — keep 6P : 3W with 4 backfill slots"
    elif max_w_student >= 3:
        target_praise, max_warning = 5, 2
        quality_m = 2
        reason = "Top warning count >= 3 — cap warnings at 2 and prioritize redemption"
    else:
        target_praise, max_warning = 5, 3
        quality_m = 3
        reason = "Balanced state — standard 5P : 3W (3 quality + 2 backfill)"

    backfill_slots = target_praise - quality_m

    praise_queue: list[dict[str, Any]] = []
    warning_queue: list[dict[str, Any]] = []

    for s in students:
        p_cnt = s["praise"]
        w_cnt = s["warning"]
        praised_last = s["last_praised_session"] == last_sid
        warned_last = s["last_warned_session"] == last_sid
        eff_score = round(p_cnt - alpha_t * w_cnt, 2)

        entry = {
            "nickname": s["nickname"],
            "chinese_name": s["chinese_name"] or "",
            "praise": p_cnt,
            "warning": w_cnt,
            "effective_score": eff_score,
            "praised_last_session": praised_last,
            "warned_last_session": warned_last,
        }
        praise_queue.append(entry)
        warning_queue.append(entry)

    # Class-wide Praise Backfill order:
    # 1) Not praised in the immediately preceding session
    # 2) Lowest effective_score = P - alpha_t * W
    # 3) Lowest raw praise count
    praise_queue.sort(
        key=lambda x: (x["praised_last_session"], x["effective_score"], x["praise"], x["nickname"])
    )

    # Class-wide Warning tie-breaker order (when multiple students are mildly off-task):
    # 1) Not warned in the immediately preceding session
    # 2) Lowest warning count
    warning_queue.sort(
        key=lambda x: (x["warned_last_session"], x["warning"], -x["praise"], x["nickname"])
    )

    return {
        "alpha_t": alpha_t,
        "deficit_ratio": round(deficit_ratio, 3),
        "zero_praise_count": zero_praise_count,
        "target_praise": target_praise,
        "max_warning": max_warning,
        "quality_slots_M": quality_m,
        "backfill_slots": backfill_slots,
        "ratio_reason": reason,
        "praise_queue": praise_queue,
        "warning_queue": warning_queue,
    }


def write_markdown(history: dict[str, Any], records: dict[str, Any], state: dict[str, Any]) -> None:
    alpha_t = state["alpha_t"]
    all_rows = []
    for s in records["students"]:
        eff = round(s["praise"] - alpha_t * s["warning"], 2)
        all_rows.append({
            "nickname": s["nickname"],
            "chinese_name": s["chinese_name"] or "",
            "praise": s["praise"],
            "warning": s["warning"],
            "effective_score": eff,
            "on_roster": True,
        })
    for u in records.get("unmatched_or_ambiguous", []):
        if u["praise"] > 0 or u["warning"] > 0:
            eff = round(u["praise"] - alpha_t * u["warning"], 2)
            all_rows.append({
                "nickname": u["name"],
                "chinese_name": "",
                "praise": u["praise"],
                "warning": u["warning"],
                "effective_score": eff,
                "on_roster": False,
            })

    all_rows.sort(key=lambda x: (-x["praise"], -x["warning"], x["nickname"]))

    n_sessions = history["total_sessions"]
    n_dups = sum(len(s.get("duplicate_images", [])) for s in history["sessions"])

    lines = [
        "# MT praise and warning",
        "",
        f"{n_sessions} sessions recorded ({n_dups} duplicate board photos skipped). "
        "Praise is every name on the star side. Warning is every name under the warning triangle.",
        "",
        f"| Student | Chinese name | Praise | Warning | Effective score ($P - {alpha_t:.2f}W$) |",
        "|---|---|---:|---:|---:|",
    ]
    for r in all_rows:
        lines.append(
            f"| {r['nickname']} | {r['chinese_name']} | {r['praise']} | {r['warning']} | {r['effective_score']:+.2f} |"
        )

    pq = state["praise_queue"]
    tier_redeem = [x for x in pq if not x["praised_last_session"] and x["effective_score"] < 0]
    tier_zero = [x for x in pq if not x["praised_last_session"] and x["effective_score"] == 0]
    tier_next = [x for x in pq if not x["praised_last_session"] and x["praise"] == 1 and x["effective_score"] >= 0]

    def fmt_list(items: list[dict[str, Any]]) -> str:
        return ", ".join(
            f"**{x['nickname']}** ({x['praise']}P/{x['warning']}W, `{x['effective_score']:+.2f}`)"
            for x in items
        ) or "None"

    lines.extend([
        "",
        "Olivia on the board is Seohyun. Mar on the board is Max D.",
        "",
        "## Next MT session recommendation (online adaptive update)",
        "",
        f"- **Suggested ratio:** **{state['target_praise']} Praise : at most {state['max_warning']} Warning** ({state['ratio_reason']})",
        f"- **Praise split:** **{state['quality_slots_M']} Quality** (Phase 1) + **{state['backfill_slots']} Fairness Backfill** (Phase 2)",
        f"- **Redemption weight $\\alpha_t$:** **{alpha_t:.2f}** (effective score $= P - {alpha_t:.2f} W$, lowest score goes first)",
        "",
        "### Class-wide Praise Backfill Priority (lowest effective score first)",
        "",
        f"1. **Tier 1 — Redemption first ($P - {alpha_t:.2f}W < 0$):** {fmt_list(tier_redeem)}",
        f"2. **Tier 2 — Zero praise & zero warning ($0.00$):** {fmt_list(tier_zero)}",
        f"3. **Tier 3 — Next least praise (1P):** {fmt_list(tier_next)}",
    ])

    MARKDOWN_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    history, records = sync_records_from_history()
    state = compute_online_state(history, records)
    write_markdown(history, records, state)

    print(f"Updated {STUDENT_RECORDS_PATH.name} and {MARKDOWN_PATH.name} (after {history['total_sessions']} sessions).")
    print(f"Suggested Next Session : {state['target_praise']} Praise : at most {state['max_warning']} Warning")
    print(f"Split                  : {state['quality_slots_M']} Quality + {state['backfill_slots']} Backfill (alpha_t = {state['alpha_t']:.2f})")
    top_10 = ", ".join(
        f"{x['nickname']}({x['praise']}P/{x['warning']}W={x['effective_score']:+.2f})"
        for x in state["praise_queue"][:10]
    )
    print(f"Top 10 Praise Backfill : {top_10}")


if __name__ == "__main__":
    main()
