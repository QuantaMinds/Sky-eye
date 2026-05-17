"""Inspect the downloaded LA County Parcels shapefile archive.

Phase 1.5c — Step 2b. Unzips parcels.zip in-place, prints the archive
contents, dumps the .prj file (CRS detection), and reads the .shp header
for geometry type + feature count. No external GIS libraries required.

Truth-first: this script reads only. Nothing uploaded, nothing modified.
"""
from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

STAGE = Path(r"D:\EYE-Lead\Sky-eye\.stage\lacounty")
ZIP_PATH = STAGE / "parcels.zip"
EXTRACT_DIR = STAGE / "parcels_unzipped"

# Shapefile geometry type codes (from ESRI whitepaper).
_SHP_TYPES = {
    0: "Null", 1: "Point", 3: "PolyLine", 5: "Polygon", 8: "MultiPoint",
    11: "PointZ", 13: "PolyLineZ", 15: "PolygonZ", 18: "MultiPointZ",
    21: "PointM", 23: "PolyLineM", 25: "PolygonM", 28: "MultiPointM",
    31: "MultiPatch",
}


def main() -> int:
    if not ZIP_PATH.exists():
        print(f"ERROR: shapefile archive not found at {ZIP_PATH}")
        print("Browser-download from the LA County Open Data page and save here.")
        return 1
    size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"Archive: {ZIP_PATH}  ({size_mb:.0f} MB)\n")

    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"=== archive contents ===")
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for info in zf.infolist():
            print(f"  {info.file_size:>14,} bytes  {info.filename}")
        print()
        print(f"extracting to {EXTRACT_DIR} ...")
        zf.extractall(EXTRACT_DIR)
    print("done.\n")

    # CRS — find the .prj file (recursively, in case of nested folders)
    prjs = list(EXTRACT_DIR.rglob("*.prj"))
    if not prjs:
        print("WARNING: no .prj file found — CRS unknown")
    else:
        for prj in prjs:
            print(f"=== {prj.name} (CRS WKT) ===")
            text = prj.read_text(encoding="utf-8", errors="replace")
            print(f"  {text[:600]}")
            # Quick fingerprinting
            up = text.upper()
            if "WGS_1984" in up or "4326" in up:
                print("  -> source CRS appears to be WGS84 (4326). No reprojection needed.")
            elif "WEB_MERCATOR" in up or "3857" in up or "102100" in up:
                print("  -> source CRS appears to be Web Mercator (3857/102100).")
            elif "NAD_1983" in up and "STATEPLANE" in up:
                print("  -> source CRS appears to be NAD83 State Plane (probably EPSG:2229 for CA Zone V).")
            else:
                print("  -> source CRS is something else; check the WKT.")
            print()

    # .shp header — feature count + geometry type
    shps = list(EXTRACT_DIR.rglob("*.shp"))
    for shp in shps:
        with shp.open("rb") as f:
            header = f.read(100)
        file_code = struct.unpack(">i", header[0:4])[0]
        file_length_16bit_words = struct.unpack(">i", header[24:28])[0]
        version = struct.unpack("<i", header[28:32])[0]
        shape_type = struct.unpack("<i", header[32:36])[0]
        xmin, ymin, xmax, ymax = struct.unpack("<dddd", header[36:68])
        print(f"=== {shp.name} (header) ===")
        print(f"  file_code:       {file_code}  (expect 9994)")
        print(f"  version:         {version}    (expect 1000)")
        print(f"  geometry_type:   {shape_type} ({_SHP_TYPES.get(shape_type, '?')})")
        print(f"  bounding_box:    [{xmin:.4f}, {ymin:.4f}, {xmax:.4f}, {ymax:.4f}]")
        print(f"  file_size:       {file_length_16bit_words * 2:,} bytes "
              f"(actual: {shp.stat().st_size:,} bytes)")
        # Feature count estimate: each record has an 8-byte header + variable content.
        # The .shx index file has 8 bytes per feature after its own 100-byte header.
        shx = shp.with_suffix(".shx")
        if shx.exists():
            count = (shx.stat().st_size - 100) // 8
            print(f"  feature_count:   {count:,} (from .shx index)")
        print()

    # .dbf — column names (skip values for now)
    dbfs = list(EXTRACT_DIR.rglob("*.dbf"))
    for dbf in dbfs:
        with dbf.open("rb") as f:
            hdr = f.read(32)
            num_records = struct.unpack("<i", hdr[4:8])[0]
            hdr_len = struct.unpack("<h", hdr[8:10])[0]
            n_fields = (hdr_len - 33) // 32
            print(f"=== {dbf.name} ({num_records:,} records, {n_fields} fields) ===")
            for _ in range(n_fields):
                fd = f.read(32)
                if not fd or fd[0:1] == b"\x0D":
                    break
                name = fd[0:11].rstrip(b"\x00").decode("ascii", errors="replace")
                ftype = chr(fd[11])
                flen = fd[16]
                print(f"  {name:20} type={ftype}  len={flen}")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
