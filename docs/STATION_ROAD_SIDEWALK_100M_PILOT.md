# GeoEngine / Fukushima station-east 100m road & sidewalk visual pilot

**Status: source implementation and synthetic CI only; NOT yet checked against the actual Fukushima GIS-derived files or target PC.**

This is a 100m × 100m **visual prototype**, not a navigable driving map, surveyed lane layout, correct sidewalk map, pedestrian accessibility assessment or collision geometry. It does not change the citywide tiles, OSM network, generated building GLBs, photo stream, original PLATEAU data, DEM or TDS road API.

## Why not just offset the road centreline?

PLATEAU's existing `tran` LOD1 polygon covers the *road corridor*, not the vehicle lane alone. OSM provides *centreline* and heuristic class width, not a measured carriageway edge. The intersection of those sources produces only a **carriageway candidate**. Even the corridor remainder is NOT necessarily sidewalk: it may be a plaza, median, parking, shoulder or unclassified space. This pilot therefore preserves a third **unclassified** region and never reports a verified pedestrian path.

## What this change adds

1. `scripts/build_station_road_split.py`: offline Shapely 2.x 100m pilot. Validates source schemas, EPSG:6677 centre and tile hashes. Unions official PLATEAU road corridor polygons, intersects those with estimated buffered OSM road centreline segments, then partitions the remainder:
   - `carriageway_candidate = PLATEAU_corridor ∩ OSM_width_buffers`
   - `sidewalk_candidate = (PLATEAU_corridor − carriageway_candidate) ∩ carriageway_candidate.buffer(3m)`
   - `unclassified_corridor = remaining corridor`
   The 3m classification distance is purely a test assumption.
2. `viewer/geoengine-station-road-split.js`: produces draped, tessellated WebGL surfaces at visual DEM-relative elevations, plus thin sidewalls at the hypothesized road/sidewalk shared edge. The depicted **9cm curb height is fictional**. No changes to the measured ground, road deck, collision or original models.
3. `viewer/citywide-v1.js/html`: independent toggle and status. Missing or invalid generated files disable the feature and keep the conventional city view. No overlay outside the 100m pilot.
4. `viewer/procedural-city-demo.js/html`: a separately labeled synthetic scene demonstrates the effect without city assets.
5. `tests/test_station_road_split.py`: deterministic synthetic geometry tests and source-integrity checks. CI includes Shapely, Node syntax and a headless Chrome WebGL smoke test.

## Install on your development PC

Your local repository is `E:\GeoEngine-Procedural`; you previously made a **junction** from that folder's `data` to `E:\GeoEngine\data`. The output below is one *new derived JSON file* in that shared data folder, so it will also be visible from the older original project. The script does not rewrite any source file.

Use a second PowerShell window (keep the existing Python HTTP server running):

```powershell
cd E:\GeoEngine-Procedural
git status --short
git fetch origin
git switch feature/station-road-sidewalk-pilot
git pull --ff-only origin feature/station-road-sidewalk-pilot
python -m pip install "shapely>=2,<3"
python scripts/build_station_road_split.py
```

If there are uncommitted local changes, **do not switch branches until they are preserved**. If Python prints an error such as missing `road_extent.json`, `tileset.json`, unexpected schema, invalid PLATEAU polygon, or OSM checksum mismatch, stop and inspect; the script will **not** fabricate data to conceal it.

Expected path created:
`E:\GeoEngine-Procedural\data\derived\fukushima-station-roads-v02\road_split_100m.json`

## Viewing

When your local server is running at port **8791**:
- Standard city baseline: `http://127.0.0.1:8791/viewer/citywide-v1.html`
- Procedural city + candidate 100m overlay: `http://127.0.0.1:8791/viewer/citywide-v1.html?procedural=1&road_split=1`
- Fully synthetic preview: `http://127.0.0.1:8791/viewer/procedural-city-demo.html`

Look for the new **駅東口100m：推定車道・歩道・縁石（実験）** checkbox, and its area/candidate status. The base PLATEAU road exterior is only hidden inside the experiment to avoid overlapping an opaque surface. Original citywide road meshes remain unchanged; they can be visible behind the overlay. The diagram is meaningful primarily near the station EAST 100m centre, not at the station-west preset or distant city areas.

Recommended visual review: compare exactly the same ground camera viewpoint with overlay OFF/ON, and test corners, 4-way intersections and narrow edges. Carefully inspect gaps, overlaps, sliver surfaces, missing terrain, protruding curbs and the 100m boundary. Inferred pedestrian paths must not be used in OT clinical judgments.

## Synthetic tests

```sh
python -m pip install "shapely>=2,<3"
python -m unittest discover -s tests -p test_station_road_split.py -v
node --check viewer/geoengine-station-road-split.js
```

The existing `procedural-city-demo.html` renders an independent synthetic preview. CI uses headless Chrome with SwiftShader; this validates a sample of rendering but not real Fukushima source quality.

## Performance / acceptance

Baseline requirements (UHD Graphics 770 / 8GB RAM / 1280×720 / >=30FPS / 10min) are **not waived**. The benchmark JSON records `station_road_split_visual_enabled`. For normal v1.0 acceptance, `performance_gate.checks.station_road_split_off` must be true. Experimental measurements should instead be run with one variable changed at a time, matching resolution, camera, settings and load state. Compare average FPS, p95, max frame time, draw calls, triangles, loaded textures and missing tiles.

**This pilot makes no claim about safe driving, real curb height, barrier-free access, legal right-of-way, or rehabilitation measurement validity.** Map-source attribution and redistribution of derivative OSM/PLATEAU/GSI data must be reviewed before hosting the generated JSON publicly.
