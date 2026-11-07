# M1 — Implementation status

## 2026-10-31 市全域LOD1の188件差分解消

`data/derived/fukushima-citywide-lod1/parser_gap_report.json` で、PLATEAUカタログ168,759件と実GMLの `bldg:Building` 168,759件が一致し、旧パーサーの採用168,571件との差188件を特定した。既存のEPSG:6677投影式で再計算すると188件すべてに有効な水平LOD1フットプリントがあり、面積1.01〜2.00㎡、高さ2.0〜6.1m、既存処理範囲内だった。旧パーサーの2㎡未満除外が原因で、CRS変換やLODの取り違えはない。公式LOD1に対する面積下限を0.01㎡へ変更し、合成フィクスチャの回帰テストを追加した。

旧出力を保持して `data/derived/fukushima-citywide-lod1-v2/` に全212ファイルを再処理。解析168,759件、境界内または交差168,752棟、境界外7棟、境界クリップ5棟、無効フットプリント0棟、カタログとの差0件。191個のJSONタイルを出力し、タイルごとのSHA-256・サイズ・件数を再照合した。既存の225枚のGSI DEM5Aから168,741棟のT.P.基部地形高を補間し、11棟は欠損のまま。Pillow 12.0でも動くよう地形画素の読み取りを修正した。プレビューは完成版タイルに切り替えた。

検証済み：ルートunittest 45件成功、JavaScript構文チェック成功、全191タイルの件数・SHA-256一致。IABの狭幅プレビューで建物168,752棟・標高168,741棟の表示、駅周辺20タイル・37,387棟の3D描画、ブラウザーconsole error/warn 0件。未検証・TODO：基準PCのFPS/長時間性能、広幅画面と他ブラウザー、測量との位置照合、市全域GLB化、PLATEAU個別データセットの再配布条件確認。以下の2026-10-30各節は、その時点の履歴を記録する。

## 2026-10-30 福島市公式境界・市域OSM道路網

国土交通省N03-2026福島県ZIP（9,802,702 bytes）から福島市コード07201を抽出し、簡略境界と全精度境界を作成。測地面積767.716km²、1成分。元ZIPは `data/raw/N03-20260101_07_GML.zip`、SHA-256 `8d002eb07f13044cdb7f0e5e6e28a677ce1096a4a3cc5621e8b2417c924e4c61`。従来のプレビュー境界とメタデータは `modules/city-boundary/data/source-backups/preview-20261030/` に保存。

Geofabrik東北OSM PBF（311,346,543 bytes）を `data/raw/tohoku-latest.osm.pbf` に保存。PBF複製時刻は2026-10-29T21:21:26Z、SHA-256 `fb96c0e3b8dd3c7b03cad66fd2bd619271483712ee9bc33f8e19895bde33ccb5`。正式境界でPBFの1,169,007 wayを調べ、福島市内の道路22,789 way／25,210線分を143個のEPSG:4326タイルへ抽出した。出力は `modules/city-boundary/data/roads/index.json`。マニフェストには境界品質、OSMデータ時刻、PBFハッシュを記録する。駅周辺の画面では市内抽出済と表示し、表示範囲の925線分を確認。

検証：ブラウザーで正式境界・面積・市域道路カバレッジを表示。駅周辺でOSM道路を925線分表示し、Console errorなし。ルートunittest 37件、city-boundary pytest 16件成功。**未完了：市全域の建物・地形3Dタイル、基準PC性能、道路収録率・位置精度の現地照合、配布ライセンスの確認。**

## 2026-10-30 福島市全域PLATEAU LOD1建物データ処理

先行容量調査で1GB超の明示承認を得た後、公式PLATEAU空間検索で得た福島市2025年度のCityGML 212ファイルをすべて取得。合計1,976,796,597 bytes。各ファイルのサイズ・SHA-256をダウンロード時に検証し、ソースマニフェストへ保存した。元データは `data/raw/plateau/fukushima_citywide_2025/`。

`scripts/build_citywide_lod1_tiles.py` を追加。正式N03-2026境界、EPSG:6677（JGD2011平面直角座標系IX系）を使用し、境界内のLOD1建物を1kmグリッドに割り当てる。処理はGMLファイル単位でSQLiteへ記録し、再開可能。境界を越える建物はポリゴンをクリップし、垂直基準・基部標高が不明なため `null` としている。出力は `data/derived/fukushima-citywide-lod1/tileset.json` と191個のJSONタイル、計168,564棟。全ファイル処理済みである一方、カタログ掲載LOD1件数168,759との差188件は既存パーサーからフットプリントを抽出できなかったため、マニフェスト状態を `complete_with_gaps` として明示。境界外の抽出建物7棟、境界クリップ5棟、無効フットプリント0棟。

