"""`isda inventory <folder>`: summarise a folder of PRADAN downloads."""
import sys

import pandas as pd

from .pds4 import inventory


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "inventory":
        sys.exit("usage: isda inventory <folder>")
    df = inventory(argv[1])
    if df.empty:
        sys.exit(f"No PDS4 product labels found under {argv[1]}")
    with pd.option_context("display.max_rows", None, "display.max_colwidth", 70, "display.width", 200):
        print(df.drop(columns="label").to_string(index=False))
    print(f"\n{len(df)} products, {df.bytes.sum() / 1e6:.1f} MB, "
          f"{df.start.min()} to {df.stop.max()}, {int(df.missing_files.sum())} missing data files")


if __name__ == "__main__":
    main()
