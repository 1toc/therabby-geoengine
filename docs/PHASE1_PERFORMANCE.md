# Phase 1: 福島駅東口の画質・性能比較（2026-10-30）

## 範囲と成果物

対象は現行の約200m四方、PLATEAU建物56棟・LOD2面1,790・写真UV面1,734。`city_sharp.glb`（元写真）、`city_photo_redrawn_all.glb`（全棟描き直し）、`city_photo_optimized.glb`（描き直し軽量化）を別ファイルで保持した。軽量化版は元の建物形状・頂点座標・UV・三角形インデックスを変えていない。描き直し画像にはAI推定が含まれる。

- 比較画面: [`viewer/performance-lab.html`](../viewer/performance-lab.html)
- 最適化生成: [`scripts/optimize_redrawn_textures.py`](../scripts/optimize_redrawn_textures.py)
- GLB構造監査: [`scripts/glb_audit.py`](../scripts/glb_audit.py) と `dist/real/fukushima-east/phase1_glb_audit.json`
- 最適化画像一覧・SHA-256: `dist/real/fukushima-east/redraw_atlas_1536_q88.json`
- Blender編集ファイル: `dist/real/fukushima-east/city_photo_optimized.blend`
- 同一カメラ全景・道路視点: `city_photo_redrawn_all_overview.png`、`city_photo_optimized_overview.png`、`city_photo_redrawn_all_street.png`、`city_photo_optimized_street.png`。差分画像は `city_photo_optimization_difference.png` と `city_photo_optimization_street_difference.png`。

## ファイル・構造測定

