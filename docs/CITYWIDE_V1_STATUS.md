# 福島市全域 v1.0 実装・受入状況（2026-11-02）

**判定: Phase 6の現時点の作業は利用者判断で暫定終了。v1.0の実装候補は動作しているが、受入完了ではない。** 静的Webアセットの生成、全件監査、開発PCブラウザでの描画を確認した。基準PC性能、測量アンカー、データセット固有の再配布条件が未確認である。これらが済むまで公開版v1.0とは表示しない。区切りの範囲と再開条件は[Phase 6暫定終了記録](PHASE6_PROVISIONAL_CLOSEOUT.md)。

**2026-11-02 追加試作:** 駅東口300m四方の公式2025年LOD2写真付き117棟を、既存市全域LOD1と同一IDで排他的に切り替えるモードを追加した。Low/Medium/High写真解像度、WASD移動、内部確認用パッケージへの同梱を確認。これはPhase 6暫定終了後の任意の画質向上試作であり、基準PC受入・測量済み高さ・外部公開を示さない。詳細は[駅東口LOD2統合記録](STATION_LOD2_INTEGRATION.md)。

## 入口とデータ

- 入口: `viewer/citywide-v1.html`。Three.jsを `viewer/vendor/three/` から読み込む。ブラウザ側にPython、Blender、CDN、APIキーは不要。開発用にはプロジェクトルートで `python -m http.server 8767 --bind 127.0.0.1` を起動する。HTTPS静的ホストでの実配備は未試験。
- 近景建物: `data/derived/fukushima-citywide-lod1-glb/tileset.json`。公式PLATEAU福島市2025 LOD1由来191 GLB、168,741棟、2,857,740三角形、163,288,384 B。DEM5A代表点標高がない11棟は3D化しない。LOD1は写真品質のLOD2ではない。
- 補完建物: `data/derived/fukushima-citywide-osm-buildings-glb/tileset.json`。既存Geofabrik東北OSM PBFの建物wayから、公式PLATEAUソース212メッシュ外の15,536件を抽出。DEM5A地表高がある15,531件を248 GLB、184,869三角形、11,092,040 Bに変換。建物階数タグ41件は階数×3m推定、残り15,495件は6mの概略推定であり、公式LOD1とは別の茶色いレイヤー。地表高欠損5件は3D化しない。relation-only建物や公式メッシュ内の局所欠損は未収録。
- 遠景建物: `data/derived/fukushima-citywide-far-glb/tileset.json`。同じ168,741棟を50mセルの概略街区33,286個に集約した191 GLB、332,860三角形、18,212,944 B。個別建物の公式足形・高さとして使わない。
- 地形: `data/derived/fukushima-citywide-terrain-glb/tileset.json`。国土地理院DEM5A由来872 GLB、1,695,408三角形、133,287,128 B。市境と交わる要求926タイルのうち54タイルは未公開。39,883頂点は標高欠損で、メッシュを張らず空白のままにする。道路面高を表さない。
- 道路: `data/derived/fukushima-citywide-roads-v1/tileset.json`。Geofabrik東北OSM PBFから抽出済みの福島市道路をEPSG:6677で1km分割。659タイル、227,218表示線分、215,903ノード。DEM5A地表標高は215,016ノードで得られ、887ノードは不明。道路幅はクラス推定、道路面高・合法走行可能性は `null`。橋・トンネルは地表塗りをしない。
- 検索: 同ディレクトリの `search_index.json`。OSM道路名183件の代表線分上の点と緯度経度入力。建物名検索は未収録。
- 読取API: `viewer/geoengine-citywide-api.js` の `CitywideRoadProvider`。タイルと最寄り道路を読み、出典・幅品質・地表高・道路面高不明・衝突未準備を返す。車両物理は含まない。
- 内部確認パッケージ: `dist/citywide-v1-preview/`。必要なHTML/JS/ローカルThree.js/GLB/道路JSON/出典文書、元データのソースマニフェスト、測定証跡とWindows起動ファイルの計2,191ファイル、約465 MBを複製。`preview_manifest.json` に全ファイルのSHA-256と受入未完了の状態を記録。公開許可を意味しない。

## 検証済み

