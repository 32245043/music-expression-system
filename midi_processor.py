import json
import copy
import io
from mido import MidiFile, MidiTrack, Message, MetaMessage
import math
import subprocess
import os

# 🧩 FluidSynthのDLLを登録（Windows環境用）
os.add_dll_directory(r"C:\tools\fluidsynth\bin")

import fluidsynth   # ← ★ Python版 FluidSynth を使用

class MidiProcessor:
    """
    Tkinter版 music_expression-1.py の MIDI 加工ロジックを完全移植したクラス。
    - CC#2 (Expression) を補間挿入
    - CC#2 に基づいて note_on.velocity を再計算（乗算式）
    - onset_ms による発音タイミング調整（ms -> tick）
    - part_index が指定されている場合は単一パートMIDIを返す
    """

    def __init__(self, midi_path):
        self.midi_path = midi_path
        self.midi = MidiFile(midi_path)
        self.ticks_per_beat = self.midi.ticks_per_beat
        self.tempo = self._get_first_tempo()

    # ------------------------------
    # ユーティリティ
    # ------------------------------
    def _get_first_tempo(self):
        for track in self.midi.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    return msg.tempo
        return 500000  # default 120 BPM

    def ms_to_tick(self, ms):
        """ms -> tick"""
        seconds = ms / 1000.0
        ticks = seconds * (1_000_000.0 / self.tempo) * self.ticks_per_beat
        return int(round(ticks))

    def beat_to_tick(self, beat_offset_quarters):
        return int(round(beat_offset_quarters * self.ticks_per_beat))

    # ------------------------------
    # note_map生成（既存と互換）
    # ------------------------------
    def create_note_map_from_part(self, part, out_json_path):
        note_map = []
        idx = 0
        measures = list(part.getElementsByClass('Measure')) or [part]

        for m in measures:
            measure_offset = m.offset
            measure_number = getattr(m, 'measureNumber', None)
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
    # MIDI表情付け関数群
    # ------------------------------
    def get_base_cc2_value(self, track, start_tick, end_tick):
        """範囲内の既存CC#2の平均を返す。なければ64を返す。"""
        expressions = []
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if msg.type == 'control_change' and msg.control == 2 and start_tick <= abs_t <= end_tick:
                expressions.append(msg.value)
        return sum(expressions) / len(expressions) if expressions else 64

    def get_base_tempo(self, midi_file, start_tick):
        """start_tick 時点で有効なテンポを返す"""
        tempo_map = []
        for track in midi_file.tracks:
            abs_track_time = 0
            for msg in track:
                abs_track_time += msg.time
                if msg.type == 'set_tempo':
                    tempo_map.append((abs_track_time, msg.tempo))
        tempo_map.sort(key=lambda x: x[0])
        current_tempo = 500000
        for t, tempo in tempo_map:
            if t <= start_tick:
                current_tempo = tempo
            else:
                break
        return current_tempo

    def interpolate_cc2_with_even_ticks(self, track, start_tick, end_tick_max, peak_tick, start_expression, peak_expression, end_expression):
        """Tkinter版: 指定範囲にCC#2を等間隔(1tick)で補間挿入"""
        events = []
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            events.append({'time': abs_time, 'msg': msg})

        # 既存のCC2を範囲内から削除
        filtered_events = [
            e for e in events
            if not (start_tick <= e['time'] <= end_tick_max and e['msg'].type == 'control_change' and e['msg'].control == 2)
        ]

        cc_events = {}
        # 上昇
        if peak_tick >= start_tick:
            dur = peak_tick - start_tick
            for i in range(dur + 1):
                tick = start_tick + i
                val = start_expression + (peak_expression - start_expression) * (i / dur if dur > 0 else 1)
                cc_events[tick] = int(max(0, min(127, round(val))))
        # 下降
        if end_tick_max >= peak_tick:
            dur = end_tick_max - peak_tick
            for i in range(dur + 1):
                tick = peak_tick + i
                val = peak_expression + (end_expression - peak_expression) * (i / dur if dur > 0 else 1)
                cc_events[tick] = int(max(0, min(127, round(val))))

        new_cc = [{'time': t, 'msg': Message('control_change', control=2, value=v, time=0)} for t, v in sorted(cc_events.items())]
        all_events = sorted(filtered_events + new_cc, key=lambda x: x['time'])

        updated = MidiTrack()
        last_time = 0
        for e in all_events:
            delta = e['time'] - last_time
            updated.append(e['msg'].copy(time=int(max(0, delta))))
            last_time = e['time']

        track.clear()
        track.extend(updated)

    def adjust_velocity_based_on_expression(self, track):
        """CC2値に基づいてVelocityを乗算補正"""
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
            if msg.type == 'note_on' and msg.velocity > 0:
                cc_val = 64
                for t in sorted_ticks:
                    if t <= cur_t:
                        cc_val = expr_map[t]
                    else:
                        break
                new_vel = int(max(1, min(127, round(msg.velocity * (cc_val / 64.0)))))
                msg = msg.copy(velocity=new_vel)
            new_msgs.append(msg)

        track.clear()
        track.extend(new_msgs)

    def adjust_onset_times(self, track, start_tick, end_tick, onset_ms, midi_obj):
        """Tkinter版: 指定範囲内のノートをms単位で前後にずらす"""
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

        total_ms_shift = 0.0
        beat_tick = (start_tick // tpq) * tpq
        if beat_tick < start_tick:
            beat_tick += tpq
        while beat_tick <= end_tick:
            total_ms_shift += onset_ms
            beat_tick += tpq

        total_shift_ticks = round(total_ms_shift / ms_per_tick)
        new_track = MidiTrack()
        last_tick_adj = 0
        for abs_tick, msg in orig_events:
            new_abs_tick = abs_tick
            if start_tick <= abs_tick <= end_tick:
                beats_in = (abs_tick - start_tick) / tpq
                shift_ms = beats_in * onset_ms
                shift_ticks = round(shift_ms / ms_per_tick)
                new_abs_tick = abs_tick + shift_ticks
            elif abs_tick > end_tick:
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
        base_cc2 = int(preset_params.get('base_cc2', 0))
        peak_cc2 = int(preset_params.get('peak_cc2', 0))
        onset_ms = int(preset_params.get('onset_ms', 0))

        midi_copy = copy.deepcopy(MidiFile(self.midi_path))

        if start_tick > end_tick:
            start_tick, end_tick = end_tick, start_tick

        target_idx = part_index if (part_index is not None and 0 <= part_index < len(midi_copy.tracks)) else None

        if target_idx is not None:
            tr = midi_copy.tracks[target_idx]
            orig_expr = self.get_base_cc2_value(tr, start_tick, end_tick)
        else:
            orig_expr = 64

        start_expr = max(0, min(127, int(orig_expr + base_cc2)))
        peak_expr = max(0, min(127, int(orig_expr + peak_cc2)))
        end_expr = start_expr

        if target_idx is not None:
            self.interpolate_cc2_with_even_ticks(tr, start_tick, end_tick, peak_tick, start_expr, peak_expr, end_expr)
            self.adjust_velocity_based_on_expression(tr)

        for tr in midi_copy.tracks:
            self.adjust_onset_times(tr, start_tick, end_tick, onset_ms, midi_copy)

        # 🎯 単一パート出力
        if target_idx is not None:
            single_midi = MidiFile(ticks_per_beat=midi_copy.ticks_per_beat)
            single_midi.tracks.append(copy.deepcopy(midi_copy.tracks[target_idx]))
            for tr in midi_copy.tracks:
                for msg in tr:
                    if msg.type == "set_tempo":
                        single_midi.tracks[0].insert(0, msg.copy(time=0))
                        break
            return single_midi

        return midi_copy

    # ------------------------------
    # 保存処理
    # ------------------------------
    def save_to_bytes(self, midi_obj):
        buf = io.BytesIO()
        midi_obj.save(file=buf)
        buf.seek(0)
        return buf

    def save_to_file(self, midi_obj, out_path):
        midi_obj.save(out_path)
        print(f"✅ Saved MIDI: {out_path}")

    def save_single_part_to_file(self, part_index, out_path):
        """指定パートだけを抜き出してMIDIファイルとして保存"""
        try:
            midi_obj = MidiFile(self.midi_path)
            if part_index < 0 or part_index >= len(midi_obj.tracks):
                print(f"⚠️ 無効なpart_index: {part_index}")
                return
            single = MidiFile(ticks_per_beat=midi_obj.ticks_per_beat)
            single.tracks.append(copy.deepcopy(midi_obj.tracks[part_index]))
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
# 🎧 【追加機能】MIDI → WAV 変換（Python版FluidSynth）
# ============================================================
def midi_to_wav(midi_path, wav_path, soundfont_path="soundfonts/FluidR3_GM.sf2"):
    """Python版 FluidSynth を使ってMIDI→WAV変換"""
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    try:
        fs = fluidsynth.Synth()
        fs.start(driver="file", file=wav_path)  # ✅ 修正版（filename→output）
        sfid = fs.sfload(soundfont_path)
        fs.program_select(0, sfid, 0, 0)
        fs.midi_file_play(midi_path)
        fs.delete()
        print(f"✅ WAV生成完了: {wav_path}")
    except Exception as e:
        print(f"⚠️ WAV変換中にエラーが発生: {e}")
