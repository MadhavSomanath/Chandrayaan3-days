"""Chandrayaan-3 surface instruments as tidy, time-indexed DataFrames, built on isda.load().

Folders are the unzipped PRADAN bundles, e.g. ``data/raw/ch3/chaste``.
"""
from pathlib import Path
import re
import warnings

import numpy as np
import pandas as pd

from .pds4 import _label_info, load

# ChaSTE sensor positions from the probe tip, mm (ChaSTE PDS4 User Manual, SPL/TR/04/2024, Table 1).
# Sensor 1 sits 4 mm below the surface when the probe is fully inserted; the rest follow from the tip offsets.
_CHASTE_FROM_TIP_MM = [137, 131, 125, 119, 113, 105, 95, 78, 60, 43]
CHASTE_DEPTH_MM = {i + 1: 4 + 137 - d for i, d in enumerate(_CHASTE_FROM_TIP_MM)}


def _table(label) -> pd.DataFrame:
    tables = [o for o in load(label).values() if isinstance(o, pd.DataFrame)]
    if len(tables) != 1:
        raise ValueError(f"expected one table in {label}, found {len(tables)}")
    return tables[0]


def _series(labels, time_col) -> pd.DataFrame:
    labels = sorted(labels)
    if not labels:
        raise FileNotFoundError("no matching products; check the folder points at an unzipped PRADAN bundle")
    frames, bad = [], []
    for lb in labels:
        try:
            frames.append(_table(lb))
        except ValueError:
            bad.append(lb)
    if not frames:
        raise ValueError(f"none of {len(labels)} products could be read")
    for lb in bad:
        # ISRO archive defect (e.g. ChaSTE 2023-08-28T11): a fixed-width table written unpadded,
        # with a wrong record count. The rows are still valid CSV, so read them as such.
        csv = _label_info(lb)["files"][0]
        frames.append(pd.read_csv(csv, header=None, names=frames[0].columns))
        warnings.warn(f"{lb.name}: file doesn't match its label; read as plain CSV", stacklevel=3)
    df = pd.concat(frames, ignore_index=True)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop(time_col), utc=True, format="ISO8601"), name="utc")
    df.attrs = {"units": frames[0].attrs["units"], "products": len(labels), "repaired": [lb.name for lb in bad]}
    return df.sort_index(kind="stable")


def _utc(t):
    """Timestamp in UTC from a string or a naive/aware datetime; None stays None."""
    if t is None:
        return None
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")


def _between(labels, start, end, stamp):
    """Keep products whose file-name timestamp falls in [start, end); avoids reading 16 GB of ILSA to get an hour."""
    start, end = _utc(start), _utc(end)
    keep = []
    for lb in labels:
        t = _utc(stamp(lb.name))
        if (start is None or t >= start - pd.Timedelta(hours=1)) and (end is None or t < end):
            keep.append(lb)
    return keep


def _clip(df, start, end):
    return df.loc[_utc(start):_utc(end)]


def chaste(folder, phase="nominal_operation") -> pd.DataFrame:
    """Calibrated ChaSTE temperatures (K), one column per sensor 1..10. Depths: CHASTE_DEPTH_MM.

    Values are what the sensors read; ISRO notes they still include heating by the probe itself.
    """
    labels = Path(folder).rglob(f"calibrated/{phase}/**/ch3_cht_cal_*.xml")
    df = _series(labels, "UTC time")
    df.columns = [int(re.search(r"\[(\d+)\]", c).group(1)) + 1 for c in df.columns]
    df.attrs["units"] = {c: "K" for c in df.columns}
    return df


def ilsa(folder, start=None, end=None) -> pd.DataFrame:
    """Calibrated ILSA accelerations (m/s^2), coarse and fine X/Y/Z, plus sensor temperatures (degC).

    Pass ``start``/``end`` (UTC) to read only the 15-minute files you need.
    """
    labels = list(Path(folder).rglob("calibrated/*/ch3_ils_*_d_accln.xml"))
    stamp = lambda name: re.search(r"_(\d{8}t\d{6})", name).group(1).upper()
    df = _series(_between(labels, start, end, stamp), "Time")
    del df.attrs["units"]["Time"]
    return _clip(df, start, end)


