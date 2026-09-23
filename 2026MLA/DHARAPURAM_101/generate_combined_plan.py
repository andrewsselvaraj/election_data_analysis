import csv
import json
from collections import Counter

CSV_PATH = "dharapuram_101_tableau.csv"
TEMPLATE_PATH = "combined_plan_template.html"
OUT_PATH = "dharapuram_101_combined_plan.html"

# Party affiliations are not listed in this constituency's Form 20 source,
# but were confirmed via web search (businesstoday.in / Wikipedia coverage
# of the 2026 Dharapuram result): P. Sathyabama = AIADMK, T. Indirani = DMK,
# Gowri Chitra = TVK. All other candidates on this ballot are independents /
# minor-party with no confirmed affiliation, so they stay unhighlighted.
PARTY_MAP = {
    "Indirani.T": ("DMK", "Dravida Munnetra Kazhagam"),
    "Sathyabama.P": ("AIADMK", "All India Anna Dravida Munnetra Kazhagam"),
    "Gowri Chitra": ("TVK", "Tamilaga Vettri Kazhagam"),
}
TVK_NAME = "Gowri Chitra"
DMK_NAME = "Indirani.T"
AIADMK_NAME = "Sathyabama.P"
BATTLEGROUND_THRESHOLD = 15.0

booths = []
index_by_booth_no = {}

with open(CSV_PATH, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        bno = row["booth_no"]
        key = index_by_booth_no.get(bno)
        if key is None:
            rec = {
                "booth_no": bno,
                "polling_station_name": row["polling_station_name"],
                "streets": [s.strip() for s in row["covered_streets"].split(";") if s.strip()],
                "total_votes": int(row["total_booth_votes"]),
                "candidates": [],
            }
            booths.append(rec)
            index_by_booth_no[bno] = len(booths) - 1
            key = len(booths) - 1
        rec = booths[key]
        party_code, party_display = PARTY_MAP.get(row["candidate_name"], (None, None))
        rec["candidates"].append({
            "name": row["candidate_name"],
            "party": party_display or "",
            "party_code": party_code,
            "votes": int(row["votes_received"]),
            "pct": float(row["vote_share_pct"]),
        })

counts = Counter(b["booth_no"] for b in booths)
seen = Counter()
for b in booths:
    if counts[b["booth_no"]] > 1:
        seen[b["booth_no"]] += 1
        b["dup_label"] = f"{b['booth_no']} (record {seen[b['booth_no']]} of {counts[b['booth_no']]})"
    else:
        b["dup_label"] = b["booth_no"]

status_counts = {"stronghold": 0, "battleground": 0, "needswork": 0}

for b in booths:
    b["candidates"].sort(key=lambda c: -c["votes"])
    cand_by_name = {c["name"]: c for c in b["candidates"]}
    tvk = cand_by_name[TVK_NAME]
    leader = b["candidates"][0]
    total = b["total_votes"]

    b["tvk_votes"] = tvk["votes"]
    b["tvk_pct"] = tvk["pct"]
    b["leader_name"] = leader["name"]
    b["leader_party"] = leader["party_code"] or ""

    if total == 0:
        b["status"] = "needswork"
        b["gap_pct"] = 0.0
        b["priority"] = 3000
    elif leader["name"] == TVK_NAME:
        runner_up = b["candidates"][1] if len(b["candidates"]) > 1 else None
        cushion = (tvk["votes"] - runner_up["votes"]) / total * 100 if runner_up else 100.0
        b["status"] = "stronghold"
        b["gap_pct"] = -cushion
        b["priority"] = 1000 + cushion
        status_counts["stronghold"] += 1
    else:
        gap = (leader["votes"] - tvk["votes"]) / total * 100
        b["gap_pct"] = gap
        if gap <= BATTLEGROUND_THRESHOLD:
            b["status"] = "battleground"
            b["priority"] = 0 + gap
            status_counts["battleground"] += 1
        else:
            b["status"] = "needswork"
            b["priority"] = 2000 + gap
            status_counts["needswork"] += 1

print(f"booth records: {len(booths)}")
print(f"status counts: {status_counts}")

totals = {}
for b in booths:
    for c in b["candidates"]:
        if c["name"] not in totals:
            totals[c["name"]] = {"name": c["name"], "party": c["party"], "party_code": c["party_code"], "votes": 0}
        totals[c["name"]]["votes"] += c["votes"]

overall = sorted(totals.values(), key=lambda c: -c["votes"])
grand_total = sum(c["votes"] for c in overall)
for i, c in enumerate(overall):
    c["pct"] = round(c["votes"] / grand_total * 100, 2) if grand_total else 0.0
    c["rank"] = i + 1

by_name = {c["name"]: c for c in overall}
overall_tvk = by_name[TVK_NAME]
overall_dmk = by_name[DMK_NAME]
overall_aiadmk = by_name[AIADMK_NAME]
overall_others_votes = grand_total - overall_tvk["votes"] - overall_dmk["votes"] - overall_aiadmk["votes"]
overall_others = {
    "votes": overall_others_votes,
    "pct": round(overall_others_votes / grand_total * 100, 2) if grand_total else 0.0,
}

summary = {
    "constituency": "101. Dharapuram (SC)",
    "total_booths": len(booths),
    "status_counts": status_counts,
    "overall": overall,
    "overall_tvk": overall_tvk,
    "overall_dmk": overall_dmk,
    "overall_aiadmk": overall_aiadmk,
    "overall_others": overall_others,
    "booths": booths,
}

data_json = json.dumps(summary, ensure_ascii=False)
safe_json = data_json.replace("</script>", "<\\/script>")

with open(TEMPLATE_PATH, encoding="utf-8") as f:
    template = f.read()

html = template.replace("__DATA_JSON__", safe_json)

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Wrote {OUT_PATH} ({len(html):,} chars)")
