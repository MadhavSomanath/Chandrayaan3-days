"""Build the chatbot's knowledge base from this project's own content.

    python3 chat/build_corpus.py      # writes chat/worker/src/corpus.json

Sources: the explorer page's text, site/data.json turned into plain-language facts (one sheet per day
plus a mission summary), the README, and the two notebooks. Standard library only.
"""
import json
import re
import statistics as st
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parents[1]
SITE = "https://madhavsomanath.github.io/Chandrayaan3-days/"
REPO = "https://github.com/MadhavSomanath/Chandrayaan3-days/blob/main/"
KINDS = {"unc": "no known cause", "rover": "rover driving", "apxs": "APXS at work", "ops": "lander at work"}
ELEMENTS = ["Mg", "Al", "Ca", "Fe", "S"]
docs = []


def add(title, text, url, kind):
    text = " ".join(text.split())
    if len(text) > 40:
        docs.append({"id": len(docs), "title": title, "kind": kind, "url": url, "text": text})


def split_words(text, n=220):
    """Long sections become ~220-word pieces so each retrieved chunk stays focused."""
    w = text.split()
    return [" ".join(w[i:i + n]) for i in range(0, len(w), n)] or [""]


# ---------- 1. the page's own words ----------
class PageText(HTMLParser):
    """Collect visible text under each h1/h2, skipping <style>, <script> and the empty JS-filled slots."""
    def __init__(self):
        super().__init__()
        self.sections, self.skip, self.head, self.in_head = [], 0, None, False

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        elif tag in ("h1", "h2"):
            self.in_head, self.head = True, ""
            self.sections.append(["", []])

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip -= 1
        elif tag in ("h1", "h2"):
            self.in_head = False

    def handle_data(self, data):
        if self.skip or not self.sections:
            return
        if self.in_head:
            self.sections[-1][0] += data
        else:
            self.sections[-1][1].append(data)


page = PageText()
page.feed((ROOT / "site/index.html").read_text())
for head, parts in page.sections:
    head = " ".join(head.split())
    for i, piece in enumerate(split_words(" ".join(parts))):
        add(f"Explorer page: {head}" + (f" ({i + 1})" if i else ""), piece, SITE, "page")

# ---------- 2. data.json as plain-language facts ----------
D = json.loads((ROOT / "site/data.json").read_text())
t = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
days = [(datetime(2023, 8, 23) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13)]
tag = lambda k: ("aug" if k[5:7] == "08" else "sep") + k[8:]
long = lambda k: datetime.strptime(k, "%Y-%m-%d").strftime("%-d %B %Y")
ev = D["events"]
# the page's own one-line notes for key days (landing, probe insertion, hop, sleep)
html = (ROOT / "site/index.html").read_text()
notes = dict(re.findall(r'"(2023-\d\d-\d\d)": "([^"]+)"', html.split("const NOTES", 1)[1].split("};", 1)[0]))
med = {el: st.median(s[el] for s in D["stops"]) for el in ELEMENTS}
kind_med = {k: st.median(e["peak_ug"] for e in ev if e["kind"] == k and e.get("peak_ug") is not None) for k in KINDS}

for n, k in enumerate(days):
    lines = [f"{long(k)} is {'landing day' if n == 0 else f'day {n} after landing'} of Chandrayaan-3's surface mission at Shiv Shakti point."]
    if k in notes:
        lines.append("What happened: " + notes[k])
    es = [e for e in ev if e["utc"].startswith(k)]
    if es:
        counts = {KINDS[x]: sum(e["kind"] == x for e in es) for x in KINDS if any(e["kind"] == x for e in es)}
        lines.append(f"ILSA seismometer: {len(es)} listed ground signals (" + ", ".join(f"{v} {c}" for c, v in counts.items()) + ").")
        meas = [e for e in es if e.get("peak_ug") is not None]
        if meas:
            top = max(meas, key=lambda e: e["peak_ug"])
            lines.append(f"The strongest reached {top['peak_ug']:g} micro-g (µg) at {top['utc'][11:16]} UTC, cause: {KINDS[top['kind']]}.")
        if len(meas) < len(es):
            lines.append(f"{len(es) - len(meas)} of the signals have no seismometer data in the archive.")
    else:
        lines.append("ILSA seismometer: no ground signals are listed for this day.")

    rows = [(u, c) for u, c in zip(D["chaste"]["utc"], D["chaste"]["c"]) if u.startswith(k)]
    top_t = [c[0] for _, c in rows if c[0] is not None]
    deep_t = [c[-1] for _, c in rows if c[-1] is not None]
    if top_t:
        lines.append(f"ChaSTE soil temperature: at 4 mm depth between {min(top_t):.1f} and {max(top_t):.1f} °C; "
                     f"at 98 mm between {min(deep_t):.1f} and {max(deep_t):.1f} °C (hourly means).")
    else:
        lines.append("ChaSTE soil temperature: no in-soil readings shown for this day.")

    stops = [s for s in D["stops"] if s["start"].startswith(k)]
    for s in stops:
        devs = ", ".join(f"{el} {(s[el] / med[el] - 1) * 100:+.0f}%" for el in ELEMENTS)
        lines.append(f"APXS rover soil reading {s['name']} from {s['start'][11:16]} to {s['stop'][11:16]} UTC. "
                     f"Element line ratios relative to silicon: " + ", ".join(f"{el} {s[el]}" for el in ELEMENTS) +
                     f". Difference from the median of all 23 stops: {devs}.")
    if not stops:
        lines.append("APXS: the rover made no X-ray soil reading this day.")
    libs = [x for x in D["libs"] if x.startswith(k)]
    if libs:
        lines.append(f"LIBS laser: {len(libs)} laser measurement time(s) this day.")

    pi = [i for i, u in enumerate(D["plasma"]["utc"]) if u.startswith(k)]
    if pi:
        te = st.median(D["plasma"]["te_k"][i] for i in pi)
        ne = st.median(D["plasma"]["ne_cm3"][i] for i in pi)
        lines.append(f"RAMBHA-LP plasma: median electron temperature {te:,.0f} K and median electron density {ne:,.0f} per cm³ "
                     f"({len(pi)} two-hour medians).")
    else:
        lines.append("RAMBHA-LP plasma: no measurements this day.")
    add(f"Data for {long(k)}", " ".join(lines), SITE + "#" + tag(k), "data")

