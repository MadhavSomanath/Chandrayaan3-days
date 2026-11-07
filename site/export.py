"""Build the explorer's small derived data files from the raw Chandrayaan-3 archive in data/raw/ch3.

    .venv/bin/python site/export.py      # writes site/data.json and site/audio/<day>.json (~10 min)

Only derived numbers leave this script: hourly means, event amplitudes, line ratios, short normalised
waveforms. No raw product is copied.
"""
import base64
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pypdf

from isda import ch3, inventory

warnings.filterwarnings("ignore")
RAW = Path(__file__).parents[1] / "data/raw/ch3"
OUT = Path(__file__).parent
KINDS = {"rover mobility": "rover", "apxs": "apxs", "chaste operation": "ops", "lp deployment": "ops", "uncorrelated": "unc"}
UG = 9.80665e-6  # 1 micro-g in m/s^2
PRE, POST = 30, 120  # event window, seconds before and after the listed start


def events():
    """ILSA's published event list (ILSA_EventIdetification_List_Note.pdf), one row per listed event."""
    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(RAW / "docs/ILSA_EventIdetification_List_Note.pdf").pages)
    rows = {}
    for t, _, what in re.findall(r"(\d{14})_([CU])\s+([A-Za-z ]+?)\s*(?:\(|\n|$)", text):
        what = what.strip().lower()
        kind = next((k for name, k in KINDS.items() if what.startswith(name)), None)
        if kind and t not in rows:  # the PDF lists a few events twice
            rows[t] = kind
    # shortcut: 20230831215006 is listed "_U" but described "Rover Mobility"; the description wins here.
    return pd.DataFrame({"utc": pd.to_datetime(list(rows), format="%Y%m%d%H%M%S", utc=True), "kind": list(rows.values())})


def highpass(z, n):
    """Remove drift slower than n samples. A centred rolling mean, so the window edges don't ring."""
    return z - pd.Series(z).rolling(n, center=True, min_periods=1).mean().to_numpy()


def shake(t):
    """Fine-sensor vertical shaking around one event: amplitude, signal-to-background, 1 s envelope, waveform."""
    try:
        d = ch3.ilsa(RAW / "ilsa", t - pd.Timedelta(seconds=PRE), t + pd.Timedelta(seconds=POST))
    except FileNotFoundError:  # no ILSA file covers this time
        return None
    if len(d) < 1000:
        return None
    rate = len(d) / (PRE + POST)  # timestamps are rounded to 8 ms, so take the rate from the count (~200 Hz)
    z = highpass(d["Z Fine Acceleration"].to_numpy(), int(rate))  # drop drift slower than ~1 s
    secs = ((d.index - d.index[0]).total_seconds()).astype(int).to_numpy()
    env = pd.Series(np.abs(z)).groupby(secs).max().reindex(range(PRE + POST), fill_value=0)
    before, after = env[:PRE - 2], env[PRE:]
    # Background as a level, not a ratio: some quiet stretches are almost flat, which makes ratios explode.
    return {"peak_ug": float(after.max() / UG), "bg_ug": float(np.median(before) / UG),
            "env": (env / UG).round(1).tolist(), "wave": z, "rate": rate}


def stops():
    inv = inventory(RAW / "apxs")
    inv = inv[inv.label.astype(str).str.contains("_lunobs_.*_pha.xml")]
    out = []
    for _, r in inv.sort_values("start").iterrows():
        stop = Path(r.label).parents[1]
        s = ch3.apxs(stop).COUNTS

        def net(e, w=0.06):
            side = (s.loc[e - 3 * w:e - w].mean() + s.loc[e + w:e + 3 * w].mean()) / 2
            peak = s.loc[e - w:e + w]
            return peak.sum() - side * len(peak)
        si = net(1.74)
        out.append({"name": stop.name, "start": r.start.isoformat(), "stop": r.stop.isoformat(),
                    **{el: round(float(net(e) / si), 4) for el, e in
                       {"Mg": 1.25, "Al": 1.49, "Ca": 3.69, "Fe": 6.40, "S": 2.31}.items()}})
    return out


def libs_shots():
    stamps = {re.search(r"_(\d{8}T\d{6})_", p.name).group(1) for p in (RAW / "libs/lib-v2/data/calibrated").glob("*/*_l1")}
    return sorted(pd.to_datetime(sorted(stamps), format="%Y%m%dT%H%M%S", utc=True).strftime("%Y-%m-%dT%H:%M:%SZ"))


def main():
    ev = events()
    print(len(ev), "listed events")
    rows, waves = [], {}
    for t, kind in zip(ev.utc, ev.kind):
        s = shake(t)
        row = {"id": t.strftime("%Y%m%d%H%M%S"), "utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "kind": kind}
        if s:
            row.update(peak_ug=round(s["peak_ug"], 1), bg_ug=round(s["bg_ug"], 2), env=s["env"])
            waves[row["id"]] = s
        rows.append(row)
    print(sum("peak_ug" in r for r in rows), "events have ILSA data")

    # Audio for every event with data, one file per day so the page loads only the day it shows.
    # 8-bit and normalised; the page speeds it up to make it audible.
    audio = {}
    for r in rows:
        if r["id"] in waves:
            z, rate = waves[r["id"]]["wave"], waves[r["id"]]["rate"]
            q = np.clip(np.round(z / max(np.abs(z).max(), 1e-12) * 127), -127, 127).astype(np.int8)
            audio.setdefault(r["utc"][:10], {})[r["id"]] = {"rate": round(rate, 2), "pcm": base64.b64encode(q.tobytes()).decode()}
            r["audio"] = True

    # In the soil from the morning after insertion (commissioning phase) to the end of nominal operations.
    temps = pd.concat([ch3.chaste(RAW / "chaste", phase="commissioning"), ch3.chaste(RAW / "chaste")]).sort_index()
    temps = temps.loc["2023-08-25 11:00":] - 273.15
    hourly = temps.resample("1h").mean().dropna(how="all").round(2)
    plasma = pd.read_csv(OUT.parent / "data/derived/rambha_langmuir.csv", parse_dates=["utc"]).set_index("utc")
    plasma = plasma[["te_k", "ne_m3"]].resample("2h").median().dropna()

    data = {
        "events": rows,
        "chaste": {"depth_mm": [ch3.CHASTE_DEPTH_MM[c] for c in hourly.columns],
                   "utc": hourly.index.strftime("%Y-%m-%dT%H:%MZ").tolist(),
                   "c": [[None if np.isnan(v) else v for v in r] for r in hourly.to_numpy().tolist()]},
        "stops": stops(),
        "libs": libs_shots(),
        "plasma": {"utc": plasma.index.strftime("%Y-%m-%dT%H:%MZ").tolist(),
                   "te_k": plasma.te_k.round(-1).astype(int).tolist(),
                   "ne_cm3": (plasma.ne_m3 / 1e6).round(0).astype(int).tolist()},
    }
    (OUT / "data.json").write_text(json.dumps(data, separators=(",", ":")))
    (OUT / "audio").mkdir(exist_ok=True)
    for day, clips in audio.items():
        (OUT / f"audio/{day}.json").write_text(json.dumps(clips, separators=(",", ":")))
    print(f"data.json {(OUT / 'data.json').stat().st_size / 1e6:.2f} MB;",
          f"{len(audio)} audio files, {sum(f.stat().st_size for f in (OUT / 'audio').glob('*.json')) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
