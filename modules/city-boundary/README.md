# Therabby GeoEngine — STEP 1-2 / OpenStreetMap 道路網 (v0.1.2)

既存の **STEP 1-1 境界表示モジュールへ道路網取込機能を追加**します。`E:\GeoEngine\modules\city-boundary\` 内で動かせる差し替え版です。既存の福島駅東口3D試作や運転シミュレータは変更しません。

## 何ができるか

- STEP 1-1：市の境界、塗りつぶし、クリック座標、GeoJSON保存（既存機能を維持）
- STEP 1-2：**実際のOSM道路の中心線**を取り込み、地図上に重ねて表示
- 幹線道路（橙）、生活道路（青）、歩道等（紫・表示切替）に分類
- 地図の表示範囲に入った道路タイルだけ読込。福島市全体を巨大なGeoJSONとして一度に表示しない
- 道路データの出典・境界精度・抽出way数・表示線分数を表示
- `oneway`, `maxspeed`, `lanes`, `bridge`, `tunnel` 等の元OSMタグを保存（**値が必ずあるとは限らない**）

**重要：配布ZIPには実道路の全件データを同梱していません。** この作業用フォルダーでは2026-10-30に公式境界と道路を生成済みです。国土交通省N03-2026境界とGeofabrik東北PBFから作成した `data/roads/index.json` は `coverage: municipality`、境界品質 `official_2026`、22,789 OSM way、25,210線分、143タイルです。元PBFはプロジェクトルートの `data/raw/tohoku-latest.osm.pbf` に保存し、マニフェストにPBFハッシュとOSMスナップショット時刻を記録しています。地理院の背景地図に道路が見えるだけでは道路中心線のOSM取込を意味しません。

## Windows導入（以前の版を差し替え）

1. 旧フォルダ `E:\GeoEngine\modules\city-boundary\` をコピーしてバックアップ（正式境界データを取得済みなら特に重要）。
2. このZIPの **中身だけ** を `E:\GeoEngine\modules\city-boundary\` に上書き展開。
3. **すでに正式版N03を取り込んでいた場合**：旧 `data/fukushima_city_boundary_full.geojson`、`data/fukushima_city_boundary.geojson`、`data/boundary_metadata.json` は削除・上書きしないこと。正式版でなければ暫定プレビューを使用。
4. PowerShellでコマンドを実行：

```powershell
cd E:\GeoEngine\modules\city-boundary
py -m pip install -r requirements.txt
```

### A. 最初は福島駅周辺だけ実データ取得（軽量・推奨）

```powershell
py -0p
py --version
py scripts/build_roads.py --overpass-station
py -m http.server 8000
```

公開Overpassが利用できない場合は、M1ですでに取得済みの駅東口1km OSM実データを再利用できます。`E:\GeoEngine` でこのファイルを確認し、モジュールの作業フォルダから次を実行してください。

```powershell
py scripts/build_roads.py --osm-json "..\..\data\raw\fukushima_osm_1km.json"
```

この入力は `https://api.openstreetmap.org/api/0.6/map?...` 由来です。生成インデックスには `coverage: local_json_import` と原典URLを記録し、市全域データとしては表示しません。入力JSONに取得日時は記録されていないため、生成日時をデータ取得日時とは扱いません。

`py -0p` は使用可能なPythonのバージョンと実行ファイルの場所を表示します。ここでPythonが見つからない、または `py scripts/build_roads.py ...` がPythonランチャーの短い表示だけで終わる場合は、道路スクリプトに到達していません。次を確認してください。

```powershell
Get-Command py,python -ErrorAction SilentlyContinue | Select-Object Name,Source
py -0p
```

Python 3.11/3.12が一覧に出ない場合は、そのPCにPython 3をインストールしてください。一覧に複数のPythonがある場合や `py -m pip` とスクリプトで環境が違う場合は、`py -0p` に表示された目的の `python.exe` を使い、同じ実行ファイルで依存導入と道路生成を行います。

```powershell
& "C:\Path\To\Python\python.exe" -m pip install -r requirements.txt
& "C:\Path\To\Python\python.exe" scripts/build_roads.py --overpass-station
```

スクリプトが起動すると、Python実行ファイル、処理モード、境界状態、Overpass接続先と取得件数を表示します。HTTP応答エラー、ネットワーク接続失敗、JSON形式の異常、内部処理エラーは別の診断メッセージになります。

ブラウザ `http://localhost:8000/` で、**福島駅周辺**を表示。地図を拡大すると橙・青の実道路線が出るはずです（OSM道路線はズーム10.5以上で表示）。歩道表示はチェックボックスから切替できます。

`py -m http.server` がPythonランチャーの短い表示だけで終了する環境では、`py -0p` で登録済みPythonを調べ、同じPython実行ファイルを使ってスクリプトとHTTPサーバーを起動してください。起動中のPowerShellウィンドウは閉じず、ブラウザには `http://127.0.0.1:8000/` を指定します。

Overpassの公開APIは接続先の混雑・容量制限・通信環境で取得できない場合があります。繰り返し大量に問い合わせないでください。失敗した場合、既存の道路タイルは保持されます。

