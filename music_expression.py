import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import copy  
import json  

import mido
from mido import MidiFile, MidiTrack, Message

# ---------------- ユーザー設定 ----------------
# 出力ディレクトリ名
output_png = "output(png)"
output_xml = "output(xml)"
output_ly = "output(ly)"
output_midi = "output(midi)"
output_single_part_midi = "output(single_part_midi)" 

# Python実行ファイルのパス
python_exe = ""
# LilyPondのルートディレクトリ
lilypond_root = r"lilypond-2.24.4-mingw-x86_64\lilypond-2.24.4"
# musicxml2ly.pyのパス
xml2ly_script = os.path.join(lilypond_root, "bin", "musicxml2ly.py")
# LilyPond実行ファイルのパス
lilypond_exe = os.path.join(lilypond_root, "bin", "lilypond.exe")
# ------------------------------------------------

class MusicProcessorApp:
    def __init__(self, master):
        self.master = master
        master.title("発想標語に対応する演奏見本システム")
        master.geometry("1300x800")

        self.full_score = None 
        self.mido_midi_file = None 
        self.current_xml_path = None
        self.current_midi_path = None
        self.current_base_name = None
        self.tk_image = None
        self.selected_mido_track_index = -1

        # 発想標語と対応するCC2値・onset(速度)のプリセット
        # フォーマット: { "発想標語": {"base_cc2": 値, "peak_cc2": 値, "onset_ms": 値_ms} }
        # base_cc2 は CC2 の値に直接加算される値（0-127の範囲）
        # peak_cc2 は 頂点で加算される値
        # onset_ms は1拍あたりに加算/減算するミリ秒数 (正:遅く, 負:速く)# 発想標語と対応するCC2値・onset(速度)のプリセット
        self.tempo_expressions = {
            "なし": {"base_cc2": 0, "peak_cc2": 0, "onset_ms": 0},
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

        # 形容詞と対応するCC2値・onset(速度)のプリセット
        # フォーマット: { "形容詞": {"base_cc2": 値, "peak_cc2": 値, "onset_ms": 値_ms} }
        # base_cc2 は CC2 の値に直接加算される値（0-127の範囲）
        # peak_cc2 は 頂点で加算される値
        # onset_ms は1拍あたりに加算/減算するミリ秒数 (正:遅く, 負:速く)
        self.adjective_expressions = {
            "なし": {"base_cc2": 0, "peak_cc2": 0, "onset_ms": 0},
            "明るい": {"base_cc2": 5, "peak_cc2": 20, "onset_ms": -5},  
            "華やか": {"base_cc2": 10, "peak_cc2": 28, "onset_ms": -10}, 
            "壮大": {"base_cc2": 15, "peak_cc2": 32, "onset_ms": 15},   
            "暗い": {"base_cc2": -5, "peak_cc2": 8, "onset_ms": 5},    
            "穏やか": {"base_cc2": -2, "peak_cc2": 12, "onset_ms": 2},   
            "激しい": {"base_cc2": 12, "peak_cc2": 30, "onset_ms": -12}, 
        }

        self.create_widgets()
        self.check_lilypond_setup()

    def check_lilypond_setup(self):
        if not os.path.exists(lilypond_exe):
            messagebox.showwarning("設定エラー", f"LilyPond実行ファイルが見つかりません。： {lilypond_exe}")
            return False
        if not os.path.exists(xml2ly_script):
            messagebox.showwarning("設定エラー", f"musicxml2ly.pyスクリプトが見つかりません。: {xml2ly_script}")
            return False
        return True

    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.pack(fill="both", expand=True)

        # --- 左パネル ---
        left_panel = ttk.Frame(main_frame, width=250, relief="groove", borderwidth=2)
        left_panel.pack(side="left", fill="y", padx=10, pady=10)
        left_panel.pack_propagate(False)

        # MusicXMLファイル読み込み
        xml_frame = ttk.LabelFrame(left_panel, text="1. 楽譜 (MusicXML) の読み込み", padding="10")
        xml_frame.pack(fill="x", pady=5)
        
        open_xml_button = ttk.Button(xml_frame, text="開く (MusicXML)", command=self.select_xml_file)
        open_xml_button.pack(fill="x")
        self.xml_file_label = ttk.Label(xml_frame, text="ファイル未選択", foreground="gray")
        self.xml_file_label.pack(fill="x", pady=(5,0))

        # MIDIファイル読み込み
        midi_frame = ttk.LabelFrame(left_panel, text="2. 演奏データ (MIDI) の読み込み", padding="10")
        midi_frame.pack(fill="x", pady=5)

        open_midi_button = ttk.Button(midi_frame, text="開く (MIDI)", command=self.select_midi_file)
        open_midi_button.pack(fill="x")
        self.midi_file_label = ttk.Label(midi_frame, text="ファイル未選択", foreground="gray")
        self.midi_file_label.pack(fill="x", pady=(5,0))

        # パートのリスト
        part_list_frame = ttk.LabelFrame(left_panel, text="3. パートの選択", padding="10")
        part_list_frame.pack(fill="both", expand=True, pady=5)

        self.part_listbox = tk.Listbox(part_list_frame, selectmode=tk.SINGLE, height=15)
        self.part_listbox.pack(side="left", fill="both", expand=True)
        self.part_listbox.bind("<<ListboxSelect>>", self.part_selected)

        part_scrollbar = ttk.Scrollbar(part_list_frame, orient="vertical", command=self.part_listbox.yview)
        part_scrollbar.pack(side="right", fill="y")
        self.part_listbox.config(yscrollcommand=part_scrollbar.set)
        
        # --- 中央パネル (楽譜表示) ---
        center_panel = ttk.Frame(main_frame, relief="groove", borderwidth=2)
        center_panel.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        # スクロールバーの追加
        score_v_scrollbar = ttk.Scrollbar(center_panel, orient="vertical")
        score_v_scrollbar.pack(side="right", fill="y")

        self.score_canvas = tk.Canvas(center_panel, bg="white", highlightbackground="gray", highlightthickness=1, yscrollcommand=score_v_scrollbar.set)
        self.score_canvas.pack(side="left", fill="both", expand=True)

        score_v_scrollbar.config(command=self.score_canvas.yview)

        # --- 右パネル (CC2、形容詞、ボタン、フレーズ設定) ---
        right_panel = ttk.Frame(main_frame, width=300, relief="groove", borderwidth=2)
        right_panel.pack(side="right", fill="y", padx=10, pady=10)
        right_panel.pack_propagate(False)

        phrase_setting_frame = ttk.LabelFrame(right_panel, text="フレーズ設定", padding="10")
        phrase_setting_frame.pack(fill="x", pady=10)

        # ### 追加 ###: JSONファイル読み込みボタン
        load_phrase_button = ttk.Button(phrase_setting_frame, text="フレーズを読み込み (.json)", command=self.load_phrase_from_file)
        load_phrase_button.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="ew")
        
        # ### 変更 ###: gridのrow番号を1つずつずらす
        ttk.Label(phrase_setting_frame, text="開始小節:").grid(row=1, column=0, sticky="w", pady=2)
        self.start_measure_entry = ttk.Entry(phrase_setting_frame)
        self.start_measure_entry.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(phrase_setting_frame, text="開始拍:").grid(row=2, column=0, sticky="w", pady=2)
        self.start_beat_entry = ttk.Entry(phrase_setting_frame)
        self.start_beat_entry.grid(row=2, column=1, sticky="ew", pady=2)

        ttk.Label(phrase_setting_frame, text="終了小節:").grid(row=3, column=0, sticky="w", pady=2)
        self.end_measure_entry = ttk.Entry(phrase_setting_frame)
        self.end_measure_entry.grid(row=3, column=1, sticky="ew", pady=2)

        ttk.Label(phrase_setting_frame, text="終了拍:").grid(row=4, column=0, sticky="w", pady=2)
        self.end_beat_entry = ttk.Entry(phrase_setting_frame)
        self.end_beat_entry.grid(row=4, column=1, sticky="ew", pady=2)

        # 頂点の小節と拍
        ttk.Label(phrase_setting_frame, text="頂点小節:").grid(row=5, column=0, sticky="w", pady=2)
        self.peak_measure_entry = ttk.Entry(phrase_setting_frame)
        self.peak_measure_entry.grid(row=5, column=1, sticky="ew", pady=2)

        ttk.Label(phrase_setting_frame, text="頂点拍:").grid(row=6, column=0, sticky="w", pady=2)
        self.peak_beat_entry = ttk.Entry(phrase_setting_frame)
        self.peak_beat_entry.grid(row=6, column=1, sticky="ew", pady=2)

        # ドロップダウンメニュー（発想標語）
        ttk.Label(phrase_setting_frame, text="発想標語プリセット:").grid(row=7, column=0, sticky="w", pady=2)
        self.tempo_preset_var = tk.StringVar(self.master)
        # 初期値：辞書の1番目(「なし」が最初になるように変更)
        initial_tempo_preset = "なし" 
        self.tempo_preset_var.set(initial_tempo_preset)
        self.tempo_preset_menu = ttk.OptionMenu(phrase_setting_frame, self.tempo_preset_var,
                                                 initial_tempo_preset,
                                                 *self.tempo_expressions.keys())
        self.tempo_preset_menu.grid(row=7, column=1, sticky="ew", pady=2)
        # ドロップダウンメニューが変更されたときにイベントをトリガー
        self.tempo_preset_var.trace_add("write", self.on_tempo_preset_selected)

        # ドロップダウンメニュー（形容詞）
        ttk.Label(phrase_setting_frame, text="形容詞プリセット:").grid(row=8, column=0, sticky="w", pady=2)
        self.adjective_preset_var = tk.StringVar(self.master)
        self.adjective_preset_var.set(list(self.adjective_expressions.keys())[0])
        self.adjective_preset_menu = ttk.OptionMenu(phrase_setting_frame, self.adjective_preset_var,
                                                     list(self.adjective_expressions.keys())[0],
                                                     *self.adjective_expressions.keys())
        self.adjective_preset_menu.grid(row=8, column=1, sticky="ew", pady=2)
        self.adjective_preset_var.trace_add("write", self.on_adjective_preset_selected)

        # ボタン
        button_frame = ttk.Frame(right_panel, padding="10")
        button_frame.pack(fill="x", pady=20)
        
        highlight_button = ttk.Button(button_frame, text="フレーズをハイライト", command=self.highlight_phrase_on_score)
        highlight_button.pack(fill="x", pady=5)

        apply_button = ttk.Button(button_frame, text="適用", command=self.apply_changes)
        apply_button.pack(fill="x", pady=5)
        save_button = ttk.Button(button_frame, text="保存", command=self.save_score)
        save_button.pack(fill="x", pady=5)

    # JSONファイルからフレーズ範囲を読み込む
    def load_phrase_from_file(self):
        file_path = filedialog.askopenfilename(
            title="フレーズ範囲ファイルを選択",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # JSONから値を取得
            start_measure = data['start']['measure']
            start_beat = data['start']['beat']
            end_measure = data['end']['measure']
            end_beat = data['end']['beat']

            # 既存の入力値をクリア
            self.start_measure_entry.delete(0, tk.END)
            self.start_beat_entry.delete(0, tk.END)
            self.end_measure_entry.delete(0, tk.END)
            self.end_beat_entry.delete(0, tk.END)
            # 頂点もクリア
            self.peak_measure_entry.delete(0, tk.END)
            self.peak_beat_entry.delete(0, tk.END)

            # 新しい値を挿入
            self.start_measure_entry.insert(0, str(start_measure))
            self.start_beat_entry.insert(0, str(start_beat))
            self.end_measure_entry.insert(0, str(end_measure))
            self.end_beat_entry.insert(0, str(end_beat))
            
            messagebox.showinfo("読み込み完了", "フレーズ範囲をファイルから読み込みました。\n頂点の小節と拍を手動で設定してください。")

        except FileNotFoundError:
            messagebox.showerror("エラー", f"ファイルが見つかりません: {file_path}")
        except json.JSONDecodeError:
            messagebox.showerror("エラー", "JSONファイルの形式が正しくありません。")
        except KeyError as e:
            messagebox.showerror("エラー", f"JSONファイルに必要なキーがありません: {e}\n\n期待されるフォーマット:\n"
                                          '{"start": {"measure": 1, "beat": 1.0}, "end": {"measure": 4, "beat": 4.0}}')
        except Exception as e:
            messagebox.showerror("エラー", f"ファイルの読み込み中に予期せぬエラーが発生しました: {e}")


    def on_tempo_preset_selected(self, *args):
        # 発想標語が選択された場合、形容詞プリセットを「なし」にリセット
        if self.adjective_preset_var.get() != "なし":
            self.adjective_preset_var.set("なし")

    def on_adjective_preset_selected(self, *args):
        # 形容詞が選択された場合、発想標語プリセットを「なし」にリセット
        current_adjective_selection = self.adjective_preset_var.get()
        if current_adjective_selection != "なし" and self.tempo_preset_var.get() != "なし":
            self.tempo_preset_var.set("なし")

    def select_xml_file(self):
        # MusicXMLファイルを選択するダイアログ
        file_path = filedialog.askopenfilename(
            title="楽譜ファイル (MusicXML) を選択してください",
            filetypes=[("MusicXML files", "*.xml *.musicxml"), ("All files", "*.*")]
        )
        if file_path:
            self.current_xml_path = file_path
            self.xml_file_label.config(text=os.path.basename(file_path))
            base_name_from_file = os.path.splitext(os.path.basename(file_path))[0]
            self.current_base_name = "".join(c if c.isalnum() else "_" for c in base_name_from_file)
            self.load_score_and_populate_parts(file_path)
            self.check_files_and_show_status()

    def select_midi_file(self):
        # MIDIファイルを選択するダイアログ
        file_path = filedialog.askopenfilename(
            title="演奏データ (MIDI) を選択してください",
            filetypes=[("MIDI files", "*.mid *.midi")]
        )
        if file_path:
            self.current_midi_path = file_path
            self.midi_file_label.config(text=os.path.basename(file_path))
            try:
                self.mido_midi_file = self.load_midi(file_path)
            except Exception as e:
                messagebox.showerror("エラー", f"MIDIファイルの読み込みに失敗しました: {e}")
                self.mido_midi_file = None
            self.check_files_and_show_status()

    def check_files_and_show_status(self):
        # MusicXMLとMIDIファイルが両方選択されているか確認
        if self.full_score and self.mido_midi_file:
            num_xml_parts = len(self.full_score.parts)
            num_midi_tracks = len([t for t in self.mido_midi_file.tracks if any(msg.type == 'note_on' for msg in t)])
            
            if num_xml_parts != num_midi_tracks:
                messagebox.showwarning("警告", f"MusicXMLのパート数 ({num_xml_parts}) とMIDIの演奏トラック数 ({num_midi_tracks}) が一致しません。\n処理は続行できますが、意図しない結果になる可能性があります。")
            else:
                messagebox.showinfo("準備完了", "楽譜とMIDIファイルが読み込まれました。\nパートを選択してください。")

    def load_score_and_populate_parts(self, xml_path):
        # 楽譜ファイルを読み込み、パートリストを更新
        try:
            from music21 import converter
            self.full_score = converter.parse(xml_path)
            self.part_listbox.delete(0, tk.END)
            if not self.full_score.parts:
                messagebox.showinfo("情報", "MusicXML内にパートが見つかりませんでした。")
                return
            for i, part in enumerate(self.full_score.parts):
                part_name = part.partName if part.partName else f"Part {i+1}"
                self.part_listbox.insert(tk.END, part_name)
            
            messagebox.showinfo("楽譜の読み込み完了", "楽譜ファイルを読み込みました。\n演奏データ (MIDI) を読み込んでください。")

        except Exception as e:
            messagebox.showerror("エラー", f"楽譜ファイルの解析に失敗しました: {e}")
            self.full_score = None
    
    def part_selected(self, event):
        # パートが選択されたときの処理
        if not self.full_score:
            messagebox.showwarning("警告", "先に楽譜ファイル (MusicXML) を読み込んでください。")
            return

        selected_indices = self.part_listbox.curselection()
        if not selected_indices:
            return

        idx = selected_indices[0]
        self.selected_mido_track_index = idx # mido操作のためにインデックスを保存

        selected_part = self.full_score.parts[idx]
        part_name = self.part_listbox.get(idx)
        self.process_and_display_part(selected_part, part_name)

    def highlight_phrase_on_score(self):
        """GUIで指定された範囲の音符をハイライトして楽譜を再表示する"""
        if not self.full_score or self.selected_mido_track_index == -1:
            messagebox.showwarning("警告", "楽譜ファイルを読み込み、パートを選択してください。")
            return
        
        selected_indices = self.part_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "パートが選択されていません。")
            return

        try:
            start_measure = int(self.start_measure_entry.get())
            start_beat = float(self.start_beat_entry.get())
            end_measure = int(self.end_measure_entry.get())
            end_beat = float(self.end_beat_entry.get())
            
            #  頂点の小節と拍を取得（空の場合はNone）
            peak_measure_str = self.peak_measure_entry.get()
            peak_beat_str = self.peak_beat_entry.get()
            peak_measure = int(peak_measure_str) if peak_measure_str else None
            peak_beat = float(peak_beat_str) if peak_beat_str else None

        except ValueError:
            messagebox.showerror("入力エラー", "小節と拍には有効な数値を入力してください。")
            return

        # 元の楽譜データを壊さないように、選択パートをディープコピー
        selected_part_index = selected_indices[0]
        original_part = self.full_score.parts[selected_part_index]
        part_to_highlight = copy.deepcopy(original_part)
        part_name = self.part_listbox.get(selected_part_index)

        notes_found = False
        # 頂点の音符を見つける
        found_peak_note = False
        
        # part_to_highlight 内の全ての音符を再帰的に検索
        for note in part_to_highlight.recurse().notes:
            # 頂点の音符に色を付ける
            # 1. 頂点の音符かどうかをチェック
            is_peak_note = False
            if peak_measure is not None and peak_beat is not None and not found_peak_note:
                # 頂点の小節にあり、かつ指定された拍に最も近い音符を頂点とする
                if note.measureNumber == peak_measure and note.beat >= peak_beat:
                    is_peak_note = True
                    found_peak_note = True # 複数の音符が該当しないようにする

            if is_peak_note:
                note.style.color = 'lightcoral'  # 頂点の音符の色を 'lightcoral' に
                notes_found = True
                continue # 頂点の音符はフレーズ範囲の色付け対象から外す

            # 2. 頂点でない場合、フレーズ範囲内かどうかをチェック
            in_range = False
            # music21では拍(beat)は1から始まる
            # フレーズ範囲内の音符
            if start_measure < note.measureNumber < end_measure:
                in_range = True
            # 開始小節にあり、開始拍以降の音符
            elif note.measureNumber == start_measure and note.beat >= start_beat:
                in_range = True
            # 終了小節にあり、終了拍以前の音符
            elif note.measureNumber == end_measure and note.beat <= end_beat:
                in_range = True
            
            if in_range:
                note.style.color = 'cornflowerblue'
                notes_found = True

        if not notes_found:
            messagebox.showinfo("情報", "指定された範囲に音符が見つかりませんでした。")
        
        messagebox.showinfo("処理中", "ハイライトされた楽譜を生成しています...")
        # 色付けしたパートオブジェクトを使って、楽譜PNGを再生成・表示する
        self.process_and_display_part(part_to_highlight, f"{part_name}_highlighted")

    def process_and_display_part(self, selected_part_obj, display_name):
        # MusicXML→ LilyPond→PNGに変換
        # PNGをGUIに表示
        if not self.check_lilypond_setup():
            return

        from music21 import stream
        # 選択されたパートの楽譜を作成
        new_score = stream.Score()
        new_score.insert(0, selected_part_obj)
        new_score.metadata = self.full_score.metadata # メタデータをコピー

        # 出力ファイル名
        safe_part_suffix = "".join(c if c.isalnum() else "_" for c in display_name)
        output_base_name = f"{self.current_base_name}_{safe_part_suffix}"

        output_xml_path = os.path.join(os.getcwd(), output_xml, output_base_name + ".xml")
        output_ly_path = os.path.join(os.getcwd(), output_ly, output_base_name + ".ly")
        output_png_dir = os.path.join(os.getcwd(), output_png)

        os.makedirs(os.path.join(os.getcwd(), output_xml), exist_ok=True)
        os.makedirs(os.path.join(os.getcwd(), output_ly), exist_ok=True)
        os.makedirs(output_png_dir, exist_ok=True)

        try:
            # 1. MusicXMLファイルとして書き出し
            print(f"'{display_name}'パートのMusicXMLファイルを書き出しています")
            new_score.write("musicxml", fp=output_xml_path)
            print(f"MusicXMLに変換完了: {output_xml_path}")

            # 2. MusicXMLをLilyPond (.ly) 
            print(f"MusicXMLをLilyPond (.ly) に変換しています")
            if os.path.exists(output_ly_path):
                os.remove(output_ly_path)
            python_command = [python_exe or "python", xml2ly_script, output_xml_path, "-o", output_ly_path]
            subprocess.run(python_command, capture_output=True, text=True, check=True, encoding="utf-8")
            if not os.path.exists(output_ly_path) or os.path.getsize(output_ly_path) == 0:
                raise RuntimeError(".lyファイルが作成されなかった、または空です。")
            print(f"LilyPond (.ly) に変換完了: {output_ly_path}")

            # 3. LilyPond(.ly) -> PNG
            print(f"LilyPondファイルからPNGを生成しています")
            # 縦長のPNGを生成
            subprocess.run([
                lilypond_exe,
                "--png",
                "-dresolution=150",
                "-dtall-page-formats=png", # 縦長PNGを生成するオプション
                "--output", os.path.join(output_png_dir, output_base_name),
                output_ly_path
            ], capture_output=True, text=True, check=True, encoding="utf-8")

            png_path = os.path.join(output_png_dir, f"{output_base_name}.png")

            if os.path.exists(png_path):
                self.display_png_on_canvas(png_path)
                messagebox.showinfo("完了", f"'{display_name}'パートの楽譜を生成し、表示しました。")
            else:
                messagebox.showerror("エラー", f"PNG画像が見つかりませんでした。: {png_path}")

        except subprocess.CalledProcessError as e:
            error_message = f"変換中にエラーが発生しました:\n{e.stderr}"
            print(error_message)
            messagebox.showerror("変換エラー", error_message)
        except Exception as e:
            messagebox.showerror("エラー", f"楽譜の処理中に予期せぬエラーが発生しました: {e}")

    def display_png_on_canvas(self, image_path):
        # 指定されたPNG画像をキャンバスに表示
        try:
            img = Image.open(image_path)
            
            # アスペクト比を維持しながらキャンバスの「幅」に合わせて画像をリサイズ
            # これにより縦長の画像は下に伸び、スクロールバーで閲覧できるようになる
            canvas_width = self.score_canvas.winfo_width()
            
            if canvas_width <= 1:
                # ウィンドウ描画前の初回呼び出し対策
                self.master.update_idletasks()
                canvas_width = self.score_canvas.winfo_width()
                if canvas_width <=1: canvas_width = 800 

            img_width, img_height = img.size

            # 常に幅を基準にリサイズする
            new_width = canvas_width - 4 # 余白
            aspect_ratio = img_height / img_width
            new_height = int(new_width * aspect_ratio)

            img = img.resize((new_width, new_height), Image.LANCZOS)

            self.tk_image = ImageTk.PhotoImage(img)
            self.score_canvas.delete("all") # 以前の画像をクリア
            # 画像をキャンバスの左上に配置
            self.score_canvas.create_image(0, 0, image=self.tk_image, anchor="nw") 
            # スクロール領域を画像全体に設定
            self.score_canvas.config(scrollregion=self.score_canvas.bbox(tk.ALL)) 

        except Exception as e:
            messagebox.showerror("画像表示エラー", f"画像の表示に失敗しました: {e}")

    # --- MIDIファイルの情報取得 ---

    def load_midi(self, filename):
        # Midoを使用してMIDIファイルを読み込む
        return MidiFile(filename)

    def get_time_signature(self, midi_file):
        # 拍子記号を取得
        for track in midi_file.tracks:
            for msg in track:
                if msg.type == 'time_signature':
                    return msg
        return mido.MetaMessage('time_signature', numerator=4, denominator=4)

    def get_tick(self, midi_file, measure, beat, ticks_per_beat, time_signature):
        # 小節、拍、拍子記号からTickを計算
        ticks_per_measure = ticks_per_beat * time_signature.numerator
        # 小節と拍は1からカウント
        tick = (measure - 1) * ticks_per_measure + round((beat - 1) * ticks_per_beat)
        return tick

    def get_max_tick_in_beat(self, midi_file, measure, beat, ticks_per_beat, time_signature):
        # 指定された小説と拍の最後のTickを計算
        ticks_per_measure = ticks_per_beat * time_signature.numerator
        start_tick = (measure - 1) * ticks_per_measure + round((beat - 1) * ticks_per_beat)
        return start_tick + ticks_per_beat - 1 # その拍の最後のTick

    def get_base_cc2_value(self, track, start_tick, end_tick):
        # 指定されたTick範囲のCC2の平均値を取得
        expressions = []
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            if start_tick <= abs_time <= end_tick and msg.type == 'control_change' and msg.control == 2:
                expressions.append(msg.value)
        return sum(expressions) / len(expressions) if expressions else 64

    def get_base_tempo(self, midi_file, start_tick):
        # 指定されたTick以前の最も近いテンポ(ms/beat)
        tempo_map = []
        current_tempo = 500000 # デフォルトテンポ 120BPM (500000μs/beat)
        for track in midi_file.tracks:
            abs_track_time = 0
            for msg in track:
                abs_track_time += msg.time
                if msg.type == 'set_tempo':
                    tempo_map.append((abs_track_time, msg.tempo))
        tempo_map.sort(key=lambda x: x[0])
        for tick, tempo in tempo_map:
            if tick <= start_tick:
                current_tempo = tempo
            else:
                break
        return current_tempo

    def interpolate_cc2_with_even_ticks(self, track, start_tick, end_tick, end_tick_max, peak_tick, start_expression, peak_expression, end_expression):
        # 指定されたTick範囲でCC2の値を補間
        # 範囲内の既存のCC2イベントを削除し、新しいものを挿入

        events = []
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            events.append({'time': abs_time, 'msg': msg})
        # 既存のCC2イベントを削除
        filtered_events = [event for event in events if not (start_tick <= event['time'] <= end_tick_max and event['msg'].type == 'control_change' and event['msg'].control == 2)]
        cc_events = {} # TickとCC2値の辞書、同じTickに複数の値がある場合は上書きされる
        
        # 上昇部分の計算（start_tick から peak_tick まで）
        if peak_tick >= start_tick:
            rise_duration = peak_tick - start_tick
            for i in range(rise_duration + 1):
                tick = start_tick + i
                if rise_duration > 0:
                    value = start_expression + (peak_expression - start_expression) * i / rise_duration
                else: # start_tick == peak_tick
                    value = peak_expression
                cc_events[tick] = int(value)

        # 下降部分の計算（peak_tick から end_tick_max まで）
        if end_tick_max >= peak_tick:
            fall_duration = end_tick_max - peak_tick
            for i in range(fall_duration + 1):
                tick = peak_tick + i
                if fall_duration > 0:
                    value = peak_expression + (end_expression - peak_expression) * i / fall_duration
                else: # peak_tick == end_tick_max
                    value = end_expression
                cc_events[tick] = int(value) # 既に設定されている場合は上書き
        
        # cc2の挿入
        new_cc_messages = [{'time': tick, 'msg': Message('control_change', control=2, value=value, time=0)} for tick, value in sorted(cc_events.items())]

        # 既存イベントと新しいcc2イベントを統合し、並び替え
        all_events = sorted(filtered_events + new_cc_messages, key=lambda x: x['time'])

        # MIDIトラックを更新
        updated_track = MidiTrack()
        last_time = 0
        for event in all_events:
            delta_time = event['time'] - last_time
            msg = event['msg'].copy(time=int(max(0, delta_time)))
            updated_track.append(msg)
            last_time = event['time']
        track.clear()
        track.extend(updated_track)

    def adjust_velocity_based_on_expression(self, track):
        # 指定されたトラックのNote OnイベントのVelocityを、最も近いCC2イベントの値に基づいて調整する
        expression_events_map = {} # {abs_time: cc2_value}で保存
        abs_time_counter = 0

        for msg in track:
            abs_time_counter += msg.time
            if msg.type == 'control_change' and msg.control == 2:
                expression_events_map[abs_time_counter] = msg.value
        if not expression_events_map:
            return
        sorted_expression_ticks = sorted(expression_events_map.keys())
        # トラックを再構築するためにイベントリストを作成
        reconstructed_messages = []
        current_abs_time = 0
        for msg in track:
            current_abs_time += msg.time
            if msg.type == 'note_on' and msg.velocity > 0: # Velocity = 0 はノートオフとして扱う可能性があるため
                # 現在のNote Onのイベントの時間に最も近いcc2イベントを探す
                closest_tick = None
                for t in sorted_expression_ticks:
                    if t <= current_abs_time:
                        closest_tick = t
                    else:
                        break
                if closest_tick is not None:
                    msg = msg.copy(velocity=expression_events_map[closest_tick])
                elif sorted_expression_ticks:
                    msg = msg.copy(velocity=expression_events_map[sorted_expression_ticks[0]])    
            reconstructed_messages.append(msg)
        track.clear()
        track.extend(reconstructed_messages)
        print("Velocity を最も近い CC2 の値に更新しました。")

    def adjust_onset_times(self, track, start_tick, end_tick_max, onset_ms):
        # 指定されたフレーズ範囲の発音時刻を調整する（フレーズ範囲外は元の発音時刻を維持）

        if not self.mido_midi_file: 
            messagebox.showwarning("エラー", "MIDIファイルが読み込まれていません。")
            return
        
        ticks_per_beat = self.mido_midi_file.ticks_per_beat
        if ticks_per_beat == 0:
            print("ticks_per_beat が0です。MIDIファイルの読み込みに問題がある可能性があります。") 
            return
        
        # 1. 初期テンポを取得し、Tickあたりのミリ秒数を計算
        initial_tempo_microseconds = self.get_base_tempo(self.mido_midi_file, 0)
        if initial_tempo_microseconds == 0: 
            print("初期テンポが0です。無効なテンポ設定です。")
            return
        
        original_ms_per_tick = (initial_tempo_microseconds / ticks_per_beat) / 1000.0
        if original_ms_per_tick == 0:
            print("初期テンポのTickあたりのミリ秒数が0です。無効なテンポ設定です。")
            return
        
        # 2. トラック内のイベントを絶対Tickで取得
        original_abs_events = [] # (abs_tick, msg) のリスト
        current_abs_tick_original = 0
        for msg in track:
            current_abs_tick_original += msg.time
            original_abs_events.append((current_abs_tick_original, msg))
        
        # 3. フレーズ範囲内の拍数を計算し、onset_msを加算
        total_phrase_shift_ms = 0.0
        # start_tick から end_tick_max までの拍数を計算し、onset_msを加算
        current_beat_for_shift_calc = (start_tick // ticks_per_beat) * ticks_per_beat
        if current_beat_for_shift_calc < start_tick:
            current_beat_for_shift_calc += ticks_per_beat

        while current_beat_for_shift_calc <= end_tick_max:
            total_phrase_shift_ms += onset_ms
            current_beat_for_shift_calc += ticks_per_beat
        
        total_shift_ticks_for_post_phrase = round(total_phrase_shift_ms / original_ms_per_tick)
        
        # 4. 新しいトラックを作成し、各イベントのTickを調整
        new_track = MidiTrack()
        last_abs_tick_adjusted = 0

        for original_abs_tick, msg in original_abs_events:
            new_abs_tick_for_event = original_abs_tick

            if start_tick <= original_abs_tick <= end_tick_max:
                # フレーズ範囲内：フレーズ開始からの拍数に基づいてonset_msを加算
                # イベントがフレーズ内で何拍目にあたるかを計算
                beats_into_phrase = (original_abs_tick - start_tick) / ticks_per_beat
                shift_ms_for_this_event = beats_into_phrase * onset_ms
                shift_ticks_for_this_event = round(shift_ms_for_this_event / original_ms_per_tick)
                new_abs_tick_for_event = original_abs_tick + shift_ticks_for_this_event
            elif original_abs_tick > end_tick_max:
                # フレーズ終了後：フレーズ全体のずれを加算(遅らせる)
                new_abs_tick_for_event = original_abs_tick + total_shift_ticks_for_post_phrase

            # 新しいトラックのデルタタイムを計算    
            delta_time = new_abs_tick_for_event - last_abs_tick_adjusted
            if delta_time < 0:
                # 負のデルタタイムは無視
                delta_time = 0
            
            new_msg = msg.copy(time=int(max(0, delta_time)))
            new_track.append(new_msg)
            last_abs_tick_adjusted = new_abs_tick_for_event
        
        # トラックを更新
        track.clear()
        track.extend(new_track)
        print(f"トラック '{getattr(track, 'name', '')}' の発音時刻の調整が完了しました。")

    def write_midi(self, output_file_path, midi_file_obj):
        # MIDIファイルを指定されたパスに保存
        midi_file_obj.save(output_file_path)
        print(f"MIDIファイルを {output_file_path} に保存しました:")

    def apply_changes(self):
        # 両方のファイルが読み込まれているかチェック
        if not self.mido_midi_file or not self.full_score or self.selected_mido_track_index == -1:
            messagebox.showwarning("警告", "楽譜ファイルとMIDIファイルを両方読み込み、パートを選択してください。")
            return
        
        try:
            start_measure = int(self.start_measure_entry.get())
            start_beat = float(self.start_beat_entry.get())
            end_measure = int(self.end_measure_entry.get())
            end_beat = float(self.end_beat_entry.get())
            peak_measure = int(self.peak_measure_entry.get())
            peak_beat = float(self.peak_beat_entry.get())
            
            # 発想標語と形容詞の選択
            selected_tempo_preset_name = self.tempo_preset_var.get()
            selected_adjective_preset_name = self.adjective_preset_var.get()

            # 発想標語のCC2値調整とテンポの変化量を取得
            tempo_preset_data = self.tempo_expressions.get(selected_tempo_preset_name, {})

            # 形容詞のCC2値調整とテンпоの変化量を取得
            adjective_preset_data = self.adjective_expressions.get(selected_adjective_preset_name, {})

            # 合計のbase_cc2、peak_cc2、onset_msの変化量
            combined_base_cc2 = tempo_preset_data.get("base_cc2", 0) + adjective_preset_data.get("base_cc2", 0)
            combined_peak_cc2 = tempo_preset_data.get("peak_cc2", 0) + adjective_preset_data.get("peak_cc2", 0)
            combined_onset_ms_change = tempo_preset_data.get("onset_ms", 0) + adjective_preset_data.get("onset_ms", 0)
            
            time_signature = self.get_time_signature(self.mido_midi_file)
            ticks_per_beat = self.mido_midi_file.ticks_per_beat
            
            # 発音時刻調整のために、全てのトラックを対象とする前に、選択トラックを特定
            selected_track_for_velocity_cc2 = self.mido_midi_file.tracks[self.selected_mido_track_index]

            start_tick = self.get_tick(self.mido_midi_file, start_measure, start_beat, ticks_per_beat, time_signature)
            end_tick = self.get_tick(self.mido_midi_file, end_measure, end_beat, ticks_per_beat, time_signature)
            end_tick_max = self.get_max_tick_in_beat(self.mido_midi_file, end_measure, end_beat, ticks_per_beat, time_signature)
            peak_tick = self.get_tick(self.mido_midi_file, peak_measure, peak_beat, ticks_per_beat, time_signature)
            
            if not (start_tick <= peak_tick <= end_tick_max): 
                messagebox.showerror("入力エラー", f"頂点拍は開始拍と終了拍の間にある必要があります。")
                return

            # 元のCC2値を取得
            original_expression = self.get_base_cc2_value(selected_track_for_velocity_cc2, start_tick, end_tick_max)
            
            # CC2の補間
            # 開始と終了のCC2値は、元のCC2値にcombined_base_cc2を加算
            start_expression = max(0, min(127, int(original_expression + combined_base_cc2)))
            end_expression = max(0, min(127, int(original_expression + combined_base_cc2)))
            
            # 頂点のCC2値は、元のCC2値にcombined_peak_cc2を加算
            peak_expression = max(0, min(127, int(original_expression + combined_peak_cc2)))
            
            # 選択されたパートのみにCC2補間とVelocity調整を適用
            self.interpolate_cc2_with_even_ticks(selected_track_for_velocity_cc2, start_tick, end_tick, end_tick_max, peak_tick, start_expression, peak_expression, end_expression)
            self.adjust_velocity_based_on_expression(selected_track_for_velocity_cc2)

            # 全てのトラックに対して発音時刻(Onset)の調整を適用
            for i, track in enumerate(self.mido_midi_file.tracks):
                # CC2値とVelocityの調整を行ったパート以外にも発音時刻調整を適用
                self.adjust_onset_times(track, start_tick, end_tick_max, combined_onset_ms_change)
            
            messagebox.showinfo("完了",
                                f"指定範囲にExpression(CC2)補間と発音時刻調整を適用しました。\n"
                                f"開始Expression(cc2): {start_expression}, 頂点Expression(CC2): {peak_expression}, 終了Expression(CC2): {end_expression}。\n"
                                f"発音時刻は1拍あたり {combined_onset_ms_change}ms 調整されました。\n"
                                f"Velocityを更新しました。")

        except ValueError:
            messagebox.showerror("入力エラー", "小節、拍は有効な数字を入力してください。")
        except Exception as e:
            messagebox.showerror("エラー", f"Expression(CC2)/発音時刻設定中にエラーが発生しました: {e}")

    def get_numbered_filename(self, base_name, extension=".mid", output_dir=""):
        # ファイル名を重複しないように連番にする
        i = 1
        while True:
            numbered_filename = f"{base_name}_{i:02d}{extension}"
            full_path = os.path.join(os.getcwd(), output_dir, numbered_filename)
            if not os.path.exists(full_path):
                return numbered_filename
            i += 1

    def save_score(self):
        # 現在のMIDIファイルを保存
        if self.mido_midi_file and self.selected_mido_track_index != -1:
            # 1. 加工されたパートのみのMIDIファイルを保存
            os.makedirs(os.path.join(os.getcwd(), output_single_part_midi), exist_ok=True)
            single_part_midi = MidiFile()
            single_part_midi.ticks_per_beat = self.mido_midi_file.ticks_per_beat
            single_part_midi.type = self.mido_midi_file.type # MIDIタイプもコピー
            single_part_midi.tracks.append(self.mido_midi_file.tracks[self.selected_mido_track_index])

            part_name = self.part_listbox.get(self.selected_mido_track_index)
            safe_part_name = "".join(c if c.isalnum() else "_" for c in part_name)
            
            # ファイル名形式: 曲名_パート名_連番.mid
            single_part_base_filename = f"{self.current_base_name}_{safe_part_name}"
            
            single_part_output_midi_filename = self.get_numbered_filename(single_part_base_filename, output_dir=output_single_part_midi)
            single_part_output_midi_path = os.path.join(os.getcwd(), output_single_part_midi, single_part_output_midi_filename)

            try:
                self.write_midi(single_part_output_midi_path, single_part_midi)
                messagebox.showinfo("保存完了", f"加工されたパートのみのMIDIファイルを保存しました: {single_part_output_midi_path}")
            except Exception as e:
                messagebox.showerror("保存エラー", f"加工されたパートのみのMIDIファイルの保存に失敗しました: {e}")

            # 2. 加工されたパートを含む元のMIDIファイル全体を保存
            os.makedirs(os.path.join(os.getcwd(), output_midi), exist_ok=True)
            
            # ファイル名形式: 曲名_full_連番.mid
            full_midi_base_filename = f"{self.current_base_name}_full"
            
            full_midi_output_midi_filename = self.get_numbered_filename(full_midi_base_filename, output_dir=output_midi)
            full_midi_output_midi_path = os.path.join(os.getcwd(), output_midi, full_midi_output_midi_filename)

            try:
                self.write_midi(full_midi_output_midi_path, self.mido_midi_file)
                messagebox.showinfo("保存完了", f"加工されたパートを含む全体のMIDIファイルを保存しました: {full_midi_output_midi_path}")
            except Exception as e:
                messagebox.showerror("保存エラー", f"全体のMIDIファイルの保存に失敗しました: {e}")
        else:
            messagebox.showwarning("警告", "保存するデータがありません。")

if __name__ == "__main__":
    root = tk.Tk()
    app = MusicProcessorApp(root)
    root.mainloop()