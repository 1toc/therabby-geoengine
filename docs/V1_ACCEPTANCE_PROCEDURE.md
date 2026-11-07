# v1.0受入測定の自動実行手順（2026-11-01）

2026-11-02にPhase 6の現時点の作業は[暫定終了](PHASE6_PROVISIONAL_CLOSEOUT.md)とした。以下の手順は、v1.0受入または外部公開を判断する際に残件を再開するために保持する。

## 10分性能測定

Windowsの測定PCには `dist/citywide-v1-preview` フォルダー全体をコピーする。Pythonのインストールやデータ再ダウンロードは不要。フォルダー直下の `start_citywide_benchmark.cmd` を起動すると、まず `preview_manifest.json` と全ファイルの有無・長さ・SHA-256を検査する。黒い画面に件数の進行が表示され、この間はブラウザがまだ開かない。成功時だけWindows標準のPowerShellがそのフォルダーを `127.0.0.1:8767` で配信して既定ブラウザに測定URLを開く。生成された `geoengine-citywide-*.json` を同じフォルダーに保存しても、更新版では次回起動を妨げない。検査失敗時はフォルダー全体をコピーし直す。ChromeまたはEdgeを使い、測定が終わるまでサーバーの窓を閉じない。サーバーは同じPCからのみ接続でき、外部ネットワークには公開しない。このローカル起動方法は内部測定用であり、公開用HTTPS配備の検証にはならない。

基準PC **I-RIHA101 / Intel UHD Graphics 770 / RAM 8GB** 上のChromeまたはEdgeで、静的ホストの `viewer/citywide-v1.html?benchmark=1` を開く。地図目録と駅周辺のOSM道路タイルが読めると、軽量表示・1280×720描画バッファ・道路線追従で測定が自動開始する。ブラウザ窓はこの解像度と違っても、描画バッファは固定される。10分後に `geoengine-citywide-*.json` の自動保存を試みる。ブラウザが保存を抑止した場合は「直前の測定JSONを再保存」を押すか、「保存できない場合は測定JSONを表示」から内容をコピーする。タブは前面に置き、PCをスリープさせない。画面には停止ボタンもあるが、途中停止は有効な10分測定ではない。

JSONの `performance_gate.checks` は、10分完了、描画解像度、軽量画質、前面表示、約1秒周期の制限疑い、道路追従、タイル読込失敗を検査する。`average_30fps_met` は平均30FPSを判定する。`result` が `provisional_pass_on_reported_gpu` でも、GPU文字列だけでI-RIHA101本体は証明できないため、ホスト名・OS/GPU・実際の操作状況を別途照合する。p95/p99、100ms超の停止、タイル交換も記録し、合否レビューに用いる。`?benchmark=smoke` は8秒の開発試験専用で、10分要件には使えない。

## 測量済み2点の位置・地表高照合

テンプレートは `config/survey_anchors.template.json`。実測資料に基づいて、異なる地点を最低2点追加する。入力座標は **JGD2011の緯度経度 EPSG:6668**、実測地表標高は **T.P.** に限る。WGS84、標高基準不明、道路面高や建物基礎高の値を黙って変換・代用しない。

各 `anchors` 要素は次の項目を持つ。数値の許容差は測量計画で事前に決めた値を記入し、結果を見てから緩めない。

| 項目 | 内容 |
|---|---|
| `id` | 実測地点の一意な識別子 |
| `feature` | `osm_road_centerline` または `plateau_building_outline` |
| `lat_deg`, `lon_deg` | JGD2011 / EPSG:6668 の緯度・経度 |
| `surveyed_bare_earth_tp_m` | その地点の実測された裸地のT.P.標高。道路床版高や建物基礎高ではない |
| `horizontal_tolerance_m`, `vertical_tolerance_m` | 事前宣言した許容差 |
| `survey_method`, `survey_date`, `survey_source` | 測量方法・日付・資料識別子 |

開発PCで次を実行すると、最寄りの実OSM道路線または公式PLATEAU建物外形との水平差、GSI DEM5A地表との標高差を別々に出力する。道路面高・建物基礎高は常に未確認として残す。

```powershell
py -3.11 scripts/check_citywide_survey_anchors.py --input config/survey_anchors.real.json --output data/derived/fukushima-survey-anchor-report.json
```

入力ファイルのSHA-256と出典を結果に記録する。`all_within_declared_tolerances` が真でも、検証した地点だけの結果であり、市域全体の測量認証ではない。

## 現在の実施状況

- **テスト済み:** Python不要のローカル起動でHTML・JS・JSON・GLBを読込、8秒の自動開始・結果表示、1280×720固定、道路追従、読込失敗0件。初回のJSON自動保存は確認済みだが、このChromeでは繰り返しの保存が抑止された。開発PCの画面操作環境ではブラウザ制限疑いがあり、性能判定は無効。測量点ツールは実タイルの座標原点と不明な道路面高の扱い、未知CRS拒否をテストした。
- **別PCで確認済み:** Intel HD Graphics 4000のChromeで2回、Intel UHD Graphics (PCI ID A721)の職場ノートPCのEdgeで1回、1280×720・軽量・10分測定を完走。いずれもGPUが指定基準PCとは異なり、平均30FPS条件は別PCでの参考値に限る。測定原文は `docs/evidence/` に保存。
- **未テスト:** I-RIHA101での10分実測、実測アンカー2点との照合、HTTPS配備上の自動保存。基準PCや実測資料が揃うまでv1.0受入完了とはしない。
