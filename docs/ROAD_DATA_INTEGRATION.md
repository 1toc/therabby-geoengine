# 駅東口1km：実道路形状・地表高の統合（2026-10-30）

## 結果

- [公式PLATEAU道路範囲](../dist/real/fukushima-east-1km/plateau_road_extent.json)：CityGML 2025 `tran` 6ファイル、9,718,876 Bを区域APIで選択。EPSG:6697・3次元緯度経度・ゼロ高さを検証し、1km内のLOD1道路範囲500面を日本平面直角IX系のローカルX東/Z南へ変換した。LOD1道路範囲は**車道や車線を分離せず**、元データの高さ0は実路面高として扱わない。
- [DEM5A地表グリッド](../dist/real/fukushima-east-1km/terrain_grid_5m.json)：国土地理院PNG標高タイル4枚、計230,605 Bから5m間隔201×201点を作成。中心はT.P. 69.399m、ローカル相対高は−3.645〜+9.277m。道路・航空写真地面・建物基部をこの地表高に沿わせた。**高架橋・トンネル・道路構造物の路面高はDEMに含まれない**。
- OSM道路366線を走行候補中心線として保持。橋18線、トンネル29線、レイヤ・車線数・路面の原本タグを保持した。車道候補エッジの3代表点をPLATEAU道路範囲と照合した平均重複率は0.783。これは位置合わせの一次検査であり、走行可否の認定ではない。
- 100/250/500mのGLB全タイルと道路JSONを再出力。デモ経路は1km区域外と橋・トンネル・別レイヤを除く1,402.93mの道路中心線。通行方向の適法性を保証する経路ではない。
- [100m](../dist/real/fukushima-east-1km/driving_route_qa_100.json)・[250m](../dist/real/fukushima-east-1km/driving_route_qa_250.json)・[500m](../dist/real/fukushima-east-1km/driving_route_qa_500.json)の経路QAで、各294点（5m以下の間隔）すべてに候補路面・公式道路範囲・DEM地表高があることを確認。地表高から計算した勾配は絶対値p95 1.36%、最大2.29%。これは実路面勾配の測定ではない。
- [道路API](../viewer/geoengine-road-api.js) は `loadNetwork()`、`loadTerrain()`、`nearestRoad(x,z)`、`roadExtentAt(x,z)`、`surfaceAt(x,z)` を提供する。公式道路範囲、OSM中心線、DEM地表高、推定幅を区別して返す。実路面高 `height_m` と `elevation_m` は `null`、`collision_ready` は `false`。

Driving Simulator側の読み取り例：

```js
import { RoadTileProvider } from '/viewer/geoengine-road-api.js';
const base = '/dist/real/fukushima-east-1km/tiles-250/';
const manifest = await fetch(base + 'tileset.json').then(r => r.json());
const roads = new RoadTileProvider(base, manifest);
await roads.loadNetwork();
await roads.loadTerrain();
const nearest = roads.nearestRoad(x, z, 10);
const surface = await roads.surfaceAt(x, z);
// surface.ground_height_m is DEM terrain; surface.height_m is null.
// collision_ready is false until roadway height and geometry are validated.
```

![公式道路範囲とOSM線の重ね合わせ](../dist/real/fukushima-east-1km/qa_plateau_road_extent.png)

赤：PLATEAU LOD1道路範囲。青：OSMの車道候補中心線。航空写真はPLATEAU-Ortho 2024。これは画像上の重なりであり、測量アンカーによる精度検証ではない。

## データの役割

| データ | 現在使う用途 | まだ使えない用途 |
|---|---|---|
| PLATEAU `tran` LOD1 | 実道路の平面範囲・描画 | 車線、歩道境界、道路構造物の高さ、法的通行判断 |
| OSM道路 | 接続、方向タグ、橋・トンネルタグ、候補経路 | 推定幅を実測車道幅として扱うこと |
| GSI DEM5A | 地表の起伏・地上視点の高さ | 橋面・トンネル内面・正確な道路衝突面 |
| 生成したGLB・JSON | 地図表示、道路候補の参照 | 実車両の衝突判定、運転評価、臨床利用の根拠 |

