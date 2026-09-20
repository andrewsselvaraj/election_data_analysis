import csv
import json

CSV_PATH = "madurantakam_35_tableau.csv"
OUT_PATH = "madurantakam_35_dashboard.html"

booths = []
index_by_booth_no = {}

with open(CSV_PATH, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        bno = row["booth_no"]
        key = index_by_booth_no.get(bno)
        # AC035's own Form 20 lists booth 218 twice (a zero row + a real
        # row) -- keep both as separate records rather than collapsing them.
        if key is not None and booths[key]["total_votes"] == 0 and int(row["total_booth_votes"]) > 0:
            # first record for this booth_no was the all-zero placeholder;
            # start a fresh second record instead of merging into it
            key = None
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
        rec["candidates"].append({
            "name": row["candidate_name"],
            "party": row["party_name"],
            "votes": int(row["votes_received"]),
            "pct": float(row["vote_share_pct"]),
            "is_winner": row["is_winner"] == "True",
        })

# tag duplicate booth_no records with an occurrence index for display/search
from collections import Counter
counts = Counter(b["booth_no"] for b in booths)
seen = Counter()
for b in booths:
    if counts[b["booth_no"]] > 1:
        seen[b["booth_no"]] += 1
        b["dup_label"] = f"{b['booth_no']} (record {seen[b['booth_no']]} of {counts[b['booth_no']]})"
    else:
        b["dup_label"] = b["booth_no"]

for b in booths:
    b["candidates"].sort(key=lambda c: -c["votes"])
    lead = b["candidates"][0] if b["candidates"] else None
    runner_up = b["candidates"][1] if len(b["candidates"]) > 1 else None
    b["leader"] = lead
    b["margin"] = (lead["votes"] - runner_up["votes"]) if (lead and runner_up) else (lead["votes"] if lead else 0)

print(f"booth records: {len(booths)}")
print(f"duplicate booth_no groups: {[k for k,v in counts.items() if v>1]}")

# constituency-wide totals per candidate (party assumed stable per candidate)
totals = {}
order = []
for b in booths:
    for c in b["candidates"]:
        if c["name"] not in totals:
            totals[c["name"]] = {"name": c["name"], "party": c["party"], "votes": 0}
            order.append(c["name"])
        totals[c["name"]]["votes"] += c["votes"]

overall = sorted(totals.values(), key=lambda c: -c["votes"])
grand_total = sum(c["votes"] for c in overall)
for c in overall:
    c["pct"] = round(c["votes"] / grand_total * 100, 2) if grand_total else 0.0
overall[0]["is_winner"] = True
for c in overall[1:]:
    c["is_winner"] = False

# flat street index for search (street -> list of booth indices)
street_rows = []
for i, b in enumerate(booths):
    for s in b["streets"]:
        street_rows.append({"street": s, "booth_index": i})

summary = {
    "constituency": "35. Madurantakam (SC)",
    "total_booths": len(booths),
    "total_valid_votes": grand_total,
    "overall": overall,
    "booths": booths,
    "street_rows": street_rows,
}

data_json = json.dumps(summary, ensure_ascii=False)
print(f"embedded JSON size: {len(data_json):,} chars")

with open("dashboard_template.html", encoding="utf-8") as f:
    template = f.read()

# escape "</script>" so the embedded JSON can't accidentally close the tag early
safe_json = data_json.replace("</script>", "<\\/script>")
html = template.replace("__DATA_JSON__", safe_json)

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Wrote {OUT_PATH} ({len(html):,} chars)")
