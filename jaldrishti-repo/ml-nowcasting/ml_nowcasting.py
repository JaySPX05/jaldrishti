"""
ML Nowcasting stretch goal (PySteps optical-flow).

PySteps requires a *sequence of 2D rainfall fields* over time to track motion.
If you only have point gauge readings (e.g. KSNDMC station data), this script
interpolates them into a synthetic grid first. If you already have gridded
data (radar/satellite composites), skip straight to build_nowcast().

Install: pip install pysteps scipy numpy pandas
"""

import numpy as np
import pandas as pd
from scipy.interpolate import griddata

try:
    from pysteps import motion, nowcasts
    from pysteps.utils import transformation
    PYSTEPS_AVAILABLE = True
except ImportError:
    PYSTEPS_AVAILABLE = False


# ---------- Path A: point gauge data -> interpolated grid ----------

def load_point_rainfall(csv_path):
    """
    Expects columns: timestamp, station_id, lat, lon, rainfall_mm
    Returns a DataFrame sorted by timestamp.
    """
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    required = {"timestamp", "station_id", "lat", "lon", "rainfall_mm"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    return df.sort_values("timestamp")


def interpolate_to_grid(df, grid_size=64, method="linear"):
    """
    Converts point gauge readings at each timestamp into a 2D grid via
    interpolation (IDW-style using scipy's griddata). This is a synthetic
    stand-in for real radar data -- resolution is only as good as your
    gauge density, so treat it as a rough visual approximation.

    Returns: numpy array of shape (n_timesteps, grid_size, grid_size)
    """
    timestamps = sorted(df["timestamp"].unique())
    lat_min, lat_max = df["lat"].min(), df["lat"].max()
    lon_min, lon_max = df["lon"].min(), df["lon"].max()

    grid_lat, grid_lon = np.meshgrid(
        np.linspace(lat_min, lat_max, grid_size),
        np.linspace(lon_min, lon_max, grid_size),
    )

    frames = []
    for ts in timestamps:
        snapshot = df[df["timestamp"] == ts]
        points = snapshot[["lat", "lon"]].values
        values = snapshot["rainfall_mm"].values

        if len(points) < 3:
            # not enough stations to interpolate -- fill with uniform value
            grid = np.full((grid_size, grid_size), values.mean() if len(values) else 0.0)
        else:
            grid = griddata(points, values, (grid_lat, grid_lon), method=method, fill_value=0.0)

        frames.append(grid)

    return np.stack(frames), timestamps


# ---------- Path B: already-gridded data ----------

def load_gridded_rainfall(npy_or_stack):
    """
    If you already have a stack of 2D rainfall fields (e.g. loaded from
    .tif/.nc files into a numpy array of shape (n_timesteps, H, W)),
    just pass that array in directly. Placeholder loader shown here.
    """
    return np.load(npy_or_stack)  # adjust if your format differs


# ---------- core PySteps nowcast ----------

def build_nowcast(rainfall_stack, n_leadtimes=6, timestep_minutes=10):
    """
    rainfall_stack: numpy array (n_timesteps, H, W) of past rainfall fields.
    Returns forecast fields for n_leadtimes steps into the future.
    """
    if not PYSTEPS_AVAILABLE:
        raise ImportError("pysteps not installed -- pip install pysteps")

    # log-transform (PySteps convention, stabilizes variance)
    rainfall_db, metadata = transformation.dB_transform(rainfall_stack, threshold=0.1, zerovalue=-15.0)

    # estimate motion field via Lucas-Kanade optical flow
    oflow_method = motion.get_method("LK")
    motion_field = oflow_method(rainfall_db)

    # extrapolate forward using the estimated motion
    extrapolate = nowcasts.get_method("extrapolation")
    forecast_db = extrapolate(rainfall_db[-1], motion_field, n_leadtimes)

    # back-transform to mm
    forecast_mm = transformation.dB_transform(forecast_db, inverse=True, threshold=-10.0, zerovalue=-15.0)[0]
    return forecast_mm


# ---------- run ----------

if __name__ == "__main__":
    CSV_PATH = "historical_rainfall.csv"  # point gauge data from Pair 1

    print("Loading point rainfall data...")
    df = load_point_rainfall(CSV_PATH)

    print("Interpolating to grid (synthetic radar-like field)...")
    rainfall_stack, timestamps = interpolate_to_grid(df)
    print(f"Grid stack shape: {rainfall_stack.shape}")

    print("Running PySteps optical-flow nowcast...")
    forecast = build_nowcast(rainfall_stack, n_leadtimes=18, timestep_minutes=10)  # 18 * 10min = 3hr
    print(f"Forecast shape: {forecast.shape}")  # (n_leadtimes, H, W)

    # forecast[i] is the predicted rainfall grid i timesteps ahead
    # feed this into your risk engine's rainfall multiplier per timestep
