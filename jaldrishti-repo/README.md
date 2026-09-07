# JalDrishti

**Real-time urban flood nowcasting for Bengaluru — street-level, 0–3 hour lead time.**

> "Predicting the puddle before the rain stops."

Software-only: no new sensors or hardware. Built on existing public rainfall, terrain, and drainage data plus open-source tooling.

---

## Decide these in the first hour

Fill these in before anyone writes code. They block everyone.

- **Pilot ward:** `_______________` (pick the one with the cleanest available data — check, don't assume)
- **API contract frozen?** `contracts/risk-api-schema.json` — yes / no
- **Map library:** Leaflet / Mapbox (pick whichever someone already knows)

---

## Repo layout

| Folder | Role | Owner |
|---|---|---|
| `contracts/` | Shared API schema — **the thing that unblocks parallel work** | Everyone |
| `data-pipeline/` | Role A — Data Engineering & GIS | |
| `hydrology-swmm/` | Role B — Hydraulic Modeling *(Phase 2)* | |
| `ml-nowcasting/` | Role C — Nowcasting & ML | |
| `backend-api/` | Role D — Backend & API | |
| `frontend-dashboard/` | Role E — Frontend & Dashboard | |
| `infra/` | Role F — Integration & Deployment | |
| `data/` | Local data (gitignored — regenerate, don't commit) | |
| `docs/` | Workflow + planning docs | |

Each folder has its own README with that role's scope, structure, and dependencies. **Read yours before starting.**

---

## Getting started

```bash
git clone <repo-url>
cd jaldrishti
git checkout dev

# Populate local data (nothing large is committed)
bash data-pipeline/download_data.sh
```

Then follow the README in your own folder.

---

## How the pipeline fits together

```
[1] Data Ingestion       rainfall · terrain (DEM) · drainage network · roads
         ↓
[2] Nowcasting           0–3 hr rainfall forecast
         ↓
[3] Hybrid Risk Engine   static GIS susceptibility × rainfall multiplier
                         (+ ML refinement layer)
         ↓
[4] Applications         dashboard · flood-safe routing · (alerts, citizen reports)
```

**The compute rule:** anything heavy (ML training, SWMM calibration) runs **once, offline, on free cloud compute**. Anything running live must be light enough for a mid-range laptop.

---

## Scope discipline

This repo contains folders for the full project vision, but **not everything is in scope for every sprint.** Phase 2 items are marked as such in their READMEs. Under a tight build window, cut aggressively and say so honestly in the pitch — a working narrow demo beats a broken broad one.

See `docs/` for the current build plan and `docs/GIT_WORKFLOW.md` for branching and commit conventions.
