import os
import subprocess
import shutil
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, session, url_for
from werkzeug.utils import secure_filename
import music21
from midi_processor import MidiProcessor  
from mido import MidiFile, MidiTrack
import copy
import threading

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
        "なし": {
            "params": {"base_cc2": 0, "peak_cc2": 0}, "meaning": ""
        },
        "Cantabile": {
            "params": {"base_cc2": 10, "peak_cc2": 30}, "meaning": "歌うように"
        },
        "Dolce": {
            "params": {"base_cc2": -20, "peak_cc2": -5}, "meaning": "甘く、柔らかく"
        },
        "Maestoso": {
            "params": {"base_cc2": 10, "peak_cc2": 40}, "meaning": "荘厳に、堂々と"
        },
        "Appassionato": {
            "params": {"base_cc2": 10, "peak_cc2": 35, "onset_ms": -10}, "meaning": "情熱的に"
        },
        "Con brio": {
            "params": {"base_cc2": 10, "peak_cc2": 25, "onset_ms": -30}, "meaning": "生き生きと"
        },
        "Leggiero": {
            "params": {"base_cc2": -10, "peak_cc2": 5, "onset_ms": -10}, "meaning": "軽く、軽快に"
        },
        "Tranquillo": {
            "params": {"base_cc2": -20, "peak_cc2": -10, "onset_ms": -20}, "meaning": "静かに、穏やかに"
        },
        "Risoluto": {
            "params": {"base_cc2": 10, "peak_cc2": 30, "onset_ms": -10}, "meaning": "決然と、きっぱりと"
        },
        "Sostenuto": {
            "params": {"base_cc2": 0, "peak_cc2": 10, "onset_ms": 30}, "meaning": "音を十分に保って"
        },
        "Marcato": {
            "params": {"base_cc2": 10, "peak_cc2": 30, "onset_ms": 0}, "meaning": "一つ一つの音をはっきりと"
        },
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

def run_fluidsynth_in_background(commands):
    """fluidsynthのコマンドリストを受け取り、サブプロセスで実行する"""
    for cmd in commands:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            app.logger.info(f"Background WAV generation succeeded for: {cmd[-2]}")
        except subprocess.CalledProcessError as e:
            app.logger.error(f"Background WAV generation failed for: {cmd[-2]}. Error: {e.stderr}")
        except Exception as e:
            app.logger.error(f"An unexpected error occurred during background WAV generation: {e}")

# ============================================================
# 共通バックグラウンド処理関数
# ============================================================
def process_in_background(midi_obj, part_index, part_name, message):
    song_name = session.get("song_name")
    safe_part_name = safe_name(part_name)
    
    # MIDIファイルの保存
    full_processed_dir = os.path.join(OUTPUT_DIRS["midi_full"], "processed")
    single_processed_dir = os.path.join(OUTPUT_DIRS["midi_single"], "processed")
    os.makedirs(full_processed_dir, exist_ok=True)
    os.makedirs(single_processed_dir, exist_ok=True)
    full_out_path = os.path.join(full_processed_dir, f"{song_name}_full_processed.mid")
    midi_obj.save(full_out_path)
    single_midi = MidiFile(ticks_per_beat=midi_obj.ticks_per_beat)
    if 0 <= part_index < len(midi_obj.tracks):
        single_midi.tracks.append(copy.deepcopy(midi_obj.tracks[part_index]))
    single_out_path = os.path.join(single_processed_dir, f"{song_name}_{safe_part_name}_processed.mid")
    single_midi.save(single_out_path)

    # オリジナル音源がなければ生成
    single_original_dir = os.path.join(OUTPUT_DIRS["midi_single"], "original")
    original_single_out = os.path.join(single_original_dir, f"{song_name}_{safe_part_name}_original.mid")
    if not os.path.exists(original_single_out):
        os.makedirs(os.path.dirname(original_single_out), exist_ok=True)
        MidiProcessor(session['original_midi_path']).save_single_part_to_file(part_index, original_single_out)
    full_original_dir = os.path.join(OUTPUT_DIRS["midi_full"], "original")
    original_full_out = os.path.join(full_original_dir, f"{song_name}_full_original.mid")
    if not os.path.exists(original_full_out):
        os.makedirs(os.path.dirname(original_full_out), exist_ok=True)
        shutil.copy(session['original_midi_path'], original_full_out)

    # WAV変換の準備と実行
    audio_root = os.path.join(OUTPUT_FOLDER, "audio")
    single_audio_processed_path = os.path.join(audio_root, "single_parts", "processed", f"{song_name}_{safe_part_name}_processed.wav")
    processed_wav_full_path = os.path.join(audio_root, "full_parts", "processed", f"{song_name}_full_processed.wav")
    if os.path.exists(single_audio_processed_path): os.remove(single_audio_processed_path)
    if os.path.exists(processed_wav_full_path): os.remove(processed_wav_full_path)
    
    fluidsynth_exe = r"C:\tools\fluidsynth\bin\fluidsynth.exe"
    soundfont_path = r"soundfonts\FluidR3_GM.sf2"
    cmd_single = [fluidsynth_exe, "-ni", soundfont_path, single_out_path, "-F", single_audio_processed_path, "-r", "44100"]
    cmd_full = [fluidsynth_exe, "-ni", soundfont_path, full_out_path, "-F", processed_wav_full_path, "-r", "44100"]
    thread = threading.Thread(target=run_fluidsynth_in_background, args=([cmd_single, cmd_full],))
    thread.start()

    # 即時レスポンスを返す
    return jsonify({
        'message': message,
        'history': session.get('history', []),
        'status': 'processing',
        'processed_single_wav': url_for('serve_output', filename=os.path.relpath(single_audio_processed_path, OUTPUT_FOLDER).replace(os.sep, '/')),
        'processed_full_wav': url_for('serve_output', filename=os.path.relpath(processed_wav_full_path, OUTPUT_FOLDER).replace(os.sep, '/')),
        'original_single_wav': url_for('serve_output', filename=f"audio/single_parts/original/{song_name}_{safe_part_name}_original.wav"),
        'original_full_wav': url_for('serve_output', filename=f"audio/full_parts/original/{song_name}_full_original.wav"),
        "can_undo": len(session.get('history', [])) > 0,
        "can_redo": len(session.get('redo_stack', [])) > 0,
    })

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
    session['redo_stack'] = []
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
            parts_info.append({'name': raw_part_name, 'index': i, 'note_map': f"json/{os.path.basename(note_map_path)}"})
        return jsonify({'message': f'ファイルが正常にアップロードされました（連番: {counter}）', 'parts': parts_info, 'all_abc_data': all_abc_data, 'history': [], 'can_undo': False, 'can_redo': False})
    except Exception as e:
        app.logger.exception("Upload error")
        return jsonify({'error': f'アップロードエラー: {e}'}), 500

