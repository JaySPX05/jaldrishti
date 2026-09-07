"""
Generates a FAKE risk lookup table matching contracts/risk-lookup-table-format.md,
so you can build and test the real data-loading path today, without waiting
on Pair 1's actual precompute output.

This is a stand-in for Pair 1's real precompute script. When theirs is ready,
you stop running this and point data_loader.py at their real output instead —
same file location, same shape, zero code change needed in the loader.

Run:
    python generate_synthetic_lookup.py
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

WARD_ID = "koramangala"
CENTER_LNG, CENTER_LAT = 77.627, 12.935
NUM_SEGMENTS = 15
NUM_TIMESTEPS = 12   # 0-3hr window in 15-min steps
STEP_MINUTES = 15

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "processed" / f"risk_lookup_{WARD_ID}.json"


def deterministic_base_risk(segment_id: str) -> float:
    """A fixed intrinsic susceptibility per segment (0.2-0.7), independent of time."""
    h = hashlib.md5(segment_id.encode()).hexdigest()
    return 0.2 + 0.5 * (int(h[:4], 16) % 100) / 100


def deterministic_jitter(segment_id: str, timestamp: str) -> float:
    """Small deterministic wobble (+/- 0.04) so the curve isn't a perfectly flat ramp."""
    h = hashlib.md5(f"jitter{segment_id}{timestamp}".encode()).hexdigest()
    return (int(h[:4], 16) % 100) / 100 * 0.08 - 0.04


def fake_geometry(i: int) -> list[list[float]]:
    offset = (i % 10) * 0.002
    return [
        [CENTER_LNG + offset, CENTER_LAT + offset * 0.6],
        [CENTER_LNG + offset + 0.0015, CENTER_LAT + offset * 0.6 + 0.0012],
    ]


def main():
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    timesteps = {}

    for step in range(NUM_TIMESTEPS):
        ts = (start + timedelta(minutes=STEP_MINUTES * step)).isoformat()
        # Smooth ramp 0 -> 1 across the window, so the "storm" visibly builds
        # instead of jittering. Real data won't be this clean, but a demo's
        # synthetic stand-in should tell an unambiguous visual story.
        storm_factor = step / (NUM_TIMESTEPS - 1)

        segments = []
        for i in range(1, NUM_SEGMENTS + 1):
            segment_id = f"seg_{i:04d}"
            base = deterministic_base_risk(segment_id)
            jitter = deterministic_jitter(segment_id, ts)
            risk = base + (1 - base) * storm_factor * 0.8 + jitter
            risk = round(max(0.0, min(1.0, risk)), 2)
            segments.append({
                "segment_id": segment_id,
                "geometry": fake_geometry(i),
                "risk_score": risk,
                "predicted_depth_cm": round(risk * 30, 1),
                "confidence": 0.6,
            })
        timesteps[ts] = segments

    payload = {
        "ward_id": WARD_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timesteps": timesteps,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(timesteps)} timesteps x {NUM_SEGMENTS} segments -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
