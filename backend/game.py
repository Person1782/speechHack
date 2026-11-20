"""Pure game logic: codes, scoring, round plans, rankings. Unit-tested in tests/test_game.py."""
import random
import secrets

CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I, no O
ANSWER_GRACE_MS = 500
MAX_TEAMS = 30


def gen_code() -> str:
    return "".join(secrets.choice(CODE_LETTERS) for _ in range(4))


def calc_points(ms_taken: int, time_limit_ms: int) -> int:
    """Correct answer: 500-1000. round(1000 * (1 - (t / limit) / 2))."""
    if time_limit_ms <= 0:
        return 500
    t = max(0, min(ms_taken, time_limit_ms))
    return int(round(1000 * (1 - (t / time_limit_ms) / 2)))


def streak_bonus(streak: int) -> int:
    """streak counts the current correct answer. 1st correct = 0, 2nd in a row = +100 ... max +500."""
    if streak <= 1:
        return 0
    return min(100 * (streak - 1), 500)


def is_fast_wrong(ms_taken: int, time_limit_ms: int) -> bool:
    return ms_taken < 0.25 * time_limit_ms


def recompute_scores(team_ids, revealed_qids, answers_by_q):
    """Derive brain points & streak data from revealed questions in reveal order.
    answers_by_q: {qid: {team_id: answer_doc}} where answer has is_correct, points_pending, ms_taken, fast_wrong.
    Returns {team_id: {...}} and {qid: {team_id: points_awarded}}.
    """
    out = {t: {"brain_points": 0, "streak": 0, "cold": 0, "fast_wrong_count": 0, "total_ms": 0,
               "best_streak": 0} for t in team_ids}
    awarded = {}
    for qid in revealed_qids:
        awarded[qid] = {}
        qa = answers_by_q.get(qid, {})
        for t in team_ids:
            s = out[t]
            a = qa.get(t)
            if a:
                s["total_ms"] += int(a.get("ms_taken", 0))
            if a and a.get("is_correct"):
                s["streak"] += 1
                s["cold"] = 0
                pts = int(a.get("points_pending", 0)) + streak_bonus(s["streak"])
                s["brain_points"] += pts
                s["best_streak"] = max(s["best_streak"], s["streak"])
                awarded[qid][t] = pts
            else:
                s["streak"] = 0
                s["cold"] += 1
                awarded[qid][t] = 0
                if a and a.get("fast_wrong"):
                    s["fast_wrong_count"] += 1
    return out, awarded


def rank_key(team: dict):
    total = int(team.get("brain_points", 0)) + int(team.get("laugh_points", 0))
    return (-total, int(team.get("total_ms", 0)), int(team.get("number", 0)))


def rank_teams(teams):
    """Sort by total desc; tie-break: lower total answer time ranks higher."""
    return sorted(teams, key=rank_key)


# Round plans. Tier 1 only has classic questions; rounds whose features don't exist yet
# are replaced by classic questions from the bank (poll rounds skipped).
BUILT_TYPES = {"classic"}

FULL_NIGHT = [
    {"key": "fool_the_room", "name_en": "Fool the Room", "name_vi": "Lừa Cả Phòng", "count": 6, "time": 20},
    {"key": "saigon", "name_en": "This Week in Saigon", "name_vi": "Sài Gòn Tuần Này", "count": 5, "time": 20},
    {"key": "caption", "name_en": "Picture It", "name_vi": "Hình Dung Đi", "count": 5, "time": 20},
    {"key": "comic_vs_room", "name_en": "Comic vs The Room", "name_vi": "MC Đấu Cả Phòng", "count": 5, "time": 20},
    {"key": "lightning", "name_en": "Lightning Round", "name_vi": "Vòng Chớp Nhoáng", "count": 8, "time": 10},
]
DEMO_NIGHT = [
    {"key": "warm_up", "name_en": "Warm-up Round", "name_vi": "Vòng Khởi Động", "count": 3, "time": 20},
]


def build_round_plan(preset: str, questions: list) -> list:
    """questions: list of dicts with id, index, round_type. Returns rounds with question_ids."""
    pool = [q for q in sorted(questions, key=lambda q: q["index"]) if q["round_type"] in ("classic", "decoy")]
    classic_first = [q for q in pool if q["round_type"] == "classic"] + [q for q in pool if q["round_type"] == "decoy"]
    template = FULL_NIGHT if preset == "full" else DEMO_NIGHT
    rounds, used = [], 0
    for r in template:
        ids = [q["id"] for q in classic_first[used:used + r["count"]]]
        used += len(ids)
        if ids:
            rounds.append({"key": r["key"], "name_en": r["name_en"], "name_vi": r["name_vi"],
                           "time": r["time"], "question_ids": ids})
    return rounds


def flatten_plan(rounds: list) -> list:
    flat = []
    for ri, r in enumerate(rounds):
        for pos, qid in enumerate(r["question_ids"]):
            flat.append({"round_index": ri, "pos": pos, "qid": qid, "round_len": len(r["question_ids"]), "time": r["time"]})
    return flat


def after_reveal_step(flat: list, qi: int, preset: str):
    """What NEXT does after a reveal: ('scoreboard', round_end) or ('question', next_qi)."""
    cur = flat[qi]
    if cur["pos"] == cur["round_len"] - 1 or qi == len(flat) - 1:
        return "scoreboard", True
    if preset == "full" and (cur["pos"] + 1) % 3 == 0:
        return "scoreboard", False
    return "question", qi + 1


def sim_choice(correct_index: int, n_options: int = 4, rng=random) -> int:
    """~60% correct; when wrong, prefer a 'plausible' neighbour option."""
    if rng.random() < 0.6:
        return correct_index
    wrong = [i for i in range(n_options) if i != correct_index]
    weights = [3 if abs(i - correct_index) == 1 else 1 for i in wrong]
    return rng.choices(wrong, weights=weights, k=1)[0]
