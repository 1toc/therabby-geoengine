# Codexへの申し送り / GeoEngine STEP 1-2

目的：ユーザーPCで動作確認済みのSTEP 1-1境界表示に、OpenStreetMap実道路の取得/ローカルタイル表示を追加する。

- 展開先：`E:\GeoEngine\modules\city-boundary\`。他の既存GeoEngine・運転シミュレーターは上書きしない。
- `data/fukushima_city_boundary_full.geojson` があれば必ず保存。ZIPに含まれる暫定版で正式データを上書きしない。
- 試験：`py scripts/build_roads.py --overpass-station` は駅周辺の小範囲。**福島市全域ではない**。
- 本番試験：Geofabrik東北PBF `tohoku-latest.osm.pbf` を `--pbf` で渡し `coverage: municipality`、`way_count > 0` を確認。
- 道路中心線、徒歩可能性、自動車通行規則、車線、速度規制は別概念。いまは描画のみ。
- ビュー：MapLibreが道路GeoJSONを表示。`index.json`のタイルから可視範囲だけ読み込む。ズーム10.5以上。
- プレビュー境界で作ったタイルは `boundary_quality: preview`。正式N03後は **道路タイルも作り直す**。
- `py -m pytest -q tests`、ブラウザ `http://localhost:8000/` で動作確認。
- OSMの© attributionおよびODbLを削除しない。PBFを公開ディレクトリへ置かない。

次：STEP 1-3地形標高DEM。正式N03境界/全域OSM道路取込が未完なら先に対応。
