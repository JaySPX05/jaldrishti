"""
06_update_dashboard.py
======================
Patches frontend-dashboard/index.html with:

1. The latest risk_lookup_koramangala.json (converted to inline JS so
   the dashboard works when opened as a file:// URL without a server).
2. Updated application logic:
  - Map centres on Koramangala (12.935 N, 77.634 E) at zoom 16.
   - Risk colouring by score bands (not hardcoded depth buckets).
   - 4 forecast steps (T+0 → T+3h) from the lookup timesteps.
   - Per-segment popups showing drain proximity + rainfall.
   - Legend updated to show risk-score bands.
   - Slider tick labels: T+0 / T+1h / T+2h / T+3h.
3. Copies the updated lookup to:
   - frontend-dashboard/risk_lookup_kormangala.JSON
   - backend-api/risk_lookup_koramangala.json

Run after scripts 04 and 05.
"""

import json
import re
import shutil
from pathlib import Path

# ============================================================
# PATHS
# ============================================================

LOOKUP_SRC   = Path("data/processed/risk_lookup_koramangala.json")
DASHBOARD    = Path("frontend-dashboard/index.html")
FRONTEND_DIR = Path("frontend-dashboard")
BACKEND_DIR  = Path("backend-api")

# ============================================================
# 1. LOAD LOOKUP
# ============================================================

print("Loading lookup:", LOOKUP_SRC)
payload = json.loads(LOOKUP_SRC.read_text(encoding="utf-8"))

ts_keys = sorted(payload["timesteps"].keys())
if len(ts_keys) < 4:
    raise ValueError(f"Expected ≥ 4 timesteps, got {len(ts_keys)}")

# Use the first 4 timesteps
ts_keys = ts_keys[:4]
horizon_labels = ["T+0", "T+1h", "T+2h", "T+3h"]

# Build compact DATA object for inline embedding
data_steps = []
for i, ts in enumerate(ts_keys):
    segs = payload["timesteps"][ts]
    data_steps.append({
        "step": i,
        "timestamp": ts,
        "horizon": horizon_labels[i],
        "segments": segs,
    })

data_inline = json.dumps({"steps": data_steps}, separators=(",", ":"))
seg_count = len(data_steps[0]["segments"])

print(f"  Timesteps  : {len(data_steps)}")
print(f"  Segments   : {seg_count}")
t0_risks = [s["risk_score"] for s in data_steps[0]["segments"]]
t3_risks = [s["risk_score"] for s in data_steps[-1]["segments"]]
print(f"  Risk at T+0: {min(t0_risks):.2f}–{max(t0_risks):.2f}")
print(f"  Risk at T+3: {min(t3_risks):.2f}–{max(t3_risks):.2f}")

# ============================================================
# 2. NEW APPLICATION SCRIPT BLOCK
# ============================================================