### B. 福島市全域の実OSM道路データを取得（本命）

現在の作業用データを再生成する場合は、取得済み原本を指定します：

```powershell
py scripts/build_roads.py --pbf "..\..\data\raw\tohoku-latest.osm.pbf"
```

以下は原本が手元にない場合の手順です。

[Geofabrik 東北エリア公式ダウンロード](https://download.geofabrik.de/asia/japan/tohoku.html) から `tohoku-latest.osm.pbf` （**約300MB**）をダウンロードし、次を実行：

```powershell
py scripts/build_roads.py --pbf "C:\Users\YOURNAME\Downloads\tohoku-latest.osm.pbf"
```

**`--download-pbf` では元PBFをユーザーの `GeoEngineSourceCache` フォルダへ保存します（公開フォルダ外）。

入力PBFと出力タイルは別物です。** 東北地方全域のPBFを読み、福島市の境界に交差するOSM道路だけを抽出して `data/roads/` に配置します。元の東北PBFは公開フォルダへコピーしないでください。

または、帯域・ディスク容量に余裕があれば、**明示的に約300MB以上のダウンロードを許可する**次のコマンドも使えます：

```powershell
py scripts/build_roads.py --download-pbf
```

WindowsでのPBF解析には `osmium` Pythonパッケージが必要です。`requirements.txt` に含めました。上記処理では東北地方全域のPBFを読み取るため、PC・SSD・メモリの負荷がかかります。公開後の来訪者PCにPBFを読ませる設計ではありません。

成功時に `data/roads/index.json` の `coverage` が `municipality`、`source` が `geofabrik_pbf` になります。

## 正式2026年境界への更新（残タスク）

現在のスクリーンショットに表示されているのは **暫定プレビュー**です。まず STEP 1-1 の `scripts/build_boundary.py` で `N03-20260101_07_GML.zip` を正式変換し、`data/fukushima_city_boundary_full.geojson` を生成してください。その後 **道路も再生成**すると、道路の抽出範囲が正式市域に一致します。

> 正式境界がない場合でも道路の小範囲試験や全域PBF抽出は実行可能ですが、その場合はデータに `boundary_quality: preview` が記録されます。境界付近の道路クリッピングは概略です。

## スクリプト一覧・出力

- `scripts/build_boundary.py`：STEP 1-1 の正式行政区域GeoJSONの生成（従来どおり）
- `scripts/build_roads.py`：STEP 1-2 の道路抽出・分割・メタデータ生成
- `data/roads/index.json`：道路データの状態、OSMライセンス、原典、タイル一覧、件数
- `data/roads/＜グリッドID＞.geojson`：表示対象エリアに必要な実道路の分割GeoJSON
- `src/roads.js`：表示エリアに必要なタイルだけ取得する処理

再生成時は `data/roads/tiles-<時刻>-<ID>/` に新しいタイル世代を書き、最後に `index.json` だけを切り替えます。既存世代は読み込み中のブラウザーを壊さないよう残します。古い世代の削除は現時点では自動化していません。

`--overpass-json <file>` オプションは保存済みOverpass JSONの読込テスト用です。**ブラウザはGeoJSONを実データとして表示しますが、ルーティングや交通安全判定はまだ行いません。**

## テスト

```powershell
py -m pytest -q tests
```

- Python単体テストは外部ネットワーク不要で実行できます。
- OSM実データ取得・PBF処理・現在のChrome表示は開発環境で確認済みです。Edge、基準PC、GeoJSON大規模表示性能は追加検証が必要です。
- 構築と表示の両方で、道路数、特徴的な市中心部の道路の向き、地域境界付近のクリッピングを確認してください。

## ライセンス・臨床用途の注意

- OSMデータは **Open Database License（ODbL）1.0**。表示・公開時に `© OpenStreetMap contributors` とODbLを明示し、加工済データを再配布する場合はライセンス上の義務を確認してください。背景地図は国土地理院（地理院タイル）。
- OSMの道路中心線には、全車線・歩道幅・信号現示・横断歩道・走行制限の完全な精度はありません。`highway` が道路という分類であっても実際に車両通行できるとは限りません。
- 区画道路・歩道の表示品質はOSMへの投稿量によって差があります。臨床評価・公道での交通判断に用いるには別途データ照合・検証が必要です。

出典： https://download.geofabrik.de/asia/japan/tohoku.html ・ https://www.openstreetmap.org/copyright ・ https://wiki.openstreetmap.org/wiki/Overpass_API

## STEP 1-2 完了基準

- [x] STEP 1-1 UIと互換性のある道路表示レイヤー実装
- [x] OSMタグの保持と地域タイル化を実装
- [x] ローカル実データ取得用パイプラインと単体テスト
- [x] 実際の福島駅周辺OSM道路の取込・表示確認（市域PBFから抽出）
- [x] 福島市全域の東北PBFから道路抽出（22,789 way／143タイル）
- [x] 正式2026年行政区域を用いたクリッピング

次工程：**STEP 1-3（標高DEM）**。ただし、STEP 1-2の実データの取込完了後に進めることを推奨します。
