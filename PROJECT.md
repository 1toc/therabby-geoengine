# Therabby GeoEngine — PROJECT.md

**Project**: Therabby GeoEngine  
**Target release**: v1.0  
**Current deliverables**: Fukushima citywide static Three.js v1.0 candidate with official near/far buildings, clearly separate OSM fallback buildings, DEM5A terrain, OSM roads, search, road following and read-only API; optional 300m Fukushima Station official-photo LOD2 overlay; acceptance still pending (see `docs/CITYWIDE_V1_STATUS.md` and `docs/STATION_LOD2_INTEGRATION.md`)
**Primary downstream application**: Therabby Driving Simulator

## Mission

**現実の街を、誰もが使える軽量な3D空間へ。**

Therabby GeoEngineは、現実の都市データを軽量な3D走行環境へ変換し、一般的なPCで動作させ、他のTherabbyアプリに再利用可能な形で提供するオープンソースの地理空間エンジンである。

## v1.0 completion goal

**v1.0の目標は福島市全域**を地図として扱い、道路に沿って連続移動できる独立GeoEngineとする。Intel UHD Graphics 770・RAM 8GB級で1280×720平均30FPS以上、実在街区を認識できる画質、地域選択・検索・画質設定を含む日本語UIを必須条件とする。現在の駅東口約200m四方は、その実装・測定基準となる小区域であり、市全域完成や性能合格を意味しない。

### Acceptance criteria (targets, not verified achievements)

- 実地図：福島市全域をタイルで扱い、道路の連続移動を維持。位置・形状・高さの出典と推定値を区別。
- 描画：Three.js/WebGL。遠景LOD、軽量表示。単純な視点操作が可能。
- 性能：I-RIHA101 (i5-14500T, UHD Graphics 770, RAM 8 GB) で**1280×720・軽量モード・平均30 FPS以上**、10分連続操作。p95と長い停止も記録。
- 操作：地域選択、利用可能な地名/座標検索、俯瞰/地上視点、画質切替、読み込み状態を日本語UIで扱う。
- 運用：臨床現場のPCにはPython/Blender不要。HTTPSで起動できる。
- 連携：地図情報の形式・ロードAPIがDriving Simulatorから利用可能。
- 再現性：設定ファイルで別区域を処理できる。変換手順とテストを公開。
- 権利：OSM/PLATEAUの出典・ライセンスを明記し、生成データの配布条件を確認。

### Exclusions for v1.0

交通法規に完全準拠した車線・信号制御、車両物理、交通AI、運転能力評価、全国データ配信、Google Mapsと同等の写真品質は対象外。これらはDriving Simulator側または後続マイルストーンの担当。

## Responsibilities and boundary

| Concern | GeoEngine | Driving Simulator |
|---|---|---|
| 地図データの取込・統一座標系・LOD・描画 | Owner | Consumer |
| 道路の接続／走行領域に関する地理情報 | Provider | Consumer |
| 自車操作・交通イベント制御・評価ログ | Not owner | Owner |

## Milestones

- **Phase 1: 小区域の性能・画質比較** — 3版比較、軽量化、計測。実装済み範囲と未実測項目は `docs/PHASE1_PERFORMANCE.md`。
- Phase 2: 駅東口タイル化 — 動的ロード、アンロード、道路接続。仕様案は `docs/PHASE2_TILING_SPEC.md`。
- Phase 3: 福島市全域のデータ統合と出典/欠損管理。
- Phase 4: 広域の連続描画と地域別LOD。
- Phase 5: 直感的な日本語UIと外部アプリ向け読取API。
- Phase 6: 基準PCの10分測定、画質・権利・安定性の総合検証。2026-11-02に利用者判断で[暫定終了](docs/PHASE6_PROVISIONAL_CLOSEOUT.md)。基準PC・測量・再配布条件などの未確認事項はv1.0受入前に再開する。

## Engineering principles

1. v0.1で動作確認済みのWebGL/Three.js構成を保護。CesiumJSへの全面移植はしない。
2. まず100～200m四方。実測のない環境で最適化完了とは言わない。
3. Blender Pythonは開発時のバッチ処理。Blender MCPは任意の編集補助。
4. 元データは破壊せず、プロジェクト側で生成物を再作成する。
5. **不明な座標系・出所不明のファイルは黙って変換しない。**
6. 描画モデルと道路の交通ロジック／測定データを混同しない。
7. 生成物にはデータの品質（実測・推定・未対応）を記録する。

## Current implementation truth

M1のCLIと駅東口200m/1km試作は保持。福島市2025 PLATEAUの212ファイル・168,759 LOD1建物を解析し、市境内168,752棟を1kmタイル化した。公式整備範囲は都市計画区域の174.6km²で、市域全体ではない。うち168,741棟を近景GLB 191タイル、同じ棟を遠景概略GLB 191タイルに変換。公式メッシュ外のOSM建物15,531件を推定高さの別レイヤー248 GLBに変換。国土地理院DEM5A地形872タイルとOSM道路659タイルをEPSG:6677に合わせ、ローカルThree.jsビューアで動的表示・検索・道路追従を確認した。道路共有境界ノード5,602件、地形共有境界54,087頂点ペアを監査済み。**v1.0受入は未完了。I-RIHA101での1280×720・10分/30FPS試験、測量点照合、固有ライセンス/再配布条件、地形欠損と道路面品質の評価が残る。** 詳細は `docs/CITYWIDE_V1_STATUS.md`。

See `docs/TECHNICAL_SPEC.md`, `docs/M1_STATUS.md` and `README.md`.
