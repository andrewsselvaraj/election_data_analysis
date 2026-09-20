import re
import csv
import subprocess
from pathlib import Path

FORM20_PDF = "AC035_form20.pdf"
BOOTHLIST_PDF = "AC035_BoothList.pdf"
FORM20_TXT = "form20_table.txt"
BOOTHLIST_TXT = "boothlist_layout.txt"


def ensure_text_extracted(pdf_path, txt_path, mode_flag):
    if not Path(txt_path).exists():
        subprocess.run(["pdftotext", mode_flag, pdf_path, txt_path], check=True)


ensure_text_extracted(FORM20_PDF, FORM20_TXT, "-table")
ensure_text_extracted(BOOTHLIST_PDF, BOOTHLIST_TXT, "-layout")

# ---------------------------------------------------------------------------
# 1. PARSE DATASET A: FORM 20 (booth-level candidate votes)
# ---------------------------------------------------------------------------

CANDIDATES = [
    # (column_index_in_row, candidate_name, party_name)
    (0, "S.Amulu Ponmalar", "Dravida Munnetra Kazhagam"),
    (1, "Maragatham Kumaravel.K", "All India Anna Dravida Munnetra Kazhagam"),
    (2, "Neelam E.Ramkumar", "Bahujan Samaj Party"),
    (3, "G.Janakiraman", "Naam Tamilar Katchi"),
    (4, "Ezhil Katharine Ezhilmalai", "Tamilaga Vettri Kazhagam"),
    (5, "R.Sugan", "All India Puratchi Thalaivar Makkal Munnettra Kazhagam"),
    (6, "S.Punniyakotti", "Tamizhaga Vaazhvurimai Katchi"),
    (7, "M.Kadirvel", "Independent"),
    (8, "Ranjitham.M", "Independent"),
    (9, "NOTA", "NOTA"),
]

with open(FORM20_TXT, encoding="utf-8") as f:
    form20_lines = f.read().split("\n")

form20_rows = []  # list of dict: sl_no, booth_no, candidate votes[10]
for raw in form20_lines[:700]:  # per-booth section only, summary starts after
    line = raw.rstrip("\n")
    m = re.match(r"^(\d+)\s+(\d+)\s", line)
    if not m:
        continue
    sl_no, booth_no = m.group(1), m.group(2)
    if sl_no == "1" and booth_no == "2":
        continue  # this is the repeated numeric header row "1 2 3 4 5..."
    vals = re.findall(r"\S+", line)
    if len(vals) != 16:
        continue
    nums = [int(v) for v in vals]
    form20_rows.append({
        "sl_no": nums[0],
        "booth_no": str(nums[1]),
        "votes": nums[2:12],  # 10 values matching CANDIDATES order
    })

print(f"[Form20] parsed {len(form20_rows)} booth rows "
      f"({len(set(r['booth_no'] for r in form20_rows))} distinct booth numbers)")

# ---------------------------------------------------------------------------
# 2. PARSE DATASET B: BOOTH LIST (polling station name + covered streets)
# ---------------------------------------------------------------------------

with open(BOOTHLIST_TXT, encoding="utf-8") as f:
    bl_lines = f.read().split("\n")

SKIP_PATTERNS = (
    "List of Polling Stations",
    "S No Polling Location",
    "Station No in which",
    "women only",
    "Polling Area",
)

booths_b = {}  # booth_no(str) -> {"building": str, "streets": [str,...]}
pending_booth_no = None
pending_station_no = None
pending_building_parts = []
pending_streets = []

NUM_PREFIX_RE = re.compile(r"^\s*(\d+)\s+")


def flush_booth():
    global pending_booth_no, pending_station_no, pending_building_parts, pending_streets
    if pending_station_no is not None:
        building = re.sub(r"\s+", " ", " ".join(pending_building_parts)).strip()
        booths_b[pending_station_no] = {
            "building": building,
            "streets": list(pending_streets),
        }
    pending_booth_no = None
    pending_station_no = None
    pending_building_parts = []
    pending_streets = []


def strip_leading_numbers(text, max_strip=2):
    """Strip up to `max_strip` leading whitespace-delimited integer tokens
    (S No / Station No columns). These are followed by whitespace, unlike a
    street marker such as '3.Foo St' which has no space before the period."""
    nums = []
    for _ in range(max_strip):
        m = NUM_PREFIX_RE.match(text)
        if not m:
            break
        nums.append(m.group(1))
        text = text[m.end():]
    return nums, text


