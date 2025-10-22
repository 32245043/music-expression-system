import os
import subprocess
import shutil
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, session
from werkzeug.utils import secure_filename
import music21
from midi_processor import MidiProcessor  

# ============================================================
# アプリケーション設定
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")

# --- 出力フォルダ構成 ---
OUTPUT_DIRS = {
    "musicxml": os.path.join(OUTPUT_FOLDER, "musicxml"),
    "abc": os.path.join(OUTPUT_FOLDER, "abc"),
    "json": os.path.join(OUTPUT_FOLDER, "json"),
    "midi_full": os.path.join(OUTPUT_FOLDER, "midi", "full_parts"),
    "midi_single": os.path.join(OUTPUT_FOLDER, "midi", "single_parts"),
    "audio": os.path.join(OUTPUT_FOLDER, "audio"),  # ← ★ WAV出力フォルダを追加
}

# 必要なディレクトリが存在しない場合は作成する
for path in [UPLOAD_FOLDER, OUTPUT_FOLDER, *OUTPUT_DIRS.values()]:
    os.makedirs(path, exist_ok=True)

# アップロードを許可するファイルの拡張子
ALLOWED_EXTENSIONS = {'xml', 'musicxml', 'mid', 'midi'}

app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    OUTPUT_FOLDER=OUTPUT_FOLDER,
    SECRET_KEY='supersecretkey_for_session'
)

# ============================================================
# 表現プリセット
# ============================================================
PRESET_DEFINITIONS = {
    "tempo_expressions": {
        "なし": {"base_cc2": 0, "peak_cc2": 0},
        "Cantabile": {"base_cc2": 10, "peak_cc2": 30},
        "Dolce": {"base_cc2": -20, "peak_cc2": -5},
        "Maestoso": {"base_cc2": 10, "peak_cc2": 40},
        "Appassionato": {"base_cc2": 10, "peak_cc2": 35, "onset_ms": -10},
        "Con brio": {"base_cc2": 10, "peak_cc2": 25, "onset_ms": -30},
        "Leggiero": {"base_cc2": -10, "peak_cc2": 5, "onset_ms": -10},
        "Tranquillo": {"base_cc2": -20, "peak_cc2": -10, "onset_ms": -20},
        "Risoluto": {"base_cc2": 10, "peak_cc2": 30, "onset_ms": -10},
        "Sostenuto": {"base_cc2": 0, "peak_cc2": 10, "onset_ms": 30},
        "Marcato": {"base_cc2": 10, "peak_cc2": 30, "onset_ms": 0},

    },
    "adjective_expressions": {
        "なし": {"base_cc2": 0, "peak_cc2": 0},
        "明るい": {"base_cc2": 5, "peak_cc2": 20},
        "華やか": {"base_cc2": 10, "peak_cc2": 28},
        "暗い": {"base_cc2": -5, "peak_cc2": 8},
    }
}

# ============================================================
# ヘルパー関数
# ============================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_name(name):
    return "".join(c if c.isalnum() or c in ('_', '-') else "_" for c in name)

def convert_with_xml2abc(xml_path, abc_path):
    """xml2abc.pyを使ってMusicXML→ABC変換"""
    try:
        out_dir = os.path.dirname(abc_path)
        if os.path.exists(abc_path):
            os.remove(abc_path)
        cmd = ["python", "xml2abc.py", xml_path, "-o", out_dir]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # xml2abcが出力するファイル名(元ファイル名.abc)をリネームする
        base_name = os.path.splitext(os.path.basename(xml_path))[0]
        generated_path = os.path.join(out_dir, base_name + ".abc")

        if os.path.exists(generated_path):
            os.rename(generated_path, abc_path)
            return True
        return False
    except Exception as e:
        app.logger.error(f"xml2abc失敗: {e}")
        return False

# ============================================================
# 生成ファイルの配信ルート
# ============================================================
@app.route('/output/<path:filename>')
def serve_output(filename):
    # outputディレクトリ内のファイルを配信する
    return send_from_directory(OUTPUT_FOLDER, filename)

# ============================================================
# トップページ
# ============================================================
@app.route('/')
def index():
    # トップページを表示
    # セッションをクリアして初期状態に戻す
    session.clear()
    return render_template('index.html', presets=PRESET_DEFINITIONS)

