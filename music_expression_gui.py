import sys
import os # osモジュールも必要なので追加
import traceback # エラーの詳細な表示のためにインポート

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QComboBox, QFileDialog,
    QTextEdit, QMessageBox, QTabWidget
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QSize

# MIDI処理と楽譜表示のためのダミー/基本的なライブラリ
import mido
from music21 import converter, stream, midi, note, duration, environment # music21は楽譜表示の補助として使用

try:
    lilypondPath = r'C:\Users\momoka\Downloads\lilypond-2.24.4-mingw-x86_64\lilypond-2.24.4\bin\lilypond.exe'
    environment.set('lilypondPath', lilypondPath)
    print(f"music21のLilyPondパスを設定しました: {lilypondPath}")
except Exception as e:
    print(f"LilyPondのパス設定に失敗しました: {e}")
    QMessageBox.critical(None, "設定エラー", f"LilyPondのパス設定に失敗しました: {e}\nLilyPondが正しくインストールされ、パスが設定されているか確認してください。")

# --- システム内部処理のダミー関数 ---

def load_midi_file(file_path):
    """
    1. MIDIファイルの読み込み
    2. パート情報を抽出、リストで表示
    """
    print(f"MIDIファイルを読み込み中: {file_path}")
    try:
        mid = mido.MidiFile(file_path)
        tracks = []
        for i, track in enumerate(mid.tracks):
            tracks.append(f"Part {i+1}: {track.name if track.name else 'Unnamed'}")
        print("パート情報抽出完了")
        return mid, tracks
    except Exception as e:
        QMessageBox.critical(None, "エラー", f"MIDIファイルの読み込みに失敗しました: {e}")
        return None, []

def display_score_for_part(midi_file_path, part_index):
    """
    2. 選択されたパートの楽譜（五線譜）を画面に表示
    MusicXMLとして書き出し、LilyPondでPNGに変換して表示
    """
    if not midi_file_path:
        return "楽譜データを表示できません。\nMIDIファイルを読み込んでください。"

    try:
        # music21でMIDIデータを解析
        score = converter.parse(midi_file_path)
        
        selected_part_stream = None
        if 0 <= part_index < len(score.parts):
            selected_part_stream = score.parts[part_index]
            print(f"music21でパート {part_index} の楽譜を取得しました")
        else:
            print(f"指定されたパート {part_index} は存在しません。スコア全体を対象とします。")
            selected_part_stream = score # パートが存在しない場合はスコア全体を対象とする

        if selected_part_stream is None:
            return "エラー: 処理対象の楽譜データが見つかりません。"

        # 一時MusicXMLファイルのパスを生成 (カレントディレクトリ)
        temp_musicxml_path = os.path.join(os.getcwd(), 'temp_score.musicxml')
        
        # MusicXMLとしてファイルを書き出す（BOM付きUTF-8を指定）
        # これがLilyPondがMusicXMLを正しく読み込むための鍵です
        print(f"MusicXMLファイルを書き出し中: {temp_musicxml_path}")
        selected_part_stream.write('musicxml', fp=temp_musicxml_path, encoding='utf-8') 
        print(f"MusicXMLファイルを生成しました: {temp_musicxml_path}")

        # PNG画像を生成するパス
        score_png_path = os.path.join(os.getcwd(), 'temp_score.png')
        
        # MusicXMLファイルからLilyPondを使ってPNG画像を生成
        # music21が自動的にtemp_musicxml_pathをLilyPondに渡し、PNGとして出力させます
        # write('lilypond.png')は、music21がlilypondPath設定を使ってレンダリングすることを意味します
        print(f"LilyPondを使用してPNG画像を生成中: {score_png_path}")
        fp_result = selected_part_stream.write('lilypond.png', fp=score_png_path)
        
        print(f"PNG生成を試行しました。結果パス: {fp_result}")
        
        # 生成されたPNGファイルが存在するか確認
        if os.path.exists(score_png_path):
            print(f"PNGファイルが存在します: {score_png_path}")
            return score_png_path
        else:
            print(f"エラー: LilyPondはPNGファイルを生成しませんでした: {score_png_path}")
            # LilyPondのエラー出力を確認するために、ここでエラーメッセージを表示する
            # 例えば、temp_score.log ファイルを読み込むなど
            log_path = os.path.splitext(temp_musicxml_path)[0] + '.log'
            lilypond_error_message = ""
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lilypond_error_message = "\nLilyPondログ:\n" + f.read()
            return f"エラー: 楽譜画像生成に失敗しました。LilyPondのエラーを確認してください。{lilypond_error_message}"

    except Exception as e:
        print(f"楽譜の表示に失敗しました: {e}")
        traceback.print_exc() # 詳細なエラー表示
        return f"楽譜の表示に失敗しました: {e}"
        