GLB内部の画像バイト列を解析した値。`RGBA8+mip概算` は全画像をRGBA8で展開し、完全なmipmapを持つ場合の **理論上の画像占有量**。GPU実メモリやCPUピークメモリの実測ではない。JPEGファイルサイズの縮小だけではGPUの展開画像メモリは減らない（[Three.js textures guide](https://threejs.org/manual/pages/textures.html)）。

| 版 | GLB容量 | 画像画素 | RGBA8+mip概算 | 画像 | メッシュ/材質 | 三角形 |
|---|---:|---:|---:|---:|---:|---:|
| 元写真 | 11,658,928 B | 91,750,400 | 466.7 MiB | 57 | 58/58 | 6,194 |
| 全棟描き直し | 23,522,456 B | 101,191,301 | 514.7 MiB | 58 | 59/59 | 6,194 |
| 軽量化版 | 17,760,400 B | 73,068,269 | 371.6 MiB | 58 | 59/59 | 6,194 |

軽量化版は全棟描き直し版からGLB容量 **24.5%減**、画像画素とRGBA8+mip概算 **27.8%減**。56アトラス中36枚だけを長辺1536pxへ縮小し、元がそれ以下の20枚は寸法を保持した。JPEG品質88、4:4:4色差。1壁面の詳細PNGと航空写真PNGは無変更。アトラス56枚の符号化容量は18,639,991 B→12,877,979 B。GLB内の全59メッシュについて、POSITION・TEXCOORD_0・indexのハッシュが描き直し版と一致する。

### 比較した候補と採否

| 候補 | 観測・判断 |
|---|---|
| JPEG品質82、寸法そのまま | アトラス総量14,396,798 B。転送量は減るが98,570,056画素のままで展開メモリを減らせない。今回は不採用。候補ファイル `redraw_atlas_2048_q82.json` を記録。 |
| 長辺1536px、JPEG品質88 | アトラス総量12,877,979 B、70,447,024画素。同一カメラ1600×900のBlender全景で差のRGB平均は各0.20/255前後、道路視点では各0.64〜0.68/255。近接壁に元の描き直し版から残るぼやけがあり、軽量化での大きな悪化は見られない。採用。 |
| KTX2/Basis Universal | [Khronos](https://www.khronos.org/ktx/)と[Three.js KTX2Loader](https://threejs.org/docs/pages/KTX2Loader.html)が対応。GPU向け圧縮を比較する価値があるが、この環境に `toktx`/`basisu`/`gltfpack` がなく、WASMトランスコーダを組み込んだ再現テストも未実施。効果を捏造せずPhase 2候補に残す。 |
| アトラス統合・材質削減 | 既に建物ごとにUVアトラスを共有し、約1枚/棟。全景約59〜60 draw callsで、6,194三角形。統合は個別更新とカリング粒度を悪化させ得るため、実機でdraw callが主因と判明するまで保留。 |
| メッシュ圧縮/LOD/InstancedMesh | 三角形数は少なく、ほぼ全棟で形状・写真材質が異なる。[InstancedMesh](https://threejs.org/docs/pages/InstancedMesh.html)は同じ形状・材質の反復向け。駅東口単体への導入を保留し、広域タイルの遠景LODで再評価。 |
| カリング・動的解像度・影/ポスト | [Three.jsのfrustumCulled初期値はtrue](https://threejs.org/docs/pages/Object3D.html)。この画面の可視draw callsは視点により54〜60。影マップとポスト処理は使用していない。倍率1/1.5/2は手動比較可能。Occlusion cullingと自動解像度調整は実機ボトルネックとタイル移動を測ってから判断。 |

## 開発環境ブラウザの30秒計測

`viewer/performance-lab.html` の自動軌道で、最初5秒静止、続く25秒移動を各モデル1回測定した。Windowsのアプリ内Chromium 156、**NVIDIA GeForce RTX 3060**（WebGL識別文字列）、1280×720、描画倍率1、同一FOV 52°、同一照明。モデルは1つずつロードし、切替時に旧geometry/material/textureをdisposeする。ブラウザ内のローカルHTTPキャッシュ、先行テスト、OS状態の影響を除去していないため、ロード時間の小差は優劣の根拠にしない。

| 版 | 読込時間 | 移動平均FPS | 移動p95 | 50ms超フレーム | 移動末尾draw calls/三角形 |
|---|---:|---:|---:|---:|---:|
| 元写真 | 526ms | 60.0 | 16.8ms | 0/1,500 | 54/5,922 |
| 全棟描き直し | 534ms | 60.0 | 16.8ms | 0/1,499 | 55/5,922 |
| 軽量化版 | 493ms | 60.0 | 16.8ms | 0/1,499 | 55/5,922 |

3版ともこの環境では60Hzの表示上限に達した。GPU処理余力や基準PCでの速度差は分からない。JavaScriptヒープはブラウザAPIで取得できたが、GCとモデル切替に左右される瞬間値であり、GPUメモリではない。画面にはリアルタイムFPS/p95、draw calls、三角形数、画像枚数/解像度/形式、理論画像メモリ、WebGL登録テクスチャ、取得可能なJSヒープ、読み込み時間を表示する。「30秒計測」で静止/移動のフレーム分布、50/100ms超回数、ブラウザ/GPU識別文字列（取得できる場合）、描画サイズをJSONに保存できる。現行の測定はモデル読込中の走行やタイル交換停止を含まない。

**基準PC i5-14500T / UHD Graphics 770 / RAM 8GBでは未測定。** 30 FPS・10分安定性・VRAM使用量の合格判定は保留。基準PCではChrome/EdgeとGPUを記録し、1280×720倍率1で各版を複数回、冷/温キャッシュを分けて計測する。街区の近景とタイル交換を含む走行経路でp95、最大フレーム、50/100ms超回数を比較する。

## 検証と再生成

`python -m unittest discover -s tests -v` は既存13件＋新規3件の16件通過。新規テストは最適化ファイル生成と元画像保護、GLBの座標/UV/index同一性・SHA-256、同一カメラの全景/道路視点レンダー画素差を確認する。`node --check viewer/performance-lab.js` 通過。ブラウザで3版のロードと各30秒計測、道路視点を確認。**道路視点の近接壁は元の描き直しテクスチャ自体がぼやけており、品質改善の残課題**。基準PC測定、KTX2比較、市全域タイルは未検証。

```powershell
python scripts/optimize_redrawn_textures.py --output dist/real/fukushima-east/redraw_atlas_1536_q88.json --max-edge 1536 --quality 88
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/blender_export.py -- --scene dist/real/fukushima-east/map.json --output dist/real/fukushima-east/city_photo_optimized.glb --texture-dir data/raw/plateau --ortho dist/real/fukushima-east/ortho_ground.png --redraw-manifest dist/real/fukushima-east/redraw_manifest.json --atlas-manifest dist/real/fukushima-east/redraw_atlas_1536_q88.json
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/render_city_overview.py -- --blend dist/real/fukushima-east/city_photo_optimized.blend --output dist/real/fukushima-east/city_photo_optimized_overview.png
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/render_city_overview.py -- --blend dist/real/fukushima-east/city_photo_redrawn_all.blend --output dist/real/fukushima-east/city_photo_redrawn_all_street.png --view street
& "C:\Program Files\Blender Foundation\Blender 3.1\blender.exe" --background --python scripts/render_city_overview.py -- --blend dist/real/fukushima-east/city_photo_optimized.blend --output dist/real/fukushima-east/city_photo_optimized_street.png --view street
python scripts/glb_audit.py dist/real/fukushima-east/city_sharp.glb dist/real/fukushima-east/city_photo_redrawn_all.glb dist/real/fukushima-east/city_photo_optimized.glb --output dist/real/fukushima-east/phase1_glb_audit.json
python -m unittest discover -s tests -v
python -m http.server 8767 --bind 127.0.0.1
```

最後に `http://127.0.0.1:8767/viewer/performance-lab.html` を開く。画像生成済みアトラスと元PLATEAU画像は既存の入力資産として必要。配布前のライセンス確認は別途残る。
