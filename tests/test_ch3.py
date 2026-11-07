"""Chandrayaan-3 readers: synthetic checks of the shared logic, plus real-data checks when the PRADAN data is present."""
from pathlib import Path

import pandas as pd
import pytest

from isda import ch3
from test_pds4 import LABEL, ROWS

RAW = Path(__file__).parent.parent / "data/raw/ch3"
real = pytest.mark.skipif(not RAW.exists(), reason="Chandrayaan-3 data not downloaded")


def test_chaste_depths_follow_manual():
    # Sensor 1 is 4 mm deep; sensor 10 sits 94 mm further up the probe from the tip side.
    assert ch3.CHASTE_DEPTH_MM[1] == 4 and ch3.CHASTE_DEPTH_MM[10] == 98
    assert list(ch3.CHASTE_DEPTH_MM.values()) == sorted(ch3.CHASTE_DEPTH_MM.values())


def test_series_repairs_product_that_breaks_its_label(tmp_path):
    for name, rows in [("a", ROWS), ("b", ROWS.replace("0.001", "not-a-number"))]:
        (tmp_path / f"{name}.xml").write_text(LABEL.replace("sample_0001.csv", f"{name}.csv"))
        (tmp_path / f"{name}.csv").write_bytes(rows.encode())
    with pytest.warns(UserWarning, match="read as plain CSV"):
        df = ch3._series(tmp_path.glob("*.xml"), "utc")
    assert len(df) == 6 and df.attrs["repaired"] == ["b.xml"]
    assert df.index.is_monotonic_increasing


def test_langmuir_recovers_known_plasma():
    import numpy as np
    te, ne, vs = 0.5, 5e8, -2.0  # eV, m^-3, V
    v = np.round(np.arange(-12, 12.01, 0.1), 1)
    vth = np.sqrt(8 * ch3._E * te / (np.pi * ch3._ME))
    i0 = 0.25 * ne * ch3._E * ch3.RAMBHA_PROBE_AREA_M2 * vth  # electron current at the plasma potential
    ie = np.where(v < vs, i0 * np.exp((v - vs) / te), i0 * np.exp(0.08 * (v - vs)))
    i = ie + (-5e-9 + 2e-10 * v)  # plus a sloped ion saturation current
    p = ch3._iv_params(v, i)
    assert p["te_ev"] == pytest.approx(te, rel=0.05)
    assert p["ne_m3"] == pytest.approx(ne, rel=0.1)
    assert p["vs_v"] == pytest.approx(vs, abs=0.15)
    assert p["vf_v"] < vs


@real
def test_real_rambha_hour_is_physical():
    sweeps = ch3.rambha(RAW / "rambha", "2023-08-29 00:10", "2023-08-29 01:10")
    assert sweeps.bias_v.min() == -12 and sweeps.bias_v.max() == 12
    assert sweeps[(sweeps.channel == 2) & (sweeps.probe_res_ohm == 20_000_000)].saturated.all()  # manual's gain-64 caveat
    p = ch3.langmuir(sweeps)
    assert 3000 < p.te_k.median() < 8000  # Manju et al. 2025 report 3,000-8,000 K
    assert 1e8 < p.ne_m3.median() < 3e9   # same order as their 3.8-6e8 m^-3


@real
def test_real_chaste_covers_mission():
    df = ch3.chaste(RAW / "chaste")
    assert list(df.columns) == list(range(1, 11))
    assert df.index.min().day == 25 and df.index.max().day == 2
    assert 250 < df[1].median() < 360  # kelvin, lunar day near the south pole


@real
def test_real_ilsa_window_and_gap():
    df = ch3.ilsa(RAW / "ilsa", "2023-08-25 17:00", "2023-08-25 17:01")
    assert 10_000 < len(df) < 20_000  # ~1 minute at ILSA's sample rate
    assert ch3.ilsa(RAW / "ilsa", "2023-08-25 18:58", "2023-08-25 19:00").empty  # archive gap 18:16-19:31


@real
def test_real_apxs_iron_line():
    spec = ch3.apxs(next((RAW / "apxs/apx/data").glob("obs29*")))
    fe = spec.COUNTS.loc[6.2:6.6]
    assert abs(fe.idxmax() - 6.40) < 0.1  # Fe K-alpha


@real
def test_real_libs_wavelength_axis():
    label = sorted((RAW / "libs/lib-v2/data/calibrated").glob("*/*/*.xml"))[0]
    spectra, shots = ch3.libs(label)
    assert spectra.shape[1] == 2094 and len(spectra) == len(shots)
    assert spectra.columns[0] == pytest.approx(164.35) and spectra.columns[-1] == pytest.approx(878.26)


def test_utc_accepts_strings_and_aware_times():
    from isda.ch3 import _utc
    want = pd.Timestamp("2023-08-26 14:40", tz="UTC")
    assert _utc("2023-08-26 14:40") == want
    assert _utc(pd.Timestamp("2023-08-26 20:10", tz="Asia/Kolkata")) == want
    assert _utc(None) is None
