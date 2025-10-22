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
# 表現プリセット（発想標語のみ）
# ============================================================
PRESET_DEFINITIONS = {
    "tempo_expressions": {
        "なし": {"base_cc2": 0, "peak_cc2": 0},
        "Cantabile": {"base_cc2": 10, "peak_cc2": 30, "onset_ms": 30},
        "Dolce": {"base_cc2": -20, "peak_cc2": -5, "onset_ms": 20},
        "Maestoso": {"base_cc2": 10, "peak_cc2": 40, "onset_ms": 40},
        "Appassionato": {"base_cc2": 10, "peak_cc2": 35, "onset_ms": -10},
        "Con brio": {"base_cc2": 10, "peak_cc2": 25, "onset_ms": -30},
        "Leggiero": {"base_cc2": -10, "peak_cc2": 5, "onset_ms": -10},
        "Tranquillo": {"base_cc2": -20, "peak_cc2": -10, "onset_ms": -20},
        "Risoluto": {"base_cc2": 10, "peak_cc2": 30, "onset_ms": -10},
        "Sostenuto": {"base_cc2": 0, "peak_cc2": 10, "onset_ms": 30},
        "Marcato": {"base_cc2": 10, "peak_cc2": 30, "onset_ms": 0},
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
# ファイルアップロード処理（★連番対応）
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

    # --- 元ファイル名と安全化 ---
    xml_filename = secure_filename(xml_file.filename)
    song_name_base = safe_name(os.path.splitext(xml_filename)[0])

    # --- ✅ 既存ファイル数をカウントして連番を付与 ---
    counter = 1
    while True:
        # オリジナルファイル名の衝突を確認
        original_xml_path = os.path.join(UPLOAD_FOLDER, f"{song_name_base}_{counter}_original.musicxml")
        original_midi_path = os.path.join(UPLOAD_FOLDER, f"{song_name_base}_{counter}_original.mid")
        if not os.path.exists(original_xml_path) and not os.path.exists(original_midi_path):
            break
        counter += 1
    
    song_name = f"{song_name_base}_{counter}"

    # 元ファイルを「_original」付きで保存
    original_xml_path = os.path.join(UPLOAD_FOLDER, f"{song_name}_original.musicxml")
    original_midi_path = os.path.join(UPLOAD_FOLDER, f"{song_name}_original.mid")
    xml_file.save(original_xml_path)
    midi_file.save(original_midi_path)
    
    # --- 「作業用MIDIファイル」を作成 ---
    working_midi_path = os.path.join(UPLOAD_FOLDER, f"{song_name}_working.mid")
    shutil.copy(original_midi_path, working_midi_path)

    # --- セッションに各種パスを保存 ---
    session['xml_path'] = original_xml_path
    session['original_midi_path'] = original_midi_path
    session['working_midi_path'] = working_midi_path
    session['song_name'] = song_name

    try:
        # MusicXMLの解析は常にオリジナルファイルで行う
        score = music21.converter.parse(session['xml_path'])
        # MidiProcessorには「作業用MIDI」を渡して初期化
        processor = MidiProcessor(session['working_midi_path'])
        parts_info = []
        all_abc_data = {}

        for i, part in enumerate(score.parts):
            raw_part_name = part.partName or f"Part{i+1}"
            part_name = safe_name(raw_part_name)

            # ✅ 出力ファイルにも連番付きの song_name を使用
            xml_out_path = os.path.join(OUTPUT_DIRS["musicxml"], f"{song_name}_{part_name}.musicxml")
            abc_out_path = os.path.join(OUTPUT_DIRS["abc"], f"{song_name}_{part_name}.abc")
            note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{song_name}_{part_name}_note_map.json")

            part.write('musicxml', fp=xml_out_path)

            try:
                # note_mapはMusicXMLの構造から生成するので、processorのMIDIファイルは直接関係ない
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
            'message': f'ファイルが正常にアップロードされました（連番: {counter}）',
            'parts': parts_info,
            'all_abc_data': all_abc_data,
            'version': counter
        })
    except Exception as e:
        app.logger.exception("MusicXML読み込みエラー")
        return jsonify({'error': f'MusicXML読み込みエラー: {str(e)}'}), 500