# ============================================================
# ファイルアップロード処理
# ============================================================
@app.route('/upload', methods=['POST'])
def upload_files():
    # MusicXMLとMIDIファイルを受け取り、パートごとに分割・変換する
    if 'xml-file' not in request.files or 'midi-file' not in request.files:
        return jsonify({'error': 'MusicXMLとMIDIファイルの両方が必要です'}), 400

    xml_file = request.files['xml-file']
    midi_file = request.files['midi-file']

    if not (xml_file and allowed_file(xml_file.filename) and midi_file and allowed_file(midi_file.filename)):
        return jsonify({'error': '許可されていないファイル形式です'}), 400

    xml_filename = secure_filename(xml_file.filename)
    midi_filename = secure_filename(midi_file.filename)
    xml_path = os.path.join(UPLOAD_FOLDER, xml_filename)
    midi_path = os.path.join(UPLOAD_FOLDER, midi_filename)
    xml_file.save(xml_path)
    midi_file.save(midi_path)

    # 後続の処理でファイルパスを使用するためセッションに保存
    session['xml_path'] = xml_path
    session['midi_path'] = midi_path

    song_name = safe_name(os.path.splitext(xml_filename)[0])

    try:
        score = music21.converter.parse(xml_path)
        processor = MidiProcessor(midi_path)
        parts_info = []
        all_abc_data = {}

        for i, part in enumerate(score.parts):
            raw_part_name = part.partName or f"Part{i+1}"
            part_name = safe_name(raw_part_name)

            # 各出力ファイルのパス
            xml_out_path = os.path.join(OUTPUT_DIRS["musicxml"], f"{song_name}_{part_name}.musicxml")
            abc_out_path = os.path.join(OUTPUT_DIRS["abc"], f"{song_name}_{part_name}.abc")
            note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{song_name}_{part_name}_note_map.json")

            # パートを個別のMusicXMLファイルとして書き出し
            part.write('musicxml', fp=xml_out_path)

            try:
                # パート情報からノートマップ（音符とTickの対応表）をJSONで生成
                processor.create_note_map_from_part(part, note_map_path)
            except Exception as e:
                app.logger.error(f"note_map生成エラー: {e}")
                note_map_path = None

            # MusicXMLからABC記譜法へ変換
            success = convert_with_xml2abc(xml_out_path, abc_out_path)
            if success and os.path.exists(abc_out_path):
                with open(abc_out_path, 'r', encoding='utf-8', errors='ignore') as f:
                    abc_text = f.read()
            else:
                # 変換失敗時はダミーデータを生成
                abc_text = f"X:1\nT:{raw_part_name}\nM:4/4\nL:1/8\nK:C\n| CDEC | GFEF |]"
            all_abc_data[i] = abc_text

            # フロントエンドに返すパート情報をまとめる
            parts_info.append({
                'id': getattr(part, 'id', None),
                'name': raw_part_name,
                'index': i,
                'note_map': f"json/{os.path.basename(note_map_path)}" if note_map_path else None,
                'musicxml': f"musicxml/{os.path.basename(xml_out_path)}",
                'abc': f"abc/{os.path.basename(abc_out_path)}" if success else None
            })

        return jsonify({
            'message': 'ファイルが正常にアップロードされました',
            'parts': parts_info,
            'all_abc_data': all_abc_data
        })
    except Exception as e:
        app.logger.exception("MusicXML読み込みエラー")
        return jsonify({'error': f'MusicXML読み込みエラー: {str(e)}'}), 500

