# 福島市全域プレビューの公開前権利確認（2026-11-01）

対象は `dist/citywide-v1-preview/` の静的GLB・JSON・ビューアである。これは内部確認用であり、この文書は公開許諾の確定ではない。元データの取得元と配布物の内容を分けて確認する。

| データ | 公式資料から確認したこと | 現在の対応 | 公開前に残る確認 |
|---|---|---|---|
| 福島市2025 PLATEAU CityGML | [PLATEAU Site Policy](https://www.mlit.go.jp/plateau/site-policy/) はG空間情報センターの3D都市モデルを対象に含み、特記がないコンテンツにはPDL1.0を適用し、出典と加工の表示を求める。[PLATEAU CityGML API文書](https://docs.plateauview.mlit.go.jp/datasets/citygml/) はG空間情報センター側のデータセットページとAPIデータが更新時点で異なり得ると説明する。 | 取得済み212 GMLのURL・SHA-256と加工記録をソースマニフェストへ保存し、画面にPLATEAU / 福島市を表示。 | **取得した2025年度版そのもののデータセットページと特記条件を未照合。** 別年度のライセンス表示を流用せず、正式公開は保留。 |
| 国土地理院 DEM5A PNG標高タイル | [地理院タイル一覧](https://cyberjapandata.gsi.go.jp/development/ichiran.html) は `dem5a_png` を「上記以外」の区分に掲載し、利用規約と個別の備考を確認するよう求める。[コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html) は出典と加工の表示例を示す。 | 取得タイルのURL・SHA-256を記録し、画面と出典文書に国土地理院とDEM5A加工を表示。 | 本製品は元タイルをリアルタイム表示せず、取得した標高をオフラインでGLB化して配布する。**リアルタイム読込の場合の申請不要案内を、そのまま本製品へ適用しない。** この利用形態での手続要否を確認する。 |
| OpenStreetMap / Geofabrik東北抽出 | [OSM公式](https://www.openstreetmap.org/copyright) はODbL 1.0と著作者表示を規定し、[OSMFの表示指針](https://osmfoundation.org/wiki/Attribution_Guidelines) は閲覧可能な地図でのクレジットとデータのライセンスリンクを求める。 | 画面隅に `© OpenStreetMap contributors`、画面内にODbLリンクを設け、OSM道路JSONと補完建物をPLATEAUとは別のレイヤー・マニフェストに保持。 | 道路JSONと補完建物GLBは元OSMから変換したデータを含む。公開時のDerivative Database / Produced Workの区分、ODbLで提供すべきデータまたは変更情報と入手方法を確定する。 |
| 国土数値情報 N03-2026 行政区域 | [N03-2026個別ページ](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html) は対象版をCC BY 4.0と表示し、原典に基づく承認番号を掲載する。[国土数値情報利用規約](https://nlftp.mlit.go.jp/ksj/other/agreement.html) は出典・加工者と適用限界の継承を求める。 | `N03-20260101_07_GML.zip` から福島市境界を抽出し、タイル採否に使用。元ZIPのSHA-256はM1記録に保存。 | 公開物の出典文書にN03-2026の正式名称、個別ページ、CC BY 4.0、境界抽出とタイル加工を明記する。境界は運転案内・測量認証に使わない。 |

## 判定

- **確認済み:** N03-2026個別ページのCC BY 4.0表示、PLATEAU共通ポリシー、GSI DEM5Aタイルの所在と利用区分、OSM/ODbLの著作者表示要件。配布済みファイルの出典連鎖はローカルマニフェストで追跡可能。
- **未確認:** 福島市2025 PLATEAUデータセットの個別特記、オフラインDEM5A派生GLBの手続要否、OSM派生データの公開方式とライセンス義務。これらが揃うまでは `acceptance_complete=false` を維持する。
- **TODO:** 対象データセットの個別ページまたは提供元の回答を保存し、GSIへの利用形態照会とOSM派生データ公開方式の確認を済ませてから、外部配布の判定を更新する。
