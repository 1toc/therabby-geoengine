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

## 2026-11-07: Fukushima LOD1 + DEM5A integration (experimental)

The independent existing URL is unchanged: `viewer/traffic-lab.html`. In **福島駅付近の実OSM道路** mode,
the new **PLATEAU建物＋DEM5A地形を重ねる** checkbox is enabled and defaults to checked.
The synthetic fixture never loads actual urban GLBs.

### Asset prerequisites (prebuilt local derived files)

```text
data/derived/fukushima-citywide-roads-v1/tileset.json
data/derived/fukushima-citywide-roads-v1/tiles/*.json
data/derived/fukushima-citywide-lod1-glb/tileset.json
data/derived/fukushima-citywide-lod1-glb/*.glb
data/derived/fukushima-citywide-terrain-glb/tileset.json
data/derived/fukushima-citywide-terrain-glb/*.glb
```

The **last four entries are not part of the public source checkout**. They must exist in the already generated `E:\GeoEngine\data\derived\...` directories. No new network data acquisition is performed in the browser.

- `geoengine-traffic-city.mjs` selects a bounded set of nearby GLBs (up to nine per layer, radius 360m), validates EPSG:6677 and T.P. and loads tiles sequentially to reduce simultaneous allocations.
- GLB positioning matches `citywide-v1.js`: `(tile_origin_east-center_east, -reference_TP, center_north-tile_origin_north)`; the reference T.P. altitude comes from the closest DEM-sampled OSM node within 250m. If no reference height is available, the renderer stays 2D rather than inventing an elevation.
- In 3D mode road-ribbon endpoints and characters use linearly interpolated **DEM5A ground samples**. Any segment lacking both endpoint samples is **not drawn as a 3D road ribbon or used as a sample agent path**. This does not imply that the road is missing in real life.
- Roads remain OSM centerlines with **estimated width** and do not supply legal lanes. No collisions, lane markings, traffic signal logic, realistic left-side driving or clinical judgments are implemented.
- The terrain layer uses published GSI DEM5A meshes and remains missing wherever input data has no-data. The near-GLB selection uses a conservative 1000m bounding approximation for DEM tiles because the manifest does not store per-tile geographic bounds; the GLB placement itself uses the exact projected tile origin.
- If either PLATEAU building or DEM5A layer fails entirely, 3D is not activated and the existing 2D traffic view is retained. Partial tile failures are reported in the status, not silently filled with fictional blocks.
- The GLB geometry is **official LOD1 with no official facade photographs**. Official LOD2 photo-overlay replacement is not included here. No modification to the existing `citywide-v1.html` or its main `.js` has been made.
- `viewer/geoengine-traffic-city.mjs` keeps tile-selection, height-reference and GLB load/placement helpers separately testable without a WebGL context.
- The 8GB / Intel UHD 30FPS acceptance remains open; this experimental UI shows observed draw calls and a non-standard FPS estimate only.

### Extended test

```powershell
node --test tests/traffic_lab_probe.mjs tests/traffic_city_probe.mjs
node --check viewer/traffic-lab.js
node --check viewer/geoengine-traffic-city.mjs
```

Unit and GitHub Actions test success verifies the **code paths against synthetic fixtures**, not a local browser's real GLB loading, map alignment, GPU frame rate or patient safety. Inspect a real-data browser screenshot and the status readout before starting any further integration.