## 再生成

開発PCにはPython（標高PNGの処理にPillow）とBlenderが必要。クライアントは静的JS/GLB/JSONだけを読む。公式PLATEAUの空間subsetを先に確認し、>1GBの地形GMLは取得していない。

```powershell
$python = 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$blender = 'C:\Program Files\Blender Foundation\Blender 3.1\blender.exe'
& $python scripts/fetch_plateau_tran.py --dry-run
& $python scripts/fetch_plateau_tran.py
& $python scripts/prepare_plateau_roads.py
& $python scripts/fetch_gsi_dem.py
& $python scripts/prepare_terrain_grid.py
& $python scripts/geoengine.py build --area config/fukushima_station_east_1km.json --osm data/raw/fukushima_osm_1km.json --plateau data/raw/plateau/56405306_bldg_6697_op.gml data/raw/plateau/56405307_bldg_6697_op.gml --buildings-source hybrid --lod1-only --output dist/real/fukushima-east-1km/map_lod1.json
& $blender --background --python-exit-code 1 --python scripts/blender_export_core_low.py -- --wide-map dist/real/fukushima-east-1km/map_lod1.json --core-map dist/real/fukushima-east/map.json --output dist/real/fukushima-east-1km/core_lod1.glb --terrain-grid dist/real/fukushima-east-1km/terrain_grid_5m.json
foreach ($size in 100,250,500) {
  & $python scripts/prepare_wide_tiles.py --map dist/real/fukushima-east-1km/map_lod1.json --ortho data/derived/fukushima_ortho_1km_z17.png --output-dir "dist/real/fukushima-east-1km/tiles-$size" --tile-size $size --plateau-roads dist/real/fukushima-east-1km/plateau_road_extent.json --terrain-grid dist/real/fukushima-east-1km/terrain_grid_5m.json
  & $blender --background --python-exit-code 1 --python scripts/blender_export_wide_tiles.py -- --tiles-dir "dist/real/fukushima-east-1km/tiles-$size" --core-map dist/real/fukushima-east/map.json
}
foreach ($size in 100,250,500) {
  & $python scripts/qa_driving_route.py --tiles-dir "dist/real/fukushima-east-1km/tiles-$size" --output "dist/real/fukushima-east-1km/driving_route_qa_$size.json"
}
& $python -m unittest discover -s tests -v
```

## 検証済み

- ソースSHA-256、EPSG:6697/鉛直ゼロの検査、未対応CRS・非ゼロ高さの拒否。
- 34件の自動テスト。500公式道路面のタイル分割後の面積差は各サイズで0.5㎡未満。DEM標高値と路面・公式範囲sidecar頂点高の一致、道路・建物数とハッシュ、橋・トンネル情報の保持、デモ経路からの除外、経路294点の3種データ被覆を確認。
- Blender 3.1.2で100/250/500m全GLBを出力。開発環境のヘッドレスChromeで道路視点、3タイルサイズ、道路API、デモ移動、計測JSONを確認。

## 未検証・TODO

- 測量済みアンカーによる水平・鉛直精度。OSMとPLATEAU、GSIタイルの年代差と測地成果差。橋・トンネルの実路面高。
- PLATEAU道路LOD1の車道/歩道分離、実測車道幅、交差点形状、交通規制・信号・車線。DEM地表高を路面高へ使える区間の個別確認。
- 車両衝突面の生成とDriving Simulatorでの実走行検証。I-RIHA101（UHD 770/RAM 8GB）での10分・30FPS計測。個別データセットの再配布条件。
- 1km境界をまたぐ126棟は建物基部をDEMグリッド端へ固定した視覚補完。旧・写真参考LOD2の各建物基部はDEM地形へ再配置していない。

資料：[PLATEAU CityGML区域API](https://docs.plateauview.mlit.go.jp/api/rest/operations/datacatalogcitygmlconditions/)／[GSI標高タイル仕様](https://maps.gsi.go.jp/development/demtile.html)／[GSI標高モデルの限界](https://maps.gsi.go.jp/development/hyokochi.html)。
