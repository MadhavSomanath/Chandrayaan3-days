"""Load PDS4 products into pandas, and list what a download folder contains."""
from pathlib import Path
import warnings
import xml.etree.ElementTree as ET

import pandas as pd
import pds4_tools

NS = {"pds": "http://pds.nasa.gov/pds4/pds/v1"}
# Data-object element names that sit inside each File_Area_Observational.
OBJECT_TYPES = ("Table_Character", "Table_Binary", "Table_Delimited",
                "Array", "Array_1D", "Array_2D", "Array_2D_Image", "Array_3D", "Array_3D_Spectrum")


def _text(root, path):
    el = root.find(path, NS)
    return el.text.strip() if el is not None and el.text else None


def _label_info(label: Path) -> dict:
    root = ET.parse(label).getroot()
    files, objects = [], []
    for area in root.findall(".//pds:File_Area_Observational", NS):
        name = _text(area, "pds:File/pds:file_name")
        if name:
            files.append(label.parent / name)
        objects += [child.tag.split("}")[1] for child in area
                    if child.tag.split("}")[1] in OBJECT_TYPES]
    return {
        "lid": _text(root, "pds:Identification_Area/pds:logical_identifier"),
        "title": _text(root, "pds:Identification_Area/pds:title"),
        "start": _text(root, ".//pds:Time_Coordinates/pds:start_date_time"),
        "stop": _text(root, ".//pds:Time_Coordinates/pds:stop_date_time"),
        "objects": ", ".join(objects),
        "files": files,
    }


def inventory(folder) -> pd.DataFrame:
    """One row per PDS4 product label found under `folder` (recursively)."""
    rows = []
    for label in sorted(Path(folder).rglob("*.xml")):
        try:
            info = _label_info(label)
        except ET.ParseError:
            continue
        if not info["lid"]:  # not a PDS4 product label (e.g. a schema or stray XML)
            continue
        files = info.pop("files")
        info["label"] = str(label)
        info["bytes"] = sum(f.stat().st_size for f in files if f.exists())
        info["missing_files"] = sum(not f.exists() for f in files)
        rows.append(info)
    df = pd.DataFrame(rows, columns=["lid", "title", "start", "stop", "objects", "bytes", "missing_files", "label"])
    for col in ("start", "stop"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce", format="ISO8601")
    return df


def load(label) -> dict:
    """Read every data object in a PDS4 product.

    Tables come back as DataFrames with ``df.attrs["units"]`` mapping column -> unit.
    A field that repeats within a record (e.g. a LIBS spectrum) becomes one column holding
    a numpy array per row. Arrays (images, cubes) come back as numpy arrays.
    Keys are the object names.
    """
    label = Path(label)
    info = _label_info(label)
    out = {}
    for struct in pds4_tools.read(str(label), quiet=True, lazy_load=True):
        own = label.with_suffix(Path(struct.parent_filename).suffix)
        if not Path(struct.parent_filename).exists() and own.exists():
            # ISRO archive defect (e.g. RAMBHA nrB 20230831T004808416 names its nrA twin): use the file named like the label.
            warnings.warn(f"{label.name}: label names missing {Path(struct.parent_filename).name}; using {own.name}", stacklevel=2)
            struct.parent_filename = str(own)
        if struct.is_table():
            # struct.fields lines up 1:1 with the structured array's columns (group members included).
            names = struct.data.dtype.names
            # Binary tables arrive big-endian; pandas/numpy reductions need native byte order.
            cols = {n: struct[n].astype(struct[n].dtype.newbyteorder("=")) for n in names}
            df = pd.DataFrame({n: list(c) if c.ndim > 1 else c for n, c in cols.items()})
            df.attrs["units"] = {n: f.meta_data.get("unit") for n, f in zip(names, struct.fields)}
            df.attrs.update(lid=info["lid"], start=info["start"], stop=info["stop"])
            out[struct.id] = df
        elif struct.is_array():
            out[struct.id] = struct.data
    return out