def get_phrase_info(score_data, start_note_idx, end_note_idx):
    """
    3. フレーズの音符情報、演奏情報を取得 (ダミー)
    """
    print(f"フレーズ情報を取得中: 開始 {start_note_idx}, 終了 {end_note_idx}")
    # 実際には、選択された楽譜上の音符データから詳細な情報を取得
    # 例: ノート番号、ベロシティ、開始時間、長さなど
    dummy_phrase_notes = [f"Note {i+1}" for i in range(start_note_idx, end_note_idx + 1)]
    dummy_performance_info = {"velocity": 64, "tempo": 120}
    return dummy_phrase_notes, dummy_performance_info

def search_preset(expression_type, expression_word):
    """
    4. プリセットの検索
        選択された言葉に対応する演奏パラメータを取得
    """
    print(f"プリセット検索中: {expression_type} - {expression_word}")
    # ダミーのプリセットデータ
    presets = {
        "形容詞": {
            "明るく": {"velocity_change": 20, "tempo_multiplier": 1.1, "articulation": "staccato_slight"},
            "優しく": {"velocity_change": -15, "tempo_multiplier": 0.95, "articulation": "legato"},
            "激しく": {"velocity_change": 30, "tempo_multiplier": 1.2, "articulation": "marcato"},
            "悲しく": {"velocity_change": -25, "tempo_multiplier": 0.9, "articulation": "tenuto"}, # 追加
            "神秘的に": {"velocity_change": -10, "tempo_multiplier": 0.98, "articulation": "soft_pedal"}, # 追加
        },
        "発想標語": {
            "Allegro": {"tempo_multiplier": 1.25, "velocity_change": 10},
            "Andante": {"tempo_multiplier": 0.8, "velocity_change": -5},
            "Moderato": {"tempo_multiplier": 1.0, "velocity_change": 0}, # 追加
            "Dolce": {"velocity_change": -20, "articulation": "legato_smooth"},
            "Cantabile": {"velocity_change": -5, "articulation": "cantabile_expressive"}, # 追加
            "Sostenuto": {"duration_multiplier": 1.1, "articulation": "sustain"}, # 追加
            "Pianissimo": {"velocity_change": -30}, # 追加
            "Fortissimo": {"velocity_change": 30}, # 追加
        }
    }
    return presets.get(expression_type, {}).get(expression_word, None)

def apply_expression_to_notes(midi_data, phrase_notes_info, preset_params):
    """
    5. フレーズに対して、表現プリセットを適用してノート情報を加工する (ダミー)
    """
    print("ノート情報を加工中...")
    processed_midi_data = mido.MidiFile() # 新しいMIDIファイルを作成
    for i, track in enumerate(midi_data.tracks):
        new_track = mido.MidiTrack()
        processed_midi_data.tracks.append(new_track)
        for msg in track:
            new_msg = msg.copy()
            # ダミーとして、フレーズ内のノートのベロシティを調整する
            if msg.type == 'note_on' and 'velocity_change' in preset_params:
                new_msg.velocity = max(0, min(127, msg.velocity + preset_params['velocity_change']))
            elif msg.type == 'set_tempo' and 'tempo_multiplier' in preset_params:
                # テンポ変更はトラック全体に影響を与えるため、簡易的な適用例
                new_tempo = int(msg.tempo / preset_params['tempo_multiplier'])
                new_msg.tempo = new_tempo
            new_track.append(new_msg)
    print("ノート情報加工完了")
    return processed_midi_data

