> **GitHub保存版について**: このリポジトリはソースコードと手順のみです。元地図データ、建物写真、生成済みタイル、配布フォルダおよびバックアップは容量と再配布条件の確認のため含めていません。この状態をクローンしただけでは福島市3Dビューアは動作せず、実データに依存するテストやパッケージングも実行できません。データ取得・変換には下記の開発手順と各出典の確認が必要です。

## 実験機能：福島駅東口100mの車道・歩道・縁石候補

実在のPLATEAU道路外形（tran LOD1）とOSM道路中心線を基に、車道候補・歩道候補・未判定領域を**推定**で分けた立体表示を実験ブランチに追加しています。歩道の実在や正確な車道境界は保証しません。元データや地理座標・3D建物は変更せず、切替式オーバーレイです。

初回のみ、ローカルでShapely 2.xを導入し `python scripts/build_station_road_split.py` で派生JSONを生成してください。生成後は `viewer/citywide-v1.html?procedural=1&road_split=1` で表示できます。都市データを含まない公開リポジトリでは、[架空デモ](viewer/procedural-city-demo.html)で立体路面を試せます。

詳細・実施コマンド・制約：[駅東口100m 車道・歩道・縁石の実験](docs/STATION_ROAD_SIDEWALK_100M_PILOT.md)。

## 新機能（開発ブランチ）：Procedural City v0.1

**実在地図とは別の架空シーンで単独動作を確認できる、手続き生成の街並み実験を追加しました。** `viewer/procedural-city-demo.html` はローカルのThree.jsだけで表示します（PythonでHTTPサーバー起動）。街路樹と装飾車のあるサンプル道路、LOD1の生成窓・外壁、推定路面標示、時間帯スライダーを試せます。

福島市の生成済みタイルがローカルにある場合は、`viewer/citywide-v1.html?procedural=1` で実験モードを開けます。既定は従来表示のままです。実測道路境界・交通規制・車両物理・高精度な夜景は未実装で、I-RIHA101等での性能検証も未完了です。

使い方・検証コマンド・制約は [Procedural City実装記録](docs/PROCEDURAL_CITY_V01.md) を参照してください。実在の都市データをGitHubに追加したものではありません。

# Therabby GeoEngine — 福島市全域 v1.0実装候補

**現在の状態：Phase 6の現時点の作業は利用者判断で[暫定終了](docs/PHASE6_PROVISIONAL_CLOSEOUT.md)。公式PLATEAU建物、対象外のOSM補完建物、DEM5A地形、OSM道路を静的GLB/JSONタイルに変換し、ローカルThree.jsビューアで統合表示できます。公式PLATEAU建物は市域全体を覆っておらず、OSM補完建物の高さは主に推定値です。基準PCでの10分/30FPS、測量点照合、固有ライセンス・再配布条件は未確認で、v1.0受入完了ではありません。** 詳細は [市全域v1.0実装・受入状況](docs/CITYWIDE_V1_STATUS.md)。

v1.0は福島市全域の連続地図、UHD Graphics 770/RAM 8GB級の安定表示、実在街区を認識できる画質、直感的な日本語UIを目標にします。測定結果・採否は [Phase 1性能記録](docs/PHASE1_PERFORMANCE.md)、タイル試作と今後の拡張条件は [Phase 2タイル仕様](docs/PHASE2_TILING_SPEC.md)。

### 福島市全域を表示する