NEW_APP_JS = f"""const DATA = {data_inline};

/* ── Risk colour bands (score 0–1) ─────────────────────────────────────── */
const RISK_BANDS = [
  {{max: 0.25, color: '#718096', label: 'Negligible', weight: 3}},
  {{max: 0.45, color: '#d69e2e', label: 'Minor',      weight: 4}},
  {{max: 0.65, color: '#dd6b20', label: 'Moderate',   weight: 5}},
  {{max: 0.80, color: '#c53030', label: 'High',       weight: 6}},
  {{max: 1.01, color: '#742a2a', label: 'Severe',     weight: 7}},
];
function colorForRisk(score){{
  for(const b of RISK_BANDS){{ if(score<=b.max) return b.color; }}
  return RISK_BANDS[RISK_BANDS.length-1].color;
}}
function weightForRisk(score){{
  for(const b of RISK_BANDS){{ if(score<=b.max) return b.weight; }}
  return 7;
}}

/* ── Map initialisation ─────────────────────────────────────────────────── */
const WARD_CENTER = [12.935, 77.634];
const WARD_ZOOM   = 16;

const map = L.map('map',{{
  zoomControl:false, attributionControl:true,
  minZoom:13, maxZoom:18
}}).setView(WARD_CENTER, WARD_ZOOM);
L.control.zoom({{position:'bottomright'}}).addTo(map);

L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{
  attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  subdomains:'abc', maxZoom:19
}}).addTo(map);

/* ── Popup builder ──────────────────────────────────────────────────────── */
function buildPopup(seg){{
  const prox = seg.drain_proximity_m!=null
    ? seg.drain_proximity_m.toFixed(0)+' m' : '—';
  const rain = seg.mean_rainfall_mm!=null
    ? seg.mean_rainfall_mm.toFixed(1)+' mm' : '—';
  return '<div class="popTitle">Segment '+seg.segment_id.replace('seg_0','#')+'</div>'+
    '<div class="popRow"><span>Risk score</span><b>'+seg.risk_score.toFixed(2)+'</b></div>'+
    '<div class="popRow"><span>Indicative depth</span><b>'+(seg.predicted_depth_cm||0).toFixed(1)+' cm</b></div>'+
    '<div class="popRow"><span>Nearest drain</span><b>'+prox+'</b></div>'+
    '<div class="popRow"><span>Rainfall (15 min)</span><b>'+rain+'</b></div>'+
    '<div class="popRow" style="font-size:11px;color:#718096;margin-top:4px">'+
      '<span>GIS-only model — not physically calibrated</span></div>';
}}

/* ── Build segment layers ───────────────────────────────────────────────── */
let segLayers = DATA.steps.map(stepData=>{{
  const layer = L.layerGroup();
  stepData.segments.forEach(seg=>{{
    const latlngs = seg.geometry.map(([lng,lat])=>[lat,lng]);
    if(latlngs.length<2) return;
    const line = L.polyline(latlngs,{{
      color:   colorForRisk(seg.risk_score),
      weight:  weightForRisk(seg.risk_score),
      opacity: 0.92,
      lineCap: 'round'
    }});
    line.bindPopup(buildPopup(seg));
    line.addTo(layer);
  }});
  return layer;
}});

/* ── Gauge markers (placeholder circles using rainfall metadata) ─────────── */
/* Gauges re-use the rainfall value stored per segment at each step.         */
let gaugeLayers = DATA.steps.map(()=>L.layerGroup());

/* ── State ──────────────────────────────────────────────────────────────── */
let currentStep = 0;
let gaugesOn = false;
segLayers[0].addTo(map);

function fmtClock(ts){{
  const d = new Date(ts);
  return d.toLocaleTimeString('en-IN',{{hour:'2-digit',minute:'2-digit',
    hour12:false,timeZone:'Asia/Kolkata'}})+' IST';
}}

const horizonLabels = DATA.steps.map(s=>s.horizon);

function setStep(i){{
  segLayers[currentStep].remove();
  if(gaugesOn) gaugeLayers[currentStep].remove();
  currentStep = i;
  segLayers[currentStep].addTo(map);
  if(gaugesOn) gaugeLayers[currentStep].addTo(map);
  document.getElementById('timeSlider').value = i;
  document.getElementById('horizonLabel').textContent = horizonLabels[i];
  document.getElementById('clockLabel').textContent = fmtClock(DATA.steps[i].timestamp);
}}
setStep(0);

document.getElementById('timeSlider').addEventListener('input', e=>{{
  setStep(parseInt(e.target.value));
}});

document.getElementById('gaugeToggle').addEventListener('click', ()=>{{
  gaugesOn = !gaugesOn;
  document.getElementById('gaugeBox').classList.toggle('on', gaugesOn);
  if(gaugesOn){{ gaugeLayers[currentStep].addTo(map); }}
  else{{ gaugeLayers[currentStep].remove(); }}
}});

let playing=false, playTimer=null;
document.getElementById('playBtn').addEventListener('click', ()=>{{
  playing=!playing;
  document.getElementById('playIcon').style.display=playing?'none':'block';
  document.getElementById('pauseIcon').style.display=playing?'block':'none';
  if(playing){{
    playTimer=setInterval(()=>{{
      let next=currentStep+1; if(next>3) next=0; setStep(next);
    }},2200);
  }} else {{ clearInterval(playTimer); }}
}});

window.addEventListener('resize', ()=>map.invalidateSize());
setTimeout(()=>map.invalidateSize(), 300);
"""

# ============================================================
# 3. PATCH THE HTML
# ============================================================

print("\nPatching dashboard HTML...")
html = DASHBOARD.read_text(encoding="utf-8")

