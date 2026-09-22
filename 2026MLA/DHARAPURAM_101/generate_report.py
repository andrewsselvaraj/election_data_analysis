import csv
import json
from collections import Counter

CSV_PATH = "dharapuram_101_tableau.csv"
TEMPLATE_PATH = "report_template.html"
OUT_PATH = "dharapuram_101_report.html"

booths = []
index_by_booth_no = {}

with open(CSV_PATH, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        bno = row["booth_no"]
        key = index_by_booth_no.get(bno)
        if key is not None and booths[key]["total_votes"] == 0 and int(row["total_booth_votes"]) > 0:
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

print(f"booth records: {len(booths)}")

summary = {
    "constituency": "101. Dharapuram (SC)",
    "total_booths": len(booths),
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
