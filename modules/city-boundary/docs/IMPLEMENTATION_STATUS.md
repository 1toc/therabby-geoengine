# 実装状況（2026-10-30）

| 工程 | 状態 | エビデンス |
|---|---|---|
| STEP 1-1 暫定境界のブラウザ表示 | 実機確認済 | ユーザーのChromeスクリーンショット |
| STEP 1-1 正式2026年境界 | 生成・ブラウザー確認済 | 国土交通省N03-2026福島県ZIP（9,802,702 bytes）、市域767.716 km2、1成分。暫定境界は `data/source-backups/preview-20261030/` に保存 |
| STEP 1-2 Python道路取込処理 | 実装・単体テスト | `scripts/build_roads.py`・`tests/test_roads.py` |
| STEP 1-2 2D道路レイヤー | 実装・構文確認 | `src/roads.js` |
| STEP 1-2 保存済みOSM道路の再抽出 | 置換済 | 1km JSON取込版は過去世代として保持 |
| STEP 1-2 全市域PBFから抽出 | 抽出・ブラウザー確認済 | Geofabrik東北PBFから22,789 way、25,210線分、143タイル。入力PBFは `../../data/raw/tohoku-latest.osm.pbf` |

出荷物ZIPは実道路GeoJSONを同梱していない。現在の道路表示はOSMの市域抽出結果であり、全道路の収録率や法的な走行可能性を保証しない。