検証：ソース212ファイルのサイズ・SHA-256一致、ファイル処理完了、タイル件数・ハッシュを記録。ルートunittest 41件成功。**GLB化・地形標高の建物への適用・188件の差分診断・基準PC性能は未実装/未検証。** PLATEAU個別データセットの再配布条件確認も必要。

## 2026-10-30 市全域LOD1ブラウザープレビュー

`viewer/citywide-lod1-preview.html` を追加し、`viewer/citywide-lod1-preview.js` がEPSG:6677のタイルを画面範囲に合わせて読み込む。最大36タイル、30タイルのLRUキャッシュ、ズーム13以上で読込、3D押し出し表示、建物クリック時の高さ/出典表示を実装。境界・道路ページにもプレビューへのリンクを追加。開発ルートHTTPサーバー上の `http://127.0.0.1:8767/viewer/citywide-lod1-preview.html` で確認できる。

検証：IABの狭幅画面でページタイトル・191タイル/168,564棟のデータ状態・地図を表示。福島駅周辺ボタンで20タイル/37,364棟を読み込み、建物表示チェックをOFF/ONして件数が0/37,364に切り替わることを確認。ブラウザーconsoleのerror/warnは0件。ソースJS構文チェック成功、ルートunittest 41件成功。デスクトップ広幅・基準PCでの長時間性能、建物ポップアップの個別ヒット、他ブラウザーは未検証。

## 2026-10-30 市全域LOD1とGSI DEM5A地形の統合

`scripts/prepare_citywide_building_dem.py` を追加。建物代表点での5m DEM5A補間に必要な225枚だけを国土地理院から取得（理論最大67,500,000 bytes）。MapLibre用Terrain-RGBへ変換し、各建物JSONにT.P.基部地形高を記録した。168,553棟で標高サンプル成功、11棟はDEM5A欠損のためNULLのまま。タイル一覧と各タイルのSHA-256/バイト数も更新した。Viewerはズーム15以上でDEM5A地形と基部標高がある建物を表示し、クリック時にT.P.基部高を表示する。

検証：ブラウザーで20地形タイル・37,363棟を描画。代表建物のポップアップで建物高24.9m、基部標高T.P. 71.76m、DEM5Aサンプル品質を確認。表示ON/OFF、ブラウザーconsole error/warn 0件。ルートunittest 43件成功、Terrain-RGB符号化は0.1m精度の往復テスト済み。DEM5Aの建物内補間は頂点平均点1点のみで、基礎の形状や地盤傾斜は表さない。Terrain-RGB表示用の欠損70613画素は描画のため標高0mにエンコードされるが、建物サンプル欠損はNULLのまま。基準PC性能と測量照合は未検証。

## 2026-10-30 LOD1パーサー差分診断（実行待ち）

`scripts/diagnose_citywide_lod1_gaps.py` を追加。既存の全GML・ソースマニフェストを読み、カタログLOD1件数、実際の `bldg:Building` 要素数、既存パーサー採用数を分けて比較し、未採用IDをCRS/座標、水平リング、面積・範囲、高さなど既存条件に沿って分類する。レポート予定先は `data/derived/fukushima-citywide-lod1/parser_gap_report.json`。未対応の形状を自動変換せず、理由を分類できないものは `unclassified_parser_disagreement` として残す。

この作業環境ではPythonランチャーが登録済み実行環境を検出できず、実GML全件の診断もルートunittestも未実行。診断コードと合成フィクスチャ（実Fukushimaデータではない）の分類テストを追加済みだが、コードの実行検証待ち。ユーザーPCでは、既に確認されたPython 3.11を使い、リポジトリ直下のPowerShellから `& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" -m unittest discover -s tests -v` と `& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" scripts\diagnose_citywide_lod1_gaps.py` を順に実行する。診断レポート作成、188件の原因確定・回収は未完了。

## 2026-10-30 市全域PLATEAU建物データの容量調査

`scripts/plan_citywide_plateau.py` で公式2026市境界に対するPLATEAU CityGML検索を実施。福島市コード07201・2025年度は212ファイル、LOD1合計168,759件、1,976,796,597 bytes（約1.84 GiB）。当時の容量調査結果。後続の明示承認後に取得・処理した実績は、本書「福島市全域PLATEAU LOD1建物データ処理」を参照。

ルートテストは新規3件を含む37件成功。空間検索は国交省PLATEAU APIで実行。市全域ファイル総量は境界の外接矩形に基づく検索結果で、境界外メッシュの可能性があり、実際に必要な容量と一致するとは限らない。

