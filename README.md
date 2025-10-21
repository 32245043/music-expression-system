# 🎵 **発想標語に対応する演奏見本生成システム**

---

## 📄 概要
本システムは、音楽の「発想標語（*Cantabile*, *Dolce*, *Maestoso*など）」と演奏の強弱や速度（音の長さ）を変化させ、その違いを体験できるWebアプリケーションです。  
ブラウザ上で楽譜を表示し、クリックで音符を選択して発想標語を選ぶと、音の違いを再生して比べることができます。  

---

## ✨ 主な特徴
- 楽譜を自動で表示（MusicXML → ABC → SVG化）
- 音符をクリックしてフレーズの範囲を指定できる
- 指定部分のMIDIを加工して演奏表情の違いを作ることができる
- 発想標語の適用前後の音を比較して聴き分けられる

---

## 🎛 機能一覧

| 機能 | 内容 |
| :--- | :--- |
| MusicXML読み込み | 楽譜データを読み込み、各パートを抽出 |
| 楽譜表示（abcjs） | ブラウザで楽譜を表示（SVG） |
| 音符クリック選択 | 音符をクリックして加工したいフレーズ範囲を指定 |
| MIDI加工 | 強弱・音の長さ・アタックなどを自動調整 |
| 音声出力（WAV） | 加工前後のMIDIをWAVとして生成 |
| 比較再生 | 「再生／停止」ボタンで聴き比べ可能 |
| データ整理 | 各出力（MIDI・WAV・JSONなど）を自動保存 |


## 📁 ディレクトリ構成
```
music-expression
│
├── app.py                         # Flaskアプリ本体（ルーティング・API処理）
├── midi_processor.py              # MIDI加工・WAV生成ロジック
│
├── uploads/                       # アップロードしたMusicXML
│   └── ファイル名.musicxml
│
├── output/                        # 自動生成される
│   ├── musicxml/                  # 各パートのMusicXML
│   ├── abc/                       # ABC記譜法ファイル
│   ├── json/                      # note_map.json(音符とMIDIのtickを対応付けるためのマッピングデータ)
│   ├── midi/                      # MIDI(出力)
│   │   ├── single_parts/          # 選択パート
│   │   │   ├── original/          # 適用前
│   │   │   └── processed/         # 適用後
│   │   └── full_parts/            # 全パート(加工も含む)
│   │       ├── original/
│   │       └── processed/
│   └── audio/                     # FluidSynthで生成されたWAV
│       ├── single_parts/
│       └── full_parts/
│
├── static/                        # Web静的ファイル
│   ├── css/style.css              # css
│   └── js/                        # JavaScript
│       ├── main.js                # Flaskで生成されたデータをブラウザ上で表示・操作・再生する
│       └── abcjs-basic-min.js
│
├── templates/
│   └── index.html                 # FlaskメインUI
│
├── soundfonts/
│   └── FluidR3_GM.sf2            # SoundFont
│
└── requirements.txt               # Python依存関係
```

---

## ⚙️ 環境構築手順（Windows）
本システムは**Visual Studio Code(VS Code)**を使用しています。  
また、VS Codeに以下の拡張機能をインストールしてください。  
- Python
- Pylance
📁ディレクトリ構成を見ながら本リポジトリ内のソースコード等を配置してください。

### ① 仮想環境の作成
プロジェクトフォルダのルートでターミナル(PowerShellなど)を開き、以下のコマンドを順番に実行してください。
```bash
python -m venv .venv
```

### ② 仮想環境の有効化 (手動)
```bash
.\.venv\Scripts\Activate.ps1
```
成功すると、コマンドラインの先頭に`(.venv)`と表示されます。

### 💡 VS Codeでの自動有効化設定 (おすすめ)
②の方法は毎回手動で`Activate.ps1`を実行するので、VS Codeに仮想環境を認識させ、ターミナル起動時に自動で有効化する設定を推奨します。

1. コマンドパレットを開く(`Ctrl + Shift + P`)
2. 「`Python： インタープリターの選択`」を選択する
3. リストから、作成した仮想環境のPython実行ファイル(例：`.\.venv\Scripts\python.exe`)を開く
これにより、自動的に仮想環境が有効化されます。

### ③ 必要ライブラリのインストール
```bash
pip install -r requirements.txt
```

### ④ FluidSynth の導入
1. 本リポジトリ内にある`fluidsynth`フォルダをダウンロードします。
2. 以下のディレクトリに`fluidsyth`フォルダを配置してください。
   ```bash
   C:\tools\fluidsynth\bin
   ```
   ※`C:\tools`がない場合は作成してください。
3. 環境変数`Path`に以下を追加してください。
   ```
   C:\tools\fluidsynth\bin
   ```
---

## 🚀 実行方法

1.  VSCodeターミナル
   ```bash
   flask run
   ```
2. ブラウザでアクセス  
   ```bash
   http://127.0.0.1:5000
   ```
   表示されるURLをクリックしてください
3. MusicXML・MIDIをアップロードし、読み込み開始ボタンを押してください。  
(正常に読み込めると画面上部に`✅ ファイル読み込み完了。パートを選択してください。`と表示されます)  
4. パート選択から、任意のパートを選択してください
(画面上部に`✅ 音符をクリックして範囲を指定できます。`と表示され、右側に楽譜が表示されます。)
5. フレーズ開始 → 終了 → 頂点となる音符を順番にクリックしてください
(音符は開始：赤、終了：青、頂点：緑になります)  
※やり直したい場合は`選択リセット`を押してください  
6. フレーズ範囲に適用させたい発想標語プリセットを選択してください。
7. `適用して加工後MIDIを生成`を押すとWAVが生成され、「再生」「停止」ボタンで音源を比較することができます。  

---

## 🔊 出力ファイルの構成
| 種別 | 保存先 | 説明 |
|------|----------|------|
| 加工前MIDI | `output/midi/single_parts/original/` | 元の単一パート |
| 加工後MIDI | `output/midi/single_parts/processed/` | 発想標語適用後 |
| WAV音声 | `output/audio/...` | FluidSynthで生成された音声 |
| note_map | `output/json/...` | tickと音符対応情報 |
| ABC譜面 | `output/abc/...` | ブラウザ用楽譜データ |

---
