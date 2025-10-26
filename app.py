import os
import subprocess
import shutil
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, session
from werkzeug.utils import secure_filename
import music21
from midi_processor import MidiProcessor  
from mido import MidiFile, MidiTrack
import copy

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
    "audio": os.path.join(OUTPUT_FOLDER, "audio"),
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

        base_name = os.path.splitext(os.path.basename(xml_path))[0]
        generated_path = os.path.join(out_dir, base_name + ".abc")

        if os.path.exists(generated_path):
            os.rename(generated_path, abc_path)
            return True
        return False
    except Exception as e:
        app.logger.error(f"xml2abc失敗: {e}")
        return False

def generate_midi_from_history():
    history = session.get('history', [])
    original_midi_path = session.get('original_midi_path')
    if not original_midi_path or not os.path.exists(original_midi_path):
        return None

    current_midi_obj = MidiFile(original_midi_path)

    for instruction in history:
        processor = MidiProcessor(current_midi_obj)
        
        phrase = instruction['phrase']
        params = instruction['preset_params']
        note_map_path = instruction['note_map_path']
        
        with open(note_map_path, 'r', encoding='utf-8') as f:
            note_map = json.load(f)

        def idx_to_tick(idx):
            entry = next((e for e in note_map if e['index'] == idx), None)
            return entry['tick'] if entry else None

        start_tick = idx_to_tick(phrase.get('start_index'))
        peak_tick = idx_to_tick(phrase.get('peak_index'))
        end_tick = idx_to_tick(phrase.get('end_index'))
        
        current_midi_obj = processor.apply_expression_by_ticks(None, start_tick, end_tick, peak_tick, params)

    return current_midi_obj

def _create_output_files_and_response(latest_midi_obj, part_index, part_name):
    song_name = session.get("song_name")
    safe_part_name = safe_name(part_name)

    single_processed_dir = os.path.join(OUTPUT_DIRS["midi_single"], "processed")
    full_processed_dir = os.path.join(OUTPUT_DIRS["midi_full"], "processed")
    single_original_dir = os.path.join(OUTPUT_DIRS["midi_single"], "original")
    full_original_dir = os.path.join(OUTPUT_DIRS["midi_full"], "original")
    for d in [single_processed_dir, full_processed_dir, single_original_dir, full_original_dir]:
        os.makedirs(d, exist_ok=True)

    full_out_path = os.path.join(full_processed_dir, f"{song_name}_full_processed.mid")
    latest_midi_obj.save(full_out_path)

    single_midi = MidiFile(ticks_per_beat=latest_midi_obj.ticks_per_beat)
    if 0 <= part_index < len(latest_midi_obj.tracks):
        track_copy = copy.deepcopy(latest_midi_obj.tracks[part_index])
        single_midi.tracks.append(track_copy)
    else:
        single_midi.tracks.append(MidiTrack())
    single_out_path = os.path.join(single_processed_dir, f"{song_name}_{safe_part_name}_processed.mid")
    single_midi.save(single_out_path)
    
    original_processor = MidiProcessor(session['original_midi_path'])
    original_single_out = os.path.join(single_original_dir, f"{song_name}_{safe_part_name}_original.mid")
    if not os.path.exists(original_single_out):
        original_processor.save_single_part_to_file(part_index, original_single_out)
    original_full_out = os.path.join(full_original_dir, f"{song_name}_full_original.mid")
    if not os.path.exists(original_full_out):
        shutil.copy(session['original_midi_path'], original_full_out)

    fluidsynth_exe = r"C:\tools\fluidsynth\bin\fluidsynth.exe"
    soundfont_path = r"soundfonts\FluidR3_GM.sf2"
    audio_root = os.path.join(OUTPUT_FOLDER, "audio")
    
    single_audio_processed = os.path.join(audio_root, "single_parts", "processed", f"{song_name}_{safe_part_name}_processed.wav")
    original_wav_single = os.path.join(audio_root, "single_parts", "original", f"{song_name}_{safe_part_name}_original.wav")
    processed_wav_full = os.path.join(audio_root, "full_parts", "processed", f"{song_name}_full_processed.wav")
    original_wav_full = os.path.join(audio_root, "full_parts", "original", f"{song_name}_full_original.wav")

    for d in [os.path.dirname(single_audio_processed), os.path.dirname(original_wav_single), os.path.dirname(processed_wav_full), os.path.dirname(original_wav_full)]:
        os.makedirs(d, exist_ok=True)
    
    try:
        subprocess.run([fluidsynth_exe, "-ni", soundfont_path, single_out_path, "-F", single_audio_processed, "-r", "44100"], check=True, capture_output=True)
        subprocess.run([fluidsynth_exe, "-ni", soundfont_path, full_out_path, "-F", processed_wav_full, "-r", "44100"], check=True, capture_output=True)
        if not os.path.exists(original_wav_single):
            subprocess.run([fluidsynth_exe, "-ni", soundfont_path, original_single_out, "-F", original_wav_single, "-r", "44100"], check=True, capture_output=True)
        if not os.path.exists(original_wav_full):
            subprocess.run([fluidsynth_exe, "-ni", soundfont_path, original_full_out, "-F", original_wav_full, "-r", "44100"], check=True, capture_output=True)
    except Exception as e:
        app.logger.error(f"WAV生成エラー: {e}")

    response = {
        "original_single_wav": f"/output/audio/single_parts/original/{os.path.basename(original_wav_single)}",
        "processed_single_wav": f"/output/audio/single_parts/processed/{os.path.basename(single_audio_processed)}",
        "original_full_wav": f"/output/audio/full_parts/original/{os.path.basename(original_wav_full)}",
        "processed_full_wav": f"/output/audio/full_parts/processed/{os.path.basename(processed_wav_full)}",
        "history": session.get('history', [])
    }
    return response