def apxs(obs_folder) -> pd.DataFrame:
    """Calibrated APXS X-ray spectrum of one rover stop (e.g. ``.../obs29_mob45_20230902``), indexed by energy (keV)."""
    cal = Path(obs_folder) / "calibrated"
    pha, rsp = list(cal.glob("*_lunobs_*_pha.xml")), list(cal.glob("*_rsp.xml"))
    if len(pha) != 1 or len(rsp) != 1:
        # 5 of the 28 stops hold only on-board calibration-target spectra (precal/poscal), no lunar soil.
        raise FileNotFoundError(f"{Path(obs_folder).name}: no lunar-soil spectrum (or response) in this stop")
    pha, rsp = pha[0], rsp[0]
    spec = load(pha)["data_Spectrum"]
    bounds = load(rsp)["data_Ebounds"]
    spec.index = pd.Index((bounds.E_MIN + bounds.E_MAX).to_numpy() / 2, name="energy_kev")
    return spec.drop(columns="CHANNEL")


RAMBHA_PROBE_AREA_M2 = 4 * np.pi * 0.025**2  # 5 cm diameter sphere (PRADAN RAMBHA-LP FAQ)
_E, _ME = 1.602176634e-19, 9.1093837015e-31


def rambha(folder, start=None, end=None, level="B") -> pd.DataFrame:
    """RAMBHA-LP Langmuir-probe I-V sweeps, averaged per 0.1 V bias step (the manual's noise removal).

    One row per (sweep, bias step), indexed by sweep start (UTC), with columns
    ``channel, probe_res_ohm, gain, saturated, bias_v, current_a``.
    ``level="B"`` gives ISRO's current with photoelectron current removed (nrB); ``"A"`` gives it before removal (nrA).
    ``saturated`` marks sweeps that sat on their maximum, which the manual warns happens on the gain-64 channel.
    """
    sweeps = []
    for ops_label in sorted(Path(folder).rglob(f"raw/*_raw{level}/ch3_rlp_nr{level}_ops_*.xml")):
        ops = _table(ops_label)
        t0 = pd.to_datetime(ops["Start_Time(UTC)"], utc=True, format="ISO8601")
        t1 = pd.to_datetime(ops["End_Time(UTC)"], utc=True, format="ISO8601")
        keep = np.ones(len(ops), bool)
        if start is not None:
            keep &= t1 > _utc(start)
        if end is not None:
            keep &= t0 < _utc(end)
        keep = np.asarray(keep, bool)
        if not keep.any():
            continue
        sci = _table(Path(str(ops_label).replace("_ops_", "_sci_")))
        v, i = sci.iloc[:, 0].to_numpy(), sci.iloc[:, 1].to_numpy()
        sweep_id = np.repeat(np.arange(len(ops)), ops.Number_of_samples.to_numpy())
        raw = pd.DataFrame({"sweep": sweep_id, "bias_v": v.round(1), "current_a": i})[keep[sweep_id]]
        at_max = raw.current_a.eq(raw.groupby("sweep").current_a.transform("max"))
        saturated = at_max.groupby(raw.sweep).mean() > 0.05  # a healthy sweep touches its maximum a handful of times
        iv = raw.groupby(["sweep", "bias_v"], as_index=False).current_a.mean()
        meta = pd.DataFrame({"utc": t0, "channel": ops.ADC_channel, "probe_res_ohm": ops.Probe_Res,
                             "gain": ops["Channel gain"], "saturated": saturated.reindex(ops.index, fill_value=False)})
        sweeps.append(iv.join(meta, on="sweep").drop(columns="sweep"))
    if not sweeps:
        raise FileNotFoundError("no RAMBHA-LP sweeps in that folder/time range")
    df = pd.concat(sweeps, ignore_index=True).set_index("utc").sort_index(kind="stable")
    return df[["channel", "probe_res_ohm", "gain", "saturated", "bias_v", "current_a"]]


