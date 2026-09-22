import re
import csv
import subprocess
from pathlib import Path

FORM20_PDF = "AC101_form20.pdf"
BOOTHLIST_PDF = "AC101_boothwise.pdf"
FORM20_TXT = "form20_table.txt"
BOOTHLIST_TXT = "boothwise_table.txt"
OUT_CSV = "dharapuram_101_tableau.csv"


def ensure_text_extracted(pdf_path, txt_path, mode_flag):
    if not Path(txt_path).exists():
        subprocess.run(["pdftotext", mode_flag, pdf_path, txt_path], check=True)


ensure_text_extracted(FORM20_PDF, FORM20_TXT, "-table")
# -table (not -layout) is required here: on several pages -layout's column
# widths collide and interleave the page-header's decorative "1 2 3 4 5"
# column-index labels with the real Sl.No sequence, corrupting booth numbers.
ensure_text_extracted(BOOTHLIST_PDF, BOOTHLIST_TXT, "-table")

# ---------------------------------------------------------------------------
# 1. PARSE DATASET A: FORM 20 (booth-level candidate votes)
# ---------------------------------------------------------------------------
#
# This constituency's Form 20 lists only candidate surnames -- no party
# affiliation column exists anywhere in the PDF (unlike AC035's form, which
# had party names inline). party_name is left blank below rather than
# guessed; see the printed note at the end of this script.
#
# Column layout (verified against the form's own "Total EVM Votes" /
# "Total Polled" summary rows at the bottom of the sheet -- every candidate
# column sum plus NOTA matches those totals exactly, and
# valid_subtotal + NOTA == grand total on every single booth row):
#   SL.NO, Polling Station No, <9 candidate vote counts>,
#   Total of Valid Votes (= sum of the 9 candidates), Rejected, NOTA,
#   Total (= valid + NOTA), Tendered

CANDIDATES = [
    # (column_index_in_row, candidate_name, party_name)
    (0, "Indirani.T", ""),
    (1, "Sathyabama.P", ""),
    (2, "Dhivya", ""),
    (3, "Gowri Chitra", ""),
    (4, "Ananthi.S", ""),
    (5, "Indhirani.C", ""),
    (6, "Gowri.P", ""),
    (7, "Mohanraj.M", ""),
    (8, "Rohini.S", ""),
    (9, "NOTA", "NOTA"),
]

with open(FORM20_TXT, encoding="utf-8") as f:
    form20_lines = f.read().split("\n")

form20_rows = []  # list of dict: sl_no, booth_no, candidate votes[10] (9 candidates + NOTA)
for raw in form20_lines:
    line = raw.rstrip("\n")
    m = re.match(r"^(\d+)\s+(\d+)\s", line)
    if not m:
        continue
    sl_no, booth_no = m.group(1), m.group(2)
    vals = re.findall(r"\S+", line)
    if len(vals) != 16:
        continue
    nums = [int(v) for v in vals]
    cands = nums[2:11]              # 9 named candidates
    valid, rejected, nota, total, tendered = nums[11:16]
    if sum(cands) != valid or total != valid + nota:
        continue  # not a real per-booth data row (e.g. a stray header/total line)
    form20_rows.append({
        "sl_no": nums[0],
        "booth_no": str(nums[1]),
        "votes": cands + [nota],     # 10 values matching CANDIDATES order (9 candidates + NOTA)
    })

print(f"[Form20] parsed {len(form20_rows)} booth rows "
      f"({len(set(r['booth_no'] for r in form20_rows))} distinct booth numbers)")

# ---------------------------------------------------------------------------
# 2. PARSE DATASET B: BOOTHWISE LIST (polling station name + covered streets)
# ---------------------------------------------------------------------------
#
# Different format from AC035's Booth List: each polling area is prefixed
# "(N) - " instead of "N.", and there is no explicit "999.Overseas Electors"
# terminator -- a booth's block simply ends where the next booth's Sl.No /
# Polling Station No header line begins.

with open(BOOTHLIST_TXT, encoding="utf-8") as f:
    bl_lines = f.read().split("\n")

SKIP_PATTERNS = (
    "List of Polling Stations",
    "Sl.No",
    "Location and name",
    "Polling Areas",
    "Voters or Men only",
    "or Women only",
    "Page Number",
    "Parliamentary Constituency",
)

booths_b = {}  # booth_no(str) -> {"building": str, "streets": [str,...]}
pending_booth_no = None
pending_station_no = None
pending_building_parts = []
pending_streets = []

