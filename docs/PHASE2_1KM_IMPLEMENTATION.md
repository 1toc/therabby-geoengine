# Phase 2 — 福島駅東口 1km連続表示（2026-10-30）

## 実装結果

- [1km表示画面](../viewer/wide-preview.html) で100m・250m・500mタイルを切り替え、読み込み・先読み・解放する。区域全体の航空写真を軽量な下地として表示するため、タイル読み込み中にも地面が見える。Three.js 0.179.1の必要モジュールとMITライセンスを `viewer/vendor/three/` に同梱した。クライアントにPython・Blender・npmのインストールは不要。
- 実データ範囲は中心 `37.75445, 140.46190` の1km四方。OSM地図APIから道路・建物2,132 wayを取得し、保存済みPLATEAU CityGML 2ファイルと統合。出力地図は道路366線、建物1,849棟（PLATEAU LOD1 1,445棟、OSM補完404棟）。OSM補完の高さはOSMタグ由来または仮値で、PLATEAUの測定値ではない。
- PLATEAU-Ortho 2024のズーム17・25画像から航空写真を作成。投影座標から緯度経度を逆算して100/250/500mの地面画像へ再標本化した。各区域の航空写真の有効な元解像度はズーム17相当で、近接時の細部は鮮明ではない。
- GRS80横メルカトルの日本平面直角座標系IX系パラメータで1km地図を作成。元の200m写真参考LOD2モデルの全頂点を同じ投影へ変換し、56棟の元IDに一致する建物を広域タイルから除外した。写真参考モデルは25,302,876 B。中心部の明瞭な描画外観は2,348,680 B。写真参考LOD2の近接壁には引き伸ばしが残るため、道路視点では描画外観を初期表示とした。
- 実OSM道路中心線の連結から、1km区域外と橋・トンネル・別レイヤを除いた1,402.93mのデモ経路を生成した。経路294点で候補路面・PLATEAU道路範囲・DEM地表高の欠落は0。道路タイルの共有境界には同一のノードIDと座標を保存する。経路は地図線の接続確認用で、進行方向・通行許可・車線を保証しない。
- PLATEAU CityGMLの公式道路LOD1を6ファイルから取得し、対象1kmで500道路範囲面を抽出した。国土地理院DEM5Aの4タイルから5m地表グリッドを生成し、道路・地面・建物基部を地表高へ沿わせた。橋・トンネル・車線・実路面高は未検証。詳細は[実道路データ統合記録](ROAD_DATA_INTEGRATION.md)。
- OSM中心線と道路種別から幅を推定した路面ポリゴンをタイルごとに生成し、GLBには舗装模様と補助的な破線を入れた。`road-network.json`、`road-surfaces_*.json`、`road-extents_*.json` を別に出し、[RoadTileProvider](../viewer/geoengine-road-api.js) で中心線、公式道路範囲、DEM地表高を区別して参照できる。実路面高は `null`、`collision_ready:false`。車両の衝突・操舵・交通ルールの根拠にはまだ使えない。
- 広域1,793棟と中心部56棟にPLATEAU/OSMの足形・高さを使った描画外観を付与。広域には道路に面する壁の窓、枠、店舗ガラス、階の見切りを生成した。100/250/500mで同じ55,332窓・4,918店舗窓を出力。壁色・窓位置・舗装模様は推定の視覚表現で、写真や測量で照合した外観ではない。

| タイル辺長 | タイル数 | 広域GLB合計 | 中心高精細を併用した場合のGLB合計 |
|---:|---:|---:|---:|
| 100m | 100 | 34,131,424 B | 59,434,300 B |
| 250m | 16 | 31,211,492 B | 56,514,368 B |
| 500m | 4 | 32,241,220 B | 57,544,096 B |

合計値はディスク上のGLBサイズで、同時読込量・GPU展開メモリではない。描画外観は鮮明さを優先した推定表現であり、実写品質・実景一致ではない。道路視点では中心部の描画外観を初期使用する。

## 試す

`E:\GeoEngine` で以下を起動し、[1km表示画面](../viewer/wide-preview.html) を `http://127.0.0.1:8767/viewer/wide-preview.html` で開く。

```powershell
$python = 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python -m http.server 8767 --bind 127.0.0.1
```

「道路沿いデモ移動」でタイル境界を越える道路視点を確認する。「中心部」で明瞭な描画外観／写真参考LOD2を比較できる。「計測・タイル情報・出典」から10分計測を開始すると、10分後にJSONを保存する。停止ボタンでは途中経過を保存する。100/250/500mの採用値は基準PCでの同条件計測後に決める。

## 再生成

