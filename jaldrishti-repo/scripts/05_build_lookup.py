"""
Build risk lookup table for JalDrishti.

Pipeline:
    road network
        +
    susceptibility raster
        +
    rainfall multiplier
        =
    time-varying risk lookup JSON

Output:
    data/processed/risk_lookup_koramangala.json
"""

import json
import math
from pathlib import Path
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import rowcol
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString


# ============================================================
# CONFIGURATION
# ============================================================

WARD_ID = "koramangala"

ROAD_FILE = Path("data/processed/roads_ward.gpkg")
SUSCEPTIBILITY_FILE = Path("data/processed/susceptibility.tif")
RAINFALL_FILE = Path("data/processed/rainfall_multiplier.csv")

OUTPUT_FILE = Path(
    f"data/processed/risk_lookup_{WARD_ID}.json"
)

# Maximum number of sample points along each road
NUM_SAMPLES = 20

# Risk-to-depth demo conversion
MAX_DEPTH_CM = 30.0

# Confidence used for this GIS-only lookup
CONFIDENCE = 0.6


# ============================================================
# HELPERS
# ============================================================

def extract_linestring(geometry):
    """
    Convert LineString/MultiLineString geometry into a usable
    LineString.

    For MultiLineString, the longest component is selected.
    """

    if geometry is None or geometry.is_empty:
        return None

    if isinstance(geometry, LineString):
        return geometry

    if isinstance(geometry, MultiLineString):

        if len(geometry.geoms) == 0:
            return None

        longest = max(
            geometry.geoms,
            key=lambda line: line.length
        )

        return longest

    return None


def geometry_to_lonlat(geometry, transformer):
    """
    Convert a LineString from projected CRS to longitude/latitude.

    Returns:
        [[lon, lat], [lon, lat], ...]
    """

    line = extract_linestring(geometry)

    if line is None:
        return None

    coordinates = []

    for coordinate in line.coords:

        # Some geometries can contain Z values.
        # We only need X and Y.
        x = coordinate[0]
        y = coordinate[1]

        lon, lat = transformer.transform(x, y)

        coordinates.append([
            round(float(lon), 6),
            round(float(lat), 6)
        ])

    return coordinates


def sample_raster_along_line(line, raster):
    """
    Sample susceptibility raster along a road.

    Returns the mean valid susceptibility value.
    """

    if line is None or line.is_empty:
        return None

    values = []

    length = line.length

    if length == 0:
        points = [line.interpolate(0)]
    else:
        points = [
            line.interpolate(
                length * i / (NUM_SAMPLES - 1)
            )
            for i in range(NUM_SAMPLES)
        ]

    for point in points:

        x = point.x
        y = point.y

        try:
            row, col = rowcol(
                raster.transform,
                x,
                y
            )

            if (
                0 <= row < raster.height
                and 0 <= col < raster.width
            ):

                value = raster.read(
                    1,
                    window=((row, row + 1), (col, col + 1)),
                    masked=True
                )[0, 0]

                if not np.ma.is_masked(value):
                    value = float(value)

                    if math.isfinite(value):
                        values.append(value)

        except Exception:
            continue

    if not values:
        return None

    return float(np.mean(values))


# ============================================================
# MAIN
# ============================================================

print("=" * 60)
print("BUILDING RISK LOOKUP")
print("=" * 60)


# ============================================================
# CHECK INPUT FILES
# ============================================================

for file_path in [
    ROAD_FILE,
    SUSCEPTIBILITY_FILE,
    RAINFALL_FILE
]:

    if not file_path.exists():

        raise FileNotFoundError(
            f"Required file not found: {file_path}"
        )


# ============================================================
# READ ROAD NETWORK
# ============================================================

print("\nReading road network...")

roads = gpd.read_file(ROAD_FILE)

print("Road features:", len(roads))
print("Road CRS:", roads.crs)

if roads.empty:
    raise ValueError("Road layer contains no features.")

if roads.crs is None:
    raise ValueError("Road layer has no CRS.")


# ============================================================
# READ SUSCEPTIBILITY RASTER
# ============================================================

print("\nReading susceptibility raster...")