NUM_PREFIX_RE = re.compile(r"^\s*(\d+)\s+")
AREA_RE = re.compile(r"\(\s*(\d{1,3})\s*\)\s*-\s*(\S.*)$")


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
    (Sl.No / Polling station No columns) -- these are followed by whitespace,
    unlike an area marker such as '(3) - Foo Village' which starts with '('."""
    nums = []
    for _ in range(max_strip):
        m = NUM_PREFIX_RE.match(text)
        if not m:
            break
        nums.append(m.group(1))
        text = text[m.end():]
    return nums, text


def split_leading_text_and_area(text):
    """Split a line into (leading_building_text, area_text_or_None)."""
    m = AREA_RE.search(text)
    if not m:
        return text.strip(), None
    lead = text[: m.start()].strip()
    area = m.group(2).strip()
    return lead, area


# Clean, non-blank/non-boilerplate content lines only.
content_lines = []
for raw in bl_lines:
    stripped = raw.rstrip("\n").strip()
    if not stripped:
        continue
    if any(p in stripped for p in SKIP_PATTERNS):
        continue
    tokens = stripped.split()
    if tokens and all(t.isdigit() for t in tokens):
        continue  # stray column-number label line ("1", "2 3 4 5", ...) from the page header
    content_lines.append(stripped)

def line_header_nums(stripped, against):
    """Leading number tokens on a line (<=3 digits), if any differ from `against`."""
    nums, _ = strip_leading_numbers(stripped)
    return [n for n in nums if len(n) <= 3]


def apply_line(lead, area):
    global pending_building_parts, pending_streets
    if lead:
        pending_building_parts.append(lead)
    if area:
        area = re.sub(r"\s+(All\s+Voters|Men\s+Only|Women\s+Only)\s*$", "", area, flags=re.I).strip()
        if area:
            pending_streets.append(area)


# Tableau centers each booth's multi-line building-name cell vertically
# within its row-span, so a booth's OWN opening content line (building-name
# lead, sometimes together with its first area) commonly renders on the
# physical line immediately BEFORE that booth's own Sl.No/Polling No header
# line -- e.g. booth 2's "Panchayat Union Middle School, (1) - ...
# Nanjchappakoundanpudur" appears right before its "2  2  ..." header. Using
# pure sequential order without lookahead attributes that line to whichever
# booth is still open (wrong, off by one). We use a 1-line lookahead: any
# non-header content line immediately followed by a NEW header belongs to
# that upcoming booth, not the currently pending one.
pre_header_buffer = []

for i, stripped in enumerate(content_lines):
    nums, rest = strip_leading_numbers(stripped)
    nums = [n for n in nums if len(n) <= 3]
    is_continuation_header = bool(nums) and pending_station_no is not None and nums[-1] == pending_station_no
    is_new_header = bool(nums) and not is_continuation_header

    if is_new_header:
        flush_booth()
        pending_booth_no = nums[0]
        pending_station_no = nums[-1]
        # attach the buffered pre-header line(s) FIRST, now that this booth is open
        for buffered in pre_header_buffer:
            apply_line(*split_leading_text_and_area(buffered))
        pre_header_buffer = []
        apply_line(*split_leading_text_and_area(rest))
        continue

    if is_continuation_header:
        apply_line(*split_leading_text_and_area(rest))
        continue

    # No header number on this line. If the VERY NEXT content line is a new
    # header, this line is that upcoming booth's pre-header opener -- buffer
    # it instead of attaching it to whatever booth is still open.
    next_line = content_lines[i + 1] if i + 1 < len(content_lines) else None
    next_is_new_header = False
    if next_line is not None:
        next_nums = line_header_nums(next_line, pending_station_no)
        next_is_new_header = bool(next_nums) and (pending_station_no is None or next_nums[-1] != pending_station_no)
    if next_is_new_header:
        pre_header_buffer.append(stripped)
        continue
    if pending_station_no is None:
        continue  # nothing open yet and no header follows -- unattributable
    apply_line(*split_leading_text_and_area(stripped))

flush_booth()

print(f"[Boothwise] parsed {len(booths_b)} booths")

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
empty_streets_booths = []

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
        polling_station_name = sanitize(b_info["building"])
        covered_streets = sanitize("; ".join(b_info["streets"]))
        if not covered_streets:
            empty_streets_booths.append(booth_no)

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

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(OUT_COLUMNS)
    writer.writerows(out_rows)

print(f"\nWrote {len(out_rows)} rows to {OUT_CSV}")
print(f"Booths in Form20 but missing from Boothwise list: {sorted(set(unmatched_in_a_not_b), key=lambda x: int(x))}")
print(f"Booths in Boothwise list but missing from Form20: {unmatched_in_b_not_a}")
if empty_streets_booths:
    print(f"Booths matched but with NO covered_streets recovered (PDF-extraction quirk -- "
          f"single-area booths where the '(1) -' area marker was lost in table extraction; "
          f"check these manually against the source PDF): {sorted(set(empty_streets_booths), key=lambda x: int(x))}")

from collections import Counter
booth_counts = Counter(r["booth_no"] for r in form20_rows)
dupes = {k: v for k, v in booth_counts.items() if v > 1}
print(f"Duplicate booth_no values in Form20: {dupes}")
print("\nNOTE: AC101_form20.pdf does not list party affiliations anywhere in the "
      "document (unlike AC035's Form 20) -- party_name is left blank for all "
      "candidates except NOTA. Fill it in manually if you have the party list.")
