# Traffic Lab — GeoEngine experiment (2026-11-07)

**Status: isolated prototype, not a production feature and not a driving assessment.**

## What was added

- `viewer/traffic-lab.html`: lightweight standalone Three.js experiment. Does **not** edit or replace `viewer/citywide-v1.html`, the driving-simulator controls, or historical v0.1.
- `viewer/geoengine-traffic-graph.mjs`: converts existing `therabby.geoengine.citywide-road-tile.v0.1` segments from EPSG:6677 east/north into X-east / Z-south local metres and a basic directed adjacency map.
- `viewer/traffic-lab.js`: batched flat visual road ribbons, simplified toy cars and pedestrians. Estimated centerlines are a toggle; three road-material batches avoid a draw call per road segment.
- `tests/traffic_lab_probe.mjs`: synthetic fixture, coordinate conversion, duplicate IDs, missing/invalid data, one-way filtering, separated pedestrian paths, restricted access, and cross-tile node connectivity.
- `.github/workflows/tests.yml`: Node smoke/unit test job.

No Valdrada code, NYC datasets, assets or models are bundled. Valdrada's concept of separating a city data compiler, a movement graph and rendering motivated this independently written demonstration: https://github.com/mkturkcan/valdrada .

## How to run

From the GeoEngine repository root:

```powershell
python -m http.server 8767 --bind 127.0.0.1
```

Open: **http://127.0.0.1:8767/viewer/traffic-lab.html**

The page starts in **SYNTHETIC_TEST_FIXTURE** mode, clearly labeled as fictional. The synthetic fixture works from source files alone. Selecting **福島駅付近の実OSM道路** loads existing locally generated files at:

```text
data/derived/fukushima-citywide-roads-v1/tileset.json
data/derived/fukushima-citywide-roads-v1/tiles/*.json
```

This dataset is not checked into the public GitHub repository. If absent, the UI reports an error and preserves the synthetic demo; it does **not** pretend its demonstration lines are real roads. The real mode loads up to nine 1 km tiles around the approximate Fukushima Station center [37.7548, 140.4597], displays edges within 280 m and animates only supported example arcs.

No Python/Blender is required in the browser. Static file hosting requires HTTPS or localhost due to ES modules.

## Minimal checks

```powershell
node --test tests/traffic_lab_probe.mjs
node --check viewer/traffic-lab.js
python -m unittest discover -s tests -v
```

The full Python suite requires the local generated datasets, original assets and environment, so a checkout without them may not be able to run all tests. GitHub CI deliberately runs the existing dataset-independent `test_geoengine.py` plus the new Node tests.

## Model and quality boundaries

| Feature | Implemented | Not implemented |
|---|---|---|
| Existing citywide source | OSM centerline coordinates and IDs | Surveyed lanes or actual carriageway |
| Topology | Shared node IDs, two-way / OSM oneway tag | Complex turn restrictions, junction priority |
| Display | Flat batched ribbons and width estimates | Proper kerbs, intersections, sidewalks, DEM road deck |
| Moving actors | Simple constant-speed demonstrators | Physical vehicle dynamics, collision, traffic signals, reactions |
| Pedestrians | Footway/pedestrian/path edges only | Verified crossing places and pedestrian right-of-way |
| Performance | One mesh per road material; real-time FPS indication | 10-minute baseline-PC acceptance and benchmark |

- Road widths are OSM class estimates; `legal_drivability: null`, `road_deck_height_m: null`, `collision_ready: false`. These are intentionally not reinterpreted as verified true.
- No vehicle motion is created on mapped `footway/path/pedestrian`, bridge/tunnel edges, private/no-access tagged edges or motorway/trunk edges. This conservative demo filtering is **not** a complete interpretation of Japanese traffic law. OSM tags are incomplete and can be inaccurate.
- Crossings without shared OSM nodes are not linked in the graph, even if lines cross visually. Direction is only approximated from `oneway_osm_tag`. Avoid interpreting the toy-car motion as legal driving.
- All agents use a **flat ground plane** with no DEM elevation, slope, collision, lane positioning, traffic rules or feedback about safety. Actors are rendered *on the centerline*, not in realistic left-hand lanes.
- Other labels and provenance: © OpenStreetMap contributors / ODbL 1.0 for real OSM tiles; Project PLATEAU / 福島市 and 国土地理院 for other GeoEngine datasets if integrated later.
- No clinical metric is computed. Never use this for driving fitness evaluation, real-world navigation or traffic safety decisions.

## Next steps (separate, gated work)

1. Test browser output with generated Fukushima road tiles and review edge continuity, junction errors and missing footways.
2. Benchmark 1280×720 / 10 minutes on the i5-14500T + Intel UHD + RAM 8 GB reference PC. FPS shown in UI is indicative only.
3. Add documented junction rules and Japanese left-side lane geometry *only after* source confidence and geometry review. Traffic events and clinical logs belong in TDS, not the GeoEngine base package.
