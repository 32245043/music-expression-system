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
# このスクリプトが存在するディレクトリの絶対パスを取得
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ファイルをアップロードするためのフォルダを設定
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
# 生成したファイル（MusicXML, MIDI, WAVなど）を保存する親フォルダを設定
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")

# --- 出力フォルダ構成 ---
# 生成するファイルの種類ごとに、保存先のサブディレクトリを定義
OUTPUT_DIRS = {
    "musicxml": os.path.join(OUTPUT_FOLDER, "musicxml"),
    "abc": os.path.join(OUTPUT_FOLDER, "abc"),
    "json": os.path.join(OUTPUT_FOLDER, "json"),
    "midi_full": os.path.join(OUTPUT_FOLDER, "midi", "full_parts"),
    "midi_single": os.path.join(OUTPUT_FOLDER, "midi", "single_parts"),
    "audio": os.path.join(OUTPUT_FOLDER, "audio"),
}

# 必要なディレクトリが存在しない場合は、すべて自動で作成する
for path in [UPLOAD_FOLDER, OUTPUT_FOLDER, *OUTPUT_DIRS.values()]:
    os.makedirs(path, exist_ok=True)

# アップロードを許可するファイルの拡張子を定義
ALLOWED_EXTENSIONS = {'xml', 'musicxml', 'mid', 'midi'}

# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)
# Flaskアプリケーションの設定を更新
app.config.update(
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    OUTPUT_FOLDER=OUTPUT_FOLDER,
    # session機能を使うための秘密鍵。安全なものに置き換えることが推奨される
    SECRET_KEY='supersecretkey_for_session'
)

# --- グローバル定数 ---
# MIDIからWAVへの変換に使用するFluidSynthの実行ファイルのパス
FLUIDSYNTH_EXE = r"C:\tools\fluidsynth\bin\fluidsynth.exe"
# FluidSynthが使用するサウンドフォントのパス
SOUNDFONT_PATH = os.path.join(BASE_DIR, "soundfonts", "FluidR3_GM.sf2")

# --- 非同期タスク管理 ---
# バックグラウンドで実行されるタスク（WAV生成など）の状態を管理するための辞書
tasks = {}

