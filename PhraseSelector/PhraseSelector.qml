import QtQuick 2.0
import QtQuick.Dialogs 1.2 
import MuseScore 3.0
import FileIO 3.0

// --- プラグイン全体の定義 ---
MuseScore {
    // MuseScoreのバージョン要件
    version: "3.0"
    description: "フレーズ範囲の開始・終了位置（小節・拍）を取得してJSONで出力するプラグイン"
    menuPath: "Plugins.フレーズ範囲取得"
    
    // --- ファイル入出力用のコンポーネント ---
    FileIO {
        id: fileIO
    }

    // --- ファイル保存ダイアログの定義 ---
    FileDialog {
        id: saveDialog
        // title は onRun イベント内で動的に設定
        selectExisting: false
        // ファイルの種類フィルター
        nameFilters: [ "JSON ファイル (*.json)" ]

        // 保存するJSONコンテンツを一時的に保持するプロパティ
        property string jsonContentToSave: ""

        // 保存ボタンが押されたとき
        onAccepted: {
            // 選択されたファイルのURLを文字列に変換
            var urlString = fileUrl.toString();
            var localPath = urlString;

            // URLの先頭にある "file:///" スキームを手動で削除し、ローカルパスに変換
            if (localPath.startsWith("file:///")) {
                localPath = localPath.substring(8); // "file:///".length は 8
            }
            
            // OSのネイティブパス形式になった文字列で処理
            // ファイル名の末尾が ".json" でない場合、拡張子を追加
            if (!localPath.toLowerCase().endsWith(".json")) {
                localPath += ".json";
                console.log("ファイル名に拡張子 .json を追加しました。");
            }
            
            // 保存パスをコンソールに出力
            console.log("保存パス (ネイティブ): " + localPath);
            // FileIOコンポーネントに保存先のパスを設定
            fileIO.source = localPath;

            // FileIOを使ってファイルに書き込み
            if (fileIO.write(jsonContentToSave)) {
                console.log("✓ ファイルを正常に保存しました: " + localPath);
            } else {
                console.log("❌ ファイルの保存に失敗しました。");
            }
            // 処理が完了したらプラグインを終了
            Qt.quit();
        }

        // ダイアログで「キャンセル」ボタンが押されたとき
        onRejected: {
            console.log("ファイル保存がキャンセルされました。");
            // 処理が完了したらプラグインを終了
            Qt.quit();
        }
    }
    
    // --- プラグイン実行時のメイン処理 ---
    onRun: {
        console.log("フレーズ範囲取得プラグインを開始します");
        
        // 楽譜が開かれていない場合
        if (typeof curScore === 'undefined' || !curScore) {
            console.log("楽譜が開かれていません");
            // プラグインを終了
            Qt.quit();
            return;
        }
        
        // 選択範囲の開始と終了のtick値を入れる変数を宣言
        var selection = curScore.selection;
        var startTick, endTick;
        
        // 範囲選択が行われている場合
        if (selection && selection.isRange && selection.startSegment && selection.endSegment) {
            // 選択範囲の開始と終了のtick値を取得
            startTick = selection.startSegment.tick;
            endTick = selection.endSegment.tick;
        // 範囲選択ではなく、単一の音符などが選択されている場合
        } else {
            // カーソルを使って選択範囲を取得
            var cursor = curScore.newCursor();
            cursor.rewind(1); // 選択範囲の先頭へ
            var selectionStartTick = cursor.tick;
            cursor.rewind(2); // 選択範囲の末尾へ
            var selectionEndTick = cursor.tick;
            
            // 選択範囲が有効な場合
            if (selectionStartTick !== selectionEndTick && selectionEndTick > selectionStartTick) {
                startTick = selectionStartTick;
                endTick = selectionEndTick;
            // 選択範囲がない場合
            } else {
                console.log("範囲が選択されていません。");
                Qt.quit();
                return;
            }
        }
        
        // 開始tickが終了tick以降の場合は無効な範囲
        if (startTick >= endTick) {
            console.log("選択範囲が無効です。");
            Qt.quit();
            return;
        }
        
        // tick値を小節と拍に変換
        var startPos = getBarAndBeat(startTick);
        // 終了位置は1tick手前を基準にする
        var endPos = getBarAndBeat(Math.max(0, endTick - 1));
        
        // 解析結果をコンソールに表示
        displayResults(startPos, endPos, startTick, endTick);
        
        // 保存するJSONオブジェクトを作成
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
        // JSONオブジェクトを整形された文字列に変換
        var jsonString = JSON.stringify(phraseData, null, 2);
        
        // 保存するファイル名のベースを決定
        var baseFilename;
        // 楽譜ファイルが保存されている場合、そのファイル名を使用
        if (curScore.filePath && curScore.filePath !== "") {
            var fullPath = curScore.filePath;
            var filenameWithExt = fullPath.substring(fullPath.lastIndexOf('/') + 1);
            baseFilename = filenameWithExt.substring(0, filenameWithExt.lastIndexOf('.'));
        // ファイルが保存されておらず、タイトルが設定されている場合、そのタイトルを使用
        } else if (curScore.title && curScore.title !== "") {
            baseFilename = curScore.title;
        // 上記以外の場合は "untitled" を使用
        } else {
            baseFilename = "untitled";
        }
        // ファイル名として使えない文字をアンダースコアに置換
        baseFilename = baseFilename.replace(/[<>:"/\\|?*]/g, '_');
        
        // 保存ダイアログにJSONコンテンツを設定
        saveDialog.jsonContentToSave = jsonString;
        
        // 保存ダイアログの初期ディレクトリを設定
        // ★パスは適宜変更してください★
        var initialDir = "C:/Users/momoka/Documents/workplace5/JSON";
        saveDialog.folder = "file:///" + initialDir;
        
        // ダイアログのタイトルバーに推奨ファイル名を表示
        saveDialog.title = "保存 - 推奨ファイル名: " + baseFilename + ".json";
        
        // 保存ダイアログを開く
        saveDialog.open();
    }
    
    // --- tick値から小節と拍を計算する関数 ---
    function getBarAndBeat(tick) {
        // 新しいカーソルを作成し、先頭に移動
        var cursor = curScore.newCursor();
        cursor.rewind(0);
        
        // デフォルトの拍子記号（4/4拍子）
        var beatsPerBar = 4;
        var beatUnit = 4;
        // 4分音符あたりのtick数（division）を取得
        var ticksPerQuarter = division;
        
        // カーソルを指定されたtick位置まで進め、途中の拍子記号をチェック
        while (cursor.segment && cursor.tick <= tick) {
            if (cursor.segment.annotations) {
                // セグメント内の要素をループ
                for (var i = 0; i < cursor.segment.annotations.length; i++) {
                    var annotation = cursor.segment.annotations[i];
                    // 拍子記号が見つかった場合
                    if (annotation && annotation.type === Element.TIMESIG) {
                        // 拍子情報を更新
                        beatsPerBar = annotation.numerator;
                        beatUnit = annotation.denominator;
                    }
                }
            }
            // カーソルを次に進める
            if (!cursor.next()) break;
        }
        
        // 1拍あたりのtick数と1小節あたりのtick数を計算
        var ticksPerBeat = ticksPerQuarter * (4 / beatUnit);
        var ticksPerBar = ticksPerBeat * beatsPerBar;
        
        // tick値から小節番号を計算（1始まり）
        var bar = Math.floor(tick / ticksPerBar) + 1;
        // 小節内の余りのtick値を計算
        var remainderTick = tick % ticksPerBar;
        // 余りのtick値から拍を計算（1始まり）
        var beat = Math.floor(remainderTick / ticksPerBeat) + 1;
        
        // 計算した拍が小節の拍数を超えた場合の調整
        if (beat > beatsPerBar) {
            bar += Math.floor((beat - 1) / beatsPerBar);
            beat = ((beat - 1) % beatsPerBar) + 1;
        }
        
        // tickが0の場合は1小節目の1拍目とする
        if (tick === 0) {
            bar = 1;
            beat = 1;
        }
        
        // 計算結果をオブジェクトとして返す
        return {
            bar: Math.max(1, bar), // 小節番号は最低でも1
            beat: Math.max(1, Math.min(beat, beatsPerBar)), // 拍は1から最大拍数の間
            ticksPerBar: ticksPerBar,
            ticksPerBeat: ticksPerBeat,
            beatsPerBar: beatsPerBar
        };
    }
    
    // --- 解析結果をコンソールに表示する関数 ---
    function displayResults(startPos, endPos, startTick, endTick) {
        console.log("=== フレーズ範囲解析結果 ===");
        console.log("開始: " + startPos.bar + "小節 " + startPos.beat + "拍 (tick: " + startTick + ")");
        console.log("終了: " + endPos.bar + "小節 " + endPos.beat + "拍 (tick: " + endTick + ")");
        console.log("=========================");
    }
}