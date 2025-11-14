// ============================================================
// main.js
// ファイルアップロードとパート情報の取得
// abcjsを利用した楽譜の描画と音符クリック処理
// フレーズ範囲（開始・頂点・終了）の選択とUIの更新
// プリセットに基づいた演奏表現パラメータのサーバーへの送信
// サーバーから返されたWAVファイルの再生処理
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    // --- DOM要素の取得 ---
    // HTMLから操作対象となる要素を取得し、定数に格納する
    const uploadForm = document.getElementById("upload-form");
    const partSelector = document.getElementById("part-selector");
    const scoreDisplay = document.getElementById("score-display");
    const statusMessage = document.getElementById("status-message");
    const applyToScoreBtn = document.getElementById("apply-to-score-btn");
    const generateAudioBtn = document.getElementById("generate-audio-btn");
    const tempoPreset = document.getElementById("tempo-preset");
    const resetSelectionBtn = document.getElementById("reset-selection-btn");
    const resetMidiBtn = document.getElementById("reset-midi-btn");
    const undoBtn = document.getElementById("undo-btn");
    const redoBtn = document.getElementById("redo-btn");
    const compareContainer = document.getElementById("compare-container");
    const saveArea = document.getElementById("save-area");
    // パラメータ調整UI用の要素を取得
    const toggleParamsBtn = document.getElementById("toggle-params-btn");
    const parameterEditor = document.getElementById("parameter-editor");
    const paramBaseCc2 = document.getElementById("param-base-cc2");
    const paramPeakCc2 = document.getElementById("param-peak-cc2");
    const paramOnsetMs = document.getElementById("param-onset-ms");
    // ▼▼▼ 変更点 ▼▼▼
    const debugModeToggle = document.getElementById("debug-mode-toggle");


    // --- グローバル変数 ---
    // アプリケーション全体で状態を管理するための変数を定義する
    let selectionMode = "start"; // 現在の音符選択モード（"start", "end", "peak"）
    let selectedNotes = { start: null, end: null, peak: null }; // 選択された開始・終了・頂点音符の情報
    let allPartAbcData = {}; // アップロードされたMIDIファイルの全パートのABC譜データ
    let allNoteMaps = {}; // 各パートの音符インデックスとMIDI tickを対応付けるマップ
    let currentPartIndex = null; // 現在選択されているパートのインデックス
    let history = []; // 適用した演奏表現の操作履歴
    let redoStack = []; // 「やり直し」用の操作を一時的に保持する
    let currentAudio = null; // 現在再生中のAudioオブジェクト
    window.lastGeneratedWavPaths = {}; // 最後に生成されたWAVファイルとMIDIファイルのパスを保持

    /**
     * 黄色の頂点候補ハイライトをすべて消去する
     */
    function clearApexCandidatesHighlights() {
        document.querySelectorAll(".abcjs-note.apex-candidate").forEach(el => el.classList.remove("apex-candidate"));
    }

    /**
     * 楽譜上に表示されているデバッグ用のスコアをすべて消去する
     */
    function clearDebugScores() {
        document.querySelectorAll('.debug-score-text').forEach(el => el.remove());
    }

    /**
     * サーバーから受け取ったスコア情報を楽譜上に描画する
     * @param {Array} scores - スコア情報の配列
     */
    function drawDebugScores(scores) {
        const scoreSVG = scoreDisplay.querySelector("svg");
        if (!scoreSVG) return;
        const svgRect = scoreSVG.getBoundingClientRect();
        const allNoteElements = Array.from(document.querySelectorAll(".abcjs-note"));

        scores.forEach(scoreInfo => {
            // fe_index を使って、対応する音符DOM要素を取得
            const noteEl = allNoteElements[scoreInfo.fe_index];
            if (noteEl) {
                const noteRect = noteEl.getBoundingClientRect();
                const textEl = document.createElementNS("http://www.w3.org/2000/svg", "text");
                
                // 音符の真ん中上部にテキストを配置
                textEl.setAttribute("x", noteRect.left - svgRect.left + (noteRect.width / 2));
                textEl.setAttribute("y", noteRect.top - svgRect.top - 5); // 5px上に表示
                textEl.setAttribute("text-anchor", "middle"); // 中央揃え
                textEl.classList.add('debug-score-text'); // CSSと削除用にクラスを付与
                textEl.textContent = scoreInfo.total_score; // 表示するスコア

                scoreSVG.appendChild(textEl);
            }
        });
    }


    /**
     * 楽譜上に適用されたフレーズの装飾（ハイライトやテキスト）を再描画する
     */
    function updateScoreDecorations() {
        // 既存の装飾をすべて削除
        document.querySelectorAll('.decoration-group').forEach(el => el.remove());
        if (!history || history.length === 0) return;

        const allNoteElements = Array.from(document.querySelectorAll(".abcjs-note"));
        if (allNoteElements.length === 0) return;

        const scoreSVG = scoreDisplay.querySelector("svg");
        if (!scoreSVG) return;

        history.forEach(instruction => {
            const phrase = instruction.phrase;
            const presetName = instruction.preset_name;

            // 指示に対応する音符DOM要素を取得
            const startNoteEl = allNoteElements[phrase.start_index];
            const endNoteEl = allNoteElements[phrase.end_index];
            const peakNoteEl = allNoteElements[phrase.peak_index];

            if (startNoteEl && endNoteEl && peakNoteEl) {
                const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
                group.classList.add('decoration-group');
                const svgRect = scoreSVG.getBoundingClientRect();

                // フレーズ範囲のハイライトを描画（譜表の改行を考慮）
                let lineNotes = [];
                for (let i = phrase.start_index; i <= phrase.end_index; i++) {
                    const currentNoteEl = allNoteElements[i];
                    if (!currentNoteEl) continue;

                    if (lineNotes.length === 0) {
                        lineNotes.push(currentNoteEl);
                    } else {
                        const prevNoteRect = lineNotes[lineNotes.length - 1].getBoundingClientRect();
                        const currentNoteRect = currentNoteEl.getBoundingClientRect();
                        // Y座標がほぼ同じなら同じ行にあるとみなす
                        if (Math.abs(prevNoteRect.top - currentNoteRect.top) < prevNoteRect.height) {
                            lineNotes.push(currentNoteEl);
                        } else {
                            // 行が変わったので、前の行のハイライトを描画
                            drawHighlightForLine(lineNotes, group, svgRect);
                            lineNotes = [currentNoteEl]; // 新しい行を開始
                        }
                    }
                }
                if (lineNotes.length > 0) drawHighlightForLine(lineNotes, group, svgRect); // 最後の行を描画

                // 頂点音符のハイライトを描画
                const peakRect = peakNoteEl.getBoundingClientRect();
                const peakHighlight = document.createElementNS("http://www.w3.org/2000/svg", "rect");
                const padding = 2;
                peakHighlight.setAttribute("x", peakRect.left - svgRect.left - padding);
                peakHighlight.setAttribute("y", peakRect.top - svgRect.top - padding);
                peakHighlight.setAttribute("width", peakRect.width + (padding * 2));
                peakHighlight.setAttribute("height", peakRect.height + (padding * 2));
                peakHighlight.classList.add('phrase-peak-highlight');
                group.appendChild(peakHighlight);

                // プリセット名を表示するテキストを描画
                const startRect = startNoteEl.getBoundingClientRect();
                const textEl = document.createElementNS("http://www.w3.org/2000/svg", "text");
                textEl.setAttribute("x", startRect.left - svgRect.left + (startRect.width / 2));
                textEl.setAttribute("y", startRect.top - svgRect.top - 12);
                textEl.setAttribute("text-anchor", "middle");
                textEl.classList.add('expression-text');
                textEl.textContent = presetName || 'Applied';
                group.appendChild(textEl);

                scoreSVG.appendChild(group);
            }
        });
    }

    /**
     * 1行分の音符の背景ハイライトを描画する
     * @param {Array<Element>} noteElements - 同じ行にある音符のDOM要素の配列
     * @param {Element} group - SVGのグループ要素
     * @param {DOMRect} svgRect - 楽譜全体のSVG要素の矩形情報
     */
    function drawHighlightForLine(noteElements, group, svgRect) {
        if (noteElements.length === 0) return;
        const firstNoteRect = noteElements[0].getBoundingClientRect();
        const lastNoteRect = noteElements[noteElements.length - 1].getBoundingClientRect();
        const padding = 5;
        const rectEl = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rectEl.setAttribute("x", firstNoteRect.left - svgRect.left - padding);
        rectEl.setAttribute("y", firstNoteRect.top - svgRect.top - padding);
        rectEl.setAttribute("width", (lastNoteRect.right - firstNoteRect.left) + (padding * 2));
        rectEl.setAttribute("height", firstNoteRect.height + (padding * 2));
        rectEl.classList.add('phrase-highlight-rect');
        group.appendChild(rectEl);
    }
    
    /**
     * 操作履歴ややり直しスタック(redo)の状態に基づいて、
     * 各種ボタン（元に戻す、やり直す、リセット、音源生成）の有効/無効を切り替える
     */
    function updateButtonsState() {
        undoBtn.disabled = history.length === 0;
        redoBtn.disabled = redoStack.length === 0;
        resetMidiBtn.disabled = history.length === 0;
        generateAudioBtn.disabled = history.length === 0;
    }


    /**
     * MIDIファイルのアップロードフォームが送信されたときの処理
     */
    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault(); // デフォルトのフォーム送信をキャンセル
        statusMessage.textContent = "⌛ ファイルをアップロード中...";
        scoreDisplay.innerHTML = ""; // 前の楽譜をクリア

        const formData = new FormData(uploadForm);
        try {
            // サーバーの/uploadエンドポイントにファイルをPOST
            const res = await fetch("/upload", { method: "POST", body: formData });
            const result = await res.json();
            if(result.error) throw new Error(result.error);
            
            statusMessage.textContent = `✅ ${result.message}。パートを選択してください。`;
            
            // サーバーから返された全パートのABC譜データをグローバル変数に保存
            allPartAbcData = result.all_abc_data;
            
            // パート選択のドロップダウンリストを生成
            partSelector.innerHTML = "";
            result.parts.forEach((p) => {
                const opt = document.createElement("option");
                opt.value = p.index;
                opt.textContent = p.name || `Part ${p.index + 1}`;
                opt.dataset.noteMap = p.note_map; // NoteMapファイルのパスをdata属性に保存
                partSelector.appendChild(opt);
            });
            partSelector.disabled = false;

            if (result.parts.length == 1) {
                partSelector.dispatchEvent(new Event('change')); 
            }

            // 各種状態を初期化
            history = [];
            redoStack = [];
            updateButtonsState();
            compareContainer.style.display = "none";
            saveArea.style.display = "none";
        } catch (err) {
            console.error(err);
            statusMessage.textContent = "⚠️ エラー: " + err.message;
        }
    });

    /**
     * パートセレクターの値が変更されたときの処理
     */
    partSelector.addEventListener("change", async () => {
        currentPartIndex = parseInt(partSelector.value);
        if (isNaN(currentPartIndex)) return;

        // 選択されたパートに対応するNoteMap（音符indexとtickの対応表）をサーバーから取得
        const noteMapFilename = partSelector.selectedOptions[0].dataset.noteMap;
        if (noteMapFilename) {
            const res = await fetch(`/output/${noteMapFilename}`);
            if (res.ok) allNoteMaps[currentPartIndex] = await res.json();
        }
        
        // ABC譜を描画
        renderScore(allPartAbcData[currentPartIndex]);
    });

    /**
     * abcjsライブラリを使って楽譜を描画する
     * @param {string} abcText - 描画するABC譜のテキスト
     */
    function renderScore(abcText) {
        scoreDisplay.innerHTML = "";
        // ABCJSを呼び出し、クリックリスナーを設定
        ABCJS.renderAbc("score-display", abcText, { add_classes: true, staffwidth: 900, clickListener: (abcElem, tuneNumber, classes, analysis, drag, mouseEvent) => {
            const clickedEl = mouseEvent.target.closest(".abcjs-note");
            if (clickedEl) handleNoteClick(clickedEl);
        }});
        // 描画が完了した少し後に装飾を更新（レンダリングのタイミングを考慮）
        setTimeout(() => { updateScoreDecorations(); }, 200);
        statusMessage.textContent = "✅ 音符をクリックして範囲を指定できます。";
    }

    /**
     * 楽譜上の音符がクリックされたときの処理
     * @param {Element} clickedEl - クリックされた音符のDOM要素
     */
    async function handleNoteClick(clickedEl) {
        const noteElements = Array.from(document.querySelectorAll(".abcjs-note"));
        const noteIndex = noteElements.indexOf(clickedEl); // クリックされた音符のインデックスを取得
        if (noteIndex === -1) return;

        // 頂点選択モードのときは、開始～終了の範囲外の音符は無視
        if (selectionMode === 'peak') {
            const startIndex = selectedNotes.start.index;
            const endIndex = selectedNotes.end.index;
            if (noteIndex < startIndex || noteIndex > endIndex) return;
        }
        
        const noteMap = allNoteMaps[currentPartIndex];
        const tick = noteMap?.[noteIndex]?.tick ?? null;
        const currentMode = selectionMode;

        // 開始音符選択時は、まず選択状態をリセット
        if (currentMode === 'start') {
            clearApexCandidatesHighlights();
            // ▼▼▼ 変更点 ▼▼▼
            clearDebugScores();
            selectedNotes = { start: null, end: null, peak: null };
        }
        
        // 現在のモードに応じて選択情報を更新
        selectedNotes[currentMode] = { index: noteIndex, tick, el: clickedEl };
        
        // 選択モードを順番に切り替える (start -> end -> peak -> start)
        if (currentMode === 'start') {
            selectionMode = 'end';
        } else if (currentMode === 'end') {
            // 開始と終了が逆順で選択された場合、入れ替える
            if (selectedNotes.start.index > selectedNotes.end.index) {
                [selectedNotes.start, selectedNotes.end] = [selectedNotes.end, selectedNotes.start];
            }
            selectionMode = 'peak';
            // 終了音符が選択されたら、頂点候補をサーバーに問い合わせる
            await fetchApexCandidates();
        } else if (currentMode === 'peak') {
            selectionMode = 'start';
        }

        // UIの表示を更新
        updateSelectionUI();
    }
    
    /**
     * サーバーにフレーズの開始・終了インデックスを送信し、頂点候補のリストを取得してハイライトする
     */
    async function fetchApexCandidates() {
        statusMessage.textContent = '⏳ 頂点候補を推定中...';
        clearApexCandidatesHighlights();
        clearDebugScores(); // ▼▼▼ 変更点 ▼▼▼

        const { start, end } = selectedNotes;
        if (!start || !end) return;

        try {
            const res = await fetch('/estimate_apex', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    partName: partSelector.selectedOptions[0].textContent,
                    startIndex: start.index,
                    endIndex: end.index
                })
            });
            const result = await res.json();
            if (result.error) throw new Error(result.error);
            
            // 返されたインデックスの音符にハイライト
            const noteElements = Array.from(document.querySelectorAll(".abcjs-note"));
            result.apex_candidates.forEach(index => {
                if (noteElements[index]) {
                    noteElements[index].classList.add('apex-candidate');
                }
            });
            
            // ▼▼▼ 変更点 ▼▼▼
            // デバッグモードがONならスコアを描画
            if (debugModeToggle.checked && result.debug_scores) {
                drawDebugScores(result.debug_scores);
            }

            statusMessage.textContent = '✅ 黄色の頂点候補から1つ選択してください';
        } catch (err) {
            statusMessage.textContent = `⚠️ 頂点推定エラー: ${err.message}`;
        }
    }

    /**
     * 音符の選択状態（ハイライトや情報表示）をUIに反映させる
     */
    function updateSelectionUI() {
        // すべての選択ハイライトを一度リセット
        document.querySelectorAll(".abcjs-note.selected, .abcjs-note.selected-end, .abcjs-note.selected-peak").forEach(el => el.classList.remove("selected", "selected-end", "selected-peak"));
        
        // 選択された音符にそれぞれ対応するクラスを追加
        if (selectedNotes.start?.el) selectedNotes.start.el.classList.add("selected");
        if (selectedNotes.end?.el) selectedNotes.end.el.classList.add("selected-end");
        if (selectedNotes.peak?.el) selectedNotes.peak.el.classList.add("selected-peak");
        
        // 画面下部の情報表示エリアを更新
        document.getElementById("start-note-info").textContent = selectedNotes.start ? `index=${selectedNotes.start.index} / tick=${selectedNotes.start.tick}` : "未選択";
        document.getElementById("end-note-info").textContent = selectedNotes.end ? `index=${selectedNotes.end.index} / tick=${selectedNotes.end.tick}` : "未選択";
        document.getElementById("peak-note-info").textContent = selectedNotes.peak ? `index=${selectedNotes.peak.index} / tick=${selectedNotes.peak.tick}` : "未選択";

        // 開始・終了・頂点がすべて選択されていたら「楽譜に適用」ボタンを有効化
        applyToScoreBtn.disabled = !(selectedNotes.start && selectedNotes.end && selectedNotes.peak);
    }

    /**
     * 「選択リセット」ボタンが押されたときの処理
     */
    resetSelectionBtn.addEventListener("click", () => {
        selectionMode = "start";
        selectedNotes = { start: null, end: null, peak: null };
        clearApexCandidatesHighlights();
        clearDebugScores(); // ▼▼▼ 変更点 ▼▼▼
        updateSelectionUI();
        statusMessage.textContent = "選択をリセットしました。";
    });

    /**
     * 「楽譜に適用」ボタンが押されたときの処理
     */
    applyToScoreBtn.addEventListener("click", () => {
        if (applyToScoreBtn.disabled) return;
        
        const phraseInfo = { start_index: selectedNotes.start.index, end_index: selectedNotes.end.index, peak_index: selectedNotes.peak.index };
        const tempoSelection = tempoPreset.value;

        // パラメータエディタから手動で設定された値を取得
        const params = {
            base_cc2: parseInt(paramBaseCc2.value) || 0,
            peak_cc2: parseInt(paramPeakCc2.value) || 0,
            onset_ms: parseInt(paramOnsetMs.value) || 0,
        };

        // サーバーに送信するための指示
        const newInstruction = {
            phrase: phraseInfo,
            preset_params: params, // 取得したパラメータを使用
            preset_name: tempoSelection,
            part_index: currentPartIndex,
            part_name: partSelector.selectedOptions[0].textContent,
        };

        // 同じフレーズ範囲に対する指示が既に存在するかチェック
        const foundIndex = history.findIndex(instr => JSON.stringify(instr.phrase) === JSON.stringify(newInstruction.phrase));
        if (foundIndex !== -1) {
            // 存在すれば、新しい指示で上書き（パラメータの変更など）
            history[foundIndex] = newInstruction;
        } else {
            // 存在しなければ、新しい指示として追加
            history.push(newInstruction);
        }
        
        redoStack = []; // 新しい操作をしたら「やり直し」スタックはクリア
        updateScoreDecorations(); // 楽譜の装飾を更新
        updateButtonsState(); // ボタンの状態を更新
        
        statusMessage.textContent = `✅ [${tempoSelection}]を楽譜に反映しました。続けてパラメータを変更するか、音源を生成してください。`;
    });

    /**
     * 「元に戻す」ボタンが押されたときの処理
     */
    undoBtn.addEventListener("click", () => {
        if (history.length === 0) return;
        const undoneAction = history.pop(); // 最後の操作をhistoryから削除
        redoStack.push(undoneAction); // 削除した操作をredoStackに追加
        updateScoreDecorations();
        updateButtonsState();
    });

    /**
     * 「やり直す」ボタンが押されたときの処理
     */
    redoBtn.addEventListener("click", () => {
        if (redoStack.length === 0) return;
        const redoneAction = redoStack.pop(); // redoStackから最後の操作を取り出す
        history.push(redoneAction); // 取り出した操作をhistoryに戻す
        updateScoreDecorations();
        updateButtonsState();
    });

    /**
     * 「すべての加工をリセット」ボタンが押されたときの処理
     */
    resetMidiBtn.addEventListener("click", () => {
        if (!confirm("本当にすべての加工をリセットしますか？")) return;
        history = [];
        redoStack = [];
        updateScoreDecorations();
        updateButtonsState();
        compareContainer.style.display = "none";
        saveArea.style.display = "none";
        statusMessage.textContent = "すべての加工をリセットしました。";
    });

    /**
     * 「音源を生成」ボタンが押されたときの処理
     */
    generateAudioBtn.addEventListener("click", async () => {
        const spinner = document.getElementById('loading-spinner');
        const progressArea = document.getElementById('progress-area');
        spinner.classList.remove('hidden');
        progressArea.classList.remove('hidden');
        generateAudioBtn.disabled = true;

        try {
            // サーバーに全操作履歴(history)を送信して音源生成をリクエスト
            const res = await fetch('/generate_audio', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    history: history,
                    partIndex: currentPartIndex,
                    partName: partSelector.selectedOptions[0].textContent
                })
            });
            const { task_id } = await res.json(); // 非同期処理のタスクIDを受け取る
            
            // 定期的に進捗を問い合わせる（ポーリング）
            const intervalId = setInterval(async () => {
                try {
                    const statusRes = await fetch(`/generation_status/${task_id}`);
                    const data = await statusRes.json();
                    
                    const progressBar = document.getElementById('progress-bar');
                    const progressText = document.getElementById('progress-text');

                    if (data.state === 'PROGRESS') {
                        // 進行中の場合、プログレスバーとテキストを更新
                        const percentage = data.total > 0 ? (data.current / data.total) * 100 : 0;
                        progressBar.style.width = `${percentage}%`;
                        progressText.textContent = `音源生成中... (${data.message})`;
                    } else if (data.state === 'SUCCESS') {
                        // 成功した場合、ポーリングを停止し、結果を表示
                        clearInterval(intervalId);
                        progressBar.style.width = '100%';
                        progressText.textContent = '生成完了！';
                        statusMessage.textContent = '✅ 音源の生成が完了しました！';
                        
                        // 生成されたファイルのパスをグローバル変数に保存
                        window.lastGeneratedWavPaths = data.result;
                        // 比較・保存エリアを表示
                        compareContainer.style.display = 'block';
                        saveArea.style.display = 'block';
                        flashPlayer(); // 完了を視覚的に知らせる
                        
                        // 少し待ってからプログレス表示を隠す
                        setTimeout(() => {
                             progressArea.classList.add('hidden');
                             spinner.classList.add('hidden');
                             generateAudioBtn.disabled = false;
                        }, 1500);

                    } else if (data.state === 'FAILURE') {
                        // 失敗した場合、ポーリングを停止し、エラーメッセージを表示
                        clearInterval(intervalId);
                        statusMessage.textContent = `⚠️ 音源生成エラー: ${data.message}`;
                        progressText.textContent = `エラーが発生しました。`;
                        spinner.classList.add('hidden');
                        generateAudioBtn.disabled = false;
                    }
                } catch (pollErr) {
                    clearInterval(intervalId);
                    console.error("Polling error:", pollErr);
                    statusMessage.textContent = '⚠️ 進捗確認中にエラーが発生しました。';
                    spinner.classList.add('hidden');
                    generateAudioBtn.disabled = false;
                }
            }, 1500); // 1.5秒ごとに進捗を確認

        } catch (err) {
            console.error("Generation start error:", err);
            statusMessage.textContent = '⚠️ 音源生成の開始に失敗しました。';
            spinner.classList.add('hidden');
            generateAudioBtn.disabled = false;
        }
    });
    
    /**
     * 音源生成完了時に、比較再生エリアを点滅させてユーザーに知らせる
     */
    function flashPlayer() {
        compareContainer.classList.remove('flash-success');
        void compareContainer.offsetWidth; // 再描画を強制
        compareContainer.classList.add('flash-success');
    }

    /**
     * MIDI保存ボタンがクリックされたときの処理 (イベント委譲)
     */
    document.addEventListener('click', function(event) {
        if (event.target?.id === 'save-midi-btn') {
            const midiPath = window.lastGeneratedWavPaths?.processed_midi_full;
            if(!midiPath) return alert("保存対象のMIDIファイルが見つかりません。");
            
            // aタグを動的に作成してクリックさせ、ダウンロードをトリガーする
            const a = document.createElement('a');
            a.href = midiPath;
            a.download = midiPath.split('/').pop(); // URLからファイル名部分を抽出
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }
    });

    /**
     * 「パラメータを調整」ボタンがクリックされたとき、パラメータ調整UIの表示/非表示を切り替える
     */
    toggleParamsBtn.addEventListener("click", () => {
        parameterEditor.classList.toggle("hidden");
        toggleParamsBtn.classList.toggle("active");
    });

    /**
     * 選択されたプリセットのデフォルト値をパラメータ入力欄に反映する
     */
    function updateParameterInputs() {
        const selectedPresetName = tempoPreset.value;
        // PRESETSオブジェクト（別ファイルで定義されている想定）から値を取得
        const params = PRESETS.tempo_expressions[selectedPresetName]?.params;
        if (params) {
            paramBaseCc2.value = params.base_cc2 ?? 0;
            paramPeakCc2.value = params.peak_cc2 ?? 0;
            paramOnsetMs.value = params.onset_ms ?? 0;
        }
    }

    // プリセットの選択が変更されたら、入力欄も更新するようイベントリスナーを設定
    tempoPreset.addEventListener("change", updateParameterInputs);
    // ページ読み込み時に、初期選択されているプリセットの値で入力欄を初期化
    updateParameterInputs(); 
});

