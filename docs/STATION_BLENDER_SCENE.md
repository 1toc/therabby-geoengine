# 福島駅東口のBlender編集用シーン（2026-11-01）

## 成果物

- 編集ファイル: `dist/real/fukushima-station-citywide/fukushima_station_citywide.blend`（21,721,212 B）
- 俯瞰プレビュー: 同フォルダーの `fukushima_station_citywide_preview.png`
- 出典・入力SHA-256: 同フォルダーの `fukushima_station_citywide.provenance.json`

`config/fukushima_station_east_1km.json` の中心（37.75445, 140.46190）と半径500mを選択範囲とした。完全なソースタイルを取り込むため、実際のメッシュは指定した1km四方の外側にも広がる。Blender内のXは東、Yは北、ZはT.P.標高（m）。中心の投影座標をシーンのカスタムプロパティに記録する。元の市全域GLBやJSONは変更しない。

| レイヤー | 内容 | 入力 |
|---|---|---:|
| 公式建物 | Project PLATEAU / 福島市2025の無写真LOD1 | 4 GLBタイル |
| 地形 | 国土地理院DEM5Aの地表、欠損は穴 | 4 GLBタイル |
| 道路 | © OpenStreetMap contributors / ODbL 1.0の中心線。DEM5A地表高のある3,759線分を細い曲線で表示 | 4 JSONタイル |
| OSM補完建物 | 今回の駅周辺範囲には該当タイルなし | 0タイル |

橋・トンネル等146線分は地表に描かない。未知の地表高は今回0線分。道路曲線は車両用路面や法定車線ではない。LOD1建物は写真付きLOD2ではない。外部への再配布条件と測量点照合は未確定で、この`.blend`は内部編集用である。

## 再生成

Blender 3.1.2のバッチモードで次を実行する。入力タイルのサイズ・SHA-256、EPSG:6677とT.P.を検証してから編集用シーンを保存する。

```powershell
& 'C:\Program Files\Blender Foundation\Blender 3.1\blender.exe' --background --python scripts/blender_build_station_scene.py -- --area config/fukushima_station_east_1km.json --output dist/real/fukushima-station-citywide/fukushima_station_citywide.blend
```

**テスト済み:** Blender 3.1.2でGLBをインポートして`.blend`保存とプレビュー描画を完了。保存ファイルを別プロセスで開き、公式建物4・地形4メッシュ、OSM道路12曲線オブジェクト内の3,759スプライン、EPSG:6677・T.P.とカメラ設定を照合。`.blend`のSHA-256は出典sidecarと一致。`python -m unittest discover -s tests -v` は52件成功。

**未テスト・TODO:** Blender GUIでの手動編集、現地測量点との位置照合、外部再配布、別Blender版での互換性。200mの既存写真付きLOD2試作は別の座標・鉛直基準で作られており、このシーンへ自動合成していない。