プロジェクトルートで `python -m http.server 8767 --bind 127.0.0.1` を起動し、[福島市3D地図](http://127.0.0.1:8767/viewer/citywide-v1.html)を開いてください。公式近景・遠景建物、茶色のOSM補完建物、地形、道路を距離で読み分けます。地域選択、OSM道路名/緯度経度検索、俯瞰/地上視点、Low/Medium/High画質、WASD移動、OSM道路線の自動追従、10分計測JSON保存を備えます。Webクライアントはローカルに同梱したThree.jsを使い、Python/BlenderやCDNは不要です。開発用HTTP起動と本番HTTPS配備の確認は別です。[出典・加工記録](docs/CITYWIDE_ATTRIBUTION.md)を参照してください。

駅東口の[300m公式写真付きLOD2試作](http://127.0.0.1:8767/viewer/citywide-v1.html?station_lod2=1)は、既存の市全域ビューアへ2025年PLATEAUの117棟を追加する別モードです。元のLOD1と同一建物を重複表示しません。写真は公式JPEGのみを使用し、地表への高さ合わせは表示用で測量精度ではありません。再生成・出典・性能上の制約は[統合記録](docs/STATION_LOD2_INTEGRATION.md)。

静的ファイルだけの[内部確認用パッケージ](dist/citywide-v1-preview/viewer/citywide-v1.html)も生成済みです。`scripts/package_citywide_preview.py` で必要ファイル2,203件（約501 MB、駅東口LOD2の品質別GLBを含む）を `dist/citywide-v1-preview/` に複製し、`preview_manifest.json` にSHA-256を残します。PLATEAU・DEM5A・OSMの元データ記録も同梱します。Windowsの別PCではフォルダーごとコピーし、駅東口の写真付きデモには直下の `start_station_lod2.cmd`、従来の10分測定には `start_citywide_benchmark.cmd` を起動します。両方とも先に全ファイルのサイズ・SHA-256を検査し、成功時だけ標準PowerShellのローカルサーバーと画面が開きます。測定結果JSONを同じフォルダーに保存しても再起動できます。測定PCへPythonを入れる必要はありません。ローカルHTTPで独立表示を確認済みですが、外部公開版ではありません。公開前の確認事項は[権利確認記録](docs/CITYWIDE_RELEASE_RIGHTS_REVIEW.md)にまとめています。

v1.0受入用には `viewer/citywide-v1.html?benchmark=1` で1280×720・10分の自動測定が始まります。測量済み2点の照合ツールと入力項目を含む[受入手順](docs/V1_ACCEPTANCE_PROCEDURE.md)を参照してください。現在は基準PC実測と測量資料が未取得です。

Blenderで福島駅東口周辺を編集する場合は、現行の市全域タイルから作成した[駅周辺の編集用 `.blend`](dist/real/fukushima-station-citywide/fukushima_station_citywide.blend)を開けます。公式LOD1建物・DEM5A地形・OSM道路中心線を別コレクションに分けています。範囲・出典・再生成方法は[Blenderシーン記録](docs/STATION_BLENDER_SCENE.md)を参照してください。

### 画質比較と4タイルの動的読込を試す

プロジェクトルートで `python -m http.server 8767 --bind 127.0.0.1` を実行し、[画質・性能比較](http://127.0.0.1:8767/viewer/performance-lab.html)または[4タイル試験](http://127.0.0.1:8767/viewer/tiled-preview.html)を開いてください。比較画面では「元写真」「全棟描き直し」「軽量化版」「近景修正版」を同じ全景/地上カメラで切替できます。タイル画面では自動移動中の読込・解放を確認できます。画像メモリの表示は理論値でありGPU実測ではありません。Three.js CDNへの接続が必要です。

GeoEngineは、PLATEAU／OpenStreetMapの都市データを軽量なThree.js向けアセットに加工し、Driving Simulatorなどに提供するための独立プロジェクトです。

## 使い方（まず実行できる最小テスト）

開発PCにPython 3を用意し、このフォルダをVS Code/Codexで開いてください。サンプルは**架空の幾何データ**です。

Windowsでは `scripts/run_m1_demo.ps1` でも実行できます。Codex付属Pythonを検出する環境では、Pythonを別途インストールする必要はありません。

```powershell
python -m unittest discover -s tests -v
python scripts/geoengine.py build --area config/fukushima_station_east.json --osm fixtures/fictional_osm.json --plateau fixtures/minimal_plateau_lod1.gml --output dist/demo/map.json
python scripts/geoengine.py validate --map dist/demo/map.json
```

`viewer/preview.html` は地図JSONの開発用確認画面です。「map.json を開く」から `dist/demo/map.json` または `dist/real/fukushima-east/map.json` を選べます。**Blenderが生成した3Dモデルを見る画面は `viewer/blender-preview.html`** です。ブラウザによる3DプレビューにはThree.js CDNへのネット接続が必要です（病院でのオフライン稼働はM2で対応）。

開発PCでBlender製の実データモデルを開く場合は、プロジェクトのルートで次を実行し、[Blender製の福島駅東口3Dプレビュー](http://127.0.0.1:8767/viewer/blender-preview.html)を開いてください。ローカルの静的サーバーは `Ctrl+C` で停止できます。

```powershell
python -m http.server 8767 --bind 127.0.0.1
```

## 実際の福島市を取得して変換する（開発PCのみ）

### 市全域の実データ状況（2026-10-31）

福島市2025年度PLATEAU LOD1建物データ212ファイルを取得済みです。公式の整備範囲は都市計画区域229km²のうち174.6km²で、市域全体の建物収録を意味しません。サイズとSHA-256を照合し、カタログ掲載168,759件すべてのLOD1フットプリントを解析しました。市境界内の168,752棟を1kmごとの建物JSONタイル191個として `data/derived/fukushima-citywide-lod1-v2/` に出力しています。7棟は市境界外です。建物形状はEPSG:6677、市境は国土交通省N03-2026です。168,741棟の基部地形高をGSI DEM5Aの代表点で補間し、T.P.標高として記録しました。11棟は標高データ欠損のためNULLで、3D化しません。近景191 GLB・遠景191 GLB、DEM地形872 GLB、道路659 JSONタイルへ変換済みです。旧プレビュー [citywide-lod1-preview.html](viewer/citywide-lod1-preview.html) は比較用に残し、統合画面は [citywide-v1.html](viewer/citywide-v1.html) です。

公式メッシュ外の閉じたOSM建物wayを市境で切り、15,536件を248個のJSONタイルに抽出しました。DEM5A地表高のある15,531件を248 GLBに変換し、主に概略推定した高さを茶色で表示します。OSM relation-only建物や公式メッシュ内の空白を網羅するものではありません。初期の建物代表点向け225枚から市域と交わる926枚まで地形取得範囲を広げ、872枚が利用可能です。54枚は未公開、39,883サンプル頂点は標高欠損で、穴として表示します。建物基部サンプルは個別の基礎高ではありません。DEM5A地表高は道路面高ではありません。

再生成スクリプトは `scripts/build_citywide_lod1_tiles.py` です。開発PythonにShapely 2.xが必要です。`--skip-hash-verification` を付けない場合、2GBの入力を再度SHA-256検証します。SQLiteの処理記録により、処理中断後は完了済みGMLを飛ばして再開します。ブラウザー側のクライアント依存は不要です。

ブラウザーでは `http://127.0.0.1:8767/viewer/citywide-lod1-preview.html` を開きます。プロジェクトルートから起動する場合：

```powershell
python -m http.server 8767 --bind 127.0.0.1
```

**1. 実道路：OSM／Overpass**

```powershell
python scripts/geoengine.py fetch-osm --area config/fukushima_station_east.json --output data/raw/fukushima_osm.json
```

Overpassサーバが混雑している場合は、他の公式・公開エンドポイントへ `--endpoint` で切替可。データの再利用にはODbL条件を守ってください。

**2. 実建物：PLATEAU福島市2025 CityGML**

国土交通省の試験運用PLATEAUデータカタログAPIから、200m四方に該当する建築物GMLファイルのURLを探索します。2026-10-29のAPI応答では福島市2025年度、LOD1建物ファイル2件、合計87,717,212バイトでした。API仕様とデータ年度は変わり得るため、まず**dry-run**で確認してください。

```powershell
python scripts/geoengine.py fetch-plateau --area config/fukushima_station_east.json --output-dir data/raw/plateau --dry-run
```

`plateau_file_list.json` の `files` に `*_bldg_*.gml` が列挙されたら、取得します。保存済みのAPIメタデータ例は `docs/evidence/plateau_catalog_fukushima_2025_observed.json` です。これは**GML本体ではありません**。

```powershell
python scripts/geoengine.py fetch-plateau --area config/fukushima_station_east.json --output-dir data/raw/plateau
```

APIでファイルリストが取得できない場合は、[PLATEAUオープンデータ](https://www.mlit.go.jp/plateau/open-data/)／[G空間情報センター](https://front.geospatial.jp/plateau_portal_site/)から福島市の対象年度のCityGMLを取得し、解凍して`udx/bldg`内の対象ファイルを指定してください。自治体一括ZIPは大容量になり得るため、先にサイズを確認してください。

**3. 統合マップJSONを生成**

```powershell
python scripts/geoengine.py build --area config/fukushima_station_east.json --osm data/raw/fukushima_osm.json --plateau data/raw/plateau --buildings-source plateau --output dist/real/fukushima-east/map.json
python scripts/geoengine.py validate --map dist/real/fukushima-east/map.json
```

M1のPLATEAUパーサーはCityGML2.0のLOD1足形・高さと、建物のLOD2屋根・壁・地表の面形状、公式写真テクスチャの貼付座標を読みます。EPSG:6697/4979の3次元経緯度のみ解釈し、未対応CRSはエラーにします。福島市2025の対象GML 2件から建物56棟、LOD2面1,790枚（うち写真付き1,734枚）の変換に成功しました。地図JSONは `dist/real/fukushima-east/map.json` です。地盤高を建物単位で平坦化した試験的な形状で、道路・建物の位置精度は測量点では検証していません。

**写真テクスチャを取得**：GML内の `app:imageURI` が参照する公式JPEGのうち、対象の建物に必要な56枚だけを取得します。写真は地図JSONには埋め込まず、BlenderでGLBに格納します。今回の取得量は9,691,772バイトでした。

```powershell
python scripts/geoengine.py fetch-textures --map dist/real/fukushima-east/map.json --file-list data/raw/plateau/plateau_file_list.json --output-dir data/raw/plateau
```

**地面の航空写真を取得**：福島市を含む[PLATEAU-Ortho公式タイル](https://docs.plateauview.mlit.go.jp/datasets/ortho/)の2024年レイヤーから、対象区域と周辺30mの30タイルを取得し、1024×1024画像へ位置合わせします。開発PCのPythonにPillowが必要です。建物データは2025年なので、年度差により現況が異なる場所があります。

```powershell
python scripts/fetch_ortho.py --area config/fukushima_station_east.json --output dist/real/fukushima-east/ortho_ground.png
```

開発用の平面重ね合わせ画像を生成するには、Pillowを備えたPythonで次を実行します。今回の実データではOSM建物面積の93.0%がPLATEAU建物と重なりました。両データの収録範囲が異なるため、測量精度を示す値ではありません。

```powershell
python scripts/qa_overlay.py --map dist/real/fukushima-east/map.json --osm data/raw/fukushima_osm.json --output dist/real/fukushima-east/qa_overlay.png
```

`config/fukushima_station_east_offset.json` を使うと、同じ実データから中心をずらした160m四方を再生成できます。今回の実行結果は道路16本・建物44棟です。

**4. BlenderでGLB出力（開発PCにBlenderが必要）**

```powershell
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_export.py -- --scene dist/real/fukushima-east/map.json --output dist/real/fukushima-east/city.glb --texture-dir data/raw/plateau --ortho dist/real/fukushima-east/ortho_ground.png --render-preview
```

Blenderのインストールパスは実機に合わせて変更してください。Blender 3.1.2で**架空デモと実データ**の出力を検証済みです。実データでは `city.blend`（写真をパックした再編集可能な作業ファイル、14,291,176バイト）、`city.glb`（建物写真と航空写真を埋め込んだ11,658,928バイト、6,604三角形）、`city_blender_preview.png` を生成しました。道路はGLBでは航空写真として表示し、OSMの70本道路線は地図JSONに保持します。`.provenance.json`に品質・出典・SHA-256、写真付き面・画像枚数を記録し、GLBにも出典情報を埋め込みます。**地形勾配、街路設備、走行可否はまだ反映していません。**

**高精細表示**：同じ実データから `city_sharp.blend` と1920×1080の `city_sharp_blender_preview.png` を作成済みです。BlenderのLayoutは写真表示・カメラ視点で、Viewport 16サンプル／Render 32サンプルのアンチエイリアス設定を保存します。ブラウザの `viewer/blender-preview.html` は高精細を初期表示し、「軽量表示に切替」で描画負荷を下げられます。元写真の解像度は建物ごとに異なるため、細部が写っていない箇所は拡大しても復元されません。

**16色表示の比較**：同じプレビューの「16色を試す」で、写真付きGLBをPC-9801VX風の16色・最大640×400ピクセルへ変換し、建物と地面の奥行き境界を強調できます。「フルカラーに戻す」で同じ視点へ戻ります。これはブラウザ上の表示実験で、Blenderの `.blend` / GLB本体や元写真は変更しません。看板・外壁などの識別は写真表示の方が適しており、16色表示の視認性は利用者・実機で未評価です。比較画像は `dist/real/fukushima-east/compare_photo.png` と `compare_16color.png` に保存しました。

**写真を参考にした1棟の再制作試作**：`scripts/blender_rebuild.py` は、福島駅東口の実LOD2建物1棟（`plateau-bldg_c21e382e-a296-4a99-aa62-2eaca866924c`）の公式JPEGを人が参照し、明るい外壁・暗い窓・屋上設備の特徴を、窓48枚・屋上設備3基の立体部品と新規生成した外壁・屋根・路面の色／法線テクスチャとして作り直します。元のJPEGや航空写真は `city_rebuilt.glb` に入れません。その他の建物は実LOD2形状＋仮素材、道路はOSM中心線と推定幅を使った仮描画です。このファイルは1棟の初期試作として残しています。

```powershell
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_rebuild.py -- --scene dist/real/fukushima-east/map.json --output dist/real/fukushima-east/city_rebuilt.glb
```

生成物は `city_rebuilt.blend`（編集用）、`city_rebuilt.glb`（Web表示用）、`city_rebuilt_preview.png`（Blenderレンダー）、`city_rebuilt.provenance.json`（参照画像・品質・SHA-256）、`rebuild_textures/*.png`（新規生成素材）です。`city_photo_browser_closeup.png` と `city_rebuilt_browser_closeup.png` はブラウザで同視点から取得した比較画像です。

**写真準拠の全56棟描き直し（現在の比較版）**：公式建物JPEG 56枚のUVアトラスをそれぞれ参照して描き直し、元のLOD2形状とUVを維持した `city_photo_redrawn_all.blend`・`city_photo_redrawn_all.glb` を出力済みです。写真付き壁1,271面・屋根463面を対象にし、1面は個別の高精細版を使用。`viewer/blender-preview.html` の「全棟描き直し版を試す」で元写真版と切り替えられます。窓や外壁の細部には画像生成による推定があり、実物との完全一致は未検証です。手順と品質範囲は `docs/FACADE_REDRAW.md` を参照してください。

旧 `city_rebuilt_all.glb` は汎用的な推定窓模様を使った初期試作として残しています。現在のプレビュー画面では表示しません。

```powershell
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_rebuild_all.py -- --scene dist/real/fukushima-east/map.json --output dist/real/fukushima-east/city_rebuilt_all.glb --texture-dir data/raw/plateau
```

全域版の生成物は `city_rebuilt_all.blend`、`city_rebuilt_all.glb`、`city_rebuilt_all_overview.png`、`city_rebuilt_all.provenance.json`、`rebuild_all_textures/*.png` です。窓・道路幅・縁石は推定表現で、写真並みの品質、現地との詳細一致、走行領域、I-RIHA101実機での30 FPSは未検証です。

```powershell
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_export.py -- --scene dist/real/fukushima-east/map.json --output dist/real/fukushima-east/city_sharp.glb --texture-dir data/raw/plateau --ortho dist/real/fukushima-east/ortho_ground.png --render-preview
```

## ファイルの役割

| Path | Role |
|---|---|
| `PROJECT.md` | v1.0完成定義、マイルストーン、プロジェクト境界 |
| `AGENTS.md` | Codexの作業原則 |
| `docs/TECHNICAL_SPEC.md` | 地図形式・座標と機能境界 |
| `docs/M1_STATUS.md` | 実装・未検証一覧 |
| `scripts/geoengine.py` | OSM/PLATEAUの取得と座標変換、JSON出力・検証 |
| `scripts/blender_rebuild.py` | 写真を参照した1棟の外観再制作試作とGLB出力 |
| `scripts/rebuild_styles.py` | 参照JPEGと壁面UVから全棟の明暗・窓候補を分析 |
| `scripts/rebuild_streets.py` | OSM道路・歩行者道・階段の平面跡と縁を描画 |
| `scripts/blender_rebuild_all.py` | 全56棟の再制作版 `.blend`・GLB・全景レンダーを出力 |
| `scripts/fetch_ortho.py` | 公式航空写真タイルを対象区域へ切り出す |
| `scripts/blender_export.py` | BlenderでLOD2面を組み立て、`.blend`・GLB・任意のレンダー画像を出力 |
| `scripts/qa_overlay.py` | OSMとPLATEAUの開発用平面照合画像を生成 |
| `viewer/preview.html` | マップJSONから直接作る開発用プレビュー |
| `viewer/blender-preview.html` | Blenderが作ったGLBを直接表示するプレビュー |
| `fixtures/` | 架空データによる自動テスト |
| `dist/demo/map.json` | 架空データの変換済み例（本物の地図ではない） |
| `dist/real/fukushima-east/` | 実データのローカル生成物（公開前にライセンス・精度確認が必要） |
| `legacy-v0.1-reference.html` | 動作実績のある旧Three.js実験の参考コード |

## ブラウザ配布について

- 病院PCにはBlender/Pythonが不要な設計です。最終的にはHTTPS経由で静的ファイル配信する予定です。
- このM1プレビューではThree.jsをCDNから読み込むため、現時点では**完全オフライン動作ではありません**。
- 臨床運転能力評価・安全な道順案内には利用できません。

## 公式データとライセンス

- 福島市2025年度PLATEAUデータ：[国交省ポータル](https://www.mlit.go.jp/plateau/open-data/)／[CityGML API](https://docs.plateauview.mlit.go.jp/datasets/citygml/)
- 福島市2024年度航空写真：[PLATEAU-Ortho公式配信仕様](https://docs.plateauview.mlit.go.jp/datasets/ortho/)
- PLATEAU CityGML API：[公式仕様](https://docs.plateauview.mlit.go.jp/datasets/citygml/)（試験運用、変更・終了の可能性あり）
- PLATEAU GIS Converter：[公式 CLI](https://project-plateau.github.io/PLATEAU-GIS-Converter/manual/use_command_line.html)（LOD2の将来取込み候補）
- OpenStreetMap：https://www.openstreetmap.org/copyright — © OpenStreetMap contributors / ODbL 1.0
- PLATEAU：公開データに適用されるライセンスを個別確認し、福島市／Project PLATEAUを出典表記。
- このリポジトリのコードのライセンスは `LICENSE`。**同梱・取得した他者の地理データにコードのMITライセンスは適用しない。**
