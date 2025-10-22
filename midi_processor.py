import json
import copy
import io
from mido import MidiFile, MidiTrack, Message, MetaMessage
import math
import subprocess
import os

# Windows環境で動作させるために、FluidSynthのDLLパスをOSに追加
os.add_dll_directory(r"C:\tools\fluidsynth\bin")

import fluidsynth   

class MidiProcessor:
    """
    CC#2 (Expression) を線形補間
    CC#2に基づいて note_on.velocity を再計算（乗算式）
    onset_ms による発音タイミング調整（ms -> tick）
    part_indexが指定されている場合は単一パートMIDIを返す
    """

    def __init__(self, midi_path):
        self.midi_path = midi_path
        self.midi = MidiFile(midi_path)
        self.ticks_per_beat = self.midi.ticks_per_beat
        self.tempo = self._get_first_tempo()

    # ------------------------------
    # ヘルパー関数
    # ------------------------------
    def _get_first_tempo(self):
        # 
        for track in self.midi.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    return msg.tempo
        return 500000  # 見つからない場合 → default 120 BPM

    def ms_to_tick(self, ms):
        # ミリ秒をTickに変換
        seconds = ms / 1000.0
        # Tick = 秒 * (マイクロ秒/分) / (マイクロ秒/拍) * (Tick/拍)
        ticks = seconds * (1_000_000.0 / self.tempo) * self.ticks_per_beat
        return int(round(ticks))

    def beat_to_tick(self, beat_offset_quarters):
        # 拍単位のオフセットをTickに変換
        return int(round(beat_offset_quarters * self.ticks_per_beat))

    # ------------------------------
    # note_map(音符と時間の対応表)の生成
    # ------------------------------
    def create_note_map_from_part(self, part, out_json_path):
        # music21のパートから音符情報とTick位置を対応付けたJSONファイル(note_map)を生成する
        note_map = []
        idx = 0
        measures = list(part.getElementsByClass('Measure')) or [part]

        for m in measures:
            measure_offset = m.offset
            measure_number = getattr(m, 'measureNumber', None)
            # 小節内の全ての音符・休符を再帰的に取得
            for elem in m.recurse().notes:
                note_offset_in_measure = getattr(elem, 'offset', 0.0)
                global_offset_quarters = measure_offset + note_offset_in_measure
                duration_quarters = getattr(elem, 'quarterLength', 0.0)

                quarter_sec = self.tempo / 1_000_000.0
                seconds = global_offset_quarters * quarter_sec
                seconds_ms = seconds * 1000.0
                tick = self.beat_to_tick(global_offset_quarters)

                note_map.append({
                    "index": idx,
                    "measure": int(measure_number) if measure_number is not None else None,
                    "offset_beats": float(global_offset_quarters),
                    "duration_beats": float(duration_quarters),
                    "seconds_ms": float(round(seconds_ms, 3)),
                    "tick": int(tick)
                })
                idx += 1

        with open(out_json_path, 'w', encoding='utf-8') as f:
            json.dump(note_map, f, ensure_ascii=False, indent=2)

        return note_map

    # ------------------------------
    # MIDI表情付け
    # ------------------------------
    def get_base_cc2_value(self, track, start_tick, end_tick):
        # 指定範囲内に存在するCC#2の平均値を計算する、存在しない場合は64を返す
        expressions = []
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if msg.type == 'control_change' and msg.control == 2 and start_tick <= abs_t <= end_tick:
                expressions.append(msg.value)
        return sum(expressions) / len(expressions) if expressions else 64

    def get_base_tempo(self, midi_file, start_tick):
        # 指定されたTick位置で有効なテンポ設定を返す
        tempo_map = []
        for track in midi_file.tracks:
            abs_track_time = 0
            for msg in track:
                abs_track_time += msg.time
                if msg.type == 'set_tempo':
                    tempo_map.append((abs_track_time, msg.tempo))
        # 時間順にソートし、指定Tick直前のテンポを取得
        tempo_map.sort(key=lambda x: x[0])
        current_tempo = 500000 # デフォルトテンポ
        for t, tempo in tempo_map:
            if t <= start_tick:
                current_tempo = tempo
            else:
                break
        return current_tempo

    def interpolate_cc2_with_even_ticks(self, track, start_tick, end_tick_max, peak_tick, start_expression, peak_expression, end_expression):
        # 指定範囲にCC#2を1Tick感覚で線形補間
        events = []
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            events.append({'time': abs_time, 'msg': msg})

        # 処理範囲内に存在する既存のCC#2イベントを削除
        filtered_events = [
            e for e in events
            if not (start_tick <= e['time'] <= end_tick_max and e['msg'].type == 'control_change' and e['msg'].control == 2)
        ]

        cc_events = {}
        # 上昇部分(startからpeakまでを線形補間)
        if peak_tick >= start_tick:
            dur = peak_tick - start_tick
            for i in range(dur + 1):
                tick = start_tick + i
                val = start_expression + (peak_expression - start_expression) * (i / dur if dur > 0 else 1)
                cc_events[tick] = int(max(0, min(127, round(val))))
        # 下降部分(peakからendまでを線形補間)
        if end_tick_max >= peak_tick:
            dur = end_tick_max - peak_tick
            for i in range(dur + 1):
                tick = peak_tick + i
                val = peak_expression + (end_expression - peak_expression) * (i / dur if dur > 0 else 1)
                cc_events[tick] = int(max(0, min(127, round(val))))

        # 新しいCC#2イベントを作成し、既存イベントとマージ
        new_cc = [{'time': t, 'msg': Message('control_change', control=2, value=v, time=0)} for t, v in sorted(cc_events.items())]
        all_events = sorted(filtered_events + new_cc, key=lambda x: x['time'])

        # マージされたイベントリストから新しいトラックを再構築
        updated = MidiTrack()
        last_time = 0
        for e in all_events:
            delta = e['time'] - last_time
            updated.append(e['msg'].copy(time=int(max(0, delta))))
            last_time = e['time']

        track.clear()
        track.extend(updated)

    def adjust_velocity_based_on_expression(self, track):
        # トラック内のCC#2の値に基づき、各ノートのベロシティを乗算補正する
        expr_map = {}
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if msg.type == 'control_change' and msg.control == 2:
                expr_map[abs_t] = msg.value

        if not expr_map:
            return

        sorted_ticks = sorted(expr_map.keys())
        new_msgs = []
        cur_t = 0
        for msg in track:
            cur_t += msg.time
            # ノートオンの場合、直前のCC#2の値でベロシティを補正
            if msg.type == 'note_on' and msg.velocity > 0:
                cc_val = 64 # デフォルト値
                for t in sorted_ticks:
                    if t <= cur_t:
                        cc_val = expr_map[t]
                    else:
                        break
                # 補正係数 = (cc#2の値) / 基準値64.0)
                new_vel = int(max(1, min(127, round(msg.velocity * (cc_val / 64.0)))))
                msg = msg.copy(velocity=new_vel)
            new_msgs.append(msg)

        track.clear()
        track.extend(new_msgs)

    def adjust_onset_times(self, track, start_tick, end_tick, onset_ms, midi_obj):
        # 指定範囲内の音符の発音タイミングをミリ秒単位で前後にずらす(onset_ms)
        if midi_obj is None:
            return
        tpq = midi_obj.ticks_per_beat
        tempo = self.get_base_tempo(midi_obj, 0)
        if tpq == 0 or tempo == 0:
            return

        ms_per_tick = (tempo / tpq) / 1000.0
        orig_events = []
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            orig_events.append((abs_t, msg))

        # 範囲全体の総シフト量を計算
        total_ms_shift = 0.0
        beat_tick = (start_tick // tpq) * tpq
        if beat_tick < start_tick:
            beat_tick += tpq
        while beat_tick <= end_tick:
            total_ms_shift += onset_ms
            beat_tick += tpq

        total_shift_ticks = round(total_ms_shift / ms_per_tick)
        
        # 新しいイベントタイミングでトラックを再構築
        new_track = MidiTrack()
        last_tick_adj = 0
        for abs_tick, msg in orig_events:
            new_abs_tick = abs_tick
            if start_tick <= abs_tick <= end_tick:
                # 範囲内は経過拍に応じてシフト量を線形に増やす
                beats_in = (abs_tick - start_tick) / tpq
                shift_ms = beats_in * onset_ms
                shift_ticks = round(shift_ms / ms_per_tick)
                new_abs_tick = abs_tick + shift_ticks
            elif abs_tick > end_tick:
                # 範囲以降は総シフト量で一律にずらす
                new_abs_tick = abs_tick + total_shift_ticks

            delta = new_abs_tick - last_tick_adj
            new_msg = msg.copy(time=int(max(0, delta)))
            new_track.append(new_msg)
            last_tick_adj = new_abs_tick

        track.clear()
        track.extend(new_track)

    # ------------------------------
    # メイン処理
    # ------------------------------
    def apply_expression_by_ticks(self, part_index, start_tick, end_tick, peak_tick, preset_params):
        # 指定されたTick範囲にプリセットパラメータを適用し、加工後のMIDIオブジェクトを返す
        # part_indexがNoneの場合は全パートに適用する
        base_cc2 = int(preset_params.get('base_cc2', 0))
        peak_cc2 = int(preset_params.get('peak_cc2', 0))
        onset_ms = int(preset_params.get('onset_ms', 0))
        
        midi_copy = copy.deepcopy(MidiFile(self.midi_path))

        if start_tick > end_tick:
            start_tick, end_tick = end_tick, start_tick

        target_idx = part_index if (part_index is not None and 0 <= part_index < len(midi_copy.tracks)) else None

        # 基準となるCC#2値を決定
        if target_idx is not None:
            tr = midi_copy.tracks[target_idx]
            orig_expr = self.get_base_cc2_value(tr, start_tick, end_tick)
        else:
            orig_expr = 64 # 全パート対象の場合は固定値

        # プリセット値を加算して最終的なCC#2の値を計算
        start_expr = max(0, min(127, int(orig_expr + base_cc2)))
        peak_expr = max(0, min(127, int(orig_expr + peak_cc2)))
        end_expr = start_expr

        # 単一パートにCC#2とベロシティの変更を適用
        if target_idx is not None:
            self.interpolate_cc2_with_even_ticks(tr, start_tick, end_tick, peak_tick, start_expr, peak_expr, end_expr)
            self.adjust_velocity_based_on_expression(tr)

        # 全トラックに発音タイミング変更を適用
        for tr in midi_copy.tracks:
            self.adjust_onset_times(tr, start_tick, end_tick, onset_ms, midi_copy)

        # 単一パートのみを抽出して出力する場合
        if target_idx is not None:
            single_midi = MidiFile(ticks_per_beat=midi_copy.ticks_per_beat)
            single_midi.tracks.append(copy.deepcopy(midi_copy.tracks[target_idx]))
            # テンポ情報をトラックの先頭にコピー
            for tr in midi_copy.tracks:
                for msg in tr:
                    if msg.type == "set_tempo":
                        single_midi.tracks[0].insert(0, msg.copy(time=0))
                        break
            return single_midi

        return midi_copy

    # ------------------------------
    # ファイル保存
    # ------------------------------
    def save_to_bytes(self, midi_obj):
        # MIDIオブジェクトをバイトデータとして保存する
        buf = io.BytesIO()
        midi_obj.save(file=buf)
        buf.seek(0)
        return buf

    def save_to_file(self, midi_obj, out_path):
        # MIDIオブジェクトを指定されたパスにファイルとして保存する
        midi_obj.save(out_path)
        print(f"✅ Saved MIDI: {out_path}")

    def save_single_part_to_file(self, part_index, out_path):
        # 元のMIDIファイルから指定パートだけを抜き出して保存する
        try:
            midi_obj = MidiFile(self.midi_path)
            if part_index < 0 or part_index >= len(midi_obj.tracks):
                print(f"⚠️ 無効なpart_index: {part_index}")
                return
            single = MidiFile(ticks_per_beat=midi_obj.ticks_per_beat)
            single.tracks.append(copy.deepcopy(midi_obj.tracks[part_index]))
            # テンポ情報をトラックの先頭にコピー
            for tr in midi_obj.tracks:
                for msg in tr:
                    if msg.type == "set_tempo":
                        single.tracks[0].insert(0, msg.copy(time=0))
                        break
            single.save(out_path)
            print(f"💾 Saved original single-part MIDI: {out_path}")
        except Exception as e:
            print(f"⚠️ save_single_part_to_file エラー: {e}")

# ============================================================
# MIDIからWAVへ変換
# ============================================================
def midi_to_wav(midi_path, wav_path, soundfont_path="soundfonts/FluidR3_GM.sf2"):
    # pyFluidSynthライブラリを使用して、MIDIファイルをWAVファイルに変換する
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    try:
        fs = fluidsynth.Synth()
        # 出力ドライバーをファイルに設定
        fs.start(driver="file", file=wav_path)  
        sfid = fs.sfload(soundfont_path)
        fs.program_select(0, sfid, 0, 0)
        fs.midi_file_play(midi_path)
        fs.delete()
        print(f"✅ WAV生成完了: {wav_path}")
    except Exception as e:
        print(f"⚠️ WAV変換中にエラーが発生: {e}")