## 2026-10-30 STEP 1-2 city-boundary道路表示の復旧

貼り付け引継ぎにある `modules/city-boundary` を実際に確認。`py.exe` はこの実行環境で登録済みPythonを検出できず、`py -0p` は `No installed Pythons found!`、`py scripts/build_roads.py --overpass-station` はスクリプトに入る前に終了コード112となった。したがって利用者が見た `Python` 表示の内部原因はこの環境では再現できていないが、現環境の直接原因はPythonランチャー設定。CLIに起動ログ、Python実行ファイル・処理モード・境界状態、Overpass接続先と応答件数、HTTP/通信/JSON/内部失敗の区別を追加し、Overpass `--endpoint` 指定を実装した。

Overpass標準URLはHTTP 502、別公開URLは読み取りタイムアウトとなり、今回の再取得には失敗。保存済み `data/raw/fukushima_osm_1km.json` はOpenStreetMap Map APIのURLを含む実データ（取得日時はJSONに記録なし）なので、これを `--osm-json` で再利用し、暫定市境界で399 OSM way / 418線分を抽出、4つのEPSG:4326地域タイルを生成した。Manifestは `coverage: local_json_import` と原典URLを保持する。駅表示のChromeでは、表示範囲に応じた4タイル取得と226線分の描画を確認。OSM出典・ODbL帰属と暫定境界の警告を表示した。

Windows実行時に既存 `data/roads` フォルダーの名前変更が `WinError 5` で拒否されたため、出力を不変の世代別フォルダーへ書き、最後に `index.json` のみ置換する方式へ変更。既存世代は残し、ブラウザーの読込中にフォルダーを移動しない。ブラウザー側は世代相対パスを個別エンコードして取得する。保存済み1km OSM JSONを新方式で再生成し、Chromeで4タイル・226線分の再表示まで確認した。

当時の検証：ルートの `python -m unittest discover -s tests -v` 相当をCodex Python 3.12.14で実行し34件成功。モジュールpytestは15件成功。Chrome表示は開発環境だけで、Edge・基準PC性能は未検証。後続の公式境界・市域PBF取込結果は本書冒頭の記録を参照。詳細手順は `modules/city-boundary/README.md`。

## 2026-10-30 Phase 2 駅東口1km連続プレビュー

OSM地図APIと保存済みPLATEAU CityGMLから道路366線・建物1,849棟の1km地図を生成。日本平面直角座標系IX系のGRS80横メルカトルへ投影し、100m（100個）・250m（16個）・500m（4個）のGLBタイルと共有道路境界ノードを出力した。さらに公式PLATEAU道路LOD1の500面と国土地理院DEM5A地表高を統合し、橋・トンネルのOSMタグを保持。道路、地面、建物基部を地表高へ沿わせた。デモ移動は区域外と橋・トンネル・別レイヤを避ける1,402.93m。294点の経路QAで候補路面・公式道路範囲・DEM地表高の欠落0。中心200mの写真参考LOD2は比較用に残し、描画外観を初期表示とした。[1km表示画面](../viewer/wide-preview.html) と読み取り専用道路API、10分計測JSON保存を実装。34件の自動テストと開発環境Chromeで道路視点3設定・API・経路移動を確認。実路面高、車線、合法通行、車両衝突は未対応。測量アンカー・基準PCの10分計測・市全域も未完了。詳細は [1km実装記録](PHASE2_1KM_IMPLEMENTATION.md) と [実道路データ統合記録](ROAD_DATA_INTEGRATION.md)。

## 2026-10-30 Phase 2 駅東口タイル試作

近景12壁面を元写真のUV領域から個別に描き直した `city_photo_crisp.blend/glb` を出力。全56棟のアトラス描き直しを基に、LOD2形状は維持した。元の描き直しPNGを保持し、表示用の四角形壁9面はJPEG品質94・4:4:4で再符号化。GLBは25,301,644バイト。新規画像には細部のAI推定が含まれ、ほかの壁と航空写真にはぼけが残る。詳しくは `docs/FACADE_REDRAW.md`。

この版の200m四方を100m四方の4 GLBへ分割し、道路の境界ノード付きJSONと `tileset.json` を生成した。`viewer/tiled-preview.html` で必要タイルの読込・先読み・解放と4タイル自動移動を確認。23件のテストが通過し、隣接する4境界の幾何/UV、14道路境界ノードの座標/IDが一致。4 GLB合計29,632,624バイトで、画像重複のため単一GLBより大きい。正式CRS・市全域・DEM・基準PCの長時間測定は今後。仕様と試作結果は `docs/PHASE2_TILING_SPEC.md`。

## 2026-10-30 Phase 1 軽量化・計測追加