# mission-wide summary
hot = max((c[0], u) for u, c in zip(D["chaste"]["utc"], D["chaste"]["c"]) if c[0] is not None and u < "2023-09-01")
odd = min(D["stops"], key=lambda s: s["Mg"] / med["Mg"])
summary = {  # one short chunk per topic, so each is easy to retrieve
    "moonquakes (ILSA seismometer)": [
        f"Across the mission the ILSA event list has {len(ev)} ground signals: " +
        ", ".join(f"{sum(e['kind'] == x for e in ev)} {KINDS[x]}" for x in KINDS) + ".",
        f"{sum(e.get('peak_ug') is not None for e in ev)} of them have seismometer data in the archive.",
        "Typical (median) peak shaking by cause: " + ", ".join(f"{KINDS[x]} {kind_med[x]:.1f} µg" for x in KINDS) + "."],
    "soil temperature (ChaSTE)": [
        f"The hottest soil reading, the highest soil temperature of the mission, was {hot[0]:.1f} °C at 4 mm deep at {hot[1]} "
        "(before the 1 September heating experiments).",
        f"ChaSTE thermometer depths (mm): {', '.join(map(str, D['chaste']['depth_mm']))}."],
    "soil chemistry (APXS)": [
        f"The rover's APXS made {len(D['stops'])} soil readings; median line ratios to silicon: " + ", ".join(f"{el} {med[el]:.4f}" for el in ELEMENTS) + ".",
        f"The odd one out is {odd['name']}, with Mg ratio {odd['Mg']} against a median of {med['Mg']:.4f}."],
    "plasma (RAMBHA-LP)": [
        f"Plasma electron temperature over the mission ranges {min(D['plasma']['te_k']):,} to {max(D['plasma']['te_k']):,} K; "
        f"electron density {min(D['plasma']['ne_cm3']):,} to {max(D['plasma']['ne_cm3']):,} per cm³ (two-hour medians)."],
}
for topic, lines in summary.items():
    add(f"Data: whole mission, {topic}", " ".join(lines), SITE, "data")

# ---------- 3. README, by section ----------
readme = (ROOT / "README.md").read_text()
for block in re.split(r"\n(?=#{2,3} )", readme):
    head = block.splitlines()[0].lstrip("# ").strip()
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)|<[^>]+>|```mermaid.*?```", " ", block, flags=re.S)
    for i, piece in enumerate(split_words(body)):
        add(f"README: {head}" + (f" ({i + 1})" if i else ""), piece, REPO + "README.md", "readme")

# ---------- 4. notebooks: markdown plus printed results, by section ----------
for nb in sorted((ROOT / "notebooks").glob("*.ipynb")):
    cells = json.loads(nb.read_text())["cells"]
    title, sections = nb.stem, [["Introduction", []]]
    for c in cells:
        src = "".join(c["source"])
        if c["cell_type"] == "markdown":
            m = re.match(r"#{1,2} (.+)", src)
            if m and src.startswith("## "):
                sections.append([m.group(1), []])
            elif m:
                title = m.group(1)
            sections[-1][1].append(src)
        else:
            out = "".join("".join(o.get("text", "")) for o in c.get("outputs", []) if o.get("output_type") == "stream")
            if out.strip():
                sections[-1][1].append("Result: " + out)
    for head, parts in sections:
        for i, piece in enumerate(split_words(" ".join(parts))):
            add(f"Notebook '{title}': {head}" + (f" ({i + 1})" if i else ""), piece, REPO + "notebooks/" + nb.name, "notebook")

out = ROOT / "chat/worker/src/corpus.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(docs, ensure_ascii=False, indent=0))
print(f"{len(docs)} chunks -> {out.relative_to(ROOT)} ({out.stat().st_size / 1e3:.0f} kB)")
for kind in ("page", "data", "readme", "notebook"):
    print(f"  {kind}: {sum(d['kind'] == kind for d in docs)}")
