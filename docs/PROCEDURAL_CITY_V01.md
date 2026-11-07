# GeoEngine Procedural City v0.1 — optional visual experiment

Status: **code implemented, synthetic checks available; Fukushima assets and target-PC performance NOT verified**.

## Goal and boundaries

This is a small, opt-in adaptation of the **approach** seen in [Procedural Tokyo](https://github.com/jeantimex/tokyo): keep city-source geometry, add near-range procedural visual detail. The JS implementation here is original; it does not import that project's runtime or data.

Adds:
- Generated window bays, sill and wall variation on **official LOD1 walls** and separately identified **OSM fallback walls**. No original PLATEAU geometry is edited.
- Approximate dashed two-way centre lines and solid edge paint on OSM road meshes, with height sampling from the existing GeoEngine road-ground logic.
- A light-weight hour slider with artistic sun/sky/fog and optional window glow.
- A **synthetic, asset-independent** 3D city demo.
- JavaScript pure geometry tests and CI syntax tests.

Does NOT add: measured carriageway/sidewalk boundaries, traffic rules, true crossings, stop signs, georeferenced lamps, vehicle physics, accurate winter/weather effects, survey-grade elevation or photorealistic reproduction.

## Run

From the root of the repo:

```powershell
python -m http.server 8767 --bind 127.0.0.1
```

- **Standalone synthetic preview (works with source checkout):** http://127.0.0.1:8767/viewer/procedural-city-demo.html
- **Fukushima city mode (requires privately built GIS derived assets under data/):** http://127.0.0.1:8767/viewer/citywide-v1.html?procedural=1
- **Baseline unchanged:** http://127.0.0.1:8767/viewer/citywide-v1.html

Enable/disable using **手続き生成の街並み（実験）**, set the time in the slider. URL `?procedural=1` initially enables the experiment. Neither choice edits maps, GLB files or persistent storage. Refresh without that query flag for the unchanged baseline.

## Design

- `viewer/geoengine-procedural-rules.mjs`: pure rules producing estimated triangles from a road tile's `edges`; excludes pedestrian-only, bridge/tunnel, unknown DEM, narrow and degenerate inputs. Limits generated quads per tile. No actual traffic rules invented.
- `viewer/geoengine-procedural-city.js`: Three.js render adapter: patches only materials whose exported names identify official / OSM wall surfaces, without changing geometry. Builds a batched road-paint mesh per tile on demand, with explicit visual-only diagnostics. Sets artistic light and window glow uniforms.
- `viewer/citywide-v1.js`: hooks the adapter into existing tile loading, LOD swapping, display toggles, cleanup and measurement logs.
- `viewer/procedural-city-demo.*`: city built from **fictional boxes, road strips, trees and decorative cars**; never present as Fukushima geography.

The existing citywide data schema, EPSG:6677/T.P. frame, station LOD2 textures, 100m pilot and photo-streaming paths remain unchanged. The photo LOD2 itself does **not** get generated windows. Only the filtered LOD1 part in that compound tile is eligible.

## Validation

```sh
node --check viewer/geoengine-procedural-city.js
node --check viewer/citywide-v1.js
node --check viewer/procedural-city-demo.js
node --test tests/procedural-city.test.mjs
python -m unittest discover -s tests -p test_geoengine.py -v
```

This GitHub source-only repo excludes derived GIS assets. Therefore executing the full city's 3D viewer or validating against real Fukushima road tiles is **not possible from clone alone**. Real-data integration requires the existing local build. Browser GPU/framerate tests for this new layer are still pending.

Important performance/quality checks before merging into an accepted version:
1. Compare same camera position, quality mode, resolution and hour with experiment off/on on Intel integrated GPU / RAM 8GB.
2. Track average FPS, p95, long frame stalls, GPU textures, draw calls and loaded tile counts. Road paint is generated per tile only when enabled.
3. Check roadside closeups for incorrectly aligned window bays and paint hovering above sloped surfaces or crossing tile boundaries.
4. Verify no changes to station photo streaming, 10-minute tour, walking collision and road API.
5. Confirm source licensing/attribution for any future hosted GIS data; this PR adds no real city data.

### Benchmark handling

The normal 10-minute acceptance run is designed for the **baseline** renderer. When the procedural visuals are enabled, the measurement JSON records `procedural_city_enabled` and `procedural_visual_hour`, and `performance_gate.checks.procedural_visuals_off` becomes false. Thus an experiment cannot be mistaken for baseline v1.0 performance acceptance.

## Next increment (separate PR)

Evaluate precomputed PLATEAU road outline + OSM carriageway/sidewalk partitioning using real Fukushima assets, keeping inferred geometry separate. Then consider georeferenced street furniture, signal states and lightweight traffic models after TDS integration and regulatory validation.

Inspired by the open-source architecture of Procedural Tokyo; **no claim of matching its visual scope**. Code MIT under Therabby repository; third-party geodata terms handled separately.
