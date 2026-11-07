"""Round-trip a small synthetic PDS4 product (ILSA-like accelerations) through load() and inventory()."""
import pytest

from isda import inventory, load
from isda.__main__ import main

LABEL = """<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
  <Identification_Area>
    <logical_identifier>urn:isro:isda:test.ilsa:data_raw:sample_0001</logical_identifier>
    <version_id>1.0</version_id>
    <title>Synthetic ILSA-like sample</title>
    <information_model_version>1.15.0.0</information_model_version>
    <product_class>Product_Observational</product_class>
  </Identification_Area>
  <Observation_Area>
    <Time_Coordinates>
      <start_date_time>2023-08-24T00:00:00.000Z</start_date_time>
      <stop_date_time>2023-08-24T00:00:00.010Z</stop_date_time>
    </Time_Coordinates>
  </Observation_Area>
  <File_Area_Observational>
    <File><file_name>sample_0001.csv</file_name></File>
    <Table_Delimited>
      <name>accel</name>
      <offset unit="byte">0</offset>
      <parsing_standard_id>PDS DSV 1</parsing_standard_id>
      <records>3</records>
      <record_delimiter>Carriage-Return Line-Feed</record_delimiter>
      <field_delimiter>Comma</field_delimiter>
      <Record_Delimited>
        <fields>4</fields>
        <groups>0</groups>
        <Field_Delimited><name>utc</name><field_number>1</field_number><data_type>ASCII_Date_Time_YMD_UTC</data_type></Field_Delimited>
        <Field_Delimited><name>x</name><field_number>2</field_number><data_type>ASCII_Real</data_type><unit>m/s**2</unit></Field_Delimited>
        <Field_Delimited><name>y</name><field_number>3</field_number><data_type>ASCII_Real</data_type><unit>m/s**2</unit></Field_Delimited>
        <Field_Delimited><name>z</name><field_number>4</field_number><data_type>ASCII_Real</data_type><unit>m/s**2</unit></Field_Delimited>
      </Record_Delimited>
    </Table_Delimited>
  </File_Area_Observational>
</Product_Observational>
"""
ROWS = ("2023-08-24T00:00:00.000Z,0.001,-0.002,1.62\r\n"
        "2023-08-24T00:00:00.005Z,0.002,-0.001,1.63\r\n"
        "2023-08-24T00:00:00.010Z,0.000,0.000,1.61\r\n")


def make_product(folder):
    (folder / "sample_0001.xml").write_text(LABEL)
    (folder / "sample_0001.csv").write_bytes(ROWS.encode())
    (folder / "notes.xml").write_text("<notes>not a product</notes>")  # must be skipped
    return folder / "sample_0001.xml"


def test_load_table_with_units(tmp_path):
    df = load(make_product(tmp_path))["accel"]
    assert list(df.columns) == ["utc", "x", "y", "z"]
    assert df.z.tolist() == [1.62, 1.63, 1.61]
    assert df.attrs["units"]["z"] == "m/s**2"
    assert df.attrs["lid"].endswith("sample_0001")


def test_inventory_lists_products_only(tmp_path):
    make_product(tmp_path)
    df = inventory(tmp_path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row.objects == "Table_Delimited"
    assert row.missing_files == 0 and row.bytes == len(ROWS)
    assert str(row.start).startswith("2023-08-24 00:00:00")


def test_repeated_field_becomes_array_per_row(tmp_path):
    # LIBS-like: each record holds a time and a 3-channel spectrum (PDS4 group field).
    group = """<Record_Delimited>
        <fields>1</fields>
        <groups>1</groups>
        <Field_Delimited><name>utc</name><field_number>1</field_number><data_type>ASCII_String</data_type></Field_Delimited>
        <Group_Field_Delimited>
          <repetitions>3</repetitions><fields>1</fields><groups>0</groups>
          <Field_Delimited><name>counts</name><field_number>1</field_number><data_type>ASCII_Integer</data_type><unit>DN</unit></Field_Delimited>
        </Group_Field_Delimited>
      </Record_Delimited>"""
    label = LABEL.replace("<records>3</records>", "<records>2</records>")
    label = label[:label.index("<Record_Delimited>")] + group + label[label.index("</Record_Delimited>") + 19:]
    (tmp_path / "spec.xml").write_text(label.replace("sample_0001.csv", "spec.csv"))
    (tmp_path / "spec.csv").write_bytes(b"t0,1,2,3\r\nt1,4,5,6\r\n")
    df = load(tmp_path / "spec.xml")["accel"]
    assert len(df) == 2 and len(df.columns) == 2
    spec_col = df.columns[1]
    assert df[spec_col].iloc[1].tolist() == [4, 5, 6]
    assert df.attrs["units"][spec_col] == "DN"


def test_label_naming_wrong_file_falls_back_to_own_name(tmp_path):
    (tmp_path / "b.xml").write_text(LABEL.replace("sample_0001.csv", "a_twin.csv"))  # a_twin.csv doesn't exist
    (tmp_path / "b.csv").write_bytes(ROWS.encode())
    with pytest.warns(UserWarning, match="using b.csv"):
        df = load(tmp_path / "b.xml")["accel"]
    assert df.z.tolist() == [1.62, 1.63, 1.61]


def test_cli_prints_summary(tmp_path, capsys):
    make_product(tmp_path)
    main(["inventory", str(tmp_path)])
    assert "1 products" in capsys.readouterr().out
