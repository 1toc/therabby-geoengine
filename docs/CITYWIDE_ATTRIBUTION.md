# 福島市全域タイルの出典・加工記録（2026-10-31）

この記録はローカル開発成果物の出典を示す。外部公開・再配布の許諾判定を完了したものではない。データ系統を別々のマニフェストとレイヤーに保持し、公式形状と推定形状を混同しない。

| レイヤー | 原典 | このプロジェクトの加工 | 明示した条件・未確認事項 |
|---|---|---|---|
| 公式建物の近景・遠景 | 福島市 / Project PLATEAU 2025 CityGML LOD1、212 GML。市公式サイトによる整備範囲174.6km²。 | CityGMLをEPSG:6677へ投影し、N03市境で切り、DEM5A地表高を代表点で補間。近景は無写真のLOD1、遠景は50mセルの概略質量。 | [PLATEAU共通ポリシー](https://www.mlit.go.jp/plateau/site-policy/)のPDL1.0原則、出典・加工表示を確認。当該2025年度データセットの個別特記は未確認。公開前に対象ページと照合する。 |
| 補完建物・道路 | © OpenStreetMap contributors。Geofabrik東北PBF、スナップショット2026-10-29。 | 公式PLATEAUのソース3次メッシュ外の閉じた建物wayをN03市境で切り、EPSG:6677へ投影。高さの多くを6mと推定。道路中心線を1km分割し、幅は種類別推定。 | ODbL 1.0。画面に著作者表示とライセンスを示す。道路JSON・補完建物GLBの外部配布では派生データのODbL上の区分と公開方式を確認する。原本way IDをJSONに保存する。 |
| 地形・建物基部地表高・道路地表高 | © 国土地理院、地理院タイル標高タイル DEM5A。 | 地表標高を補間し、1km地形GLBへ再構成。54ソースタイル未公開・39,883頂点欠損。 | [地理院タイル一覧](https://cyberjapandata.gsi.go.jp/development/ichiran.html)ではDEM5Aを個別備考確認が必要な区分に掲載。[コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)の出典・加工表示を行い、オフライン派生GLB配布の手続要否を公開前に確認する。 |
| 市境 | 国土交通省 N03-2026 行政区域。 | 福島市コード07201の境界を抽出し、建物・道路・地形範囲の選別に使用。 | [N03-2026個別ページ](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html)はCC BY 4.0と表示。出典と加工内容、適用限界を本書に記録する。 |

参照元: [福島市 3D都市モデル](https://www.city.fukushima.fukushima.jp/soshiki/12/1059/1/12474.html)、[OpenStreetMap copyright and license](https://www.openstreetmap.org/copyright)、[国土地理院コンテンツ利用規約](https://web2.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)。

生成物の出典連鎖とSHA-256は `data/raw/plateau/fukushima_citywide_2025/source_manifest.json`、`data/raw/gsi_dem5a_citywide_full/source_manifest.json`、`data/derived/fukushima-road-source-snapshot/index.json`、各派生 `tileset.json`、`data/derived/fukushima-citywide-release-audit.json` に残す。3つの元データ記録は内部確認用パッケージにも同梱するが、GML・PNG・PBF原本は含めない。道路面高、合法走行可能性、衝突形状は不明である。

2026-11-02の駅東口300m追加試作は、同じ福島市2025 PLATEAU CityGMLの対象2メッシュのLOD2形状と公式写真JPEGを使用した。117枚の取得元URL・SHA-256、各建物ID、品質別GLBのSHA-256は `data/derived/fukushima-station-lod2-overlay/source_photos.json` と `tileset.json` に保存した。写真は画質別に縮小してGLBに埋め込み、AI描き直し画像は使用していない。DEM5A地表高への表示用高さ合わせは鉛直基準変換でも基礎高の実測でもない。詳細は[駅東口LOD2統合記録](STATION_LOD2_INTEGRATION.md)。この追加試作にもPLATEAU個別特記とDEM5A派生データの公開前確認が必要である。

公開前の判断と未確認事項は[権利確認記録](CITYWIDE_RELEASE_RIGHTS_REVIEW.md)に分離した。現行パッケージは内部確認用である。