# ============================================================
# 頂点推定API
# ============================================================
@app.route('/estimate_apex', methods=['POST'])
def estimate_apex():
    data = request.json
    part_name = data.get('partName')
    start_index = data.get('startIndex')
    end_index = data.get('endIndex')

    note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{session.get('song_name')}_{safe_name(part_name)}_note_map.json")
    if not os.path.exists(note_map_path):
        return jsonify({'error': 'Note map not found'}), 404
        
    with open(note_map_path, 'r', encoding='utf-8') as f:
        note_map = json.load(f)

    scores = {}
    phrase_notes = [n for n in note_map if start_index <= n['index'] <= end_index and not n['is_rest']]
    
    # --- 論文ルールに基づくスコアリング ---
    # 最初に同一音価のグループを見つける
    duration_groups = []
    if phrase_notes:
        current_group = [phrase_notes[0]]
        for i in range(1, len(phrase_notes)):
            if phrase_notes[i]['duration_beats'] == current_group[0]['duration_beats']:
                current_group.append(phrase_notes[i])
            else:
                duration_groups.append(current_group)
                current_group = [phrase_notes[i]]
        duration_groups.append(current_group)

    # 各音符のスコアを初期化
    for note in phrase_notes:
        scores[note['index']] = 0

    # ルールを適用してスコアリング
    for i, note in enumerate(phrase_notes):
        # --- 音価ルール ---
        # 1. 隣接する2音の比較
        if i + 1 < len(phrase_notes):
            next_note = phrase_notes[i+1]
            if note['duration_beats'] > next_note['duration_beats']:
                scores[note['index']] += 1
        
        # 2. 同一音価が連続する音群
        for group in duration_groups:
            if len(group) > 1 and note['index'] == group[0]['index']:
                scores[note['index']] += 1
            if len(group) > 1 and note['index'] in [g['index'] for g in group[1:]]:
                pos_in_group = [g['index'] for g in group].index(note['index'])
                scores[note['index']] += (pos_in_group + 1) / len(group)

    # --- 音高ルール ---
    for i, note in enumerate(phrase_notes):
        # 1. 隣接する2音の比較
        if i + 1 < len(phrase_notes):
            next_note = phrase_notes[i+1]
            if note['pitch'] > next_note['pitch']:
                scores[note['index']] += 1

        # 2. 進行到達音 (4音のパターン)
        if i > 0 and i + 2 < len(phrase_notes):
            n_minus_1 = phrase_notes[i-1]
            n = note
            n_plus_1 = phrase_notes[i+1]
            n_plus_2 = phrase_notes[i+2]
            
            p_m1, p_n, p_p1, p_p2 = n_minus_1['pitch'], n['pitch'], n_plus_1['pitch'], n_plus_2['pitch']
            
            dir1 = 1 if p_n > p_m1 else -1 if p_n < p_m1 else 0
            dir2 = 1 if p_p1 > p_n else -1 if p_p1 < p_n else 0
            dir3 = 1 if p_p2 > p_p1 else -1 if p_p2 < p_p1 else 0

            target_note = n_plus_1
            pattern = 0
            if dir1 >= 0 and dir2 > 0 and dir3 < 0:
                scores[target_note['index']] += 1
                pattern = 1
            elif dir1 < 0 and dir2 > 0 and dir3 < 0:
                scores[target_note['index']] += 1
                pattern = 2
            elif dir1 >= 0 and dir2 < 0 and dir3 > 0:
                scores[target_note['index']] += 2
            elif dir1 < 0 and dir2 < 0 and dir3 > 0:
                scores[target_note['index']] += 2

            if (pattern in [1, 2]) and target_note['duration_seconds'] < 0.25:
                 scores[n_minus_1['index']] += 1

    # --- ここからデバッグ出力 ---
    print("\n--- 頂点推定デバッグ情報 ---")
    print(f"対象パート: {part_name}")
    print(f"選択範囲インデックス: {start_index} から {end_index}")
    print("計算されたスコア:")
    if not scores:
        print("  スコア計算対象の音符がありません。")
    else:
        for index, score in sorted(scores.items()):
            print(f"  Note Index {index:<3}: Score {score:.2f}")
    
    if not scores:
        max_score = 0
    else:
        max_score = max(scores.values())
    
    candidates = [index for index, score in scores.items() if score == max_score and max_score > 0]
    
    print(f"最高スコア: {max_score:.2f}")
    print(f"最終的な頂点候補 (インデックス): {candidates}")
    print("--- デバッグ情報 終了 ---\n")
    # --- ここまでデバッグ出力 ---
    
    return jsonify({'apex_candidates': candidates})