# ============================================================
# 表現プリセット（発想標語のみ）
# ============================================================
# 演奏表現のプリセットを定義。フロントエンドで選択肢として表示される
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
    """アップロードされたファイルが許可された拡張子かチェックする"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_name(name):
    """ファイル名やパート名として安全な文字列に変換する"""
    # 英数字、アンダースコア、ハイフン以外をアンダースコアに置換
    return "".join(c if c.isalnum() or c in ('_', '-') else "_" for c in name)

def convert_with_xml2abc(xml_path, abc_path):
    """xml2abc.pyの外部スクリプトを呼び出してMusicXMLをABC記法に変換する"""
    try:
        out_dir = os.path.dirname(abc_path)
        # 変換先に同名ファイルがあれば削除
        if os.path.exists(abc_path): os.remove(abc_path)
        # コマンドプロンプトで実行するコマンドをリストで作成
        cmd = ["python", "xml2abc.py", xml_path, "-o", out_dir]
        # コマンドを実行
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # xml2abcは元のファイル名で.abcファイルを作るため、リネームが必要
        base_name = os.path.splitext(os.path.basename(xml_path))[0]
        generated_path = os.path.join(out_dir, base_name + ".abc")
        if os.path.exists(generated_path):
            os.rename(generated_path, abc_path) # 目的のファイル名にリネーム
            return True
        return False
    except Exception as e:
        app.logger.error(f"xml2abc失敗: {e}")
        return False

def generate_midi_from_history(original_midi_path, history, song_name):
    """適用履歴（history）に基づいて元のMIDIを加工し、新しいMIDIオブジェクトを生成する"""
    if not original_midi_path or not os.path.exists(original_midi_path):
        return None
    current_midi_obj = MidiFile(original_midi_path)
    # 履歴がなければ元のMIDIをそのまま返す
    if not history:
        return current_midi_obj

    # note_mapの読み込みをキャッシュして、同じファイルを何度も読み込まないようにする
    note_map_cache = {}
    
    # 履歴の指示を一つずつ適用していく
    for instruction in history:
        processor = MidiProcessor(current_midi_obj)
        phrase = instruction['phrase']
        params = instruction['preset_params']
        part_name = safe_name(instruction['part_name'])
        
        note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{song_name}_{part_name}_note_map.json")

        # キャッシュになければファイルを読み込む
        if note_map_path not in note_map_cache:
            with open(note_map_path, 'r', encoding='utf-8') as f:
                note_map_cache[note_map_path] = json.load(f)
        
        note_map = note_map_cache[note_map_path]

        # 音符のインデックスからMIDIのtick（時間）を取得する内部関数
        def idx_to_tick(idx):
            entry = next((e for e in note_map if e['index'] == idx), None)
            return entry['tick'] if entry else None
            
        start_tick = idx_to_tick(phrase.get('start_index'))
        peak_tick = idx_to_tick(phrase.get('peak_index'))
        end_tick = idx_to_tick(phrase.get('end_index'))
        
        # MIDIプロセッサを使って表現を適用
        current_midi_obj = processor.apply_expression_by_ticks(None, start_tick, end_tick, peak_tick, params)
    return current_midi_obj

def run_fluidsynth_command(cmd, task_id, total_steps):
    """単一のfluidsynthコマンドを実行し、タスクの進捗を更新する"""
    try:
        tasks[task_id]['message'] = f"{os.path.basename(cmd[-2])} をWAVに変換中..."
        app.logger.info(f"実行コマンド: {' '.join(cmd)}")
        # コマンドを実行。エラーがあれば例外が発生する
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        # 成功したらタスクの現在ステップを1つ進める
        tasks[task_id]['current'] += 1
        return True
    except Exception as e:
        # 失敗したらタスクの状態を'FAILURE'にし、エラーメッセージを保存
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
    """（別スレッドで実行）適用履歴から加工後のMIDIとWAVを生成する一連の処理"""
    try:
        safe_part_name = safe_name(part_name)
        
        # タスクの初期状態を設定
        tasks[task_id]['state'] = 'PROGRESS'
        tasks[task_id]['total'] = 3 # 処理は3ステップ (MIDI生成, 単一パートWAV, 全体WAV)
        tasks[task_id]['current'] = 0
        tasks[task_id]['message'] = '加工後MIDIを生成中...'

        # ステップ1: 履歴に基づいてMIDIを生成
        processed_midi_obj = generate_midi_from_history(original_midi_path, history, song_name)
        if not processed_midi_obj:
            raise Exception("MIDIオブジェクトの生成に失敗しました。")

        # 加工後のMIDIファイルの保存先ディレクトリを準備
        full_processed_dir = os.path.join(OUTPUT_DIRS["midi_full"], "processed")
        single_processed_dir = os.path.join(OUTPUT_DIRS["midi_single"], "processed")
        os.makedirs(full_processed_dir, exist_ok=True)
        os.makedirs(single_processed_dir, exist_ok=True)
        
        # 加工後の全パートMIDIファイルを保存
        full_out_path = os.path.join(full_processed_dir, f"{song_name}_full_processed.mid")
        processed_midi_obj.save(full_out_path)

        # 加工後の単一パートMIDIファイルを抽出して保存
        single_midi = MidiFile(ticks_per_beat=processed_midi_obj.ticks_per_beat)
        if 0 <= part_index < len(processed_midi_obj.tracks):
            single_midi.tracks.append(copy.deepcopy(processed_midi_obj.tracks[part_index]))
        single_out_path = os.path.join(single_processed_dir, f"{song_name}_{safe_part_name}_processed.mid")
        single_midi.save(single_out_path)
        tasks[task_id]['current'] += 1

        # ステップ2: WAV変換
        audio_root = os.path.join(OUTPUT_FOLDER, "audio")
        single_proc_dir = os.path.join(audio_root, "single_parts", "processed")
        full_proc_dir = os.path.join(audio_root, "full_parts", "processed")
        os.makedirs(single_proc_dir, exist_ok=True)
        os.makedirs(full_proc_dir, exist_ok=True)

        single_audio_processed_path = os.path.join(single_proc_dir, f"{song_name}_{safe_part_name}_processed.wav")
        processed_wav_full_path = os.path.join(full_proc_dir, f"{song_name}_full_processed.wav")
        
        # 既存のWAVファイルがあれば削除
        if os.path.exists(single_audio_processed_path): os.remove(single_audio_processed_path)
        if os.path.exists(processed_wav_full_path): os.remove(processed_wav_full_path)

        # 単一パートMIDIをWAVに変換
        cmd_single = [FLUIDSYNTH_EXE, "-ni", SOUNDFONT_PATH, single_out_path, "-F", single_audio_processed_path, "-r", "44100"]
        if not run_fluidsynth_command(cmd_single, task_id, 3): return # 失敗したら中断

        # 全パートMIDIをWAVに変換
        cmd_full = [FLUIDSYNTH_EXE, "-ni", SOUNDFONT_PATH, full_out_path, "-F", processed_wav_full_path, "-r", "44100"]
        if not run_fluidsynth_command(cmd_full, task_id, 3): return # 失敗したら中断

        # ステップ3: 完了処理
        tasks[task_id]['state'] = 'SUCCESS'
        tasks[task_id]['message'] = '完了'
        
        # フロントエンドに返すファイルパスを生成
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
        # タスク全体でエラーが発生した場合の処理
        app.logger.exception("Audio generation task failed")
        tasks[task_id]['state'] = 'FAILURE'
        tasks[task_id]['message'] = str(e)


# ============================================================
# APIエンドポイント & ルーティング
# ============================================================

@app.route('/output/<path:filename>')
def serve_output(filename):
    """/output/以下のURLでアクセスされたファイルを配信する"""
    return send_from_directory(OUTPUT_FOLDER, filename)

@app.route('/')
def index():
    """トップページを表示する"""
    session.clear() # ページを開くたびにセッション情報をクリア
    return render_template('index.html', presets=PRESET_DEFINITIONS)

@app.route('/upload', methods=['POST'])
def upload_files():
    """MusicXMLとMIDIファイルを受け取り、解析して各種ファイルを生成する"""
    # ファイルが正しく送信されているかチェック
    if 'xml-file' not in request.files or 'midi-file' not in request.files:
        return jsonify({'error': 'MusicXMLとMIDIファイルの両方が必要です'}), 400
    xml_file = request.files['xml-file']
    midi_file = request.files['midi-file']
    if not (xml_file and allowed_file(xml_file.filename) and midi_file and allowed_file(midi_file.filename)):
        return jsonify({'error': '許可されていないファイル形式です'}), 400
    
    # --- ファイル名の決定 ---
    # 元のファイル名から安全なベース名を作成
    xml_filename = secure_filename(xml_file.filename)
    song_name_base = safe_name(os.path.splitext(xml_filename)[0])
    # 同名ファイルの上書きを防ぐため、連番を付与する
    counter = 1
    while True:
        path_check = os.path.join(UPLOAD_FOLDER, f"{song_name_base}_{counter}.musicxml")
        if not os.path.exists(path_check): break
        counter += 1
    song_name = f"{song_name_base}_{counter}"
    
    # --- ファイルの保存 ---
    original_xml_path = os.path.join(UPLOAD_FOLDER, f"{song_name}.musicxml")
    original_midi_path = os.path.join(UPLOAD_FOLDER, f"{song_name}.mid")
    xml_file.save(original_xml_path)
    midi_file.save(original_midi_path)
    
    # --- セッション情報の保存 ---
    # ユーザーごとのファイルパスなどをセッションに保存
    session.clear()
    session['xml_path'] = original_xml_path
    session['original_midi_path'] = original_midi_path
    session['song_name'] = song_name

    try:
        # --- ファイル解析と前処理 ---
        score = music21.converter.parse(original_xml_path)
        processor = MidiProcessor(original_midi_path)
        parts_info, all_abc_data = [], {}
        initial_wav_commands = [] # 初期WAV生成のためのコマンドリスト
        
        # オリジナルの全パートMIDIをコピーし、WAV生成コマンドを追加
        original_full_midi_dir = os.path.join(OUTPUT_DIRS["midi_full"], "original")
        os.makedirs(original_full_midi_dir, exist_ok=True)
        original_full_midi_path = os.path.join(original_full_midi_dir, f"{song_name}_full_original.mid")
        shutil.copy(original_midi_path, original_full_midi_path)
        original_full_audio_dir = os.path.join(OUTPUT_DIRS["audio"], "full_parts", "original")
        os.makedirs(original_full_audio_dir, exist_ok=True)
        original_full_wav_path = os.path.join(original_full_audio_dir, f"{song_name}_full_original.wav")
        initial_wav_commands.append([FLUIDSYNTH_EXE, "-ni", SOUNDFONT_PATH, original_full_midi_path, "-F", original_full_wav_path, "-r", "44100"])
        
        # 楽譜の各パートをループして処理
        for i, part in enumerate(score.parts):
            raw_part_name = part.partName or f"Part{i+1}"
            part_name = safe_name(raw_part_name)
            xml_out_path = os.path.join(OUTPUT_DIRS["musicxml"], f"{song_name}_{part_name}.musicxml")
            abc_out_path = os.path.join(OUTPUT_DIRS["abc"], f"{song_name}_{part_name}.abc")
            note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{song_name}_{part_name}_note_map.json")
            
            # パートごとにMusicXMLファイルとして書き出し
            part.write('musicxml', fp=xml_out_path)
            # 頂点推定などに使うための音符情報（note_map）をJSONとして生成
            processor.create_note_map_from_part(part, note_map_path)
            
            # オリジナルの単一パートMIDIを抽出し、WAV生成コマンドを追加
            original_single_midi_dir = os.path.join(OUTPUT_DIRS["midi_single"], "original")
            os.makedirs(original_single_midi_dir, exist_ok=True)
            original_single_midi_path = os.path.join(original_single_midi_dir, f"{song_name}_{part_name}_original.mid")
            processor.save_single_part_to_file(i, original_single_midi_path)
            original_single_audio_dir = os.path.join(OUTPUT_DIRS["audio"], "single_parts", "original")
            os.makedirs(original_single_audio_dir, exist_ok=True)
            original_single_wav_path = os.path.join(original_single_audio_dir, f"{song_name}_{part_name}_original.wav")
            initial_wav_commands.append([FLUIDSYNTH_EXE, "-ni", SOUNDFONT_PATH, original_single_midi_path, "-F", original_single_wav_path, "-r", "44100"])

            # ABC記法に変換し、フロントエンドに渡す
            if convert_with_xml2abc(xml_out_path, abc_out_path) and os.path.exists(abc_out_path):
                with open(abc_out_path, 'r', encoding='utf-8', errors='ignore') as f: all_abc_data[i] = f.read()
            else:
                # 変換失敗時はダミーデータを設定
                all_abc_data[i] = f"X:1\nT:{raw_part_name}\nM:4/4\nL:1/8\nK:C\n| CDEC | GFEF |]"
            # フロントエンドに返すパート情報のリストに追加
            parts_info.append({'name': raw_part_name, 'index': i, 'note_map': f"json/{os.path.basename(note_map_path)}"})
            
        # --- バックグラウンドで初期WAVを生成 ---
        # サウンドフォントが存在する場合のみ実行
        if os.path.exists(SOUNDFONT_PATH):
            task_id = str(uuid.uuid4())
            tasks[task_id] = {'state': 'PENDING', 'message': '初期WAV生成タスク待機中...'}
            
            # スレッドで実行する関数
            def initial_wav_task_wrapper():
                tasks[task_id]['state'] = 'PROGRESS'
                tasks[task_id]['total'] = len(initial_wav_commands)
                tasks[task_id]['current'] = 0
                for cmd in initial_wav_commands:
                    if not run_fluidsynth_command(cmd, task_id, len(initial_wav_commands)):
                        break # 途中で失敗したらループを抜ける
                if tasks[task_id]['state'] != 'FAILURE':
                    tasks[task_id]['state'] = 'SUCCESS'
            
            # 別スレッドを作成してタスクを開始
            thread = threading.Thread(target=initial_wav_task_wrapper)
            thread.start()
        else:
            app.logger.error(f"Upload: SoundFont not found. Original WAVs will not be generated.")
            
        # 正常に処理が完了したら、フロントエンドにパート情報などを返す
        return jsonify({'message': f'ファイルが正常にアップロードされました（連番: {counter}）', 'parts': parts_info, 'all_abc_data': all_abc_data})
    except Exception as e:
        app.logger.exception("Upload error")
        return jsonify({'error': f'アップロードエラー: {e}'}), 500

# ★★★ ここからが修正箇所 ★★★

def midi_to_note_name(midi_number):
    """MIDIノート番号を 'C4' のような音名表記に変換するヘルパー関数"""
    if midi_number is None:
        return None
    try:
        p = music21.pitch.Pitch()
        p.midi = midi_number
        return p.nameWithOctave
    except Exception:
        return str(midi_number)

@app.route('/estimate_apex', methods=['POST'])
def estimate_apex():
    """指定された範囲の音符群から、論文ルールに基づき頂点（アペックス）を推定する"""
    data = request.json
    part_name = data.get('partName')
    # フロントエンドから送られてくるのは「休符抜き」のインデックス
    fe_start_index = data.get('startIndex')
    fe_end_index = data.get('endIndex')

    note_map_path = os.path.join(OUTPUT_DIRS["json"], f"{session.get('song_name')}_{safe_name(part_name)}_note_map.json")
    if not os.path.exists(note_map_path):
        return jsonify({'error': 'Note map not found'}), 404
        
    with open(note_map_path, 'r', encoding='utf-8') as f:
        note_map = json.load(f)

    # =======================================================================================
    # --- フロントエンドのインデックスを、note_mapのインデックスに ---
    # =======================================================================================
    notes_only_map = [n for n in note_map if not n['is_rest']]
    
    if not (0 <= fe_start_index < len(notes_only_map) and 0 <= fe_end_index < len(notes_only_map)):
        return jsonify({'error': '無効な音符インデックスです。'}), 400

    true_start_index = notes_only_map[fe_start_index]['index']
    true_end_index = notes_only_map[fe_end_index]['index']
    
    # =======================================================================================
    # --- タイ結合を考慮した論理音符リストの作成 ---
    # =======================================================================================
    logical_full_note_map = []
    i = 0
    while i < len(note_map):
        current_event = note_map[i]
        
        if current_event['is_rest']:
            logical_full_note_map.append(current_event)
            i += 1
            continue

        last_index_in_tie = i
        if current_event.get('tie_info') == 'start':
            tied_duration = current_event['duration_beats']
            j = i + 1
            while j < len(note_map):
                next_event = note_map[j]
                if next_event.get('tie_info') in ['continue', 'stop'] and next_event.get('pitch') == current_event.get('pitch'):
                    tied_duration += next_event['duration_beats']
                    last_index_in_tie = j
                    if next_event.get('tie_info') == 'stop':
                        break
                else:
                    break
                j += 1
            
            logical_note = current_event.copy()
            logical_note['duration_beats'] = tied_duration
            logical_note['original_indices_range'] = (current_event['index'], note_map[last_index_in_tie]['index'])
            logical_full_note_map.append(logical_note)
            i = j + 1
        else:
            current_event['original_indices_range'] = (current_event['index'], current_event['index'])
            logical_full_note_map.append(current_event)
            i += 1
    
    # =======================================================================================
    # --- 選択されたフレーズ内の音符リストを抽出 ---
    # =======================================================================================
    logical_phrase_notes = []
    for logical_note in logical_full_note_map:
        if logical_note.get('is_rest', False):
            continue
            
        note_start, note_end = logical_note['original_indices_range']
        phrase_start, phrase_end = true_start_index, true_end_index
        if max(note_start, phrase_start) <= min(note_end, phrase_end):
            logical_phrase_notes.append(logical_note)

    if not logical_phrase_notes:
        return jsonify({'apex_candidates': []})
        
    # デバッグ用
    print("\n--- 選択されたフレーズの論理音符リスト ---")
    for note in logical_phrase_notes:
        start_orig_idx, end_orig_idx = note['original_indices_range']
        range_str = f"(covers: {start_orig_idx}-{end_orig_idx})" if start_orig_idx != end_orig_idx else ""
        
        print(
            f"  Index: {note['index']:<4} "
            f"音名: {midi_to_note_name(note.get('pitch')):<5} "
            f"音価(beats): {note['duration_beats']:.2f} {range_str}"
        )
    print("-------------------------------------\n")
    
    # =======================================================================================
    # --- 論文ルールに基づくスコアリング ---
    # =======================================================================================

    # 【ステップ1：前準備】
    # -----------------------------------------------------------------------------------
    scores = {note['index']: 0 for note in logical_phrase_notes}

    # 同じ音価が続く音符をグループ分けする
    duration_groups = []
    if logical_phrase_notes:
        current_group = [logical_phrase_notes[0]]
        for i in range(1, len(logical_phrase_notes)):
            if logical_phrase_notes[i]['duration_beats'] == current_group[0]['duration_beats']:
                current_group.append(logical_phrase_notes[i])
            else:
                duration_groups.append(current_group)
                current_group = [logical_phrase_notes[i]]
        duration_groups.append(current_group)

    # 【ステップ2：スコア計算】
    # -----------------------------------------------------------------------------------
    # --- ルール適用：音価 ---
    
    # ルール1. 隣接する2音の比較
    for i in range(len(logical_phrase_notes) - 1):
        note = logical_phrase_notes[i]
        next_note = logical_phrase_notes[i+1]
        if note['duration_beats'] > next_note['duration_beats']:
            scores[note['index']] += 1
        elif note['duration_beats'] < next_note['duration_beats']:
            scores[next_note['index']] += 1
            
    # ルール2. 同一音価が連続する音群
    for group in duration_groups:
        if len(group) > 1:
            # 第1音に1点加算
            scores[group[0]['index']] += 1
            # 第2音以降に「発音順/音符数」を加算
            for pos, note_in_group in enumerate(group):
                if pos > 0:
                    scores[note_in_group['index']] += (pos + 1) / len(group)

    # --- ルール適用：音高 ---
    
    # ルール1. 隣接する2音の比較
    for i in range(len(logical_phrase_notes) - 1):
        note = logical_phrase_notes[i]
        next_note = logical_phrase_notes[i+1]
        if note['pitch'] > next_note['pitch']:
            scores[note['index']] += 1
        elif note['pitch'] < next_note['pitch']:
            scores[next_note['index']] += 1

    # ルール2. 進行到達音 (4音のパターン)
    for i in range(1, len(logical_phrase_notes) - 2):
        n_minus_1, n, n_plus_1, n_plus_2 = logical_phrase_notes[i-1], logical_phrase_notes[i], logical_phrase_notes[i+1], logical_phrase_notes[i+2]
        p_m1, p_n, p_p1, p_p2 = n_minus_1['pitch'], n['pitch'], n_plus_1['pitch'], n_plus_2['pitch']
        
        dir1 = 1 if p_n > p_m1 else -1 if p_n < p_m1 else 0
        dir2 = 1 if p_p1 > p_n else -1 if p_p1 < p_n else 0
        dir3 = 1 if p_p2 > p_p1 else -1 if p_p2 < p_p1 else 0
        pattern = 0
        
        # 1) 上行-上行-下行
        if dir1 >= 0 and dir2 > 0 and dir3 < 0: 
            scores[n_plus_1['index']] += 1
            pattern = 1
        # 2) 下行-上行-下行
        elif dir1 < 0 and dir2 > 0 and dir3 < 0: 
            scores[n['index']] += 2
            scores[n_plus_1['index']] += 1
            pattern = 2
        # 3) 上行-下行-上行
        elif dir1 >= 0 and dir2 < 0 and dir3 > 0: 
            scores[n['index']] += 1
            scores[n_plus_1['index']] += 2
            scores[n_plus_2['index']] += 1
        # 4) 下行-下行-上行
        elif dir1 < 0 and dir2 < 0 and dir3 > 0: 
            scores[n_plus_1['index']] += 2
            scores[n_plus_2['index']] += 1
        
        # 5) 追加ルール
        if (pattern in [1, 2]) and n_plus_1['duration_seconds'] < 0.25:
            scores[n_minus_1['index']] += 1

    # 【ステップ3：結果の集計】
    # -----------------------------------------------------------------------------------
    max_score = max(scores.values()) if scores else 0
    candidates = [index for index, score in scores.items() if score == max_score and max_score > 0]
    
    expanded_candidates = []
    for index in candidates:
        expanded_candidates.append(index)
        note = next((n for n in note_map if n['index'] == index), None)
        
        if note and note.get('tie_info') == 'start':
            current_index = index + 1
            while current_index < len(note_map):
                next_note = note_map[current_index]
                if next_note.get('tie_info') in ['continue', 'stop']:
                    expanded_candidates.append(current_index)
                    if next_note.get('tie_info') == 'stop':
                        break
                else:
                    break
                current_index += 1
                
    final_candidates = sorted(list(set(expanded_candidates)))
    
    # 候補のインデックスも休符抜きにして返す
    notes_only_indices = {note['index']: i for i, note in enumerate(notes_only_map)}
    fe_candidates = [notes_only_indices[i] for i in final_candidates if i in notes_only_indices]
    
    return jsonify({'apex_candidates': fe_candidates})


@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    """フロントエンドからの指示（適用履歴）に基づき、音源生成のバックグラウンドタスクを開始する"""
    data = request.json
    history = data.get('history', [])
    part_index = data.get('partIndex')
    part_name = data.get('partName')
    
    # セッションから必要な情報を取得
    song_name = session.get('song_name')
    original_midi_path = session.get('original_midi_path')

    # タスクIDをユニークに生成
    task_id = str(uuid.uuid4())
    tasks[task_id] = {'state': 'PENDING', 'message': 'タスク待機中...'}

    # 別スレッドを作成し、重い処理（perform_audio_generation）を実行させる
    thread = threading.Thread(target=perform_audio_generation, args=(
        task_id, history, part_index, part_name, song_name, original_midi_path
    ))
    thread.start()
    
    # フロントエンドにはすぐにタスクIDを返す
    return jsonify({'task_id': task_id})

@app.route('/generation_status/<task_id>')
def generation_status(task_id):
    """指定されたタスクIDの現在の状態（進捗）を返す"""
    task = tasks.get(task_id, {'state': 'NOT_FOUND', 'message': 'タスクが見つかりません。'})
    return jsonify(task)

# ============================================================
# 実行
# ============================================================
if __name__ == '__main__':
    # このスクリプトが直接実行された場合に、開発用Webサーバーを起動する
    app.run(debug=True, port=5000)