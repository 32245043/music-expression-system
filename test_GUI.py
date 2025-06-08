import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsScene, QGraphicsView, QGraphicsEllipseItem
from PyQt5.QtCore import Qt, QRectF
from music21 import converter, note

class NoteItem(QGraphicsEllipseItem):
    def __init__(self, x, y, pitch, index):
        super().__init__(QRectF(x, y, 20, 20))
        self.setBrush(Qt.white)
        self.setPen(Qt.black)
        self.pitch = pitch
        self.index = index
        self.setFlag(QGraphicsEllipseItem.ItemIsSelectable)

    def mousePressEvent(self, event):
        self.setBrush(Qt.red if self.brush().color() == Qt.white else Qt.white)
        print(f"Clicked Note: {self.pitch}, Index: {self.index}")

class MusicGUI(QMainWindow):
    def __init__(self, midi_path):
        super().__init__()
        self.setWindowTitle("MIDI Note Selector")
        self.setGeometry(100, 100, 800, 400)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene, self)
        self.setCentralWidget(self.view)

        self.notes = self.load_midi_notes(midi_path)
        self.display_notes()

    def load_midi_notes(self, path):
        score = converter.parse(path)
        flat_notes = list(score.flat.notes)
        return [n for n in flat_notes if isinstance(n, note.Note)]

    def display_notes(self):
        x_offset = 30
        y_base = 150
        for i, n in enumerate(self.notes):
            pitch_offset = (n.pitch.midi - 60) * -5
            note_item = NoteItem(x_offset + i * 30, y_base + pitch_offset, n.nameWithOctave, i)
            self.scene.addItem(note_item)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = MusicGUI("dvorak_sveta-2.mid")  # ←ここを自分のMIDIファイル名に書き換えてください
    gui.show()
    sys.exit(app.exec_())
