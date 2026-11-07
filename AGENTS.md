# Guidance for Codex agents — Therabby GeoEngine

Before writing code, read `PROJECT.md`, `docs/TECHNICAL_SPEC.md`, `docs/M1_STATUS.md`.

Phase 1の画質・性能比較は `docs/PHASE1_PERFORMANCE.md`、Phase 2タイル化設計は `docs/PHASE2_TILING_SPEC.md` も確認する。基準PCでの実測と開発環境の計測を混同しない。

- Prioritize M1 real-data processing for Fukushima Station east side, not a new driving simulator.
- Keep legacy v0.1 HTML as a reference; do NOT change its controls, vehicle handling or engine.
- Prefer Python stdlib for ETL; Blender's bundled Python for GLB. MCP is optional, not a hard dependency.
- Never call synthetic fixture authentic Fukushima data. Tests/fixtures are obviously labeled.
- Never automatically convert unsupported EPSG or vertical coordinates; fail with diagnostic.
- Don't assume CityGML2.0 LOD1 extrusion equals photorealistic LOD2.
- Keep all client-side runtime dependencies install-free. Development PC is allowed Python/Blender.
- Avoid huge PLATEAU downloads by default; prefer official spatial subset API and ask the operator before >1GB downloads.
- Preserve license/attribution and clear provenance in every asset.
- Run `python -m unittest discover -s tests -v` after each change.
- Record exactly which outputs are tested, untested, and TODO.
