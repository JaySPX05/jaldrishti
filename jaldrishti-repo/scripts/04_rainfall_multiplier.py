import os
import pandas as pd
import numpy as np


# ============================================================
# PATHS
# ============================================================

INPUT = "ml-nowcasting/historical_rainfall.csv"
OUTPUT_DIR = "data/processed"
OUTPUT = os.path.join(OUTPUT_DIR, "rainfall_multiplier.csv")


# ============================================================
# SETTINGS
# ============================================================

# Rainfall thresholds in mm
LOW_RAIN = 5
MODERATE_RAIN = 15
HEAVY_RAIN = 30


# ============================================================
# READ RAINFALL DATA
# ============================================================

print("=" * 55)
print("RAINFALL MULTIPLIER")
print("=" * 55)

print("\nReading rainfall data...")

df = pd.read_csv(INPUT)

print("Rainfall records:", len(df))


# ============================================================
# VALIDATE COLUMNS
# ============================================================

required = [
    "timestamp",
    "station_id",
    "lat",
    "lon",
    "rainfall_mm"
]

missing = [c for c in required if c not in df.columns]

if missing:
    raise ValueError(f"Missing columns: {missing}")


# ============================================================
# CALCULATE WARD-LEVEL RAINFALL
# ============================================================

print("\nCalculating rainfall by timestamp...")

rainfall = (
    df.groupby("timestamp")["rainfall_mm"]
    .mean()
    .reset_index()
)

rainfall.rename(
    columns={"rainfall_mm": "mean_rainfall_mm"},
    inplace=True
)


# ============================================================
# RAINFALL MULTIPLIER
# ============================================================

def calculate_multiplier(rain):

    if rain < LOW_RAIN:
        return 1.0

    elif rain < MODERATE_RAIN:
        return 1.25

    elif rain < HEAVY_RAIN:
        return 1.5

    else:
        return 2.0


rainfall["rainfall_multiplier"] = (
    rainfall["mean_rainfall_mm"]
    .apply(calculate_multiplier)
)


# ============================================================
# SAVE
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

rainfall.to_csv(
    OUTPUT,
    index=False
)


# ============================================================
# SUMMARY
# ============================================================

print("\nRainfall timestamps:", len(rainfall))

print(
    "\nMultiplier range:",
    rainfall["rainfall_multiplier"].min(),
    "to",
    rainfall["rainfall_multiplier"].max()
)

print("\nSaved:")
print(OUTPUT)

print("\n" + "=" * 55)
print("RAINFALL MULTIPLIER COMPLETE")
print("=" * 55)