# --- 3a. Replace legend panel ---
old_legend = (
    '<div id="legend" class="console">\n'
    '  <div class="label">PREDICTED DEPTH</div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:var(--d-none)"></span><span class="lbl">No flooding</span><span class="rng">0 cm</span></div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:var(--d-minor)"></span><span class="lbl">Minor</span><span class="rng">1\u201310</span></div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:var(--d-mod)"></span><span class="lbl">Moderate</span><span class="rng">11\u201320</span></div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:var(--d-severe)"></span><span class="lbl">Severe</span><span class="rng">21\u201328</span></div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:var(--d-impass)"></span><span class="lbl">Impassable</span><span class="rng">29+</span></div>\n'
    '</div>'
)
new_legend = (
    '<div id="legend" class="console">\n'
    '  <div class="label">FLOOD RISK SCORE</div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:#718096"></span><span class="lbl">Negligible</span><span class="rng">0\u20130.25</span></div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:#d69e2e"></span><span class="lbl">Minor</span><span class="rng">0.25\u20130.45</span></div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:#dd6b20"></span><span class="lbl">Moderate</span><span class="rng">0.45\u20130.65</span></div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:#c53030"></span><span class="lbl">High</span><span class="rng">0.65\u20130.80</span></div>\n'
    '  <div class="legend-row"><span class="swatch" style="background:#742a2a"></span><span class="lbl">Severe</span><span class="rng">0.80+</span></div>\n'
    '</div>'
)
if old_legend in html:
    html = html.replace(old_legend, new_legend)
    print("  ✓ Legend panel updated")
else:
    print("  ⚠ Legend panel not found — skipping (manual update may be needed)")

# --- 3b. Replace slider ticks ---
old_ticks = '<div class="ticks"><span>T+0</span><span>+45m</span><span>+1h30</span><span>+2h15</span></div>'
new_ticks  = '<div class="ticks"><span>T+0</span><span>T+1h</span><span>T+2h</span><span>T+3h</span></div>'
if old_ticks in html:
    html = html.replace(old_ticks, new_ticks)
    print("  ✓ Slider ticks updated")
else:
    # Try regex fallback
    html, n = re.subn(
        r'<div class="ticks">.*?</div>',
        new_ticks,
        html,
        count=1,
        flags=re.DOTALL,
    )
    if n:
        print("  ✓ Slider ticks updated (regex)")
    else:
        print("  ⚠ Slider ticks not found — skipping")

# --- 3c. Replace loadTag ---
old_tag = 'SEGMENTS: 15 &nbsp;·&nbsp; GAUGES: 10 &nbsp;·&nbsp; WARD: KORAMANGALA'
new_tag = f'SEGMENTS: {seg_count} &nbsp;·&nbsp; STEPS: 4 (T+0→T+3h) &nbsp;·&nbsp; WARD: KORAMANGALA'
if old_tag in html:
    html = html.replace(old_tag, new_tag)
    print("  ✓ Load tag updated")
else:
    print("  ⚠ Load tag text not found — skipping")

# --- 3d. Replace the application script block ---
# Strategy: find everything from `const DATA = {` to `</script>` at end of body
# and replace with the new application code.
# The marker we look for is the start of the DATA const.
pattern = re.compile(
    r'const DATA\s*=\s*\{.+?</script>',
    re.DOTALL,
)
new_block = NEW_APP_JS.strip() + "\n</script>"
html_new, count = pattern.subn(new_block, html, count=1)

if count == 0:
    print("  ⚠ Could not find 'const DATA = {' pattern in HTML.")
    print("    Trying alternate boundary marker...")
    # Fallback: look for function getVar which appears right after DATA
    pattern2 = re.compile(r'function getVar\(name\).+?</script>', re.DOTALL)
    html_new, count2 = pattern2.subn(new_block, html, count=1)
    if count2 == 0:
        print("  ✗ Could not patch app script block. Writing HTML unchanged.")
    else:
        html = html_new
        print("  ✓ App script block replaced (fallback marker)")
else:
    html = html_new
    print("  ✓ App script block replaced")

# --- 3e. Save patched HTML ---
DASHBOARD.write_text(html, encoding="utf-8")
print(f"\nSaved: {DASHBOARD}  ({len(html):,} bytes)")

# ============================================================
# 4. COPY LOOKUP FILES
# ============================================================

# Frontend folder copy (note existing file uses capital .JSON)
fe_dest = FRONTEND_DIR / "risk_lookup_kormangala.JSON"
shutil.copy2(LOOKUP_SRC, fe_dest)
print(f"Copied lookup → {fe_dest}")

# Backend folder copy
be_dest = BACKEND_DIR / "risk_lookup_koramangala.json"
shutil.copy2(LOOKUP_SRC, be_dest)
print(f"Copied lookup → {be_dest}")

# ============================================================
# 5. DONE
# ============================================================
print("\n" + "=" * 60)
print("DASHBOARD UPDATE COMPLETE")
print("=" * 60)
print("\nOpen frontend-dashboard/index.html in a browser to verify.")
print("Expected: map centred on Koramangala, "
      f"{seg_count} coloured street segments,")
print(f"         slider T+0→T+3h changes risk colours visibly.")
