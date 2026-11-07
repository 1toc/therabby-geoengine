# Technical specification — GeoEngine v1.0 target

> **2026-10-30 scope update:** v1.0の受入目標は福島市全域の連続タイル表示。以下のM1記述は駅東口200mの実装事実として読む。Phase 1の測定は `PHASE1_PERFORMANCE.md`、市全域へのタイル設計は `PHASE2_TILING_SPEC.md`。現行の小区域用座標近似を市全域へそのまま適用しない。

> **2026-10-31 implementation update:** 市全域の現行実装は `CITYWIDE_V1_STATUS.md` を参照。EPSG:6677 / T.P. の近景・遠景・DEM5A・OSMタイルをローカルThree.jsで描画し、読取専用の `viewer/geoengine-citywide-api.js` を備える。公式PLATEAU建物は整備範囲174.6km²のみで、市域全体ではない。対象外のOSM建物足形は推定高さ付きの別レイヤーとして扱う。以下のM1小区域用座標近似・CDN記述・暫定インターフェースは歴史的試作として残す。基準PC性能と公開条件は未確認。

## Deployment architecture

```
[Development PC]                                      [Client / Hospital PC]
OSM Overpass --------+                                Browser (HTTPS)
                     +--> local scene JSON --+                 |
PLATEAU CityGML -----+                       +--> optimized GLB / static JSON
     |                                       |                 |
CityGML LOD1/LOD2 surface parser / Converter  |         Three.js (WebGL)
     |                                       |                 |
Blender Python (offline, optional batch) ----+        Driving Simulator consumer
```

- Production clients receive only static JS/assets. No Blender, Python, local server, or API keys on client PCs.
- Source data acquisition is development-time / build-time, not render-time.
- Rendering runtime should be configured separately from the map creation pipeline.

## Map JSON contract (`therabby.geoengine.map.v0.1`)

- `area`: identifier, WGS84 lat/lon origin, half-size in meters.
- `coordinate_system`: axes **X east, Y up, Z south** and meter unit. M1 makes a **flat base plane**, no vertical geodetic precision.
- `roads`: `points: [[x,z], ...]`, provisional `width_m`, OSM highway type, `oneway`, `name`, width-quality flag.
- `buildings`: `footprint: [[x,z], ...]`, `height_m`, quality flag, source, LOD. LOD2がある建物には `lod2_surfaces: [{type, rings, texture_uri?, texture_uv_rings?}]` を追加し、各点は `[x,z,y]`（建物単位の相対高さ）で表す。UVは各リングの頂点に対応する。BlenderはLOD2の面を三角化して公式JPEGを貼り、LOD2がなければLOD1を押し出す。
- `provenance`: license and attribution per data origin.
- `status`: declared missing features.
- `statistics`: counts for map integrity.

地表写真は地図JSONとは別の `ortho_ground.png` と出典sidecarで管理する。福島市のPLATEAU-Ortho 2024 XYZタイルをWeb Mercatorで対象区域へ切り出し、Blender内のローカル座標の水平面へUVで貼る。GLBでは道路を航空写真として描画し、OSM道路線は地図JSONに残す。航空写真と建物GMLは年度が異なる。

Geographic conversion uses a **small-area equirectangular approximation** (111,320 m per degree of latitude, longitude scaled by cos(latitude)). Not suitable for large national-scale tiles or elevation-sensitive driving simulation. Implement a proper georeferenced projected CRS, seam handling and geodetic vertical datum before production-ready multi-city use.

## PLATEAU compatibility limits (M1)

- CityGML 2.0 `bldg:Building > bldg:lod1Solid > gml:posList` と `bldg:boundedBy > bldg:lod2MultiSurface` のポリゴン。EPSG:6697/4979の3次元経緯度（緯度・経度・高さ）と対象区域内の建物。CRSの明示がなければ変換を拒否する。
- BuildingParts、別のポリゴン符号化、投影座標、CityGML 3.0は未対応。LOD2の `lod2Solid` はXLink参照でも、現実装は同じ建物の `boundedBy` にあるインライン面を読む。その他のXLink構造は未対応。
- LOD1の足形・高さを保持し、LOD2の屋根・壁・地表面を試験的に三角化する。穴のある面はBlenderで三角化する。GML `app:ParameterizedTexture` の画像参照・リング別UVを読み、対象建物に必要なJPEGだけを別途取得してBlenderの画像材質とGLBに埋め込む。写真のない面は単色材質。建物ごとの最低標高をY=0にするため、建物間の地形勾配は表現できない。
- 写真材質は建物ごとの画像アトラスをそのまま使用し、2024年航空写真パッチも追加して現状約11.7 MBのGLBとなる。元建物JPEGの画素数を単純にRGBA 4バイトへ展開すると合計約363 MBで、実際のGPUメモリ消費や病院PCでの描画性能は未測定。画像縮小・アトラス統合は実機測定後に検討する。
- Rejects unsupported coordinate numerics instead of outputting silently shifted data.
- 正式なLOD2変換・配布工程には公式PLATEAU GIS Converter/SDKとの結果比較を行い、道路アンカーとの座標照合を経る。モデルのバウンディングボックス中心だけで任意のglTFを配置しない。