既存の元写真GLBと全棟描き直しGLBを保存したまま、56棟の描き直しアトラス36枚を長辺1536pxへ縮小してJPEG品質88で再符号化。`city_photo_optimized.blend/glb` を別名出力した。GLBは23,522,456→17,760,400バイト、画像画素101,191,301→73,068,269、RGBA8+mip画像メモリ**概算**514.7→371.6MiB。全59メッシュの座標・UV・indexハッシュは一致。全景同一カメラ画像の平均画素差は各色約0.2/255、道路視点では最大約0.68/255。`viewer/performance-lab.html` で元写真/描き直し/最適化を1版ずつ切替し、30秒の静止/移動計測とJSON保存を実装した。開発環境は**RTX 3060**・Chromium 156・1280×720・倍率1で、3版とも移動60FPS、p95 16.8ms、50ms超0。60Hz上限に達しているため性能差は不明。基準PCの測定ではない。近接壁には元の描き直し画像由来のぼやけが残る。既存13件＋新規3件の16テスト通過。詳細は `docs/PHASE1_PERFORMANCE.md`。Phase 2のタイル化仕様案は `docs/PHASE2_TILING_SPEC.md`。


## 2026-10-29 実施結果

**M1の実データ取得・LOD1/LOD2変換・建物と地面の公式写真付きBlender作業ファイルとGLBの出力を実行済み。** 測量点による位置精度、道路勾配、低スペック実機性能、配布ライセンスの個別確認は残る。v1.0完成ではない。