1. `python -m unittest discover -s tests -v`: 最新の全52件成功。架空fixtureは実データとは表示しない。
2. `python scripts/audit_citywide_release.py`: 公式近景191、OSM補完248、遠景191、地形872、道路659の計2,161ファイルのサイズとSHA-256を全件確認。GLBのX東・Y=T.P.高さ・Z南を全件確認。OSM補完の原本way ID・ODbL・高さ品質・公式メッシュ外指定を全件照合。道路227,218線分の品質フラグと共有境界ノード5,602件、検索名183件の実線分上配置を確認。地形の隣接境界54,087頂点ペアの投影座標を2mm以内で確認し、高さのある52,672ペアは1cm以内一致。1,415ペアは両側欠損。結果は `data/derived/fukushima-citywide-release-audit.json`。
3. 開発PCのChrome 156 / NVIDIA GeForce RTX 3060で駅周辺の公式緑色建物・地形・道路の重なり、地上視点、国道13号検索の郊外地形、道路追従のタイル境界通過、タイルの読込・解放を目視確認。公式メッシュ外の座標37.66058, 140.54173では茶色のOSM補完3,298棟を9タイルから表示し、読み込み失敗・コンソール警告・エラー0件。実機の継続運用合格とは別。
4. `viewer/citywide-v1.js` と `viewer/geoengine-citywide-api.js` の構文チェック成功。読取APIは実データの駅付近で最寄り道路を返し、道路面高 `null`・衝突未準備を確認。
5. 10分測定画面の開始・終了とJSON保存を確認。開発PCで行った36秒の試験は **1920×919、RTX 3060、画面操作環境で約1fpsを記録**した。ブラウザ制限が疑われるため、基準PCの30FPS判定に使用しない。測定JSONは解像度、GPU、p95/p99、100ms超、約1秒周期の長いフレーム、道路追従距離・境界通過を記録する。
6. 福島市公式サイトによる2025年度までのLOD1整備範囲は都市計画区域229km²のうち174.6km²。市域全体の公式建物を収録したと表示しない。OSM補完は公式ソースの3次メッシュコードで大まかに除外し、詳細なカバレッジポリゴン照合ではない。[出典・加工記録](CITYWIDE_ATTRIBUTION.md)を参照。
7. 内部確認パッケージの全2,180ファイルをコピー後にSHA-256照合。`http://127.0.0.1:8767/dist/citywide-v1-preview/viewer/citywide-v1.html` をChromeで開き、公式建物/道路/地形の読込78タイル・失敗0・コンソール警告/エラー0を確認。CDNや作業用Python/Blenderへのブラウザ依存はない。

## 2026-11-01 受入検証の自動化

`viewer/citywide-v1.html?benchmark=1` はOSM道路タイル読込後に1280×720・軽量画質の10分道路追従を自動開始し、JSONの自動保存を試みる。JSONには有効測定条件と平均30FPSの暫定判定を追加した。GPU文字列だけではI-RIHA101本体を証明できないため、`v1_0_acceptance_complete` は常に偽のままにする。短時間の `?benchmark=smoke` で自動開始・8秒後の初回保存、1280×720、道路追従97.8m・境界1回、読込失敗0を確認。繰り返しの保存がChromeに抑止されたため、画面上でJSON全体を確認・コピーできる経路も設けた。画面操作環境で約1秒周期の制限疑いがある測定は基準PC性能に利用しない。

`scripts/check_citywide_survey_anchors.py` はJGD2011/EPSG:6668・T.P.と宣言した異なる実測2点以上だけを受け付け、OSM道路中心線または公式PLATEAU建物外形との水平差、DEM5A裸地地表高との差を別々に報告する。道路面高と建物基礎高は認証しない。4件の追加テストを含む全50件成功。実測アンカー入力は未入手で、現地照合は未実行。詳細は[受入手順](V1_ACCEPTANCE_PROCEDURE.md)。

## 2026-11-01 Python不要の測定PC起動

`start_citywide_benchmark.cmd` と `serve_citywide_preview.ps1` を内部確認パッケージに追加。Windows標準PowerShellのTCPサーバーがコピー済みフォルダーだけをループバックで配信し、既定ブラウザの10分測定画面を開く。**テスト済み:** 開発PCでPythonなしの起動、HTML/JS/JSON/GLBのGET 200、存在しないファイルの404、親フォルダー参照の403、Chromeで8秒測定完走・ページエラー0、全50件のユニットテスト。**未テスト・TODO:** 別のWindows PCとEdgeでの起動、基準PC10分性能、実測点照合、HTTPS公開配備と配布条件。ローカルPowerShellサーバーは内部測定用のみ。