def _iv_params(v, i):
    """Floating potential, plasma potential, Te and Ne from one averaged sweep, per the RAMBHA-LP user manual."""
    up = np.flatnonzero((i[:-1] < 0) & (i[1:] >= 0))
    if not len(up):
        return None
    k = up[0]
    vf = v[k] - i[k] * (v[k + 1] - v[k]) / (i[k + 1] - i[k])
    ion = v < vf - 2  # ion saturation region, well below Vf where electron current is negligible
    if ion.sum() < 5:
        return None
    ie = i - np.polyval(np.polyfit(v[ion], i[ion], 1), v)
    m = (v > vf) & (ie > 0)
    x, y = v[m], np.log(ie[m])
    best = None
    for b in range(3, len(x) - 3):  # two-line fit of ln(Ie): retarding region, then electron saturation
        p1, r1 = np.polyfit(x[:b], y[:b], 1, full=True)[:2]
        p2, r2 = np.polyfit(x[b:], y[b:], 1, full=True)[:2]
        err = (r1[0] if len(r1) else 0) + (r2[0] if len(r2) else 0)
        if best is None or err < best[0]:
            best = (err, p1, p2)
    if best is None or best[1][0] <= best[2][0]:
        return None  # no knee
    _, p1, p2 = best
    vs = (p2[1] - p1[1]) / (p1[0] - p2[0])
    te_ev = 1 / p1[0]
    vth = np.sqrt(8 * _E * te_ev / (np.pi * _ME))
    ne = 4 * np.exp(np.polyval(p1, vs)) / (_E * RAMBHA_PROBE_AREA_M2 * vth)
    return {"vf_v": vf, "vs_v": vs, "te_ev": te_ev, "te_k": te_ev * _E / 1.380649e-23, "ne_m3": ne}


def langmuir(sweeps: pd.DataFrame) -> pd.DataFrame:
    """Plasma parameters for each unsaturated sweep from :func:`rambha` (level B).

    First pass following the user manual's method; not yet checked against ISRO's published values.
    """
    rows = []
    # Channel 1 at 20 MOhm has an offset (its sweeps rarely cross zero); across the mission it gives Te of
    # 22,000-34,000 K while the other four settings agree at ~5,000-8,000 K, so it's left out.
    good = sweeps[~sweeps.saturated & ~((sweeps.channel == 1) & (sweeps.probe_res_ohm == 20_000_000))]
    for (t, ch, r, g), s in good.groupby([good.index, "channel", "probe_res_ohm", "gain"], sort=True):
        p = _iv_params(s.bias_v.to_numpy(), s.current_a.to_numpy())
        if p:
            rows.append({"utc": t, "channel": ch, "probe_res_ohm": r, "gain": g, **p})
    return pd.DataFrame(rows).set_index("utc") if rows else pd.DataFrame()


def libs(label) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One calibrated LIBS product as ``(spectra, shots)``, both indexed by shot time.

    ``spectra``: one row per laser shot, columns are wavelengths in nm.
    ``shots``: per-shot metadata (laser energy, delay, integration time...).
    """
    label = Path(label)
    df = _table(label)
    spectra_col = next((c for c in df.columns if "Response_Count" in c), None)
    if spectra_col is None:
        raise ValueError(f"{label.name} is a single-shot subtable; pass the product's main *_l1.xml label")
    # The wavelength axis lives only in the CSV header row, which the label declares as a Header object.
    csv = _label_info(label)["files"][0]
    header = csv.open().readline().strip().split(",")
    n = len(df[spectra_col].iloc[0])
    first = next(i for i, h in enumerate(header) if re.fullmatch(r"\d+(\.\d+)?", h))
    wavelengths = np.array(header[first:first + n], dtype=float)
    spectra = pd.DataFrame(np.vstack(df[spectra_col]), columns=pd.Index(wavelengths, name="wavelength_nm"))
    spectra.index = pd.DatetimeIndex(pd.to_datetime(df["Time"], utc=True, format="ISO8601"), name="utc")
    return spectra, df.drop(columns=[spectra_col, "Time"]).set_index(spectra.index)