# ============================================================
# MIDI加工処理（曲名＋パート名付き出力）
# ============================================================
@app.route('/process', methods=['POST'])
def process_midi():
    # 加工対象はセッションに保存された「作業用MIDI」
    if 'working_midi_path' not in session:
        return jsonify({'error': '作業用MIDIファイルが見つかりません。'}), 400

    data = request.json
    part_index = data.get('partIndex')
    part_name = data.get('partName')
    phrase_info = data.get('phrase')
    preset_params = data.get('presetParams')

    if phrase_info is None or preset_params is None or part_index is None or part_name is None:
        return jsonify({'error': '処理に必要なデータが不足しています。'}), 400

    try:
        # MidiProcessorに現在の「作業用MIDI」を読み込ませる
        processor = MidiProcessor(session['working_midi_path'])
        song_name = session.get("song_name", "unknown_song")
        safe_part_name = part_name.replace(" ", "_").replace("/", "_")

        note_map_candidates = [
            f for f in os.listdir(OUTPUT_DIRS["json"])
            if safe_name(part_name) in f and f.endswith("_note_map.json") and song_name in f
        ]
        if not note_map_candidates:
            return jsonify({'error': f'note_mapが見つかりません: {part_name}'}), 404

        note_map_path = os.path.join(OUTPUT_DIRS["json"], note_map_candidates[0])
        with open(note_map_path, 'r', encoding='utf-8') as f:
            note_map = json.load(f)

        def idx_to_tick(idx):
            entry = next((e for e in note_map if e['index'] == idx), None)
            return entry['tick'] if entry else None

        start_tick = idx_to_tick(phrase_info['start_index'])
        peak_tick = idx_to_tick(phrase_info['peak_index'])
        end_tick = idx_to_tick(phrase_info['end_index'])
        
        # --- ディレクトリ作成 ---
        single_processed_dir = os.path.join(OUTPUT_DIRS["midi_single"], "processed")
        full_processed_dir = os.path.join(OUTPUT_DIRS["midi_full"], "processed")
        single_original_dir = os.path.join(OUTPUT_DIRS["midi_single"], "original")
        full_original_dir = os.path.join(OUTPUT_DIRS["midi_full"], "original")
        os.makedirs(single_processed_dir, exist_ok=True)
        os.makedirs(full_processed_dir, exist_ok=True)
        os.makedirs(single_original_dir, exist_ok=True)
        os.makedirs(full_original_dir, exist_ok=True)

        # --- オリジナルMIDIの出力（初回のみ） ---
        original_single_out = os.path.join(single_original_dir, f"{song_name}_{safe_part_name}_original.mid")
        original_full_out = os.path.join(full_original_dir, f"{song_name}_full_original.mid")
        if not os.path.exists(original_full_out):
            shutil.copy(session['original_midi_path'], original_full_out)
        if not os.path.exists(original_single_out):
            # オリジナルMIDIから単一パートを抜き出す
            original_processor = MidiProcessor(session['original_midi_path'])
            original_processor.save_single_part_to_file(part_index, original_single_out)

        # --- 加工処理 ---
        # 全パート加工後のMIDIオブジェクトを取得し、「作業用MIDI」に上書き保存
        processed_full = processor.apply_expression_by_ticks(None, start_tick, end_tick, peak_tick, preset_params)
        processor.save_to_file(processed_full, session['working_midi_path'])

        # 単一パート加工後のMIDIオブジェクトも取得（これはファイルには直接保存しない）
        processed_single = processor.apply_expression_by_ticks(part_index, start_tick, end_tick, peak_tick, preset_params)

        # --- ダウンロード/再生用のファイルとして出力 ---
        single_out_path = os.path.join(single_processed_dir, f"{song_name}_{safe_part_name}_processed.mid")
        processor.save_to_file(processed_single, single_out_path)
        
        full_out_path = os.path.join(full_processed_dir, f"{song_name}_full_processed.mid")
        shutil.copy(session['working_midi_path'], full_out_path) # 最新の作業用MIDIをコピー

        # --- FluidSynthでMIDIからWAVへの変換 ---
        fluidsynth_exe = r"C:\tools\fluidsynth\bin\fluidsynth.exe"
        soundfont_path = r"soundfonts\FluidR3_GM.sf2"

        audio_root = os.path.join(OUTPUT_FOLDER, "audio")
        single_audio_original = os.path.join(audio_root, "single_parts", "original")
        single_audio_processed = os.path.join(audio_root, "single_parts", "processed")
        full_audio_original = os.path.join(audio_root, "full_parts", "original")
        full_audio_processed = os.path.join(audio_root, "full_parts", "processed")

        for d in [single_audio_original, single_audio_processed, full_audio_original, full_audio_processed]:
            os.makedirs(d, exist_ok=True)

        processed_wav_single = os.path.join(single_audio_processed, f"{song_name}_{safe_part_name}_processed.wav")
        original_wav_single = os.path.join(single_audio_original, f"{song_name}_{safe_part_name}_original.wav")
        processed_wav_full = os.path.join(full_audio_processed, f"{song_name}_full_processed.wav")
        original_wav_full = os.path.join(full_audio_original, f"{song_name}_full_original.wav")

        try:
            # 加工後のWAVを生成
            subprocess.run([fluidsynth_exe, "-ni", soundfont_path, single_out_path, "-F", processed_wav_single, "-r", "44100"], check=True)
            subprocess.run([fluidsynth_exe, "-ni", soundfont_path, full_out_path, "-F", processed_wav_full, "-r", "44100"], check=True)
            # オリジナルWAVがなければ生成
            if not os.path.exists(original_wav_single):
                subprocess.run([fluidsynth_exe, "-ni", soundfont_path, original_single_out, "-F", original_wav_single, "-r", "44100"], check=True)
            if not os.path.exists(original_wav_full):
                subprocess.run([fluidsynth_exe, "-ni", soundfont_path, original_full_out, "-F", original_wav_full, "-r", "44100"], check=True)
            print(f"✅ WAV生成完了: {processed_wav_single}")
        except subprocess.CalledProcessError as e:
            print("⚠️ FluidSynth 実行エラー:", e.stderr.decode(errors="ignore"))

        return jsonify({
            "original_single": f"/output/midi/single_parts/original/{os.path.basename(original_single_out)}",
            "processed_single": f"/output/midi/single_parts/processed/{os.path.basename(single_out_path)}",
            "original_full": f"/output/midi/full_parts/original/{os.path.basename(original_full_out)}",
            "processed_full": f"/output/midi/full_parts/processed/{os.path.basename(full_out_path)}",
            "original_single_wav": f"/output/audio/single_parts/original/{os.path.basename(original_wav_single)}",
            "processed_single_wav": f"/output/audio/single_parts/processed/{os.path.basename(processed_wav_single)}",
            "original_full_wav": f"/output/audio/full_parts/original/{os.path.basename(original_wav_full)}",
            "processed_full_wav": f"/output/audio/full_parts/processed/{os.path.basename(processed_wav_full)}"
        })

    except Exception as e:
        app.logger.exception("MIDI処理エラー")
        return jsonify({'error': f'MIDI処理中にエラーが発生しました: {str(e)}'}), 500

# ============================================================
# ★★★ 新しいルート：MIDIのリセット ★★★
# ============================================================
@app.route('/reset_midi', methods=['POST'])
def reset_midi():
    """すべての加工をリセットして、元のMIDIの状態に戻す"""
    if 'original_midi_path' in session and 'working_midi_path' in session:
        try:
            # 元のMIDIファイルを、作業用MIDIファイルに上書きコピーする
            shutil.copy(session['original_midi_path'], session['working_midi_path'])
            return jsonify({'message': 'すべての加工をリセットしました。'})
        except Exception as e:
            app.logger.exception("リセットエラー")
            return jsonify({'error': f'リセット中にエラーが発生しました: {str(e)}'}), 500
    return jsonify({'error': 'リセット対象のファイルが見つかりません。'}), 400

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