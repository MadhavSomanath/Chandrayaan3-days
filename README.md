# Chandrayaan3-days

Chandrayaan-3's twelve days on the Moon, rebuilt from ISRO's public archive. **[Open the explorer](https://madhavsomanath.github.io/Chandrayaan3-days/)**: pick a day and see how the ground shook, how hot the soil got, what it's made of and what was above it.

Under it is `isda`, a Python package that reads the mission's surface instruments (ILSA, ChaSTE, RAMBHA-LP, APXS, LIBS) from the PDS4 files at the Indian Space Science Data Centre (ISSDC), served through [PRADAN](https://pradan.issdc.gov.in/).

## Install

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
```

## Use

1. Make a free PRADAN account and download Chandrayaan-3 products ("Bulk Download" avoids the ZIP size cap).
2. Unzip them into `data/raw/ch3/` (git-ignored).
3. See what you have:

```bash
.venv/bin/isda inventory data/raw/ch3
```

4. Load any product from its label:

```python
from isda import load
objects = load("data/raw/ch3/.../some_product.xml")   # {object name: DataFrame or ndarray}
df = next(iter(objects.values()))
df.attrs["units"]          # column -> unit, from the PDS4 label
```

5. Or use the Chandrayaan-3 readers, which return tidy, UTC-indexed DataFrames:

```python
from isda import ch3
temps = ch3.chaste("data/raw/ch3/chaste")            # K, sensors 1..10; depths in ch3.CHASTE_DEPTH_MM
quake = ch3.ilsa("data/raw/ch3/ilsa", "2023-08-25 17:00", "2023-08-25 17:05")  # m/s^2, reads only the files needed
xray = ch3.apxs("data/raw/ch3/apxs/apx/data/obs29_mob45_20230902")             # counts vs energy (keV)
spectra, shots = ch3.libs("data/raw/ch3/libs/lib-v2/data/calibrated/20230831/<product>/<product>.xml")  # counts vs nm
sweeps = ch3.rambha("data/raw/ch3/rambha", "2023-08-29 00:10", "2023-08-29 01:10")  # I-V sweeps, 0.1 V steps
plasma = ch3.langmuir(sweeps)   # per sweep: floating/plasma potential (V), Te (eV, K), Ne (m^-3)
```

`ch3.langmuir()` follows the RAMBHA-LP user manual's method. It's a first pass. Over the whole mission (6,533 sweeps, 85 s), the daily median electron temperature is 5,300–7,500 K from 26 Aug on, inside the published 3,000–8,000 K ([Manju et al. 2025, MNRAS](https://doi.org/10.1093/mnras/staf1276)). The daily median density is 3.8–9.7×10⁸ m⁻³, against their 3.8–6×10⁸, so it runs up to ~1.6× high. Likely causes: the fit windows, and ISRO's per-day shift of the zero crossing, which this code doesn't apply. 24–25 Aug (just after probe deployment) give 11,000–18,000 K and need a closer look. Channel 1 at 20 MΩ is excluded: it disagrees with the other four settings by ~4×.

## Notebooks

Two notebooks in `notebooks/` reproduce published Chandrayaan-3 results from the archive. They read from `data/raw/ch3/`.

```bash
.venv/bin/pip install -e '.[notebooks]'
cd notebooks && ../.venv/bin/jupyter nbconvert --to notebook --execute --inplace 01_chaste_temperature_profile.ipynb
```

| Notebook | Reproduces | Result |
|---|---|---|
| `01_chaste_temperature_profile` | ISRO's first temperature-vs-depth plot (27 Aug 2023) | 68 °C at 4 mm (ISRO: ~70 °C). Coldest is −5.6 °C at 98 mm, not ISRO's −10 °C at 80 mm. Gradient 3.9–6.8 °C/cm through 25–31 Aug |
| `02_rover_soil_chemistry` | Vadawale et al. 2024 (*Nature*), Sinha et al. 2025, ISRO's LIBS release (29 Aug 2023) | All 23 APXS soil stops, element ratios within ~1–14 % of each other, sulphur at every stop. LIBS shows Mg (strongest line), O, Al and Si; sulphur doesn't show in a traverse-wide stack |

## Explorer site

`site/` is a one-page explorer of Chandrayaan-3's twelve days on the surface: pick a day on the Sun's arc and see that day's ground shaking (with playback), soil temperatures, soil make-up and plasma.

```bash
.venv/bin/python site/export.py                                  # ~10 min; writes site/data.json and site/audio/<day>.json
.venv/bin/python -m http.server 8765 --directory site            # then open http://localhost:8765
```

`export.py` writes only derived values (hourly means, event peaks, element ratios, short normalised waveforms), never raw products. The day picker places each day at the Sun's height from a fit to the LIBS operations table (local noon 28 Aug 2023 12:58 UTC, peak 19.4°).

`index.html` has no `<!doctype>`/`<html>` wrapper (it's also published as a claude.ai artifact). `.github/workflows/pages.yml` adds one and publishes `site/` to GitHub Pages on every push to `main`.

## Known archive issues

Found while building the readers. Worth reporting to ISSDC (issdc@istrac.gov.in).

- **ChaSTE `ch3_cht_cal_20230828T11`**: rows aren't padded to the fixed width the label declares, and the file has 3,248 records against the label's 3,337. `ch3.chaste()` reads it as plain CSV and warns.
- **ChaSTE calibration**: `ch3_cht_res_temp_cal_coe.xml` points to `ch3_cht_res_temp_cal_coe.csv`, but the file shipped as `ch3_cht_temp_cal_coe.csv`.
- **RAMBHA-LP `nrB` dump 20230831T004808416**: both labels name the `nrA` files. `load()` falls back to the file named like the label and warns.
- **ChaSTE `re-insertion_temperature.xml`**: the label gives the unit as K, but the values are °C (0–37).
- **LIBS wavelengths run long**: in the calibrated products, lines sit ~1.6 nm high in the ultraviolet (Si 251.6, Mg 280.3) and ~0.8 nm high at O 777.2. The user manual's detector-temperature correction isn't applied.
- **ILSA gaps aren't documented**: e.g. no data 18:16–19:31 UTC on 25 Aug 2023 (raw or calibrated), though the event list has rover motion at 18:58. Every `miscellaneous/missing_data_regions` file is empty. Use `isda inventory` start/stop times to see real coverage.

## Data rules

From the PRADAN Chandrayaan-3 disclaimer:

- The data is free for **non-profit scientific use**; ISRO keeps ownership and copyright.
- **Do not copy, lease or loan the raw data** without ISRO/DOS permission. This repo never commits or re-hosts raw files.
- **No commercial use**, including selling data derived from it.
- Any print of the data carries **"© reserved ISRO"**.

Every notebook, figure and page that uses an instrument's data carries that instrument's acknowledgement:

- **ILSA:** We acknowledge the instrument development team - ILSA, Laboratory for Electro-Optics Systems (LEOS), ISRO, Bengaluru. In addition, we acknowledge Chandrayaan-3 Project, Mission, Indian Space Science Data Centre (ISSDC) for data handling, Storage and Archival.
- **ChaSTE:** We acknowledge the use of data from the Chandrayaan-3, of Indian Space Research Organisation (ISRO), available at the PRADAN Portal, Indian Space Science Data Centre (ISSDC). ChaSTE Payload is jointly developed by Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Thiruvananthapuram and Physical Research Laboratory (PRL), Ahmedabad.
- **RAMBHA-LP:** We acknowledge the use of data or results from RAMBHA-LP on Indian Space Research Organization's Chandrayaan-3 lander, which is the first ever lunar landing mission close to the South pole. The above data is archived at the Indian Space Science Data Centre (ISSDC). The lead entity for the development of the RAMBHA-LP payload is Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Thiruvananthapuram.
- **APXS:** We acknowledge the use of data from the APXS instrument on the rover of the Chandrayaan-3 mission of the Indian Space Research Organisation (ISRO), archived at the Indian Space Science Data Centre (ISSDC). APXS experiment is designed and developed by the Physical Research Laboratory (PRL), Ahmedabad with support from Space Applications Center (SAC), Ahmedabad and U.R Rao Satellite Center (URSC), Bangalore.
- **LIBS:** We acknowledge the use of the data recorded by the LIBS instrument aboard the ISRO Pragyan rover, Chandrayaan-3 mission, archived at the Indian Space Science Data Centre (ISSDC). The LIBS instrument is developed at the Laboratory for Electro-Optics Systems (LEOS), Bengaluru with support from U.R.Rao Satellite Centre (URSC), Bengaluru.

## License

Code: MIT. Data: owned by ISRO; see the rules above.
