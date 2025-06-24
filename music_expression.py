import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

import mido
from mido import MidiFile, MidiTrack, Message

# ---------------- ユーザー設定 ----------------
# 出力ディレクトリ名
output_png = "output(png)"
output_xml = "output(xml)"
output_ly = "output(ly)"

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
        self.current_midi_path = None 
        self.current_base_name = None 
        self.tk_image = None 
        self.mido_midi_file = None 
        self.selected_mido_track_index = -1 

        # 発想標語と対応するExpression値のプリセット
        self.tempo_expressions = {
            "Marcato": 90,
            "Cantabile": 65,
            "Espressivo": 70,
            "Con fuoco": 100,
            "Dolce": 50,
        }

        # 形容詞と対応するExpression値のプリセット
        self.adjective_expressions = {
            "なし": 0,
            "明るい": 10,
            "華やか": 15,
            "壮大": 20,
            "暗い": -10,
            "穏やか": -5,
            "激しい": 25,
        }

        self.create_widgets() 
        self.check_lilypond_setup() 

    def check_lilypond_setup(self):
        """LilyPond実行ファイル、musicxml2ly.pyスクリプトが存在するかを確認"""
        if not os.path.exists(lilypond_exe):
            messagebox.showwarning("設定エラー", f"LilyPond実行ファイルが見つかりません。設定を確認してください: {lilypond_exe}")
            return False
        if not os.path.exists(xml2ly_script):
            messagebox.showwarning("設定エラー", f"musicxml2ly.pyスクリプトが見つかりません。設定を確認してください: {xml2ly_script}")
            return False
        return True

    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.pack(fill="both", expand=True)

        # 左パネル (MIDIファイル、パートリスト)
        left_panel = ttk.Frame(main_frame, width=200, relief="groove", borderwidth=2)
        left_panel.pack(side="left", fill="y", padx=10, pady=10)
        left_panel.pack_propagate(False) # フレームが縮むのを防ぐ

        # MIDIファイル読み込み
        midi_frame = ttk.LabelFrame(left_panel, text="MIDIファイルの読み込み", padding="10")
        midi_frame.pack(fill="x", pady=10)
        
        open_button = ttk.Button(midi_frame, text="開く", command=self.select_midi_file)
        open_button.pack(fill="x")

        # パートリストセクション
        part_list_frame = ttk.LabelFrame(left_panel, text="パートのリスト (選択する)", padding="10")
        part_list_frame.pack(fill="both", expand=True, pady=10)

        self.part_listbox = tk.Listbox(part_list_frame, selectmode=tk.SINGLE, height=15)
        self.part_listbox.pack(side="left", fill="both", expand=True)
        self.part_listbox.bind("<<ListboxSelect>>", self.on_part_selected)

        part_scrollbar = ttk.Scrollbar(part_list_frame, orient="vertical", command=self.part_listbox.yview)
        part_scrollbar.pack(side="right", fill="y")
        self.part_listbox.config(yscrollcommand=part_scrollbar.set)

        # 中央パネル (楽譜表示)
        center_panel = ttk.Frame(main_frame, relief="groove", borderwidth=2)
        center_panel.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        self.score_canvas = tk.Canvas(center_panel, bg="white", highlightbackground="gray", highlightthickness=1)
        self.score_canvas.pack(fill="both", expand=True)

        # 右パネル (Expression、形容詞、ボタン、フレーズ設定)
        right_panel = ttk.Frame(main_frame, width=300, relief="groove", borderwidth=2)
        right_panel.pack(side="right", fill="y", padx=10, pady=10)
        right_panel.pack_propagate(False) # フレームが縮むのを防ぐ

        # フレーズ設定
        phrase_setting_frame = ttk.LabelFrame(right_panel, text="フレーズ設定", padding="10")
        phrase_setting_frame.pack(fill="x", pady=10)

        ttk.Label(phrase_setting_frame, text="開始小節:").grid(row=0, column=0, sticky="w", pady=2)
        self.start_measure_entry = ttk.Entry(phrase_setting_frame)
        self.start_measure_entry.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(phrase_setting_frame, text="開始拍:").grid(row=1, column=0, sticky="w", pady=2)
        self.start_beat_entry = ttk.Entry(phrase_setting_frame)
        self.start_beat_entry.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(phrase_setting_frame, text="終了小節:").grid(row=2, column=0, sticky="w", pady=2)
        self.end_measure_entry = ttk.Entry(phrase_setting_frame)
        self.end_measure_entry.grid(row=2, column=1, sticky="ew", pady=2)

        ttk.Label(phrase_setting_frame, text="終了拍:").grid(row=3, column=0, sticky="w", pady=2)
        self.end_beat_entry = ttk.Entry(phrase_setting_frame)
        self.end_beat_entry.grid(row=3, column=1, sticky="ew", pady=2)
        
        # 発想標語プリセットのドロップダウンメニュー
        ttk.Label(phrase_setting_frame, text="発想標語プリセット:").grid(row=4, column=0, sticky="w", pady=2)
        self.tempo_preset_var = tk.StringVar(self.master)
        self.tempo_preset_var.set(list(self.tempo_expressions.keys())[3]) # 初期値: Moderato
        self.tempo_preset_menu = ttk.OptionMenu(phrase_setting_frame, self.tempo_preset_var,
                                                 list(self.tempo_expressions.keys())[3],
                                                 *self.tempo_expressions.keys())
        self.tempo_preset_menu.grid(row=4, column=1, sticky="ew", pady=2)

        # 形容詞プリセットのドロップダウンメニュー
        ttk.Label(phrase_setting_frame, text="形容詞プリセット:").grid(row=5, column=0, sticky="w", pady=2)
        self.adjective_preset_var = tk.StringVar(self.master)
        self.adjective_preset_var.set(list(self.adjective_expressions.keys())[0]) # 初期値: なし
        self.adjective_preset_menu = ttk.OptionMenu(phrase_setting_frame, self.adjective_preset_var,
                                                     list(self.adjective_expressions.keys())[0],
                                                     *self.adjective_expressions.keys())
        self.adjective_preset_menu.grid(row=5, column=1, sticky="ew", pady=2)

        # ボタン
        button_frame = ttk.Frame(right_panel, padding="10")
        button_frame.pack(fill="x", pady=20)

        apply_button = ttk.Button(button_frame, text="適用", command=self.apply_changes)
        apply_button.pack(fill="x", pady=5)

        play_button = ttk.Button(button_frame, text="再生", command=self.play_score)
        play_button.pack(fill="x", pady=5)

        save_button = ttk.Button(button_frame, text="保存", command=self.save_score)
        save_button.pack(fill="x", pady=5)

    def select_midi_file(self):
        """ユーザーにMIDIファイルを選択させるファイルダイアログを開きます。"""
        file_path = filedialog.askopenfilename(
            title="MIDIファイルを選択してください",
            filetypes=[("MIDI files", "*.mid *.midi")]
        )
        if file_path:
            self.current_midi_path = file_path
            self.current_base_name = os.path.splitext(os.path.basename(file_path))[0]
            self.load_midi_and_populate_parts(file_path)
            # MIDIファイルを読み込む
            try:
                self.mido_midi_file = self.load_midi(file_path)
            except Exception as e:
                messagebox.showerror("エラー", f"MidoでのMIDIファイルの読み込みに失敗しました: {e}")
                self.mido_midi_file = None

    def load_midi_and_populate_parts(self, midi_path):
        """MIDIファイルを読み込み、パートリストにデータを入力"""
        try:
            from music21 import converter, midi, stream # music21はここでインポート
            self.full_score = converter.parse(midi_path)
            self.part_listbox.delete(0, tk.END) # 既存のリストをクリア
            if not self.full_score.parts:
                messagebox.showinfo("情報", "このMIDIファイルにはパートが見つかりませんでした。")
                return

            for i, part in enumerate(self.full_score.parts):
                part_name = part.partName if part.partName else f"Part {i+1}"
                self.part_listbox.insert(tk.END, part_name)
            messagebox.showinfo("読み込み完了", "MIDIファイルを読み込みました。パートを選択してください。")
        except Exception as e:
            messagebox.showerror("エラー", f"MIDIファイルの解析に失敗しました: {e}")
            self.full_score = None

    def on_part_selected(self, event):
        """リストボックスからのパート選択"""
        if not self.full_score:
            return

        selected_indices = self.part_listbox.curselection()
        if not selected_indices:
            return

        idx = selected_indices[0]
        self.selected_mido_track_index = idx # mido操作のためにインデックスを保存
        
        # music21で表示用のパートを処理
        from music21 import stream
        selected_part = self.full_score.parts[idx]
        part_name = self.part_listbox.get(idx)

        self.process_and_display_part(selected_part, part_name)

    def process_and_display_part(self, selected_part_obj, display_name):
        """
        選択されたパートを処理し（MusicXML、LilyPond、PNGに変換）、
        PNGをGUIに表示
        """
        if not self.check_lilypond_setup():
            return
        
        from music21 import stream 
        # 選択されたパートのみを含む新しい楽譜を作成
        new_score = stream.Score()
        new_score.insert(0, selected_part_obj)
        new_score.metadata = self.full_score.metadata # メタデータをコピー

        # 出力ファイル名の生成
        safe_part_suffix = "".join(c if c.isalnum() else "_" for c in display_name)
        output_base_name = f"{self.current_base_name}_{safe_part_suffix}"
        
        output_xml_path = os.path.join(os.getcwd(), output_xml, output_base_name + ".xml")
        output_ly_path = os.path.join(os.getcwd(), output_ly, output_base_name + ".ly")
        output_png_dir = os.path.join(os.getcwd(), output_png) # LilyPondはこのディレクトリにPNGを生成

        os.makedirs(os.path.join(os.getcwd(), output_xml), exist_ok=True)
        os.makedirs(os.path.join(os.getcwd(), output_ly), exist_ok=True)
        os.makedirs(output_png_dir, exist_ok=True)

        try:
            # 1. midi -> MusicXML
            print(f"パート '{display_name}' をMusicXMLに変換しています")
            new_score.write("musicxml", fp=output_xml_path)
            print(f"✓ MusicXML書き込み完了: {output_xml_path}")

            # 2. MusicXML -> LilyPond (.ly)
            print(f"MusicXMLをLilyPond (.ly) に変換しています")
            if os.path.exists(output_ly_path):
                os.remove(output_ly_path)

            python_command = [python_exe or "python", xml2ly_script, output_xml_path, "-o", output_ly_path]
            subprocess.run(python_command, capture_output=True, text=True, check=True, encoding="utf-8")

            if not os.path.exists(output_ly_path) or os.path.getsize(output_ly_path) == 0:
                raise RuntimeError(".lyファイルが作成されなかった、または空です。")
            print(f"✓ LilyPond (.ly) 書き込み完了: {output_ly_path}")

            # 3. LilyPond (.ly) -> PNG
            print(f"LilyPondファイルからPNGを生成しています")
            subprocess.run([
                lilypond_exe,
                "--png",
                "--output", output_png_dir, 
                output_ly_path
            ], capture_output=True, text=True, check=True, encoding="utf-8")

            # 生成されたPNGファイルを探す
            generated_png_path = None
            for file in os.listdir(output_png_dir):
                if file.startswith(output_base_name) and file.endswith(".png"):
                    generated_png_path = os.path.join(output_png_dir, file)
                    break
            
            if generated_png_path:
                self.display_png_on_canvas(generated_png_path)
                messagebox.showinfo("完了", f"パート '{display_name}' の楽譜を生成し、表示しました。")
            else:
                messagebox.showerror("エラー", f"PNG画像が見つかりませんでした: {output_base_name}*.png")

        except subprocess.CalledProcessError as e:
            messagebox.showerror("変換エラー", f"変換中にエラーが発生しました:\n{e.stderr}")
        except Exception as e:
            messagebox.showerror("エラー", f"楽譜の処理中に予期せぬエラーが発生しました: {e}")

    def display_png_on_canvas(self, image_path):
        """指定されたPNG画像をscore_canvasに表示"""
        try:
            img = Image.open(image_path)
            
            # アスペクト比を維持しながらキャンバスに合わせて画像をリサイズ
            canvas_width = self.score_canvas.winfo_width()
            canvas_height = self.score_canvas.winfo_height()

            if canvas_width == 1 and canvas_height == 1: # レイアウトがまだ管理されていない場合のデフォルトサイズ
                # デフォルトサイズ
                canvas_width = 800
                canvas_height = 600

            img_width, img_height = img.size
            
            aspect_ratio = img_width / img_height
            
            if img_width > canvas_width or img_height > canvas_height:
                if (canvas_width / canvas_height) > aspect_ratio:
                    # キャンバスが画像より幅広の場合、高さに合わせてリサイズ
                    new_height = canvas_height
                    new_width = int(new_height * aspect_ratio)
                else:
                    # キャンバスが画像より縦長または同じアスペクト比の場合、幅に合わせてリサイズ
                    new_width = canvas_width
                    new_height = int(new_width / aspect_ratio)
                img = img.resize((new_width, new_height), Image.LANCZOS)
            
            self.tk_image = ImageTk.PhotoImage(img)
            self.score_canvas.delete("all") # 以前の画像をクリア
            self.score_canvas.create_image(canvas_width / 2, canvas_height / 2, image=self.tk_image, anchor="center")
            self.score_canvas.config(scrollregion=self.score_canvas.bbox(tk.ALL)) # 必要に応じてスクロール可能にする

        except Exception as e:
            messagebox.showerror("画像表示エラー", f"画像の表示に失敗しました: {e}")

    # --- Mido連携機能 ---

    def load_midi(self, filename):
        """midoを使用してMIDIファイルを読み込む"""
        return MidiFile(filename)

    def get_time_signature(self, midi_file):
        """mido MidiFileから拍子記号を取得"""
        for track in midi_file.tracks:
            abs_time = 0
            for msg in track:
                abs_time += msg.time
                if msg.type == 'time_signature':
                    return msg
        return mido.MetaMessage('time_signature', numerator=4, denominator=4) # デフォルトで4/4拍子

    def get_tick(self, midi_file, measure, beat, ticks_per_beat, time_signature):
        """小節、拍、拍子記号からティックを計算"""
        ticks_per_measure = ticks_per_beat * time_signature.numerator
        tick = (measure - 1) * ticks_per_measure + round((beat - 1) * ticks_per_beat)
        return tick

    def set_expression_in_range(self, track, start_tick, end_tick, expression_value):
        """
        指定されたティック範囲内のExpression (CC11) 値を設定
        範囲内の既存のExpressionイベントを削除し、新しいものを挿入
        """
        events = []
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            events.append({'time': abs_time, 'msg': msg})

        # 範囲内の既存のExpressionイベントを除外
        filtered_events = [
            event for event in events
            if not (start_tick < event['time'] <= end_tick and # start_tickより後かつend_tickまでのCC11を削除
                    event['msg'].type == 'control_change' and event['msg'].control == 11)
        ]

        # start_tickに新しいExpressionイベントを追加または更新
        found_start_expression = False
        for event in filtered_events:
            if event['time'] == start_tick and event['msg'].type == 'control_change' and event['msg'].control == 11:
                event['msg'].value = int(expression_value)
                found_start_expression = True
                break
        
        if not found_start_expression:
            filtered_events.append({'time': start_tick, 'msg': Message('control_change', control=11, value=int(expression_value), time=0)})

        filtered_events.sort(key=lambda x: x['time'])

        # トラックを再構築
        updated_track = MidiTrack()
        last_time = 0
        for event in filtered_events:
            delta_time = event['time'] - last_time

            if delta_time < 0:
                delta_time = 0 
            msg = event['msg'].copy()
            msg.time = int(delta_time)
            updated_track.append(msg)
            last_time = event['time']

        track.clear()
        track.extend(updated_track)

    def adjust_velocity_based_on_expression(self, track):
        """
        ノートオンイベントのベロシティを、最も近いExpression値に基づいて更新します。
        """
        note_on_events = []
        expression_events = {}

        abs_time = 0
        for msg in track:
            abs_time += msg.time
            if msg.type == 'note_on' and msg.velocity > 1:
                note_on_events.append({'time': abs_time, 'msg': msg})
            elif msg.type == 'control_change' and msg.control == 11:
                expression_events[abs_time] = msg.value

        if not expression_events:
            print("Expression イベントが見つかりません。Velocity の調整は行いません。")
            return

        sorted_ticks = sorted(expression_events.keys())
        for event in note_on_events:
            note_tick = event['time']
            # 最も近い、または先行するExpressionイベントを見つける
            closest_tick = None
            for t in sorted_ticks:
                if t <= note_tick:
                    closest_tick = t
                else:
                    break
            
            if closest_tick is not None:
                # Expression値をベロシティとして直接設定する
                event['msg'].velocity = expression_events[closest_tick]
            elif sorted_ticks: # 先行するExpressionイベントがない場合、最初のExpressionイベントを使用
                event['msg'].velocity = expression_events[sorted_ticks[0]]

        print("Velocity を最も近い Expression の値に更新しました。")

    def write_midi(self, output_file_path, midi_file_obj):
        """変更されたMIDIファイルを保存します。"""
        midi_file_obj.save(output_file_path)
        print(f"MIDIファイルを保存しました: {output_file_path}")

    # --- ボタンコールバック ---
    def apply_changes(self):
        """選択されたMIDIトラックにExpression設定とベロシティ調整を適用"""
        if not self.mido_midi_file or self.selected_mido_track_index == -1:
            messagebox.showwarning("警告", "まずMIDIファイルを読み込み、パートを選択してください。")
            return

        try:
            start_measure = int(self.start_measure_entry.get())
            start_beat = float(self.start_beat_entry.get())
            end_measure = int(self.end_measure_entry.get())
            end_beat = float(self.end_beat_entry.get())
            
            # 発想標語のExpression値を取得
            selected_tempo_preset_name = self.tempo_preset_var.get()
            tempo_expression_value = self.tempo_expressions[selected_tempo_preset_name]

            # 形容詞のExpression値を取得
            selected_adjective_preset_name = self.adjective_preset_var.get()
            adjective_expression_value = self.adjective_expressions[selected_adjective_preset_name]
            
            # 発想標語と形容詞の値を合計し、0-127の範囲にクランプ
            combined_expression_value = tempo_expression_value + adjective_expression_value
            final_expression_value = max(0, min(127, combined_expression_value))

            time_signature = self.get_time_signature(self.mido_midi_file)
            ticks_per_beat = self.mido_midi_file.ticks_per_beat
            selected_track = self.mido_midi_file.tracks[self.selected_mido_track_index]

            start_tick = self.get_tick(self.mido_midi_file, start_measure, start_beat, ticks_per_beat, time_signature)
            end_tick = self.get_tick(self.mido_midi_file, end_measure, end_beat, ticks_per_beat, time_signature)
            
            if not (start_tick <= end_tick):
                messagebox.showerror("入力エラー", "開始拍は終了拍よりも小さいか同じである必要があります。")
                return

            self.set_expression_in_range(selected_track, start_tick, end_tick, final_expression_value)
            self.adjust_velocity_based_on_expression(selected_track)
            
            messagebox.showinfo("完了", 
                                f"指定範囲に発想標語 '{selected_tempo_preset_name}' と 形容詞 '{selected_adjective_preset_name}' を適用しました。\n"
                                f"最終Expression値: {final_expression_value}。\n"
                                f"Velocityを更新しました。")

        except ValueError:
            messagebox.showerror("入力エラー", "小節、拍は有効な数字を入力してください。")
        except Exception as e:
            messagebox.showerror("エラー", f"Expression設定中にエラーが発生しました: {e}")

    def play_score(self):
        """現在の楽譜を再生します（変更されたMIDIを保存し、外部再生を促します）。"""
        if self.mido_midi_file and self.selected_mido_track_index != -1:
            output_midi_path = f"250221_03expression_output_part_{self.selected_mido_track_index}.mid"
            try:
                self.write_midi(output_midi_path, self.mido_midi_file)
                messagebox.showinfo("再生", f"MIDIファイルを保存しました: {output_midi_path}\n（再生機能はシステムに依存します）")
            except Exception as e:
                messagebox.showerror("再生エラー", f"MIDIファイルの保存または再生に失敗しました: {e}")
        else:
            messagebox.showwarning("警告", "再生するMIDIファイルがありません。")

    def save_score(self):
        """変更されたMIDIファイルの現在の状態を保存します。"""
        if self.mido_midi_file and self.selected_mido_track_index != -1:
            default_filename = f"{self.current_base_name}_modified_part_{self.selected_mido_track_index}.mid"
            output_file_path = filedialog.asksaveasfilename(
                defaultextension=".mid",
                filetypes=[("MIDI files", "*.mid")],
                initialfile=default_filename
            )
            if output_file_path:
                try:
                    self.write_midi(output_file_path, self.mido_midi_file)
                    messagebox.showinfo("保存完了", f"MIDIファイルを保存しました: {output_file_path}")
                except Exception as e:
                    messagebox.showerror("保存エラー", f"MIDIファイルの保存に失敗しました: {e}")
        else:
            messagebox.showwarning("警告", "保存するデータがありません。")

if __name__ == "__main__":
    root = tk.Tk()
    app = MusicProcessorApp(root)
    root.mainloop()