def split_leading_text_and_street(text):
    """Split a line into (leading_building_text, street_text_or_None)."""
    m = re.search(r"(\d{1,3})\.(\S.*)$", text)
    if not m:
        return text.strip(), None
    lead = text[: m.start()].strip()
    street = (m.group(1) + "." + m.group(2)).strip()
    return lead, street


for raw in bl_lines:
    line = raw.rstrip("\n")
    stripped = line.strip()
    if not stripped:
        continue
    if any(p in stripped for p in SKIP_PATTERNS):
        continue

    # A booth's S No / Station No can appear as one or two leading
    # whitespace-delimited integers, sometimes split across two physical
    # lines when the building name text is long. Whichever leading
    # integer(s) we find, the last one is the Station No (= booth_no,
    # the join key). Only trust a leading number as S No/Station No the
    # first time we see it in a block, or if it reaffirms the number
    # already pending -- otherwise it's a stray number embedded in the
    # building text (e.g. "...EAST SIDE ROOM\n1") and must be treated as
    # plain text, not a new booth identifier.
    nums, rest = strip_leading_numbers(stripped)
    if nums and (pending_station_no is None or nums[-1] == pending_station_no):
        pending_booth_no = nums[0]
        pending_station_no = nums[-1]
        lead, street = split_leading_text_and_street(rest)
    else:
        lead, street = split_leading_text_and_street(stripped)

    if lead:
        pending_building_parts.append(lead)
    if street:
        num, txt = street.split(".", 1)
        txt = txt.strip()
        # a street entry on the same physical line as the header can pick up
        # the trailing "All Voters" / "Men Only" / "Women Only" voter-type
        # label from the far-right column -- strip it off.
        txt = re.sub(r"\s+(All\s+Voters|Men\s+Only|Women\s+Only)\s*$", "", txt, flags=re.I).strip()
        if txt.lower().startswith("overseas electors"):
            flush_booth()
        else:
            pending_streets.append(txt)

flush_booth()

print(f"[BoothList] parsed {len(booths_b)} booths")

# ---------------------------------------------------------------------------
# 3. SANITIZE TEXT helper
# ---------------------------------------------------------------------------

def sanitize(text):
    if text is None:
        return ""
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ---------------------------------------------------------------------------
# 4. MERGE, PIVOT, COMPUTE, WRITE CSV
# ---------------------------------------------------------------------------

OUT_COLUMNS = [
    "booth_no", "polling_station_name", "covered_streets",
    "candidate_name", "party_name", "votes_received",
    "total_booth_votes", "vote_share_pct", "is_winner",
]

unmatched_in_a_not_b = []
booth_nos_in_b_used = set()

out_rows = []
for row in form20_rows:
    booth_no = row["booth_no"]
    votes = row["votes"]
    total_booth_votes = sum(votes)

    b_info = booths_b.get(booth_no)
    if b_info is None:
        unmatched_in_a_not_b.append(booth_no)
        polling_station_name = ""
        covered_streets = ""
    else:
        booth_nos_in_b_used.add(booth_no)
        polling_station_name = sanitize(b_info["building"])
        covered_streets = sanitize("; ".join(b_info["streets"]))

    max_votes = max(votes) if total_booth_votes > 0 else -1

    for idx, cand_name, party_name in CANDIDATES:
        v = votes[idx]
        pct = round((v / total_booth_votes) * 100, 2) if total_booth_votes > 0 else 0.0
        is_winner = bool(total_booth_votes > 0 and v == max_votes)
        out_rows.append([
            booth_no,
            polling_station_name,
            covered_streets,
            sanitize(cand_name),
            sanitize(party_name),
            v,
            total_booth_votes,
            pct,
            is_winner,
        ])

unmatched_in_b_not_a = sorted(
    set(booths_b.keys()) - set(r["booth_no"] for r in form20_rows),
    key=lambda x: int(x)
)

with open("madurantakam_35_tableau.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(OUT_COLUMNS)
    writer.writerows(out_rows)

print(f"\nWrote {len(out_rows)} rows to madurantakam_35_tableau.csv")
print(f"Booths in Form20 but missing from BoothList: {sorted(set(unmatched_in_a_not_b), key=lambda x: int(x))}")
print(f"Booths in BoothList but missing from Form20: {unmatched_in_b_not_a}")

# duplicate booth_no check
from collections import Counter
booth_counts = Counter(r["booth_no"] for r in form20_rows)
dupes = {k: v for k, v in booth_counts.items() if v > 1}
print(f"Duplicate booth_no values in Form20: {dupes}")
