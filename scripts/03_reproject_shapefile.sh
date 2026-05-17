#!/usr/bin/env bash
# Phase 1.5c — reproject LA County parcels from EPSG:2229 (NAD83 CA State
# Plane Zone V, feet) to EPSG:4326 (WGS84) and emit GeoJSONSeq (NDJSON) so
# BigQuery can load with --source_format=NEWLINE_DELIMITED_JSON and
# --json_extension=GEOJSON.
#
# Uses the portable GDAL 3.12.1 binary in .tools/gdal/ — no system install
# required. Paths verified against the actual layout 2026-05-17.

set -euo pipefail

GDAL_BASE="/d/EYE-Lead/Sky-eye/.tools/gdal/release-1929-x64-gdal-3-12-1-mapserver-8-6-0/bin"
OGR="$GDAL_BASE/gdal/apps/ogr2ogr.exe"

# Required env: GDAL must find its CRS / proj / data files.
# PATH must include $GDAL_BASE so the .exe loads its companion DLLs.
export GDAL_DATA="$GDAL_BASE/gdal-data"
export PROJ_LIB="$GDAL_BASE/proj9/share"   # NOT proj/SHARE — version 9 lowercase
export PATH="$GDAL_BASE:$PATH"

STAGE="/d/EYE-Lead/Sky-eye/.stage/lacounty"
SHP="$STAGE/parcels_unzipped/LACounty_Parcels_Shapefile/LACounty_Parcels.shp"
OUT="$STAGE/parcels.jsonl"

if [[ ! -f "$SHP" ]]; then
    echo "ERROR: shapefile not found at $SHP"
    echo "Run scripts/02_inspect_shapefile.py first to unzip parcels.zip."
    exit 1
fi

echo "GDAL: $($OGR --version)"
echo "input:  $SHP"
echo "output: $OUT"
echo "reproject EPSG:2229 -> EPSG:4326, format GeoJSONSeq..."

# -progress prints %% to stderr as the file is processed.
# -mapFieldType Date=String avoids the "Date type not natively supported" warning
#   on GeoJSON output (SpatialCha is a date field).
# -lco RFC7946=YES enforces strict GeoJSON (lng/lat order, 7-decimal rounding).
time "$OGR" \
    -f "GeoJSONSeq" \
    -s_srs EPSG:2229 \
    -t_srs EPSG:4326 \
    -mapFieldType Date=String \
    -lco RFC7946=YES \
    -progress \
    "$OUT" \
    "$SHP"

echo
echo "=== output stats ==="
ls -lh "$OUT"
echo "feature count (lines):"
wc -l "$OUT"
echo "first line preview (truncated):"
head -c 400 "$OUT"; echo
