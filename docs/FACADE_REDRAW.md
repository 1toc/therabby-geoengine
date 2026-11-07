# 写真準拠の壁面描き直し試作

## 近景の追加修正（2026-10-30）

駅前道路から見える写真のぼけを優先し、レイキャストで画面内の壁面IDを特定した。`scripts/extract_wall_reference.py` を拡張し、四角形に加えて多角形の壁も元UVから正面図へ展開できるようにした。組み込み `image_gen` の画像編集で11面を追加描き直し、先行1面と合わせて `redraw_manifest_crisp.json` の**12面**を直接差し替えた。残りの写真付き1,722面は全56棟のアトラス描き直し版を使用する。

- 参照画像: `dist/real/fukushima-east/redraw_refs/`。元のPLATEAU写真と、登録済み全棟アトラス版から壁面を抽出。
- 生成画像: `dist/real/fukushima-east/redraw_textures/`。不規則な3面は `scripts/align_wall_repaint.py` で壁形状へ位置合わせし、`redraw_textures_aligned/` に保存。黒い欠損を元参照画像で補った割合は0.45%、2.68%、0.013%。
- 配布用画像: `scripts/optimize_wall_textures.py` で四角形壁9面だけJPEG品質94・色差サブサンプリングなしに再符号化し、`redraw_textures_web/` と `redraw_manifest_crisp_web.json` に保存。元PNGは無変更。JPEGの最大チャンネルRMS差は3.299/255。多角形3面は黒いUVマスクのためPNGを維持。
- Blender作業ファイル: `dist/real/fukushima-east/city_photo_crisp.blend`。Web表示用: `city_photo_crisp.glb`（25,301,644 bytes）。最終JPEG版の近景画像: `city_photo_crisp_street.png`（Blender）と `city_photo_crisp_browser_street.png`（比較画面）。
- 比較画面: `viewer/performance-lab.html` の「近景修正版」。12面の細部はAIによる推定で、現地確認済みの実物コピーではない。駅前のほかの壁や路面にはまだ元のぼけが残る。

今回の画像編集に渡した指示セットの要旨（組み込み `image_gen`、ローカル参照画像を編集対象に指定）：

> 元の壁面写真の正面図を、同じ建物へ貼れる鮮明なフォトリアルの外壁テクスチャとして描き直す。壁の外形、窓・ガラス・帯・入口・植栽の大きな配置と数を維持し、ぼけた縁、細いフレーム、パネル目地をはっきり描く。新しい階や規則的な窓格子、看板、読める文字を作らない。黒い多角形外側は黒のまま残す。視点と壁面の縦横比を動かさない。暗く情報がない下部は作り込まず暗さを保つ。

この指示を各壁面の写真内容に合わせ、`fe5ae763:67` は上部の窓列と暗い下部、`:28` は長い水平窓列、`b7d25c72:19` は上部格子と暗い開口、`d799d499:22/44/50/61/89` は薄色外壁と青灰・赤茶の帯、`:56` は青いガラスと灰色パネル、`:59` はガラスと植栽、`:88` は下部の帯・縦配管・茶色パネルを指定した。生成物を公式写真から直接観測できた構造と区別するため、マニフェストに各面の参照・推定範囲を記録した。

## 全56棟版（2026-10-30）

ユーザーの「全部描き直して」に合わせ、区域内56棟の公式写真UVアトラス56枚を、組み込み `image_gen` の画像編集で1枚ずつ描き直した。対象は写真付きの壁1,271面と屋根463面、合計**1,734面**。元のLOD2形状とUV座標は維持した。下記の1壁面詳細版は全棟版でも優先して使用している。

- Blender作業ファイル: `dist/real/fukushima-east/city_photo_redrawn_all.blend`
- Web表示用: `dist/real/fukushima-east/city_photo_redrawn_all.glb`（23,522,456 bytes）
- 元写真と同一カメラでの全景比較: `city_photo_before_overview.png`、`city_photo_redrawn_all_overview.png`
- ブラウザ比較: `viewer/blender-preview.html` の「全棟描き直し版を試す」
- 生成画像の原本: `redraw_atlases/`。元の公式JPEGは無変更。
- UV位置合わせしたPNG・配布用JPEG: `redraw_atlases_aligned/`。画像生成で余白や島の外形が動いた場合、元写真の外接矩形へ位置合わせした。黒い穴になる境界だけ元JPEGで補った。
- 入力・出力・出典SHA-256・各棟の検査値: `redraw_atlas_manifest.json`、`redraw_atlases_aligned/coverage.json`。

最終JPEGは56枚で17.8 MiB。PNGのまま埋めたGLBは約94 MBだったため、JPEG品質91・色差サブサンプリングなしで再出力した。位置合わせ後に元写真で補った画素は全アトラスの約1.03%。元写真で有効なUV内部サンプル22,464点のうち、圧縮後に黒と判定された点は30点（約0.13%）。GLBの三角形数は元版と同じ6,194、画像58枚、サイドカーSHA-256一致。Blenderで全景、ブラウザで全景・代表壁面の切替を目視確認し、ブラウザの警告・エラーはなかった。既存ユニットテスト13件は通過した。