def generate_midi_output(processed_midi_data, output_path="output.mid"):
    """
    6. 音源の生成（MIDI）
    """
    print(f"音源を生成中: {output_path}")
    try:
        processed_midi_data.save(output_path)
        QMessageBox.information(None, "成功", f"加工済みMIDIファイルを保存しました:\n{output_path}")
        return output_path
    except Exception as e:
        QMessageBox.critical(None, "エラー", f"MIDIファイルの保存に失敗しました: {e}")
        return None

# --- GUIクラス ---

class MusicExpressionGenerator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("音楽表現生成システム")
        self.setGeometry(100, 100, 1200, 800) # ウィンドウサイズを調整

        self.midi_data = None
        self.current_midi_path = None
        self.current_part_index = -1
        self.selected_phrase_start = -1 # ダミーの音符インデックス
        self.selected_phrase_end = -1   # ダミーの音符インデックス
        self.processed_midi_output_path = None

        self.init_ui()
        self.enable_controls(False) # 初期状態ではほとんどのコントロールを無効にする

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- 左サイドバー ---
        left_sidebar_layout = QVBoxLayout()
        left_sidebar_layout.setContentsMargins(10, 10, 10, 10)
        left_sidebar_layout.setSpacing(15)

        # MIDIファイル読み込み
        midi_group_label = QLabel("MIDIファイルの読み込み")
        midi_group_label.setStyleSheet("font-weight: bold;")
        left_sidebar_layout.addWidget(midi_group_label)

        self.upload_midi_button = QPushButton("MIDIファイルをアップロード...")
        self.upload_midi_button.clicked.connect(self.upload_midi)
        left_sidebar_layout.addWidget(self.upload_midi_button)

        self.current_midi_label = QLabel("選択中のファイル: なし")
        self.current_midi_label.setWordWrap(True) # ファイル名が長い場合に折り返し
        left_sidebar_layout.addWidget(self.current_midi_label)

        # パートリスト
        part_group_label = QLabel("パートのリスト（選択する）")
        part_group_label.setStyleSheet("font-weight: bold; margin-top: 20px;")
        left_sidebar_layout.addWidget(part_group_label)

        self.part_list_widget = QListWidget()
        self.part_list_widget.setMinimumHeight(200)
        self.part_list_widget.currentItemChanged.connect(self.select_part)
        left_sidebar_layout.addWidget(self.part_list_widget)

        left_sidebar_layout.addStretch(1) # 余白

        main_layout.addLayout(left_sidebar_layout, 2) # 左サイドバーの幅

        # --- 中央エリア (楽譜表示) ---
        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(10, 10, 10, 10)
        center_layout.setSpacing(10)

        score_label = QLabel("楽譜の表示（パート）")
        score_label.setStyleSheet("font-weight: bold;")
        center_layout.addWidget(score_label)

        self.score_display = QLabel("ここに楽譜が表示されます。")
        self.score_display.setAlignment(Qt.AlignCenter)
        self.score_display.setMinimumSize(600, 400) # 最小サイズを設定
        self.score_display.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")
        self.score_display.setScaledContents(False) # QLabelでスケールするのでFalseに

        # 簡易的なフレーズ選択のラベル (実際には楽譜画像上でクリックなど)
        phrase_selection_label = QLabel("フレーズを選択: 開始点と終了点の音符をクリック (現在はダミー)")
        center_layout.addWidget(phrase_selection_label)
        self.phrase_start_button = QPushButton("開始点を選択 (ダミー)")
        self.phrase_start_button.clicked.connect(self.select_phrase_start)
        self.phrase_end_button = QPushButton("終了点を選択 (ダミー)")
        self.phrase_end_button.clicked.connect(self.select_phrase_end)
        phrase_button_layout = QHBoxLayout()
        phrase_button_layout.addWidget(self.phrase_start_button)
        phrase_button_layout.addWidget(self.phrase_end_button)
        center_layout.addLayout(phrase_button_layout)
        self.selected_phrase_label = QLabel("選択中のフレーズ: 未選択")
        center_layout.addWidget(self.selected_phrase_label)

        center_layout.addWidget(self.score_display)
        center_layout.addStretch(1)

        main_layout.addLayout(center_layout, 5) # 中央エリアの幅

        # --- 右サイドバー ---
        right_sidebar_layout = QVBoxLayout()
        right_sidebar_layout.setContentsMargins(10, 10, 10, 10)
        right_sidebar_layout.setSpacing(15)

        # 発想標語/形容詞タブ
        self.expression_tab_widget = QTabWidget()
        
        # 形容詞タブ
        adjective_widget = QWidget()
        adjective_layout = QVBoxLayout(adjective_widget)
        adjective_layout.setAlignment(Qt.AlignTop) # 上に寄せる
        adjective_label = QLabel("形容詞を選択")
        adjective_label.setStyleSheet("font-weight: bold;")
        adjective_layout.addWidget(adjective_label)
        self.adjective_combo = QComboBox()
        self.adjective_combo.addItems(["明るく", "優しく", "激しく", "悲しく", "神秘的に"])
        adjective_layout.addWidget(self.adjective_combo)
        adjective_layout.addStretch(1)
        self.expression_tab_widget.addTab(adjective_widget, "形容詞")

        # 発想標語タブ
        motto_widget = QWidget()
        motto_layout = QVBoxLayout(motto_widget)
        motto_layout.setAlignment(Qt.AlignTop) # 上に寄せる
        motto_label = QLabel("発想標語を選択")
        motto_label.setStyleSheet("font-weight: bold;")
        motto_layout.addWidget(motto_label)
        self.motto_combo = QComboBox()
        self.motto_combo.addItems(["Allegro", "Andante", "Moderato", "Dolce", "Cantabile", "Sostenuto", "Pianissimo", "Fortissimo"])
        motto_layout.addWidget(self.motto_combo)
        motto_layout.addStretch(1)
        self.expression_tab_widget.addTab(motto_widget, "発想標語")
        
        right_sidebar_layout.addWidget(self.expression_tab_widget)

        right_sidebar_layout.addStretch(1) # 上部の余白

        # 実行・再生・保存ボタン
        self.execute_button = QPushButton("実行")
        self.execute_button.setStyleSheet("background-color: #4CAF50; color: white; font-size: 16px; padding: 10px;")
        self.execute_button.clicked.connect(self.execute_processing)
        right_sidebar_layout.addWidget(self.execute_button)

        self.play_button = QPushButton("再生")
        self.play_button.clicked.connect(self.play_midi)
        self.play_button.setEnabled(False) # 処理後まで無効
        right_sidebar_layout.addWidget(self.play_button)

        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.save_midi)
        self.save_button.setEnabled(False) # 処理後まで無効
        right_sidebar_layout.addWidget(self.save_button)

        main_layout.addLayout(right_sidebar_layout, 3) # 右サイドバーの幅

    # --- スロット (ボタンクリックなどのイベントハンドラ) ---

    def upload_midi(self):
        """
        ユーザー操作: 1. MIDIファイルのアップロード
        システム内部処理: 1. MIDIファイルの読み込み、パート情報抽出、リスト表示
        """
        file_path, _ = QFileDialog.getOpenFileName(self, "MIDIファイルを選択", "", "MIDI Files (*.mid *.midi)")
        if file_path:
            self.current_midi_path = file_path
            self.current_midi_label.setText(f"選択中のファイル: {os.path.basename(file_path)}") # ファイル名のみ表示
            self.midi_data, tracks = load_midi_file(file_path)
            self.part_list_widget.clear()
            self.score_display.clear() # 楽譜表示をクリア
            self.score_display.setText("パートを選択してください") # 新しいテキストを設定

            if self.midi_data:
                self.part_list_widget.addItems(tracks)
                if tracks:
                    self.part_list_widget.setCurrentRow(0) # 最初のパートをデフォルトで選択
                self.enable_controls(True) # コントロールを有効化
            else:
                self.enable_controls(False)
                self.score_display.setText("MIDIファイルの読み込みに失敗しました。")

    def select_part(self):
        """
        ユーザー操作: 2. リストから該当パートを選択する
        システム内部処理: 2. 選択されたパートの楽譜（五線譜）を画面に表示
        """
        if self.part_list_widget.currentItem() and self.current_midi_path:
            self.current_part_index = self.part_list_widget.currentRow()
            print(f"パート選択: {self.part_list_widget.currentItem().text()} (Index: {self.current_part_index})")
            
            score_image_path = display_score_for_part(self.current_midi_path, self.current_part_index)
            
            print(f"display_score_for_partから返されたパス/エラーメッセージ: {score_image_path}") # デバッグ用

            if score_image_path and score_image_path.endswith('.png') and os.path.exists(score_image_path):
                pixmap = QPixmap(score_image_path)
                
                print(f"QPixmap.isNull(): {pixmap.isNull()}") # QPixmapが画像をロードできたか確認
                
                if pixmap.isNull():
                    self.score_display.setText("エラー: 楽譜画像を読み込めませんでした。ファイルが壊れているか、パスが不正です。")
                    print("エラー: QPixmapが画像を読み込めませんでした (isNullがTrue)。")
                    return
                
                # QLabelのサイズに合わせて画像をスケーリング
                # setScaledContents(False)なので、手動でscaled()を呼び出す
                # self.score_display.size() を使用して現在のラベルサイズを取得
                scaled_pixmap = pixmap.scaled(self.score_display.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.score_display.setPixmap(scaled_pixmap)
                self.score_display.setText("") # エラーテキストをクリア
            else:
                # エラーメッセージが返された場合はそれを表示
                self.score_display.setText(score_image_path if score_image_path else "楽譜表示エラーが発生しました。")
                print(f"楽譜表示に失敗: {score_image_path}") # デバッグ用
        elif not self.current_midi_path:
            self.score_display.setText("MIDIファイルを読み込んでからパートを選択してください。")


    def select_phrase_start(self):
        """
        ユーザー操作: 3. 演奏表現をつけたいフレーズを選択する (開始点)
        システム内部処理: 3. フレーズの音符情報、演奏情報を取得 (ダミー)
        """
        # ダミーの音符選択
        self.selected_phrase_start = 0 # 例: 最初の音符
        self.update_phrase_selection_label()

    def select_phrase_end(self):
        """
        ユーザー操作: 3. 演奏表現をつけたいフレーズを選択する (終了点)
        システム内部処理: 3. フレーズの音符情報、演奏情報を取得 (ダミー)
        """
        # ダミーの音符選択
        # 実際には楽譜から取得した音符数に基づいて設定
        self.selected_phrase_end = 5 # 例: 6番目の音符
        self.update_phrase_selection_label()

    def update_phrase_selection_label(self):
        if self.selected_phrase_start != -1 and self.selected_phrase_end != -1:
            self.selected_phrase_label.setText(f"選択中のフレーズ: 音符 {self.selected_phrase_start} から {self.selected_phrase_end}")
        else:
            self.selected_phrase_label.setText("選択中のフレーズ: 未選択")


    def execute_processing(self):
        """
        ユーザー操作: 5. 実行ボタンを押す
        システム内部処理:
            4. プリセットの検索
            5. フレーズに対して、表現プリセットを適用してノート情報を加工する
            6. 音源の生成（MIDI）
        """
        if not self.midi_data or self.current_part_index == -1 or \
           self.selected_phrase_start == -1 or self.selected_phrase_end == -1:
            QMessageBox.warning(self, "警告", "MIDIファイルの読み込み、パート選択、フレーズ選択を完了してください。")
            return

        current_tab_index = self.expression_tab_widget.currentIndex()
        if current_tab_index == 0: # 形容詞タブ
            expression_type = "形容詞"
            expression_word = self.adjective_combo.currentText()
        else: # 発想標語タブ
            expression_type = "発想標語"
            expression_word = self.motto_combo.currentText()

        # 3. フレーズの音符情報、演奏情報を取得 (ダミー)
        phrase_notes_info, _ = get_phrase_info(self.midi_data, self.selected_phrase_start, self.selected_phrase_end)

        # 4. プリセットの検索
        preset_params = search_preset(expression_type, expression_word)
        if not preset_params:
            QMessageBox.warning(self, "警告", f"選択された表現「{expression_word}」に対応するプリセットが見つかりません。")
            return

        # 5. フレーズに対して、表現プリセットを適用してノート情報を加工する
        processed_midi_data = apply_expression_to_notes(self.midi_data, phrase_notes_info, preset_params)

        # 6. 音源の生成（MIDI）
        # output_file_nameを生成する際に、basenameを使うことでファイル名のみを取得
        output_file_name = f"processed_{expression_word}_{os.path.basename(self.current_midi_path)}" if self.current_midi_path else "processed_output.mid"
        self.processed_midi_output_path = generate_midi_output(processed_midi_data, output_file_name)

        if self.processed_midi_output_path:
            self.play_button.setEnabled(True)
            self.save_button.setEnabled(True)

    def play_midi(self):
        """
        ユーザー操作: 7. (再生ボタン)
        システム内部処理: 7. (音源の再生)
        """
        if self.processed_midi_output_path and os.path.exists(self.processed_midi_output_path):
            QMessageBox.information(self, "再生", f"加工済みMIDIファイルを再生します。\n(実際には外部MIDIシンセサイザーやライブラリが必要です): {self.processed_midi_output_path}")
            # 実際には、ここにMIDI再生ライブラリのコードを記述します。
            # 例: fluidsynth, python-rtmidi など
            # Windowsの場合、関連付けられたプログラムで開く簡易的な方法
            try:
                os.startfile(self.processed_midi_output_path) # Windows専用
            except AttributeError:
                # macOS / Linux の場合は open コマンドなどを使用
                # import subprocess
                # subprocess.Popen(['open', self.processed_midi_output_path])
                QMessageBox.warning(self, "警告", "自動再生はサポートされていないOSです。手動でファイルを開いてください。")

        else:
            QMessageBox.warning(self, "警告", "再生する加工済みMIDIファイルがありません。")

    def save_midi(self):
        """
        ユーザー操作: 8. 保存ボタン
        システム内部処理: 8. 音源を保存する
        """
        if self.processed_midi_output_path and os.path.exists(self.processed_midi_output_path):
            initial_filename = os.path.basename(self.processed_midi_output_path)
            save_path, _ = QFileDialog.getSaveFileName(self, "加工済みMIDIファイルを保存", initial_filename, "MIDI Files (*.mid *.midi)")
            if save_path:
                try:
                    import shutil
                    shutil.copy(self.processed_midi_output_path, save_path)
                    QMessageBox.information(self, "保存", f"加工済みMIDIファイルを保存しました:\n{save_path}")
                    # self.processed_midi_output_path = save_path # 保存パスを更新するかは要検討（元のファイルはそのまま残したい場合もある）
                except Exception as e:
                    QMessageBox.critical(self, "エラー", f"ファイルの保存に失敗しました: {e}")
            else:
                QMessageBox.information(self, "情報", "保存がキャンセルされました。")
        else:
            QMessageBox.warning(self, "警告", "保存する加工済みMIDIファイルがありません。先に「実行」してください。")

    def enable_controls(self, enable):
        """特定のコントロールの有効/無効を切り替える"""
        self.part_list_widget.setEnabled(enable)
        self.phrase_start_button.setEnabled(enable)
        self.phrase_end_button.setEnabled(enable)
        self.expression_tab_widget.setEnabled(enable)
        self.execute_button.setEnabled(enable)
        # MIDIファイルが読み込まれていない場合は再生・保存も無効にする
        if not enable: 
            self.play_button.setEnabled(False)
            self.save_button.setEnabled(False)
        # ただし、実行後には play/save ボタンが有効になるように、execute_processing内で別途設定

    # ウィンドウのリサイズ時に楽譜画像を再スケーリングする
    def resizeEvent(self, event):
        # QLabelの現在のサイズを取得
        current_label_size = self.score_display.size()
        
        # QPixmapが設定されている場合のみ
        if self.score_display.pixmap(): 
            current_pixmap = self.score_display.pixmap()
            # QLabelのサイズに合わせてアスペクト比を維持してスケーリング
            scaled_pixmap = current_pixmap.scaled(current_label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.score_display.setPixmap(scaled_pixmap)
        super().resizeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MusicExpressionGenerator()
    window.show()
    sys.exit(app.exec_())