# ============================================================
# MIDI加工処理
# ============================================================
@app.route('/process', methods=['POST'])
def process_midi():
    data = request.json
    part_index = data.get('partIndex')
    part_name = data.get('partName')
    phrase_info = data.get('phrase')
    
    new_instruction = {
        'phrase': phrase_info,
        'preset_params': data.get('presetParams'),
        'preset_name': data.get('presetName'),
        'part_index': part_index,
        'part_name': part_name,
        'note_map_path': os.path.join(OUTPUT_DIRS["json"], f"{session.get('song_name')}_{safe_name(part_name)}_note_map.json")
    }
    history = session.get('history', [])
    found_index = next((i for i, instr in enumerate(history) if instr['phrase'] == new_instruction['phrase']), -1)
    if found_index != -1:
        history[found_index] = new_instruction
    else:
        history.append(new_instruction)
    session['history'] = history
    session['redo_stack'] = []
    
    latest_midi_obj = generate_midi_from_history()
    return process_in_background(latest_midi_obj, part_index, part_name, '表現を適用しました。')

# ============================================================
# 音声ファイル存在確認
# ============================================================
@app.route('/check_audio_status', methods=['POST'])
def check_audio_status():
    files_to_check = request.json.get('files', [])
    all_files_exist = all(os.path.exists(os.path.join(OUTPUT_FOLDER, f.replace('/output/', '', 1).replace('/', os.sep))) for f in files_to_check)
    return jsonify({'status': 'ready' if all_files_exist else 'processing'})

# ============================================================
# Undo・Redo・Resetルート
# ============================================================
@app.route('/undo', methods=['POST'])
def undo_last_action():
    history = session.get('history', [])
    if not history:
        return jsonify({'message': '元に戻す操作はありません。', 'history': [], 'can_undo': False, 'can_redo': len(session.get('redo_stack', [])) > 0})
    
    redo_stack = session.get('redo_stack', [])
    undone_action = history.pop()
    redo_stack.append(undone_action)
    session['history'] = history
    session['redo_stack'] = redo_stack

    latest_midi_obj = generate_midi_from_history() if history else MidiFile(session['original_midi_path'])
    return process_in_background(latest_midi_obj, undone_action['part_index'], undone_action['part_name'], '操作を元に戻しました。')

@app.route('/redo', methods=['POST'])
def redo_action():
    redo_stack = session.get('redo_stack', [])
    if not redo_stack:
        return jsonify({'message': 'やり直す操作はありません。', 'history': session.get('history', []), 'can_undo': len(session.get('history', [])) > 0, 'can_redo': False})

    history = session.get('history', [])
    redone_action = redo_stack.pop()
    history.append(redone_action)
    session['history'] = history
    session['redo_stack'] = redo_stack
    
    latest_midi_obj = generate_midi_from_history()
    return process_in_background(latest_midi_obj, redone_action['part_index'], redone_action['part_name'], '操作をやり直しました。')

@app.route('/reset_midi', methods=['POST'])
def reset_midi():
    if 'original_midi_path' not in session:
        return jsonify({'error': 'セッションが見つかりません。'})

    session['history'] = []
    session['redo_stack'] = []
    
    latest_midi_obj = MidiFile(session['original_midi_path'])
    score = music21.converter.parse(session['xml_path'])
    part_index = 0
    part_name = score.parts[0].partName or "Part1"
    
    return process_in_background(latest_midi_obj, part_index, part_name, 'すべての加工をリセットしました。')

# ============================================================
# WAV・MIDI配信ルート
# ============================================================
@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(os.path.join(OUTPUT_FOLDER, "audio"), filename)

@app.route("/midi/<path:filename>")
def serve_midi(filename):
    return send_from_directory(os.path.join(OUTPUT_FOLDER, "midi"), filename)

# ============================================================
# 実行
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)