画像生成は、各アトラスを編集対象として「黒い余白とUV島の位置を維持し、写真に写る窓・入口・屋根設備などを同じ場所で鮮明に描き直す。規則的な窓列や新しい階を発明しない」と指示した。代表プロンプトは `redraw_atlas_manifest.json` に保存。判読できない細部、目地、反射、屋上設備は生成による推定を含み、現地写真との一致は未確認。生成画像のUV配置が大きく動いた2棟（`474210f2` と `6143206a`）では、境界の一部に元写真が残る。地面の2024年航空写真は描き直していない。

再現手順（画像生成済みの `redraw_atlases/` から）：

```powershell
python scripts/align_redrawn_atlases.py
python scripts/make_redraw_atlas_manifest.py
blender --background --python scripts/blender_export.py -- --scene dist/real/fukushima-east/map.json --output dist/real/fukushima-east/city_photo_redrawn_all.glb --texture-dir data/raw/plateau --ortho dist/real/fukushima-east/ortho_ground.png --redraw-manifest dist/real/fukushima-east/redraw_manifest.json --atlas-manifest dist/real/fukushima-east/redraw_atlas_manifest.json
```

以下は最初に制作した1壁面の検証記録。

## 狙い

`city_textured` / `city_sharp` の写真テクスチャがぼやける壁を、同じ建物の写真に写る窓・入口・換気口などの**位置と数**を手掛かりに描き直す。汎用の窓模様を当てはめない。

## 今回実施した範囲

- 福島駅東口エリアのPLATEAU LOD2建物 `plateau-bldg_bc117abb-d716-47ca-b1a2-c4044ba8509a` の壁面インデックス12を対象にした。
- 公式JPEG `a4fdf53b-4765-4cbc-ae1b-92f25562ddc1.jpg` のUV領域を、`scripts/extract_wall_reference.py` で正面図へ展開した。
- 展開画像を画像生成ツールの編集入力とし、窓列・下部開口・電柱類の配置を保って、輪郭や外壁材を鮮明に描き直した。
- `scripts/blender_export.py --redraw-manifest ...` で、この1面だけに新しい画像を貼った。残りの壁・屋根・航空写真は元画像のまま。LOD2形状は変更していない。
- `city_photo_redrawn.blend` と `city_photo_redrawn.glb` を出力。元の `city_sharp` は保存した。

## 比較

同じBlenderカメラから出力した画像：

- 元写真: `dist/real/fukushima-east/redraw_refs/bc117_wall12_before_3d.png`
- 描き直し: `dist/real/fukushima-east/redraw_refs/bc117_wall12_after_3d.png`

ブラウザの `viewer/blender-preview.html` でも「描き直した壁を見る」→「写真準拠の描き直しを試す」で切り替えられる。対象壁の手前に別の建物があるため、比較視点ではその手前を一時的に断面表示する。視点リセットで戻る。

## 再実行

開発用PythonにPillowとNumPy、Blender 3.1が必要。対象壁は上辺2頂点、下辺2頂点の順に並ぶ四角形を選ぶ。

```powershell
python scripts/extract_wall_reference.py --building-id plateau-bldg_bc117abb-d716-47ca-b1a2-c4044ba8509a --surface-index 12 --output dist/real/fukushima-east/redraw_refs/bc117_wall12_reference.png
blender --background --python scripts/blender_export.py -- --scene dist/real/fukushima-east/map.json --output dist/real/fukushima-east/city_photo_redrawn.glb --texture-dir data/raw/plateau --ortho dist/real/fukushima-east/ortho_ground.png --redraw-manifest dist/real/fukushima-east/redraw_manifest.json
```

元写真の各壁を先に展開し、見える構造を確認してから、描き直し画像を `redraw_manifest.json` に追加する。元写真のアトラスに直接描画すると、別の壁のUVや画素をずらす恐れがある。

## 画像生成に使用したプロンプト

モード: 組み込み `image_gen` のローカル画像編集。入力は `redraw_refs/bc117_wall12_reference.png`。

> Edit the attached flat, front-on reference image of ONE real building facade into a clean, sharply drawn, realistic architectural texture for a 3D building wall. The attached image is the edit target and exact layout reference. Preserve the image's rectangular framing and every visible facade feature at the same coordinates and scale: medium gray concrete wall; the isolated upper vents/openings; three rows of narrow vertical windows with exactly their observed spacing, count, and sizes; the small shadows and bright window sills; the lower horizontal ledge, glass/metal ground-floor openings and entrance; the vertical cables/poles crossing the facade. Carefully reconstruct crisp straight edges, window frames, concrete panel seams and tonal variation, removing photographic blur and pixel noise. Make it look like detailed hand-repainted photorealistic PBR base color texture, perfectly orthographic flat elevation, evenly lit, no perspective, no sky or ground outside the wall. Do not add or remove windows, doors, signs, floors, ornaments, or arbitrary decorative patterns; do not invent legible text. Keep the dark right edge/shadow where it is. The final image must be directly usable as a UV texture on this same wall.

## 品質と残件

窓の列・主要な開口・入口の配置は元写真と目視比較した。細いフレーム、コンクリートの目地、一部の反射や電柱の形には画像生成による推定が入るため、実物の厳密な再現とは呼ばない。この**1面の高精細版**は全56棟版でも使用している。元JPEG自体にない情報は確定できない。

Blenderで差し替え版を再読込し、GLBに新規画像1枚が含まれること、三角形数が元版と同じ6,194であること、SHA-256サイドカーが一致することを確認した。ブラウザで両版の表示切替と比較画像を確認した。測量点との照合、実物との撮影比較、低スペック実機の速度測定は未実施。