## 2026-11-01 別PCの10分測定

利用者提供の[測定JSON](evidence/geoengine-citywide-2026-10-31T21-57-31-614Z.json)を原文のまま保存。SHA-256は `9234f120812310fdca3ac280beb9433d3367fb7ce8b1864a08842061d9646ac1`。Chrome 156 / WebGL報告GPU **Intel HD Graphics 4000**、1280×720・軽量、600.47秒の自動完走。35,929フレーム、平均59.82 FPS、p95 16.9ms、p99 18.4ms、最大133.6ms、50ms超7回・100ms超2回。背面化0回、タイル読込失敗0回、道路追従7,207m・境界通過10回、読込229件・解放153件。JSONの `valid_measurement` は真、30FPS条件は真、総合結果は `non_baseline_gpu`。別途利用者が提示した構成画像には **NEC LaVie LL750/LS6R（PC-LL750LS6R）/ Core i7-3630QM / RAM 16 GB DDR3-1600 / Lexar SSD 480 GB / Intel HD Graphics 4000** と記載され、GPUはJSONと一致する。OS欄のWindows 10 Pro 64-bitには「過去確認」とあるため現在のOSの独立確認とはしない。Windowsのデバイス名は未取得。指定基準PC I-RIHA101 / UHD Graphics 770 / RAM 8GBの試験とはみなさず、v1.0受入完了とはしない。**TODO:** 基準PCで同条件の10分測定、実測アンカー2点、権利・公開条件の確認。

## 2026-11-01 測定PCへのコピー検査

`verify_citywide_preview.ps1` を追加し、`start_citywide_benchmark.cmd` が起動前に `preview_manifest.json` の全ファイルの有無・長さ・SHA-256を照合する。目録の重複・不正パスや、測定結果JSON以外の余分なファイルを拒否し、検査失敗時は測定サーバーを起動しない。測定結果が同じフォルダーに保存されても再起動できるようにした。PLATEAU 212 GML、DEM5A、OSMの元データソースマニフェストを内部確認パッケージに同梱した。**テスト済み:** 正常な小型コピーと測定結果JSONを含むコピーの通過、同じ長さの改変・欠損・無関係な余分ファイルの拒否、全52件のユニットテスト、開発PCの実パッケージ全件照合。**未テスト・TODO:** 更新版のコピー先PCでの再起動、基準PC性能、HTTPS配備、実測点照合、配布条件の確定。SHA-256はコピー破損検知用で、目録自体の発行者認証ではない。

## 2026-11-01 別PCの10分追試

利用者提供の[追試JSON](evidence/geoengine-citywide-2026-11-01T05-33-54-406Z.json)を原文のまま保存。SHA-256は `1751189f8efca8e0a4e58bd45381773f8900616568e10127910acdc31e33aa3b`。記録時刻は2026-11-01 14:33 JST。Chrome 156 / WebGL報告GPU **Intel HD Graphics 4000**、1280×720・軽量、600.2秒の自動完走。35,919フレーム、平均59.84 FPS、p95 16.8ms、p99 16.8ms、最大200.4ms、50ms超2回・100ms超1回。背面化0回、タイル読込失敗0回、道路追従7,202.6m・境界通過10回、読込227件・解放152件。JSONの全測定条件は真、`valid_measurement=true`、平均30FPS条件は真、総合結果は `non_baseline_gpu`。前回と同じGPU名だが、JSONだけではPC本体の同一性は確認できない。指定基準PC I-RIHA101 / UHD Graphics 770 / RAM 8GBの試験とはみなさず、v1.0受入完了とはしない。測定JSONが `F:/citywide-v1-preview/` 直下に保存されていたため、旧コピー検査器では次回起動時に余分なファイルとして拒否されることを再現し、更新版でこの形式の結果JSONだけを許容した。

## 2026-11-02 職場ノートPCのEdge測定

利用者提供の[測定JSON](evidence/geoengine-citywide-2026-11-02T09-52-57-038Z.json)を原文のまま保存。SHA-256は `1691e4e5978f79ca101e7493e89fa3505f1dfc9619232885f4e7e0ebabe329d6`。記録時刻は2026-11-02 18:52 JST。Edge 156 / WebGL報告GPU **Intel UHD Graphics (PCI ID A721)**、1280×720・軽量、600.21秒の自動完走。36,023フレーム、平均60.02 FPS、p95 16.8ms、p99 17.1ms、最大50.0ms、50ms超0回・100ms超0回。背面化0回、タイル読込失敗0回、道路追従7,202.3m・境界通過10回、読込230件・解放153件。JSONの全測定条件は真、`valid_measurement=true`、平均30FPS条件は真。利用者によると職場の電算室のノートPCで、CPU・メモリ・デバイス名は不明。

