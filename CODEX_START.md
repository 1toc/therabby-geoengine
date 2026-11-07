# Codexへの最初の指示（コピーして使う）

このリポジトリはTherabby GeoEngineのM1実装基盤です。`PROJECT.md`と`AGENTS.md`を最初に読み、M1の実データ動作検証と完成を進めてください。

前提：動作実績のあるv0.1のThree.js方式を維持。利用者PCにPythonやBlenderを要求しない。開発PCではBlender Pythonのバッチ実行を使い、MCPは必須にしない。対象は福島駅東口周辺200m四方。テスト用fixtureは実在データと絶対に混同しないこと。

まず `python -m unittest discover -s tests -v` を実行して既存テストが通ることを確認し、ネット接続がある場合は `fetch-osm` と `fetch-plateau --dry-run` を実行してレスポンスを検証する。PLATEAU実データのCityGML2.0 LOD1を読み、`build`と`validate`で福島市の実マップJSONを作成する。必要であればパーサーを拡張して回帰テストを追加する。

次にBlenderのバックグラウンド処理でGLBを生成し、3Dプレビュー上で建物・道路の位置ずれを確認する。GLBが生成できてもLOD2テクスチャ対応や地形勾配がないことを明示する。最後にI-RIHA101（i5-14500T／8GB／Intel内蔵GPU）で実測できる計測項目と確認手順をまとめる。少なくとも別の小区域でも再生成できるかを確認する。

完了時には、変更ファイル、試したコマンド、成功・失敗、出典URL、未検証事項、次マイルストーンへ渡す課題を`docs/M1_STATUS.md`へ追記し報告する。実データが取得できなければデモだけで完了扱いにしないこと。
