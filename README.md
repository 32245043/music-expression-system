### 発想標語に対応する演奏見本システム

#### システム実行に必要なもの  
・music_expression.py　(メイン)  
・lilypond-2.24.4-mingw-x86_64　(楽譜表示)  
　・music_expression.py内でlilypond-2.24.4-mingw-x86_64\lilypond-2.24.4\bin\musicxml2ly.pyを呼び出すため  

#### 操作方法  
1. music_expression.pyを実行する  
2. GUI左上の"開く"ボタンを押すとファイル選択ダイアログが表示されるので、演奏表現をつけるMIDIファイルを選択して"開く"を押す  
   読み込みが完了すると、左側の"パートのリスト"にMIDIファイルに含まれるパート名が表示される
3. 