# ============================================================
# 生成ファイルの配信ルート
# ============================================================
@app.route('/output/<path:filename>')
def serve_output(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

# ============================================================
# トップページ
# ============================================================
@app.route('/')
def index():
    session.clear()
    return render_template('index.html', presets=PRESET_DEFINITIONS)

# ============================================================
# ファイルアップロード処理
# ============================================================
@app.route('/upload', methods=['POST'])
def upload_files():
    if 'xml-file' not in request.files or 'midi-file' not in request.files:
        return jsonify({'error': 'MusicXMLとMIDIファイルの両方が必要です'}), 400
    xml_file = request.files['xml-file']
    midi_file = request.files['midi-file']
    if not (xml_file and allowed_file(xml_file.filename) and midi_file and allowed_file(midi_file.filename)):
        return jsonify({'error': '許可されていないファイル形式です'}), 400

    xml_filename = secure_filename(xml_file.filename)
    song_name_base = safe_name(os.path.splitext(xml_filename)[0])
    counter = 1
    while True:
        path_check = os.path.join(UPLOAD_FOLDER, f"{song_name_base}_{counter}.musicxml")
        if not os.path.exists(path_check):
            break
        counter += 1
    song_name = f"{song_name_base}_{counter}"
    
    original_xml_path = os.path.join(UPLOAD_FOLDER, f"{song_name}.musicxml")
    original_midi_path = os.path.join(UPLOAD_FOLDER, f"{song_name}.mid")
    xml_file.save(original_xml_path)
    midi_file.save(original_midi_path)
    
    session.clear()
    session['xml_path'] = original_xml_path
    session['original_midi_path'] = original_midi_path
    session['song_name'] = song_name
    session['history'] = []

    try:
        score = music21.converter.parse(original_xml_path)
        processor = MidiProcessor(original_midi_path)
        parts_info = []
        all_abc_data = {}
        for i, part in enumerate(score.parts):
            raw_part_name = part.partName or f"Part{i+1}"
            part_name = safe_name(raw_part_name)
            
            xml_out_path = os.path.join(OUTPUT_DIRS["musicxml"], f"{song_name}_{part_name}.musicxml")
            abc_out_path = os.path.join(OUTPUT_DIRS["abc"], f"{song_name}_{part_name}.abc")
            note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{song_name}_{part_name}_note_map.json")

            part.write('musicxml', fp=xml_out_path)
            processor.create_note_map_from_part(part, note_map_path)

            success = convert_with_xml2abc(xml_out_path, abc_out_path)
            if success and os.path.exists(abc_out_path):
                with open(abc_out_path, 'r', encoding='utf-8', errors='ignore') as f:
                    all_abc_data[i] = f.read()
            else:
                all_abc_data[i] = f"X:1\nT:{raw_part_name}\nM:4/4\nL:1/8\nK:C\n| CDEC | GFEF |]"
            
            parts_info.append({
                'name': raw_part_name,
                'index': i,
                'note_map': f"json/{os.path.basename(note_map_path)}"
            })
            
        return jsonify({
            'message': f'ファイルが正常にアップロードされました（連番: {counter}）',
            'parts': parts_info,
            'all_abc_data': all_abc_data
        })
    except Exception as e:
        app.logger.exception("Upload error")
        return jsonify({'error': f'アップロードエラー: {e}'}), 500

# ============================================================
# MIDI加工処理
# ============================================================
@app.route('/process', methods=['POST'])
def process_midi():
    if 'original_midi_path' not in session:
        return jsonify({'error': 'MIDIファイルがアップロードされていません。'}), 400

    data = request.json
    part_index = data.get('partIndex')
    part_name = data.get('partName')
    phrase_info = data.get('phrase')
    preset_params = data.get('presetParams')
    preset_name = data.get('presetName')
    
    if any(v is None for v in [part_index, part_name, phrase_info, preset_params, preset_name]):
        return jsonify({'error': '処理に必要なデータが不足しています。'}), 400

    history = session.get('history', [])
    song_name = session.get("song_name")
    
    note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{song_name}_{safe_name(part_name)}_note_map.json")
    if not os.path.exists(note_map_path):
        return jsonify({'error': f'note_mapが見つかりません: {note_map_path}'}), 404

    new_instruction = {
        'phrase': phrase_info,
        'preset_params': preset_params,
        'preset_name': preset_name,
        'part_index': part_index,
        'part_name': part_name,
        'note_map_path': note_map_path
    }
    
    found_index = -1
    for i, instruction in enumerate(history):
        if instruction['phrase'] == new_instruction['phrase']:
            found_index = i
            break
    if found_index != -1:
        history[found_index] = new_instruction
    else:
        history.append(new_instruction)
    session['history'] = history

    try:
        latest_midi_obj = generate_midi_from_history()
        if latest_midi_obj is None:
            return jsonify({'error': 'MIDIの生成に失敗しました。'}), 500
        
        response_data = _create_output_files_and_response(latest_midi_obj, part_index, part_name)
        response_data['message'] = '表現を適用しました。'
        return jsonify(response_data)
    except Exception as e:
        app.logger.exception("Process error")
        return jsonify({'error': f'MIDI処理エラー: {e}'}), 500

# ============================================================
# Undo・Resetルート
# ============================================================
@app.route('/undo', methods=['POST'])
def undo_last_action():
    history = session.get('history', [])
    if not history:
        return jsonify({'message': '元に戻す操作はありません。', 'history_empty': True, 'history': []})

    undone_action = history.pop()
    session['history'] = history
    
    try:
        latest_midi_obj = generate_midi_from_history() if history else MidiFile(session['original_midi_path'])
        
        part_index = undone_action['part_index']
        part_name = undone_action['part_name']
        response_data = _create_output_files_and_response(latest_midi_obj, part_index, part_name)
        response_data['message'] = '最後の操作を元に戻しました。'
        return jsonify(response_data)
    except Exception as e:
        app.logger.exception("Undo error")
        return jsonify({'error': f'Undo処理エラー: {e}'}), 500

@app.route('/reset_midi', methods=['POST'])
def reset_midi():
    if 'history' in session:
        session['history'] = []
        try:
            latest_midi_obj = MidiFile(session['original_midi_path'])
            # リセット時は特定のパートがないので、ダミー値（最初のパート）でファイル生成
            score = music21.converter.parse(session['xml_path'])
            part_index = 0
            part_name = score.parts[0].partName or "Part1"
            response_data = _create_output_files_and_response(latest_midi_obj, part_index, part_name)
            response_data['message'] = 'すべての加工をリセットしました。'
            return jsonify(response_data)
        except Exception as e:
            app.logger.exception("Reset error")
            return jsonify({'error': f'Reset処理エラー: {e}'}), 500

    return jsonify({'error': 'リセット対象のセッションが見つかりません。'})

# ============================================================
# WAV配信ルート
# ============================================================
@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(os.path.join(OUTPUT_FOLDER, "audio"), filename)

# ============================================================
# MIDI配信ルート
# ============================================================
@app.route("/midi/<path:filename>")
def serve_midi(filename):
    return send_from_directory(os.path.join(OUTPUT_FOLDER, "midi"), filename)

# ============================================================
# 実行
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)