import QtQuick 2.0
import QtQuick.Dialogs 1.2 // ファイルダイアログ機能のインポート
import MuseScore 3.0
import FileIO 3.0

MuseScore {
    version: "3.0"
    description: "フレーズ範囲の開始・終了位置（小節・拍）を取得してJSONで出力するプラグイン"
    menuPath: "Plugins.フレーズ範囲取得"
    
    // FileIOコンポーネント
    FileIO {
        id: fileIO
    }

    // --- ファイル保存ダイアログの定義 (最終決定版) ---
    FileDialog {
        id: saveDialog
        // title は onRun で動的に設定
        selectExisting: false
        nameFilters: [ "JSON ファイル (*.json)" ]

        property string jsonContentToSave: ""

        // ユーザーが「保存」ボタンを押したときの処理 (最終決定版)
        onAccepted: {
            // 1. fileUrlをまず文字列に変換する
            var urlString = fileUrl.toString();
            var localPath = urlString;

            // 2. ★★★ 文字列の先頭が "file:///" であれば、手動で削除する ★★★
            if (localPath.startsWith("file:///")) {
                localPath = localPath.substring(8); // "file:///".length は 8
            }
            
            // 3. OSのネイティブパスになった文字列で処理を続ける
            if (!localPath.toLowerCase().endsWith(".json")) {
                localPath += ".json";
                console.log("ファイル名に拡張子 .json を追加しました。");
            }
            
            console.log("保存パス (ネイティブ): " + localPath);
            fileIO.source = localPath; // 正しい形式のパスをFileIOに設定

            if (fileIO.write(jsonContentToSave)) {
                console.log("✓ ファイルを正常に保存しました: " + localPath);
            } else {
                console.log("❌ ファイルの保存に失敗しました。");
            }
            Qt.quit();
        }

        onRejected: {
            console.log("ファイル保存がキャンセルされました。");
            Qt.quit();
        }
    }
    
    onRun: {
        console.log("フレーズ範囲取得プラグインを開始します");
        
        if (typeof curScore === 'undefined' || !curScore) {
            console.log("楽譜が開かれていません");
            Qt.quit();
            return;
        }
        
        var selection = curScore.selection;
        var startTick, endTick;
        
        if (selection && selection.isRange && selection.startSegment && selection.endSegment) {
            startTick = selection.startSegment.tick;
            endTick = selection.endSegment.tick;
        } else {
            var cursor = curScore.newCursor();
            cursor.rewind(1);
            var selectionStartTick = cursor.tick;
            cursor.rewind(2);
            var selectionEndTick = cursor.tick;
            
            if (selectionStartTick !== selectionEndTick && selectionEndTick > selectionStartTick) {
                startTick = selectionStartTick;
                endTick = selectionEndTick;
            } else {
                console.log("範囲が選択されていません。");
                Qt.quit();
                return;
            }
        }
        
        if (startTick >= endTick) {
            console.log("選択範囲が無効です。");
            Qt.quit();
            return;
        }
        
        var startPos = getBarAndBeat(startTick);
        var endPos = getBarAndBeat(Math.max(0, endTick - 1));
        
        displayResults(startPos, endPos, startTick, endTick);
        
        var phraseData = {
            "start": {
                "measure": startPos.bar,
                "beat": parseFloat(startPos.beat.toFixed(1))
            },
            "end": {
                "measure": endPos.bar,
                "beat": parseFloat(endPos.beat.toFixed(1))
            }
        };
        var jsonString = JSON.stringify(phraseData, null, 2);
        
        var baseFilename;
        if (curScore.filePath && curScore.filePath !== "") {
            var fullPath = curScore.filePath;
            var filenameWithExt = fullPath.substring(fullPath.lastIndexOf('/') + 1);
            baseFilename = filenameWithExt.substring(0, filenameWithExt.lastIndexOf('.'));
        } else if (curScore.title && curScore.title !== "") {
            baseFilename = curScore.title;
        } else {
            baseFilename = "untitled";
        }
        baseFilename = baseFilename.replace(/[<>:"/\\|?*]/g, '_');
        
        saveDialog.jsonContentToSave = jsonString;
        
        var initialDir = "C:/Users/momoka/Documents/workplace5/JSON";
        
        saveDialog.folder = "file:///" + initialDir;
        
        // ダイアログのタイトルバーに推奨ファイル名を表示
        saveDialog.title = "保存 - 推奨ファイル名: " + baseFilename + ".json";
        
        saveDialog.open();
    }
    
    function getBarAndBeat(tick) {
        var cursor = curScore.newCursor();
        cursor.rewind(0);
        var beatsPerBar = 4;
        var beatUnit = 4;
        var ticksPerQuarter = division;
        
        while (cursor.segment && cursor.tick <= tick) {
            if (cursor.segment.annotations) {
                for (var i = 0; i < cursor.segment.annotations.length; i++) {
                    var annotation = cursor.segment.annotations[i];
                    if (annotation && annotation.type === Element.TIMESIG) {
                        beatsPerBar = annotation.numerator;
                        beatUnit = annotation.denominator;
                    }
                }
            }
            if (!cursor.next()) break;
        }
        
        var ticksPerBeat = ticksPerQuarter * (4 / beatUnit);
        var ticksPerBar = ticksPerBeat * beatsPerBar;
        var bar = Math.floor(tick / ticksPerBar) + 1;
        var remainderTick = tick % ticksPerBar;
        var beat = Math.floor(remainderTick / ticksPerBeat) + 1;
        
        if (beat > beatsPerBar) {
            bar += Math.floor((beat - 1) / beatsPerBar);
            beat = ((beat - 1) % beatsPerBar) + 1;
        }
        
        if (tick === 0) {
            bar = 1;
            beat = 1;
        }
        
        return {
            bar: Math.max(1, bar),
            beat: Math.max(1, Math.min(beat, beatsPerBar)),
            ticksPerBar: ticksPerBar,
            ticksPerBeat: ticksPerBeat,
            beatsPerBar: beatsPerBar
        };
    }
    
    function displayResults(startPos, endPos, startTick, endTick) {
        console.log("=== フレーズ範囲解析結果 ===");
        console.log("開始: " + startPos.bar + "小節 " + startPos.beat + "拍 (tick: " + startTick + ")");
        console.log("終了: " + endPos.bar + "小節 " + endPos.beat + "拍 (tick: " + endTick + ")");
        console.log("=========================");
    }
}