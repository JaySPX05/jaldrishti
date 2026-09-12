"""
04_rainfall_multiplier.py
=========================
Derives four nowcast forecast steps (T+0 → T+3h) from the historical
rainfall CSV, using the observed peak intensity to calibrate a simple
ramp-up / decay curve.

Outputs
-------
data/processed/rainfall_multiplier.csv
  Columns: timestamp, mean_rainfall_mm, rainfall_multiplier, horizon_label

Formula
-------
  multiplier(t) driven by rain intensity bucket:
    dry   (< 5 mm)  → 1.00  (baseline susceptibility only)
    light (5–15 mm) → 1.25
    mod  (15–30 mm) → 1.60  (conservative peak; multiplier kept ≤ 2 since
                              we do not model pipe capacity explicitly)
    heavy (≥ 30 mm) → 2.00

  Forecast steps are spaced at 0 / 60 / 120 / 180 minutes from the
  first timestamp in the historical record, with rainfall values taken
  from the nearest observed timestep.  This produces a clearly visible
  ramp-up then decay when the slider is moved T+0 → T+3.

No Phase-2 features (SWMM, ML, live feeds) are added.
"""

import os
import pandas as pd
import numpy as np


# ============================================================
# PATHS
# ============================================================

INPUT = "data/raw/rainfall.csv"
OUTPUT_DIR = "data/processed"
OUTPUT = os.path.join(OUTPUT_DIR, "rainfall_multiplier.csv")


# ============================================================
# THRESHOLDS (mm per 15-min accumulation)
# ============================================================

DRY_THRESH      = 5.0   # < 5 mm   → multiplier 1.00
LIGHT_THRESH    = 15.0  # 5–15 mm  → multiplier 1.25
MODERATE_THRESH = 30.0  # 15–30 mm → multiplier 1.60
#                          ≥ 30 mm  → multiplier 2.00


def multiplier_from_rain(rain_mm: float) -> float:
    """Step-function: rainfall intensity (mm) → dimensionless multiplier."""
    if rain_mm < DRY_THRESH:
        return 1.00
    elif rain_mm < LIGHT_THRESH:
        return 1.25
    elif rain_mm < MODERATE_THRESH:
        return 1.60
    else:
        return 2.00


# ============================================================
# READ & VALIDATE
# ============================================================

print("=" * 55)
print("RAINFALL MULTIPLIER — 4-STEP FORECAST")
print("=" * 55)

print("\nReading rainfall data:", INPUT)

df = pd.read_csv(INPUT)

required = ["timestamp", "station_id", "lat", "lon", "rainfall_mm"]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing columns in {INPUT}: {missing}")

print(f"  Records loaded: {len(df)}")


# ============================================================
# AGGREGATE: mean rainfall per timestamp across all gauges
# ============================================================

rain_by_ts = (
    df.groupby("timestamp")["rainfall_mm"]
    .mean()
    .reset_index()
    .rename(columns={"rainfall_mm": "mean_rainfall_mm"})
    .sort_values("timestamp")
    .reset_index(drop=True)
)

print(f"  Unique timestamps: {len(rain_by_ts)}")
print(f"  Rainfall range: {rain_by_ts['mean_rainfall_mm'].min():.2f} – "
      f"{rain_by_ts['mean_rainfall_mm'].max():.2f} mm")


# ============================================================
# SELECT 4 FORECAST STEPS: T+0, T+1h, T+2h, T+3h
# ============================================================
# We pick the first observed timestamp as T+0, then snap to
# the nearest observed timestep at +60, +120, +180 minutes.

# Parse timestamps
rain_by_ts["dt"] = pd.to_datetime(rain_by_ts["timestamp"])

t0 = rain_by_ts["dt"].iloc[0]

offsets_min = [0, 60, 120, 180]
horizon_labels = ["T+0", "T+1h", "T+2h", "T+3h"]

steps = []
for offset, label in zip(offsets_min, horizon_labels):
    target = t0 + pd.Timedelta(minutes=offset)

    # Nearest available observed timestep
    idx = (rain_by_ts["dt"] - target).abs().idxmin()
    row = rain_by_ts.loc[idx]

    rain = float(row["mean_rainfall_mm"])
    mult = multiplier_from_rain(rain)

    steps.append({
        "timestamp": row["timestamp"],
        "mean_rainfall_mm": round(rain, 3),
        "rainfall_multiplier": mult,
        "horizon_label": label,
    })
    print(f"  {label:6s}  ts={row['timestamp']}  rain={rain:.2f} mm  "
          f"multiplier={mult:.2f}")


# ============================================================
# SAVE
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

out_df = pd.DataFrame(steps)
out_df.to_csv(OUTPUT, index=False)

print(f"\nSaved: {OUTPUT}")
print(f"Multiplier range: {out_df['rainfall_multiplier'].min()} "
      f"– {out_df['rainfall_multiplier'].max()}")

print("\n" + "=" * 55)
print("RAINFALL MULTIPLIER COMPLETE")
print("=" * 55)