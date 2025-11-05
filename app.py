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
import uuid
from collections import defaultdict

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

# --- グローバル定数 ---
FLUIDSYNTH_EXE = r"C:\tools\fluidsynth\bin\fluidsynth.exe"
SOUNDFONT_PATH = os.path.join(BASE_DIR, "soundfonts", "FluidR3_GM.sf2")

# --- 非同期タスク管理 ---
tasks = {}

# ============================================================
# 表現プリセット（発想標語のみ）
# ============================================================
PRESET_DEFINITIONS = {
    "tempo_expressions": {
        "なし": {"params": {"base_cc2": 0, "peak_cc2": 0}, "meaning": ""},
        "Cantabile": {"params": {"base_cc2": 10, "peak_cc2": 30}, "meaning": "歌うように"},
        "Dolce": {"params": {"base_cc2": -20, "peak_cc2": -5}, "meaning": "甘く、柔らかく"},
        "Maestoso": {"params": {"base_cc2": 10, "peak_cc2": 40}, "meaning": "荘厳に、堂々と"},
        "Appassionato": {"params": {"base_cc2": 10, "peak_cc2": 35, "onset_ms": -10}, "meaning": "情熱的に"},
        "Con brio": {"params": {"base_cc2": 10, "peak_cc2": 25, "onset_ms": -30}, "meaning": "生き生きと"},
        "Leggiero": {"params": {"base_cc2": -10, "peak_cc2": 5, "onset_ms": -10}, "meaning": "軽く、軽快に"},
        "Tranquillo": {"params": {"base_cc2": -20, "peak_cc2": -10, "onset_ms": -20}, "meaning": "静かに、穏やかに"},
        "Risoluto": {"params": {"base_cc2": 10, "peak_cc2": 30, "onset_ms": -10}, "meaning": "決然と、きっぱりと"},
        "Sostenuto": {"params": {"base_cc2": 0, "peak_cc2": 10, "onset_ms": 30}, "meaning": "音を十分に保って"},
        "Marcato": {"params": {"base_cc2": 10, "peak_cc2": 30, "onset_ms": 0}, "meaning": "一つ一つの音をはっきりと"},
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
        if os.path.exists(abc_path): os.remove(abc_path)
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

def generate_midi_from_history(original_midi_path, history, song_name):
    if not original_midi_path or not os.path.exists(original_midi_path):
        return None
    current_midi_obj = MidiFile(original_midi_path)
    # 履歴がなければ元のMIDIをそのまま返す
    if not history:
        return current_midi_obj

    # note_mapのパスをキャッシュ
    note_map_cache = {}
    
    for instruction in history:
        processor = MidiProcessor(current_midi_obj)
        phrase = instruction['phrase']
        params = instruction['preset_params']
        part_name = safe_name(instruction['part_name'])
        
        note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{song_name}_{part_name}_note_map.json")

        if note_map_path not in note_map_cache:
            with open(note_map_path, 'r', encoding='utf-8') as f:
                note_map_cache[note_map_path] = json.load(f)
        
        note_map = note_map_cache[note_map_path]

        def idx_to_tick(idx):
            entry = next((e for e in note_map if e['index'] == idx), None)
            return entry['tick'] if entry else None
            
        start_tick = idx_to_tick(phrase.get('start_index'))
        peak_tick = idx_to_tick(phrase.get('peak_index'))
        end_tick = idx_to_tick(phrase.get('end_index'))
        
        # 履歴内のすべての指示は全パートに適用(part_index=None)
        current_midi_obj = processor.apply_expression_by_ticks(None, start_tick, end_tick, peak_tick, params)
    return current_midi_obj

def run_fluidsynth_command(cmd, task_id, total_steps):
    """単一のfluidsynthコマンドを実行し、進捗を更新する"""
    try:
        tasks[task_id]['message'] = f"{os.path.basename(cmd[-2])} をWAVに変換中..."
        app.logger.info(f"実行コマンド: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        tasks[task_id]['current'] += 1
        return True
    except Exception as e:
        error_message = f"WAV生成失敗: {cmd[-2]}. Error: {e}"
        if hasattr(e, 'stderr'): error_message += f" - {e.stderr}"
        tasks[task_id]['state'] = 'FAILURE'
        tasks[task_id]['message'] = error_message
        app.logger.error(error_message)
        return False

# ============================================================
# バックグラウンドタスク本体
# ============================================================
def perform_audio_generation(task_id, history, part_index, part_name, song_name, original_midi_path):
    try:
        safe_part_name = safe_name(part_name)
        
        tasks[task_id]['state'] = 'PROGRESS'
        tasks[task_id]['total'] = 3 # 1.MIDI生成, 2.単一パートWAV, 3.全体WAV
        tasks[task_id]['current'] = 0
        tasks[task_id]['message'] = '加工後MIDIを生成中...'

        # 1. 履歴に基づいてMIDIを生成
        processed_midi_obj = generate_midi_from_history(original_midi_path, history, song_name)
        if not processed_midi_obj:
            raise Exception("MIDIオブジェクトの生成に失敗しました。")

        full_processed_dir = os.path.join(OUTPUT_DIRS["midi_full"], "processed")
        single_processed_dir = os.path.join(OUTPUT_DIRS["midi_single"], "processed")
        os.makedirs(full_processed_dir, exist_ok=True)
        os.makedirs(single_processed_dir, exist_ok=True)
        
        full_out_path = os.path.join(full_processed_dir, f"{song_name}_full_processed.mid")
        processed_midi_obj.save(full_out_path)

        single_midi = MidiFile(ticks_per_beat=processed_midi_obj.ticks_per_beat)
        if 0 <= part_index < len(processed_midi_obj.tracks):
            single_midi.tracks.append(copy.deepcopy(processed_midi_obj.tracks[part_index]))
        single_out_path = os.path.join(single_processed_dir, f"{song_name}_{safe_part_name}_processed.mid")
        single_midi.save(single_out_path)
        tasks[task_id]['current'] += 1

        # 2. WAV変換
        audio_root = os.path.join(OUTPUT_FOLDER, "audio")
        single_proc_dir = os.path.join(audio_root, "single_parts", "processed")
        full_proc_dir = os.path.join(audio_root, "full_parts", "processed")
        os.makedirs(single_proc_dir, exist_ok=True)
        os.makedirs(full_proc_dir, exist_ok=True)

        single_audio_processed_path = os.path.join(single_proc_dir, f"{song_name}_{safe_part_name}_processed.wav")
        processed_wav_full_path = os.path.join(full_proc_dir, f"{song_name}_full_processed.wav")
        
        # 既存ファイルを削除
        if os.path.exists(single_audio_processed_path): os.remove(single_audio_processed_path)
        if os.path.exists(processed_wav_full_path): os.remove(processed_wav_full_path)

        cmd_single = [FLUIDSYNTH_EXE, "-ni", SOUNDFONT_PATH, single_out_path, "-F", single_audio_processed_path, "-r", "44100"]
        if not run_fluidsynth_command(cmd_single, task_id, 3): return

        cmd_full = [FLUIDSYNTH_EXE, "-ni", SOUNDFONT_PATH, full_out_path, "-F", processed_wav_full_path, "-r", "44100"]
        if not run_fluidsynth_command(cmd_full, task_id, 3): return

        # 3. 完了
        tasks[task_id]['state'] = 'SUCCESS'
        tasks[task_id]['message'] = '完了'
        
        # url_forの代わりに手動でURLを構築
        def get_rel_path(full_path):
            return os.path.relpath(full_path, OUTPUT_FOLDER).replace(os.sep, '/')

        tasks[task_id]['result'] = {
            'processed_single_wav': f"/output/{get_rel_path(single_audio_processed_path)}",
            'processed_full_wav': f"/output/{get_rel_path(processed_wav_full_path)}",
            'original_single_wav': f"/output/audio/single_parts/original/{song_name}_{safe_part_name}_original.wav",
            'original_full_wav': f"/output/audio/full_parts/original/{song_name}_full_original.wav",
            'processed_midi_full': f"/output/{get_rel_path(full_out_path)}",
        }

    except Exception as e:
        app.logger.exception("Audio generation task failed")
        tasks[task_id]['state'] = 'FAILURE'
        tasks[task_id]['message'] = str(e)


# ============================================================
# APIエンドポイント & ルーティング
# ============================================================

# --- 生成ファイルの配信ルート ---
@app.route('/output/<path:filename>')
def serve_output(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

# --- トップページ ---
@app.route('/')
def index():
    session.clear()
    return render_template('index.html', presets=PRESET_DEFINITIONS)

# --- ファイルアップロード処理 ---
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
        if not os.path.exists(path_check): break
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

    try:
        score = music21.converter.parse(original_xml_path)
        processor = MidiProcessor(original_midi_path)
        parts_info, all_abc_data = [], {}
        initial_wav_commands = []
        
        # オリジナルの全パートMIDIとWAVを準備
        original_full_midi_dir = os.path.join(OUTPUT_DIRS["midi_full"], "original")
        os.makedirs(original_full_midi_dir, exist_ok=True)
        original_full_midi_path = os.path.join(original_full_midi_dir, f"{song_name}_full_original.mid")
        shutil.copy(original_midi_path, original_full_midi_path)
        original_full_audio_dir = os.path.join(OUTPUT_DIRS["audio"], "full_parts", "original")
        os.makedirs(original_full_audio_dir, exist_ok=True)
        original_full_wav_path = os.path.join(original_full_audio_dir, f"{song_name}_full_original.wav")
        initial_wav_commands.append([FLUIDSYNTH_EXE, "-ni", SOUNDFONT_PATH, original_full_midi_path, "-F", original_full_wav_path, "-r", "44100"])
        
        for i, part in enumerate(score.parts):
            raw_part_name = part.partName or f"Part{i+1}"
            part_name = safe_name(raw_part_name)
            xml_out_path = os.path.join(OUTPUT_DIRS["musicxml"], f"{song_name}_{part_name}.musicxml")
            abc_out_path = os.path.join(OUTPUT_DIRS["abc"], f"{song_name}_{part_name}.abc")
            note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{song_name}_{part_name}_note_map.json")
            
            part.write('musicxml', fp=xml_out_path)
            processor.create_note_map_from_part(part, note_map_path)
            
            # オリジナルの単一パートMIDIとWAVを準備
            original_single_midi_dir = os.path.join(OUTPUT_DIRS["midi_single"], "original")
            os.makedirs(original_single_midi_dir, exist_ok=True)
            original_single_midi_path = os.path.join(original_single_midi_dir, f"{song_name}_{part_name}_original.mid")
            processor.save_single_part_to_file(i, original_single_midi_path)
            original_single_audio_dir = os.path.join(OUTPUT_DIRS["audio"], "single_parts", "original")
            os.makedirs(original_single_audio_dir, exist_ok=True)
            original_single_wav_path = os.path.join(original_single_audio_dir, f"{song_name}_{part_name}_original.wav")
            initial_wav_commands.append([FLUIDSYNTH_EXE, "-ni", SOUNDFONT_PATH, original_single_midi_path, "-F", original_single_wav_path, "-r", "44100"])

            if convert_with_xml2abc(xml_out_path, abc_out_path) and os.path.exists(abc_out_path):
                with open(abc_out_path, 'r', encoding='utf-8', errors='ignore') as f: all_abc_data[i] = f.read()
            else:
                all_abc_data[i] = f"X:1\nT:{raw_part_name}\nM:4/4\nL:1/8\nK:C\n| CDEC | GFEF |]"
            parts_info.append({'name': raw_part_name, 'index': i, 'note_map': f"json/{os.path.basename(note_map_path)}"})
            
        # バックグラウンドで初期WAVを生成
        if os.path.exists(SOUNDFONT_PATH):
            task_id = str(uuid.uuid4())
            tasks[task_id] = {'state': 'PENDING', 'message': '初期WAV生成タスク待機中...'}
            
            def initial_wav_task_wrapper():
                tasks[task_id]['state'] = 'PROGRESS'
                tasks[task_id]['total'] = len(initial_wav_commands)
                tasks[task_id]['current'] = 0
                for cmd in initial_wav_commands:
                    if not run_fluidsynth_command(cmd, task_id, len(initial_wav_commands)):
                        break
                if tasks[task_id]['state'] != 'FAILURE':
                    tasks[task_id]['state'] = 'SUCCESS'
            
            thread = threading.Thread(target=initial_wav_task_wrapper)
            thread.start()
        else:
            app.logger.error(f"Upload: SoundFont not found. Original WAVs will not be generated.")
            
        return jsonify({'message': f'ファイルが正常にアップロードされました（連番: {counter}）', 'parts': parts_info, 'all_abc_data': all_abc_data})
    except Exception as e:
        app.logger.exception("Upload error")
        return jsonify({'error': f'アップロードエラー: {e}'}), 500

# --- 頂点推定API ---
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
    
    if not phrase_notes:
        return jsonify({'apex_candidates': []})
        
    # --- 論文ルールに基づくスコアリング ---
    # 最初に同一音価のグループを見つける
    duration_groups = []
    current_group = [phrase_notes[0]]
    for i in range(1, len(phrase_notes)):
        if phrase_notes[i]['duration_beats'] == current_group[0]['duration_beats']:
            current_group.append(phrase_notes[i])
        else:
            duration_groups.append(current_group)
            current_group = [phrase_notes[i]]
    duration_groups.append(current_group)

    # 各音符のスコアを初期化
    for note in phrase_notes: scores[note['index']] = 0

    # ルールを適用してスコアリング
    for i, note in enumerate(phrase_notes):
        # --- 音価ルール ---
        # 1. 隣接する2音の比較
        if i + 1 < len(phrase_notes):
            next_note = phrase_notes[i+1]
            if note['duration_beats'] > next_note['duration_beats']: scores[note['index']] += 1
        
        # 2. 同一音価が連続する音群
        for group in duration_groups:
            if len(group) > 1 and note['index'] == group[0]['index']: scores[note['index']] += 1
            if len(group) > 1 and note['index'] in [g['index'] for g in group[1:]]:
                pos_in_group = [g['index'] for g in group].index(note['index'])
                scores[note['index']] += (pos_in_group + 1) / len(group)

    # --- 音高ルール ---
    for i, note in enumerate(phrase_notes):
        # 1. 隣接する2音の比較
        if i + 1 < len(phrase_notes):
            next_note = phrase_notes[i+1]
            if note['pitch'] > next_note['pitch']: scores[note['index']] += 1

        # 2. 進行到達音 (4音のパターン)
        if i > 0 and i + 2 < len(phrase_notes):
            n_minus_1, n, n_plus_1, n_plus_2 = phrase_notes[i-1], note, phrase_notes[i+1], phrase_notes[i+2]
            p_m1, p_n, p_p1, p_p2 = n_minus_1['pitch'], n['pitch'], n_plus_1['pitch'], n_plus_2['pitch']
            dir1 = 1 if p_n > p_m1 else -1 if p_n < p_m1 else 0
            dir2 = 1 if p_p1 > p_n else -1 if p_p1 < p_n else 0
            dir3 = 1 if p_p2 > p_p1 else -1 if p_p2 < p_p1 else 0
            target_note, pattern = n_plus_1, 0
            if dir1 >= 0 and dir2 > 0 and dir3 < 0: scores[target_note['index']] += 1; pattern = 1
            elif dir1 < 0 and dir2 > 0 and dir3 < 0: scores[target_note['index']] += 1; pattern = 2
            elif dir1 >= 0 and dir2 < 0 and dir3 > 0: scores[target_note['index']] += 2
            elif dir1 < 0 and dir2 < 0 and dir3 > 0: scores[target_note['index']] += 2
            if (pattern in [1, 2]) and target_note['duration_seconds'] < 0.25: scores[n_minus_1['index']] += 1
    
    # --- ここからデバッグ出力 ---
    # print("\n--- 頂点推定デバッグ情報 ---")
    # (省略)
    
    max_score = max(scores.values()) if scores else 0
    candidates = [index for index, score in scores.items() if score == max_score and max_score > 0]
    return jsonify({'apex_candidates': candidates})

# --- 音源生成タスク関連API ---
@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    data = request.json
    history = data.get('history', [])
    part_index = data.get('partIndex')
    part_name = data.get('partName')
    
    # バックグラウンドタスクに必要な情報をセッションから取得
    song_name = session.get('song_name')
    original_midi_path = session.get('original_midi_path')

    task_id = str(uuid.uuid4())
    tasks[task_id] = {'state': 'PENDING', 'message': 'タスク待機中...'}

    # スレッドに情報を渡す
    thread = threading.Thread(target=perform_audio_generation, args=(
        task_id, history, part_index, part_name, song_name, original_midi_path
    ))
    thread.start()
    
    return jsonify({'task_id': task_id})

@app.route('/generation_status/<task_id>')
def generation_status(task_id):
    task = tasks.get(task_id, {'state': 'NOT_FOUND', 'message': 'タスクが見つかりません。'})
    return jsonify(task)

# ============================================================
# 実行
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)