# 福島駅東口300m LOD2公式写真 統合試作（2026-11-02）

## 実装と確認範囲

市全域v1.0候補のThree.jsビューアに、福島駅東口を中心とする300m四方の2025年PLATEAU LOD2写真モデルを選択表示できるようにした。入口は `viewer/citywide-v1.html?station_lod2=1`。通常の市全域表示はLOD1のままで、画面のチェックボックスで切り替える。既存のレガシーv0.1 HTML、車両挙動、Driving Simulatorは変更していない。

- 公式2025年CityGMLの対象2ファイル（`56405306`、`56405307`）から、対象範囲と交わるLOD2建物 **117棟**、LOD2面 **3,064**、写真UV付き面 **2,947**、参照JPEG **117枚**を抽出。うち61枚はこの工程で公式配信元から追加取得した。未取得の写真を架空画像で補っていない。
- 300mは選択範囲で、境界を横切る建物の面は範囲外へ続く。対象2メッシュ外のLOD2有無や、福島市のLOD2整備区域全体の網羅性を示す件数ではない。
- 投影は既存市全域と同じJGD2011平面直角IX系（EPSG:6677）。元GMLはEPSG:6697/4979の明示された3D経緯度のみ解析し、未知のCRSは既存パーサーが拒否する。
- 元LOD2の**建物内相対高さ**と公式UVを保持し、同じIDの市全域LOD1タイルに付いた国土地理院DEM5A地表標高を**表示用の基準**にした。これはEPSG:6697/4979の高さをT.P.へ測地変換したものではなく、建物基礎高を測量したものでもない。地盤との浮き・埋まり、道路面高、水平位置の現地照合は未検証。
- 該当117棟のIDを持つLOD1だけを2つの既存1kmタイルから除いた代替GLBを生成した。LOD2と同じIDのLOD1が同時に描画されない。範囲外またはチェックを外した場合は元のLOD1タイルへ戻る。
- 写真は**公式JPEGのみ**を使用し、AI描き直し版は使用しない。写真のない面は単色PBR材質。道路・地形・OSM補完の既存タイルは維持する。

## 画質と操作

| 設定 | 写真の最大辺 | 写真117枚のRGBA8+mipmap理論概算 | 用途 |
|---|---:|---:|---|
| Low | 512px | 94.8 MiB | 8GB機向け初期設定 |
| Medium | 1024px | 271.8 MiB | 標準PC向け |
| High | 原寸 | 889.8 MiB | 大きな画像メモリを許容できるPC向け |

概算は写真JPEGをRGBA8へ展開した場合であり、GPU使用量の実測ではない。GLB転送量、他の地形・建物テクスチャ、ブラウザの作業領域は含まない。Highを8GB機の性能合格とみなさない。既存の俯瞰・地上切替、マウス操作、OSM道路追従、FPS/p95・draw call表示に加えてWASD移動を使える。地上カメラの表示高さは近傍OSM道路のDEM5A地表高から1.8mで、路面実測ではない。

## 再生成

元GMLは `data/raw/plateau/fukushima_citywide_2025/`、写真は `data/raw/plateau/*_appearance/` に保持する。写真取得は追加分のみ、各20MB・全選択写真250MBで止める。新たな巨大CityGML ZIPは取得しない。開発PCではPillow入りPython、Blender 3.1が必要。ブラウザ側は同梱Three.jsと静的ファイルのみ。

```powershell
$python = 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$blender = 'C:\Program Files\Blender Foundation\Blender 3.1\blender.exe'
& $python scripts/build_station_lod2_overlay.py --fetch-photos
& $blender --background --python-exit-code 1 --python scripts/blender_export_station_lod2.py -- --overlay data/derived/fukushima-station-lod2-overlay/tileset.json
& $python -m unittest discover -s tests -v
& $python -m http.server 8767 --bind 127.0.0.1
```

ブラウザで `http://127.0.0.1:8767/viewer/citywide-v1.html?station_lod2=1` を開く。生成された `data/derived/fukushima-station-lod2-overlay/tileset.json` にはソースGML・LOD1タイル・写真一覧のSHA-256、建物ID、品質別GLBの長さとSHA-256を記録する。`source_photos.json` は公式URLと画像ごとのSHA-256を記録する。画像の縮小版は開発用の中間成果物で、ブラウザは画像埋込済みGLBだけを読む。

Pythonを入れない確認用PCには `dist/citywide-v1-preview/` フォルダーを丸ごとコピーし、`start_station_lod2.cmd` を起動する。全ファイルのSHA-256を先に検査し、PowerShellのローカルHTTPサーバーから同じ画面を開く。従来の `start_citywide_benchmark.cmd` は10分測定用のまま維持する。

## 検証済み・未検証

**検証済み:** 117棟の同一IDによるLOD1の置換、2タイルのGLB存在・サイズ・SHA-256、写真117枚のサイズ・SHA-256、UVリング長と面頂点長、各建物の最小表示高とDEM5A基準高の一致。Pythonユニットテスト54件成功、JavaScript構文確認。開発PCのアプリ内ブラウザでLow/Medium/Highが117棟を読み、切替・LOD1復帰・地上視点・Wキー移動を確認。各状態の読込失敗0、ブラウザ警告/エラー0。狭幅画面での目視確認であり、基準PC性能試験ではない。

**未検証/TODO:** I-RIHA101（UHD Graphics 770・RAM 8GB）の1280×720・10分・平均30FPS、測量済み2点での水平位置と基礎高照合、すべての建物境界での浮き/埋まり、実写の現況一致、2025年PLATEAU個別の再配布特記、国土地理院DEM5A派生データ公開条件、HTTPS配信。市全域のLOD2化は公式整備範囲と画像容量を見て別計画とする。現行は内部確認用で、v1.0受入完了ではない。

出典: [福島市の3D都市モデル整備状況](https://www.city.fukushima.fukushima.jp/soshiki/12/1059/1/12474.html)、[PLATEAU配信サービス](https://docs.plateauview.mlit.go.jp/datasets/citygml/)、[既存市全域の出典・加工記録](CITYWIDE_ATTRIBUTION.md)。