## Browser performance contract (target)

- I-RIHA101 baseline: i5-14500T, integrated Intel GPU, RAM 8 GB. Test Edge/Chrome versions and actual GPU.
- v1.0 target: 1280×720 light preset, average >=30 FPS, 10-minute continuous view navigation with no catastrophic failure. Record frame-time p95, draw calls, triangle counts and texture memory where measurable.
- Visual quality hierarchy: road geometry/signs within driving sight range > nearby façade > distant city silhouette.
- Workload reduction candidates: tile chunking, LOD, batching, instancing, reduced texture sizes, no shadows/bloom in light preset. Actual benefit requires measurement.
- Development preview defaults to MSAA, up to 2× display pixel ratio and anisotropy 8 for clearer oblique imagery; the viewer has a lower-cost toggle. I-RIHA101 performance of the sharper setting remains unverified.
- The experimental PC-9801VX-style view applies a 16-entry 4-bit-per-channel palette, ordered dithering, and nearest-neighbor scaling at no more than 640×400 to the browser render target. A depth discontinuity pass outlines building silhouettes. It changes only the browser output; the Blender project and GLB retain their source textures. This is a style approximation, not a hardware emulator or a validated legibility improvement.
- The photo-reference rebuild pilot is a separate GLB. One named PLATEAU LOD2 building receives approximate modeled windows and rooftop units plus newly generated tileable base-color/normal textures. The source JPEG is recorded by SHA-256 as a visual reference and is not embedded. Other buildings retain LOD2 geometry with generic proxy materials. Road strips use OSM centerlines and class-estimated widths; one adjacent street has illustrative kerbs and markings. Keep these approximations separate from surveyed geometry or driving lanes.
- The whole-area repaint reads each of the 56 official JPEG atlases only during offline build. Wall UV samples rank buildings into four lightness groups; the source JPEG datablocks are removed before saving the Blender file. Conservative image evidence identifies 21 possible window walls; broader rectilinear walls receive clearly labeled estimated window-pattern textures for visual continuity. Nearer selected walls receive capped batched 3D window geometry. New tileable color/normal textures, roofs, streets and pedestrian strips are exported; original photo pixels are absent. Window positions, road widths, kerbs and stair heights are visual approximations, not survey data. The browser swaps the original photo GLB and this whole-area GLB at a fixed camera.

## Integration with Driving Simulator

1km試作では `viewer/geoengine-road-api.js` の読み取り専用 `RoadTileProvider` を実装済み。`loadNetwork()`、`loadTerrain()`、`nearestRoad(x,z)`、`roadExtentAt(x,z)`、`surfaceAt(x,z)` はOSM中心線、公式PLATEAU LOD1道路範囲、GSI DEM5AのT.P.地表高を品質と出典付きで返す。道路の実路面高・合法通行は `null`、衝突準備は `false` と明示する。描画GLBと道路の参照データを分離した。DEM地表高へ沿わせた描画面は車両の物理衝突面として採用しない。詳細は `ROAD_DATA_INTEGRATION.md`。

Tentative app-side interface after M1:

```ts
interface GeoMapHandle {
  loadMap(mapId: string): Promise<void>;
  getRoads(): Array<{id: string; points: [number, number][]; width_m: number}>;
  getCoordinateOrigin(): {lat: number; lon: number};
  dispose(): void;
}
```

この `GeoMapHandle` 案は未実装。市全域向けには `viewer/geoengine-citywide-api.js` の `CitywideRoadProvider` が `loadMap()`、`loadTile(id)`、`nearestRoad(east,north,maxDistance_m)` を読取専用で提供する。道路面高と合法走行可能性は `null`、衝突準備は `false` と返す。Driving Simulatorの実車両走行への統合検証は未実施。

## Safety

Map coordinates and road width estimates are approximate. Do not use these assets for real-world driving guidance, route safety decisions, or clinical reaction-time assessment without separate technical validation.