# ============================================================
# MIDI加工処理
# ============================================================
@app.route('/process', methods=['POST'])
def process_midi():
    # 指定されたパートのフレーズに表現を適用し、MIDIとWAVファイルを生成する
    if 'midi_path' not in session:
        return jsonify({'error': 'MIDIファイルがアップロードされていません。'}), 400

    data = request.json
    part_index = data.get('partIndex')
    part_name = data.get('partName')
    phrase_info = data.get('phrase')
    preset_params = data.get('presetParams')

    if phrase_info is None or preset_params is None or part_index is None or part_name is None:
        return jsonify({'error': '処理に必要なデータが不足しています。'}), 400

    try:
        processor = MidiProcessor(session['midi_path'])

        # 対応するノートマップJSONファイルを探す
        safe_part_name = part_name.replace(" ", "_").replace("/", "_")
        note_map_candidates = [
            f for f in os.listdir(OUTPUT_DIRS["json"])
            if safe_part_name in f and f.endswith("_note_map.json")
        ]
        if not note_map_candidates:
            return jsonify({'error': f'note_mapが見つかりません: {part_name}'}), 404

        note_map_path = os.path.join(OUTPUT_DIRS["json"], note_map_candidates[0])
        with open(note_map_path, 'r', encoding='utf-8') as f:
            note_map = json.load(f)

        # 音符のインデックスをMIDIのTickに変換する
        def idx_to_tick(idx):
            entry = next((e for e in note_map if e['index'] == idx), None)
            return entry['tick'] if entry else None

        # フレーズの開始、ピーク、終了位置をTickに変換
        start_tick = idx_to_tick(phrase_info['start_index'])
        peak_tick = idx_to_tick(phrase_info['peak_index'])
        end_tick = idx_to_tick(phrase_info['end_index'])

        # 出力ディレクトリのパス
        single_processed_dir = os.path.join(OUTPUT_DIRS["midi_single"], "processed")
        full_processed_dir = os.path.join(OUTPUT_DIRS["midi_full"], "processed")
        single_original_dir = os.path.join(OUTPUT_DIRS["midi_single"], "original")
        full_original_dir = os.path.join(OUTPUT_DIRS["midi_full"], "original")
        os.makedirs(single_processed_dir, exist_ok=True)
        os.makedirs(full_processed_dir, exist_ok=True)
        os.makedirs(single_original_dir, exist_ok=True)
        os.makedirs(full_original_dir, exist_ok=True)

        # 比較用のMIDIファイルを作成
        original_single_out = os.path.join(single_original_dir, f"part{part_index+1}_original.mid")
        original_full_out = os.path.join(full_original_dir, "full_original.mid")
        if not os.path.exists(original_full_out):
            shutil.copy(session['midi_path'], original_full_out)
        if not os.path.exists(original_single_out):
            processor.save_single_part_to_file(part_index, original_single_out)

        # MIDIに表現を適用
        processed_single = processor.apply_expression_by_ticks(part_index, start_tick, end_tick, peak_tick, preset_params)
        single_out_path = os.path.join(single_processed_dir, f"processed_part{part_index+1}.mid")
        processor.save_to_file(processed_single, single_out_path)

        processed_full = processor.apply_expression_by_ticks(None, start_tick, end_tick, peak_tick, preset_params)
        full_out_path = os.path.join(full_processed_dir, "processed_full.mid")
        processor.save_to_file(processed_full, full_out_path)

        # --- FluidSynthでMIDIからWAVへの変換 ---
        fluidsynth_exe = r"C:\tools\fluidsynth\bin\fluidsynth.exe"
        soundfont_path = r"soundfonts\FluidR3_GM.sf2"

        # WAVファイルへの出力ディレクトリ構造をMIDIと合わせる
        audio_root = os.path.join(OUTPUT_FOLDER, "audio")
        single_audio_original = os.path.join(audio_root, "single_parts", "original")
        single_audio_processed = os.path.join(audio_root, "single_parts", "processed")
        full_audio_original = os.path.join(audio_root, "full_parts", "original")
        full_audio_processed = os.path.join(audio_root, "full_parts", "processed")

        for d in [single_audio_original, single_audio_processed, full_audio_original, full_audio_processed]:
            os.makedirs(d, exist_ok=True)

        # WAVファイルの出力パス
        processed_wav_single = os.path.join(single_audio_processed, f"processed_part{part_index+1}.wav")
        original_wav_single = os.path.join(single_audio_original, f"part{part_index+1}_original.wav")
        processed_wav_full = os.path.join(full_audio_processed, "processed_full.wav")
        original_wav_full = os.path.join(full_audio_original, "full_original.wav")

        try:
            # 各MIDIファイルをWAVに変換
            subprocess.run([fluidsynth_exe, "-ni", soundfont_path, single_out_path, "-F", processed_wav_single, "-r", "44100"],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run([fluidsynth_exe, "-ni", soundfont_path, original_single_out, "-F", original_wav_single, "-r", "44100"],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run([fluidsynth_exe, "-ni", soundfont_path, full_out_path, "-F", processed_wav_full, "-r", "44100"],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run([fluidsynth_exe, "-ni", soundfont_path, original_full_out, "-F", original_wav_full, "-r", "44100"],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"✅ WAV生成完了: {processed_wav_single}")
        except subprocess.CalledProcessError as e:
            print("⚠️ FluidSynth 実行エラー:", e.stderr.decode(errors="ignore"))

        # フロントエンドに生成されたファイルのパスを返す
        return jsonify({
            "original_single": f"/output/midi/single_parts/original/part{part_index+1}_original.mid",
            "processed_single": f"/output/midi/single_parts/processed/processed_part{part_index+1}.mid",
            "original_full": "/output/midi/full_parts/original/full_original.mid",
            "processed_full": "/output/midi/full_parts/processed/processed_full.mid",
            "original_single_wav": f"/output/audio/single_parts/original/part{part_index+1}_original.wav",
            "processed_single_wav": f"/output/audio/single_parts/processed/processed_part{part_index+1}.wav",
            "original_full_wav": "/output/audio/full_parts/original/full_original.wav",
            "processed_full_wav": "/output/audio/full_parts/processed/processed_full.wav"
        })

    except Exception as e:
        app.logger.exception("MIDI処理エラー")
        return jsonify({'error': f'MIDI処理中にエラーが発生しました: {str(e)}'}), 500

# ============================================================
# WAV配信ルート
# ============================================================
@app.route("/audio/<path:filename>")
def serve_audio(filename):
    """生成されたWAVファイルをブラウザへ配信"""
    return send_from_directory(os.path.join(OUTPUT_FOLDER, "audio"), filename)

# ============================================================
# MIDI配信ルート
# ============================================================
@app.route("/midi/<path:filename>")
def serve_midi(filename):
    """MIDIファイルをブラウザへ配信"""
    return send_from_directory(os.path.join(OUTPUT_FOLDER, "midi"), filename)

# ============================================================
# 実行
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)