- スターターZIPを `E:\GeoEngine` に展開。元フォルダは空で、Git管理はまだない。
- Python 3.12.14の `-m unittest discover -s tests -v` は13件通過。`scripts/run_m1_demo.ps1` による架空 `dist/demo/map.json` のbuild/validateも成功。
- Blender 3.1.2で架空 `dist/demo/city.glb`（3,220バイト）を出力。建物・道路の2メッシュ、GLB内の `SYNTHETIC_TEST_FIXTURE`、付随する `dist/demo/city.provenance.json` のSHA-256一致を確認。
- [PLATEAU CityGML API](https://docs.plateauview.mlit.go.jp/datasets/citygml/)で福島市コード `07201`、整備年度 **2025**、仕様 `5.0` を確認。建物GML `56405306`（30,293,767バイト・LOD1 1,628件）と `56405307`（57,423,445バイト・LOD1 1,809件）、合計87,717,212バイトを `data/raw/plateau/` に取得した。`docs/evidence/plateau_catalog_fukushima_2025_observed.json` は取得前のメタデータ抜粋。
- 保存したAPIメタデータを `fetch-plateau --index-file docs/evidence/plateau_catalog_fukushima_2025_observed.json --dry-run` に通し、上記2ファイルが選択されることを確認。
- 標準の制限環境では `WinError 10013` だったが、正規の権限経路で公式OverpassとPLATEAUから取得できた。OSMの143要素を `data/raw/fukushima_osm.json` に保存。
- 実データで `dist/real/fukushima-east/map.json`（道路70本・PLATEAU建物56棟・LOD2面1,790枚）をbuild/validate。GMLの外観情報から対象建物の公式JPEG 56枚（9,691,772バイト）を取得し、屋根・壁1,734面のUVを照合した。福島市PLATEAU-Ortho 2024の30タイルから対象区域と周辺30mの地面画像を作成。Blenderで写真をパックした `city.blend`（14,291,176バイト）と `city.glb`（11,658,928バイト、6,604三角形）を生成。GLB内の品質表示と付随JSONのSHA-256一致を確認した。
- `dist/real/fukushima-east/qa_overlay.png` でOSM道路・建物とPLATEAU建物を重ねた。200m四方のラスタ比較でOSM建物面積の93.0%、PLATEAU建物面積の77.4%が重なる。**測量点による精度検証ではなく、両データの建物収録範囲も異なる。**
- `viewer/blender-preview.html` で写真付きGLBを直接読み込み、建物56棟・OSM道路データ70本・LOD2面1,790枚（写真付き1,734枚）を3D表示できた。道路の見た目は2024年航空写真で、線データはJSONに保持。`viewer/preview.html?map=real` はJSONから簡易表示する開発用画面として残す。BlenderのWorkbenchレンダー `city_blender_preview.png` も目視確認した。
- 写真付き `.blend` をBlender 3.1.2で再読込し、建物56枚＋航空写真1枚のパック済み画像57枚、UVメッシュ57個、航空写真地面オブジェクトを確認した。元建物JPEGの画素をRGBAで展開した理論値は約363 MBで、実機GPUメモリ使用量は未測定。
- ぼけを抑えるため `city_sharp.blend`・`city_sharp.glb` と1920×1080の全景・近景画像を生成。BlenderのLayoutは写真表示／カメラ視点、Viewport AA 16・Render AA 32。ブラウザはMSAA、最大2倍の描画解像度、テクスチャ異方性最大8を高精細の初期値とし、軽量表示へ切替可。写真の元解像度を超える細部の復元はしていない。
- `viewer/blender-preview.html` にPC-9801VX風の16色切替を追加。同一視点の写真表示との往復、GLB読み込み成功、WebGL警告・エラーなしをアプリ内ブラウザで確認し、`compare_photo.png` と `compare_16color.png` を保存。輪郭の見え方は目視比較のみで、視認性の利用者評価、実機性能、ハードウェア忠実度は未検証。
- 写真を参照して1棟を再制作する `scripts/blender_rebuild.py` を追加し、`city_rebuilt.blend`・`city_rebuilt.glb`（1,292,236 bytes）・`city_rebuilt_preview.png`・新規素材PNG 6枚をBlender 3.1.2で出力。対象建物はLOD2形状に窓48枚・屋上設備3基を追加。GLBを再解析し、画像はPNG 6枚のみで元の公式JPEGを含まないことを確認。ブラウザで「対象の建物を見る」から同視点の写真版と再制作版を往復し、WebGL警告・エラーなし。近景画像2枚を保存。詳細化は1棟のみで、周辺の外観、窓配置、路面・道路幅は近似。写真並みの品質、実物一致、I-RIHA101実機性能は未検証。
- 全56棟へ広げる `scripts/rebuild_styles.py`・`scripts/rebuild_streets.py`・`scripts/blender_rebuild_all.py` を追加。写真56枚を一時的に解析して壁色を4階調へ分類、窓候補21壁面を検出し、見た目の連続性のため推定窓模様を104壁面へ配置。近景中心に立体窓177枚。道路70本を車道・歩行者道・階段平面跡・道路縁に分けてバッチ化。`city_rebuilt_all.blend`・`city_rebuilt_all.glb`（2,486,524 bytes）・全景画像・新規素材PNG 20枚をBlender 3.1.2で生成し、ブラウザで写真版との全景・近景切替とWebGL警告・エラーなしを確認。元JPEGは参照専用で出力に埋め込まない。窓の推定、街路設備、道路幅・走行領域、写真同等の品質、低スペック実機性能は未検証。
- ユーザー意図に合わせ、汎用の窓模様から写真準拠の壁面個別描き直しへ変更。写真UV領域を壁面正面図に展開し、1面の窓・入口・電柱類の配置を確認したうえで画像生成による鮮明化を試作。`city_photo_redrawn.blend`・`city_photo_redrawn.glb` を生成し、元写真版と同一カメラでBlender描画比較。ブラウザでも1面を切替確認。画像生成による細部の推定と、残りの壁が未対応であることを明示。手順・出典・品質範囲は `docs/FACADE_REDRAW.md`。
- 2026-10-30に写真準拠の描き直しを56棟全体へ拡張。公式JPEGのUVアトラス56枚を1枚ずつ描き直し、元の島配置へ登録して、写真付き壁1,271面・屋根463面に反映。詳細版1壁面を重ねた `city_photo_redrawn_all.blend` と `city_photo_redrawn_all.glb`（23,522,456 bytes）をBlenderで出力。GLBは6,194三角形で元版と同数、SHA-256サイドカー一致。ブラウザで全景と代表壁面を表示し、警告・エラーなし。判読できない細部はAI推定であり、地面の航空写真、現地照合、低スペック実機性能は未対応。詳細は `docs/FACADE_REDRAW.md`。
- 実データで別の中心点・80m半径の `config/fukushima_station_east_offset.json` をbuild/validate。道路16本・建物44棟。

### 変更ファイル

`config/fukushima_station_east.json`、`config/fukushima_station_east_offset.json`、`scripts/geoengine.py`、`scripts/fetch_ortho.py`、`scripts/blender_export.py`、`scripts/blender_rebuild.py`、`scripts/rebuild_styles.py`、`scripts/rebuild_streets.py`、`scripts/blender_rebuild_all.py`、`scripts/qa_overlay.py`、`scripts/run_m1_demo.ps1`、`tests/test_geoengine.py`、`viewer/preview.html`、`viewer/blender-preview.html`、`docs/evidence/plateau_catalog_fukushima_2025_observed.json`、`README.md`、`PROJECT.md`、`docs/TECHNICAL_SPEC.md`、`docs/M1_STATUS.md`、`dist/demo/` と `dist/real/` の生成物。

取得処理は2025年度・市区町村コード・LOD1件数・公式URL・ファイルサイズを照合する。1ファイル150 MB超、合計1 GB超は停止する。GML変換は明示されたEPSG:6697/4979のみ受け付け、未知CRSや経緯度逆順を拒否する。GLBには品質・出典を埋め込む。

### 次の作業と実機測定

1. `data/raw/` の実ファイルは取得済み。ソースのSHA-256を下記に記録。PLATEAU個別データセットの再配布条件を確認し、公開前に出典表記を確定する。
2. 測量済みアンカーによる道路・建物の位置精度、実際の高さ・地盤標高を検証する。現在の重なりと3D表示は目視・ラスタの一次確認。
3. I-RIHA101（i5-14500T、RAM 8 GB、Intel内蔵GPU）でEdge/ChromeのバージョンとGPUを記録。1280×720の軽量設定で5分間操作し、平均FPS、最低FPS、フレーム時間p95、draw calls、三角形数、メモリ使用量、カクつき・クラッシュを測る。平均30 FPS以上は目標であり、達成の根拠はまだない。
4. M2以降で街路設備、地形勾配、写真と建物の年度差の照合、公式Converterとの形状比較を進める。道路参照APIの試作はできたが、Driving Simulatorの車両衝突・車線・交通規則に使うには検証が必要。

### 取得ファイルのSHA-256

| ファイル | SHA-256 |
|---|---|
| `data/raw/fukushima_osm.json` | `0775f914701108e0c4b0652a4c8f3686905dcc0e7766ea3d8fc41a75000e80f8` |
| `data/raw/plateau/56405306_bldg_6697_op.gml` | `33a544124e4324593131b8a8607acb815716faff3608ebde4181f3b0f7e910db` |
| `data/raw/plateau/56405307_bldg_6697_op.gml` | `360c4944fbc1532a2ce501c59867b6dfb4d89ccd15e546d09fab237baeadadf4` |

### 再現コマンド（開発PC）

`python` は開発PCのPython 3に読み替える。Windowsのこの環境ではCodex付属Python 3.12.14を使用した。

```powershell
python scripts/geoengine.py fetch-osm --area config/fukushima_station_east.json --output data/raw/fukushima_osm.json
python scripts/geoengine.py fetch-plateau --area config/fukushima_station_east.json --output-dir data/raw/plateau --dry-run
python scripts/geoengine.py fetch-plateau --area config/fukushima_station_east.json --output-dir data/raw/plateau
python scripts/geoengine.py build --area config/fukushima_station_east.json --osm data/raw/fukushima_osm.json --plateau data/raw/plateau --buildings-source plateau --output dist/real/fukushima-east/map.json
python scripts/geoengine.py validate --map dist/real/fukushima-east/map.json
python scripts/geoengine.py fetch-textures --map dist/real/fukushima-east/map.json --file-list data/raw/plateau/plateau_file_list.json --output-dir data/raw/plateau
python scripts/fetch_ortho.py --area config/fukushima_station_east.json --output dist/real/fukushima-east/ortho_ground.png
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_export.py -- --scene dist/real/fukushima-east/map.json --output dist/real/fukushima-east/city.glb --texture-dir data/raw/plateau --ortho dist/real/fukushima-east/ortho_ground.png --render-preview
python scripts/qa_overlay.py --map dist/real/fukushima-east/map.json --osm data/raw/fukushima_osm.json --output dist/real/fukushima-east/qa_overlay.png
python scripts/geoengine.py build --area config/fukushima_station_east_offset.json --osm data/raw/fukushima_osm.json --plateau data/raw/plateau --buildings-source plateau --output dist/real/fukushima-east-offset/map.json
python scripts/geoengine.py validate --map dist/real/fukushima-east-offset/map.json
python -m unittest discover -s tests -v
```

OSM取得元は `https://overpass-api.de/api/interpreter`。PLATEAUの検索URLとGML個別URLは `docs/evidence/plateau_catalog_fukushima_2025_observed.json` に記録。標準の制限環境では最初の取得コマンドが `WinError 10013` で失敗したが、正規の権限経路では同じコマンドが成功した。`qa_overlay.py` には開発PCのPillowが必要。

出典：[PLATEAUファイル検索API](https://docs.plateauview.mlit.go.jp/api/rest/operations/datacatalogcitygmlconditions/)／[OpenStreetMapの著作権・ODbL](https://www.openstreetmap.org/copyright)。`dist/demo/` は架空データであり、LOD1押出建物・推定道路幅だけを含む。

## Implemented and tested

- [x] CLI `scripts/geoengine.py` with `fetch-osm`, `fetch-plateau`, `build`, `validate`.
- [x] 200m-square AOI configuration (near Fukushima Station east entrance).
- [x] Overpass JSON ingestion; local-meter X-east/Z-south transformation.
- [x] Roads cropped at AOI boundaries, with **estimated width** based on highway class.
- [x] OSM polygon buildings; separate measured/tag-derived/fallback height quality.
- [x] CityGML2/PLATEAU `lod1Solid` 足形・高さと `boundedBy` 内のLOD2屋根・壁・地表面の抽出（架空fixtureと福島市2025実データで実行）。
- [x] CityGML外観情報の `app:imageURI` とリング別UVを抽出し、公式JPEGを56枚だけ取得・Blenderで貼付。
- [x] PLATEAU-Ortho 2024の30タイルを200m四方と周辺30mへ位置合わせし、GLBの地面に貼付。
- [x] Prefer PLATEAU LOD1 if available, otherwise OSM building approximations.
- [x] JSON provenance, schema, validation, synthetic end-to-end tests.
- [x] Blender background-mode `.blend`・GLB・Workbench画像の出力（実データでBlender 3.1.2実行検証済み）。
- [x] Browser preview of Blender-produced GLB（CDN接続が必要）。
- [x] Browser developer preview that opens map JSON as file selection (requires Three.js CDN).

## External systems / unverified

- [x] Real Fukushima OSM fetch: 143 Overpass elements acquired.
- [x] PLATEAU trial data-catalog API response format and 2025 metadata (ブラウザ確認)。
- [x] PLATEAU GML本体2件のダウンロード。
- [x] PLATEAU Fukushima 2025 LOD1 conversion with authentic CityGML (56 buildings in target AOI).
- [x] Blender実行とGLB出力（建物・航空写真付き実データGLB 11,658,928 bytes）。
- [x] 実GMLのLOD2屋根・壁・地表面1,790枚を抽出し、Blenderで三角化。
- [ ] Street/height georeferencing against two surveyed anchors; sloped roads.
- [ ] 街路設備、建物・航空写真の年度差確認、公式Converter/SDKとの形状比較。
- [ ] Low-spec I-RIHA101 FPS/VRAM/CPU testing.

## Remaining validation sequence

1. Re-run unit tests and synthetic `build`/`validate` after code changes.
2. Survey two or more known anchors and check road/building position against them.
3. Verify the dataset-specific PLATEAU license and redistribution terms before publishing derivatives.
4. Record real asset preprocessing time and FPS/frame times on I-RIHA101.
5. If additional CityGML structures are encountered, add regression tests rather than silently substituting geometry.

## Stop conditions

If actual PLATEAU GML geometry fails/coordinate system is unknown, report and stop; do not substitute synthetic 'real' data. If browser preview fails to import library on hospital network, plan local vendoring in M2 (no CDN dependency). Avoid publishing OSM derivatives without confirming license obligations.

## 2026-10-31 市全域 v1.0実装候補

現行の実装・受入判定は [CITYWIDE_V1_STATUS.md](CITYWIDE_V1_STATUS.md) に記録した。近景建物191 GLB（168,741棟）、遠景191 GLB、DEM5A地形872 GLB、OSM道路659 JSONタイルをEPSG:6677で統合し、`viewer/citywide-v1.html` でローカルThree.js表示、地域/道路名/座標検索、道路線追従、画質切替、10分測定JSONを実装。v0.1 HTMLは変更していない。

**テスト済み出力:** 近景・遠景・地形GLBと道路JSONの計1,913ファイル全件SHA-256/サイズ/GLB軸、道路227,218線分と共有ノード5,602件、地形共有境界54,087頂点ペア、検索183件。`data/derived/fukushima-citywide-release-audit.json` は合格。ユニットテスト46件成功。開発Chromeで駅/郊外/地上/追従を目視確認、コンソール警告・エラー0件。

**未テスト:** I-RIHA101の1280×720・10分で平均30FPS以上、測量済み2点の位置・標高、HTTPS配備、Driving Simulator側利用、特定PLATEAUデータセットとGSI/OSM派生データの再配布条件。開発PCの短時間計測は1920×919/RTX 3060かつブラウザ制限で約1fpsとなり、基準性能の判断には使わない。地形未公開54タイル、欠損39,883頂点、地表高不明の道路ノード887件は残る。

**TODO:** 基準PC実測・必要な軽量化、測量アンカー照合、配布ライセンス記録、欠損域方針、HTTPS/外部API検証。これらが完了するまでv1.0受入済みとはしない。

## 2026-10-31 市域の建物欠損を区別した補完

福島市公式サイトによれば、2025年度までのPLATEAU LOD1整備範囲は都市計画区域229km²のうち174.6km²で、市域全体ではない。既存の東北OSM PBFから公式ソースメッシュ外の閉じた建物way 15,536件を抽出し、DEM5A地表高がある15,531件を別色の248 GLBに変換した。41件はOSM階数から高さを推定し、15,495件は6mと概略推定。公式建物とは別のマニフェスト・画面表示・監査を維持する。

**テスト済み出力:** 公式近景191、OSM補完248、遠景191、地形872、道路659の計2,161ファイルを全件SHA-256・サイズ検証。OSM補完の原本ID、品質、ODbL表示、公式ソースメッシュとの非重複を全件検査。ユニットテスト46件。開発Chromeで駅の公式建物と郊外のOSM補完3,298棟を目視確認し、読込失敗・コンソール警告/エラー0件。

**未テスト・TODO:** 公式メッシュ内の局所的な空白、relation-only OSM建物、建物推定高さの実測、基準PC10分/30FPS、測量アンカー2点、データセット固有の再配布条件、HTTPS配備、Driving Simulator側API利用。詳細は [CITYWIDE_V1_STATUS.md](CITYWIDE_V1_STATUS.md) と [CITYWIDE_ATTRIBUTION.md](CITYWIDE_ATTRIBUTION.md)。

内部確認用の静的パッケージも `dist/citywide-v1-preview/` に作成。HTML/JS/同梱Three.js、2,161タイル、道路検索、出典文書等の計2,180ファイル（約464 MB）をSHA-256で複写照合し、ローカルHTTPのChromeで表示・読込失敗0件を確認。パッケージの `acceptance_complete` は `false`。HTTPS実配備と公開条件は未検証。

## 2026-11-01 v1.0受入検証の自動化

基準PC向け `?benchmark=1` 自動10分測定、1280×720描画バッファ固定、道路追従とJSON暫定合否を実装。8秒の開発スモーク試験では初回の自動保存・境界通過1回・読込失敗0を確認した。繰り返しの保存はChromeに抑止されたため、JSON全体の画面表示・コピー経路を確認した。RTX 3060の画面操作環境にはブラウザ制限疑いがあり性能判定には使わない。JGD2011/EPSG:6668・T.P.宣言と出典を要求する実測アンカー照合CLIを追加し、道路線・公式建物外形・DEM5A地表を分けて比較する。実測資料なしでは報告を生成しない。全50件のユニットテスト成功。手順は [V1_ACCEPTANCE_PROCEDURE.md](V1_ACCEPTANCE_PROCEDURE.md)。

## 2026-11-01 測定PC向けローカル起動

Windows標準PowerShellだけで内部確認パッケージを配信し、10分測定画面を開く起動ファイルを追加。Pythonのない測定PCでもフォルダー全体をコピーして使用できる。開発PCではパッケージ内のHTML/JS/JSON/GLBのGET、欠損404、親フォルダー参照403、Chromeの8秒自動測定とページエラー0を確認。全50件のユニットテスト成功。別PC・Edge・I-RIHA101の10分測定、公開用HTTPSは未テスト。


## 2026-11-07 — 交通実験ラボ（GeoEngine本体とは分離）

- `viewer/traffic-lab.html`、`viewer/traffic-lab.js`、`viewer/geoengine-traffic-graph.mjs` を追加。既存の `viewer/citywide-v1.html` と v0.1 操作系は変更していない。
- 市全域の既存OSM道路タイルを入力とするEPSG:6677の2D接続グラフ、簡易道路面、車両・歩行者の視覚デモ。実データが手元にない場合は架空デモと明示する。
- 通行権・車線・地形・衝突・信号・交通優先・運転評価は未実装。交通イベントはTDS側で扱う。
- `tests/traffic_lab_probe.mjs` を追加し、Nodeテスト・構文チェック・既存fixture系PythonテストをGitHub Actionsで実行して成功。ローカルのフルPythonテスト、実データでのブラウザ動作、基準PCでの30FPS/10分は未実施。
- 詳細は `docs/TRAFFIC_LAB.md`。

**2026-11-07 3D交通統合追加試作**：既存 `traffic-lab.html` にPLATEAU LOD1建物・GSI DEM5A地形の小範囲GLB読込を追加。既存Citywide/TDS本体は変更せず、座標EPSG:6677と標高T.P.参照・OSM道路のDEM地表高サンプルによる暫定描画を実装。既知の標高がない道路上には3Dデモ車両を置かず、GLBがない場合は2D表示へ復帰。Node fixtureテストとCIは実装（成功確認）、実データブラウザ検証、基準PC10分/30FPS、道路と建物の整合性は未確認。詳細：`docs/TRAFFIC_LAB.md`。