/**
 * 指定されたタイプのWAVファイルを再生する
 * @param {string} type - 再生する音源の種類 ("original" または "processed")
 * @param {Element} clickedButton - クリックされた再生ボタンのDOM要素
 */
function playWAV(type, clickedButton) {
    const wavPath = window.lastGeneratedWavPaths?.[`${type}_wav`];
    if (!wavPath) return;

    // 加工後の音源は毎回内容が変わる可能性があるため、キャッシュを無効にするクエリパラメータを付与
    const finalUrl = (type.startsWith("processed")) ? `${wavPath}?v=${new Date().getTime()}` : wavPath;

    // 他の音声が再生中なら停止し、再生ボタンのハイライトをリセット
    document.querySelectorAll('.compare-block button').forEach(btn => btn.classList.remove('is-playing'));
    if (window.currentAudio) window.currentAudio.pause();

    // 新しいAudioオブジェクトを作成して再生
    window.currentAudio = new Audio(finalUrl);
    window.currentAudio.play().then(() => clickedButton?.classList.add('is-playing'));
    // 再生が終了したらハイライトを解除
    window.currentAudio.onended = () => clickedButton?.classList.remove('is-playing');
}

/**
 * 現在再生中のWAVファイルを停止する
 */
function stopWAV() {
    if (window.currentAudio) {
        window.currentAudio.pause();
        window.currentAudio.currentTime = 0; // 再生位置を先頭に戻す
        // すべての再生ボタンのハイライトを解除
        document.querySelectorAll('.compare-block button').forEach(btn => btn.classList.remove('is-playing'));
    }
}