既存の200m高精細 `.blend` と地図JSON、1km OSM/PLATEAU原本がある前提。取得からやり直す場合は `scripts/geoengine.py fetch-osm --source osm-api` と `scripts/fetch_ortho.py --zoom 17 --size 2048` を使う。

```powershell
$python = 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python scripts/fetch_plateau_tran.py --dry-run
& $python scripts/fetch_plateau_tran.py
& $python scripts/prepare_plateau_roads.py
& $python scripts/fetch_gsi_dem.py
& $python scripts/prepare_terrain_grid.py
& $python scripts/geoengine.py build --area config/fukushima_station_east_1km.json --osm data/raw/fukushima_osm_1km.json --plateau data/raw/plateau/56405306_bldg_6697_op.gml data/raw/plateau/56405307_bldg_6697_op.gml --buildings-source hybrid --lod1-only --output dist/real/fukushima-east-1km/map_lod1.json
& $python scripts/geoengine.py validate --map dist/real/fukushima-east-1km/map_lod1.json
```

```powershell
$blender = 'C:\Program Files\Blender Foundation\Blender 3.1\blender.exe'
& $blender --background --python scripts/blender_reproject_core.py -- --source-blend dist/real/fukushima-east/city_photo_crisp.blend --source-area config/fukushima_station_east.json --wide-area config/fukushima_station_east_1km.json --output dist/real/fukushima-east-1km/city_photo_crisp_projected.glb
& $blender --background --python-exit-code 1 --python scripts/blender_export_core_low.py -- --wide-map dist/real/fukushima-east-1km/map_lod1.json --core-map dist/real/fukushima-east/map.json --output dist/real/fukushima-east-1km/core_lod1.glb --terrain-grid dist/real/fukushima-east-1km/terrain_grid_5m.json
foreach ($size in 100,250,500) {
  & $python scripts/prepare_wide_tiles.py --map dist/real/fukushima-east-1km/map_lod1.json --ortho data/derived/fukushima_ortho_1km_z17.png --output-dir "dist/real/fukushima-east-1km/tiles-$size" --tile-size $size --plateau-roads dist/real/fukushima-east-1km/plateau_road_extent.json --terrain-grid dist/real/fukushima-east-1km/terrain_grid_5m.json
  & $blender --background --python-exit-code 1 --python scripts/blender_export_wide_tiles.py -- --tiles-dir "dist/real/fukushima-east-1km/tiles-$size" --core-map dist/real/fukushima-east/map.json
  & $python scripts/qa_driving_route.py --tiles-dir "dist/real/fukushima-east-1km/tiles-$size" --output "dist/real/fukushima-east-1km/driving_route_qa_$size.json"
}
& $python -m unittest discover -s tests -v
```

`prepare_wide_tiles.py` は開発PCのPillowを使う。出力には元地図・航空写真・中心モデルのSHA-256と各GLB・道路中心線・路面・道路ネットワーク・舗装模様・地面JPEGのSHA-256を保存する。

## 検証済み・未検証

**検証済み:** 地図整合性、34件の自動テスト、3種類の全GLB・道路JSON・公式道路範囲JSON・DEM地表グリッド・地面画像の存在とハッシュ、合成道路fixtureでの境界座標一致、公式道路面のタイル分割面積差0.5㎡未満、3タイルサイズでの建物外観数の一致、橋・トンネル情報の保持とデモ経路からの除外、Blenderでの全GLB出力。開発環境のヘッドレスChromeで道路視点の250m描画外観・写真参考LOD2、軽量100m・500m、道路API、経路移動、途中計測JSONの保存を確認。画面記録は [描画外観250m](../dist/real/fukushima-east-1km/wide_browser_250_low_street.png)、[写真参考LOD2 250m](../dist/real/fukushima-east-1km/wide_browser_250_high_street.png)、[描画外観100m](../dist/real/fukushima-east-1km/wide_browser_100_low_street.png)、[描画外観500m](../dist/real/fukushima-east-1km/wide_browser_500_low_street.png)。

**未検証・TODO:** 実測アンカー2点による位置精度。OSM WGS84とJGD2011の厳密な地殻変動・測地変換は未適用。PLATEAU GMLの北端は区域より短く、一部はOSM補完。DEMは地表のみで、高架・トンネルの路面高、実路面勾配・車線・合法経路・交差点・路面衝突判定は未実装。描画外観の窓・店舗・色・舗装・破線は実景照合前。2024航空写真と2025建物の時差も未照合。I-RIHA101（UHD 770/RAM 8GB）での10分・30FPS判定、タイルサイズの最終選定、福島市全域の収録率、配布ライセンスの個別確認は未実施。開発環境の短いブラウザ確認を基準PCの合格として扱わない。