[IntelのGPU ID一覧](https://dgpu-docs.intel.com/overview/supported-hardware/i915-driver-gpus.html)ではA721はRaptor Lake-Pの「Intel UHD Graphics」であり、[i5-14500Tの公式仕様](https://www.intel.com/content/www/us/en/products/sku/236780/intel-core-i5-processor-14500t-24m-cache-up-to-4-80-ghz/specifications.html)はUHD Graphics 770 / Device ID 0x4680を示す。したがって今回のGPU報告は指定基準PCのGPUと一致せず、JSONの `result=non_baseline_gpu` を妥当と判定する。PC本体の同一性はGPUだけでは証明できない。**今回のEdge測定は別PCの性能証拠であり、I-RIHA101の受入試験ではない。**

## 未検証・TODO

公開前の出典・再配布条件について、公式のPLATEAUポリシー、GSIタイル一覧、OSM/ODbL表示指針、国土数値情報N03-2026個別ページを照合した。[権利確認記録](CITYWIDE_RELEASE_RIGHTS_REVIEW.md)に確認済み条件と残る判断を記録。N03-2026はCC BY 4.0と確認したが、福島市2025 PLATEAU個別特記、オフラインDEM5A派生GLB、OSM派生データ公開方式は未確定のため外部公開は保留する。

1. **受入必須**: I-RIHA101（i5-14500T / UHD Graphics 770 / RAM 8GB）でChrome/Edgeを前面表示し、レンダー領域1280×720・軽量モードで10分の道路追従を実施する。測定JSONの平均≥30FPS、p95、最大停止、50/100ms超、GPU名、タイル交換と画像品質を確認する。ブラウザ制限疑いのある測定は無効とする。結果が不合格なら近景・地形・遠景の表示半径やメッシュ密度を調整して再測定する。
2. **受入必須**: 測量済みの少なくとも2点で道路・建物位置とT.P.標高を現地照合する。現状のDEM5Aは地表高であり、道路面や建物基礎高ではない。
3. **公開前必須**: 福島市2025 PLATEAUデータセット固有のライセンス、国土地理院地形タイルの加工・再配布条件、OSM ODbLの派生データ義務を確認し、配布パッケージに原典・変更内容・必要な表記を入れる。PLATEAU一般案内はオープンライセンスを列挙するが、当該データセットの特定条件をこれだけで確定しない。
4. 地形の未公開54タイルと39,883欠損頂点を正規の標高ソースで補うか、欠損領域として明示し続ける。未対応の座標系・鉛直基準を自動変換しない。
5. HTTPS静的ホスト、クライアント8GB実機のメモリ・帯域・長時間安定性、Driving Simulator側からのAPI利用を実配備で確認する。現在はローカルHTTPのみ。
6. OSM補完の高度品質を向上するには、建物高さ・階数の信頼できる原典が必要。現状15,495件は6m推定。relation-only建物と公式メッシュ内の局所欠損も未対応。

## 再生成・監査

PowerShellの例。Pythonは開発PCの3.11、GLB生成はBlender同梱Pythonで実行する。建物JSON原本とDEM5A・OSM取得物が既にあることを前提とする。未承認の1GB超PLATEAU一括取得は行わない。

```powershell
python scripts/build_citywide_road_tiles.py --source-index data/derived/fukushima-road-source-snapshot/index.json
python scripts/build_citywide_search_index.py
python scripts/build_citywide_osm_buildings.py
python scripts/build_citywide_terrain_meshes.py
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_export_citywide_lod1.py --
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_export_citywide_far.py --
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_export_citywide_osm_buildings.py --
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_export_citywide_terrain.py --
python scripts/audit_citywide_release.py
python scripts/package_citywide_preview.py
python -m unittest discover -s tests -v
python -m http.server 8767 --bind 127.0.0.1
```

ローカルURL: `http://127.0.0.1:8767/viewer/citywide-v1.html`。v0.1 HTMLの操作系・車両挙動・エンジンは変更していない。