raster = rasterio.open(SUSCEPTIBILITY_FILE)

print("Raster CRS:", raster.crs)
print(
    "Raster size:",
    raster.width,
    raster.height
)


# ============================================================
# REPROJECT ROADS TO RASTER CRS
# ============================================================

if roads.crs != raster.crs:

    print(
        "\nReprojecting roads to raster CRS..."
    )

    roads = roads.to_crs(raster.crs)


# ============================================================
# PREPARE TRANSFORMER
# ============================================================

transformer = Transformer.from_crs(
    raster.crs,
    "EPSG:4326",
    always_xy=True
)


# ============================================================
# CALCULATE STATIC RISK
# ============================================================

print("\nCalculating static risk for road segments...")

segments = []

for index, row in roads.iterrows():

    geometry = row.geometry

    line = extract_linestring(geometry)

    if line is None:
        print(
            f"Skipping feature {index}: "
            f"unsupported geometry type "
            f"{geometry.geom_type}"
        )
        continue

    static_risk = sample_raster_along_line(
        line,
        raster
    )

    if static_risk is None:
        print(
            f"Skipping feature {index}: "
            "no raster values found"
        )
        continue

    geometry_lonlat = geometry_to_lonlat(
        line,
        transformer
    )

    if not geometry_lonlat:
        continue

    segment_id = f"seg_{len(segments) + 1:04d}"

    segments.append({
        "segment_id": segment_id,
        "geometry": geometry_lonlat,
        "static_risk": round(
            max(0.0, min(1.0, static_risk)),
            4
        )
    })


print(
    "Usable road segments:",
    len(segments)
)


if not segments:
    raise ValueError(
        "No usable road segments were created."
    )


# ============================================================
# CLOSE RASTER
# ============================================================

raster.close()


# ============================================================
# READ RAINFALL MULTIPLIER
# ============================================================

print("\nReading rainfall multiplier...")

rainfall = pd.read_csv(RAINFALL_FILE)

required_columns = [
    "timestamp",
    "rainfall_multiplier"
]

missing = [
    column
    for column in required_columns
    if column not in rainfall.columns
]

if missing:

    raise ValueError(
        f"Missing rainfall columns: {missing}"
    )


print(
    "Rainfall timestamps:",
    len(rainfall)
)


# ============================================================
# BUILD LOOKUP
# ============================================================

print("\nBuilding risk lookup...")

timesteps = {}


for _, rainfall_row in rainfall.iterrows():

    timestamp = str(
        rainfall_row["timestamp"]
    )

    multiplier = float(
        rainfall_row["rainfall_multiplier"]
    )

    timestep_segments = []

    for segment in segments:

        static_risk = segment["static_risk"]

        # Hybrid risk:
        # static GIS susceptibility × rainfall multiplier
        risk_score = static_risk * multiplier

        # Keep risk in [0, 1]
        risk_score = max(
            0.0,
            min(1.0, risk_score)
        )

        predicted_depth = (
            risk_score * MAX_DEPTH_CM
        )

        timestep_segments.append({

            "segment_id": segment["segment_id"],

            "geometry": segment["geometry"],

            "risk_score": round(
                risk_score,
                2
            ),

            "predicted_depth_cm": round(
                predicted_depth,
                1
            ),

            "confidence": CONFIDENCE

        })

    timesteps[timestamp] = timestep_segments


# ============================================================
# BUILD FINAL JSON
# ============================================================

payload = {

    "ward_id": WARD_ID,

    "generated_at":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "timesteps":
        timesteps

}


# ============================================================
# SAVE
# ============================================================

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_FILE.write_text(
    json.dumps(
        payload,
        indent=2
    ),
    encoding="utf-8"
)


# ============================================================
# SUMMARY
# ============================================================

print("\n" + "=" * 60)
print("RISK LOOKUP COMPLETE")
print("=" * 60)

print(
    f"\nSaved: {OUTPUT_FILE}"
)

print(
    "Timesteps:",
    len(timesteps)
)

print(
    "Road segments:",
    len(segments)
)

print(
    "Expected records:",
    len(timesteps) * len(segments)
)

print("\nDone.")