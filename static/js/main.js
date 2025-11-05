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

    // --- グローバル変数 ---
    let selectionMode = "start";
    let selectedNotes = { start: null, end: null, peak: null };
    let allPartAbcData = {};
    let allNoteMaps = {};
    let currentPartIndex = null;
    let history = []; // 適用した操作の履歴
    let redoStack = []; // Redo用のスタック
    let currentAudio = null;
    window.lastGeneratedWavPaths = {}; // 生成されたWAVのパスを保持

    /**
     * 黄色の頂点候補ハイライトをすべて消去するヘルパー関数
     */
    function clearApexCandidatesHighlights() {
        document.querySelectorAll(".abcjs-note.apex-candidate").forEach(el => el.classList.remove("apex-candidate"));
    }

    function updateScoreDecorations() {
        document.querySelectorAll('.decoration-group').forEach(el => el.remove());
        if (!history || history.length === 0) return;
        const allNoteElements = Array.from(document.querySelectorAll(".abcjs-note"));
        if (allNoteElements.length === 0) return;
        const scoreSVG = scoreDisplay.querySelector("svg");
        if (!scoreSVG) return;

        history.forEach(instruction => {
            const phrase = instruction.phrase;
            const presetName = instruction.preset_name;
            const startNoteEl = allNoteElements[phrase.start_index];
            const endNoteEl = allNoteElements[phrase.end_index];
            const peakNoteEl = allNoteElements[phrase.peak_index];
            if (startNoteEl && endNoteEl && peakNoteEl) {
                const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
                group.classList.add('decoration-group');
                const svgRect = scoreSVG.getBoundingClientRect();
                let lineNotes = [];
                for (let i = phrase.start_index; i <= phrase.end_index; i++) {
                    const currentNoteEl = allNoteElements[i];
                    if (!currentNoteEl) continue;
                    if (lineNotes.length === 0) {
                        lineNotes.push(currentNoteEl);
                    } else {
                        const prevNoteRect = lineNotes[lineNotes.length - 1].getBoundingClientRect();
                        const currentNoteRect = currentNoteEl.getBoundingClientRect();
                        if (Math.abs(prevNoteRect.top - currentNoteRect.top) < prevNoteRect.height) {
                            lineNotes.push(currentNoteEl);
                        } else {
                            drawHighlightForLine(lineNotes, group, svgRect);
                            lineNotes = [currentNoteEl];
                        }
                    }
                }
                if (lineNotes.length > 0) drawHighlightForLine(lineNotes, group, svgRect);
                const peakRect = peakNoteEl.getBoundingClientRect();
                const peakHighlight = document.createElementNS("http://www.w3.org/2000/svg", "rect");
                const padding = 2;
                peakHighlight.setAttribute("x", peakRect.left - svgRect.left - padding);
                peakHighlight.setAttribute("y", peakRect.top - svgRect.top - padding);
                peakHighlight.setAttribute("width", peakRect.width + (padding * 2));
                peakHighlight.setAttribute("height", peakRect.height + (padding * 2));
                peakHighlight.classList.add('phrase-peak-highlight');
                group.appendChild(peakHighlight);
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
    
    function updateButtonsState() {
        undoBtn.disabled = history.length === 0;
        redoBtn.disabled = redoStack.length === 0;
        resetMidiBtn.disabled = history.length === 0;
        generateAudioBtn.disabled = history.length === 0;
    }

    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        statusMessage.textContent = "⌛ ファイルをアップロード中...";
        scoreDisplay.innerHTML = ""; // 前の楽譜をクリア
        const formData = new FormData(uploadForm);
        try {
            const res = await fetch("/upload", { method: "POST", body: formData });
            const result = await res.json();
            if(result.error) throw new Error(result.error);
            
            statusMessage.textContent = `✅ ${result.message}。パートを選択してください。`;
            allPartAbcData = result.all_abc_data;
            partSelector.innerHTML = "";
            result.parts.forEach((p) => {
                const opt = document.createElement("option");
                opt.value = p.index;
                opt.textContent = p.name || `Part ${p.index + 1}`;
                opt.dataset.noteMap = p.note_map;
                partSelector.appendChild(opt);
            });
            partSelector.disabled = false;
            // 初期化
            history = [];
            redoStack = [];
            updateButtonsState();
            compareContainer.style.display = "none";
            saveArea.style.display = "none";
            // partSelector.dispatchEvent(new Event('change')); // この行を削除！
        } catch (err) {
            console.error(err);
            statusMessage.textContent = "⚠️ エラー: " + err.message;
        }
    });

    partSelector.addEventListener("change", async () => {
        currentPartIndex = parseInt(partSelector.value);
        if (isNaN(currentPartIndex)) return;
        const noteMapFilename = partSelector.selectedOptions[0].dataset.noteMap;
        if (noteMapFilename) {
            const res = await fetch(`/output/${noteMapFilename}`);
            if (res.ok) allNoteMaps[currentPartIndex] = await res.json();
        }
        renderScore(allPartAbcData[currentPartIndex]);
    });

    function renderScore(abcText) {
        scoreDisplay.innerHTML = "";
        ABCJS.renderAbc("score-display", abcText, { add_classes: true, staffwidth: 900, clickListener: (abcElem, tuneNumber, classes, analysis, drag, mouseEvent) => {
            const clickedEl = mouseEvent.target.closest(".abcjs-note");
            if (clickedEl) handleNoteClick(clickedEl);
        }});
        setTimeout(() => { updateScoreDecorations(); }, 200);
        statusMessage.textContent = "✅ 音符をクリックして範囲を指定できます。";
    }

    async function handleNoteClick(clickedEl) {
        const noteElements = Array.from(document.querySelectorAll(".abcjs-note"));
        const noteIndex = noteElements.indexOf(clickedEl);
        if (noteIndex === -1) return;

        if (selectionMode === 'peak') {
            const startIndex = selectedNotes.start.index;
            const endIndex = selectedNotes.end.index;
            if (noteIndex < startIndex || noteIndex > endIndex) return;
        }
        
        const noteMap = allNoteMaps[currentPartIndex];
        const tick = noteMap?.[noteIndex]?.tick ?? null;
        const currentMode = selectionMode;

        if (currentMode === 'start') {
            clearApexCandidatesHighlights();
            selectedNotes = { start: null, end: null, peak: null };
        }
        
        selectedNotes[currentMode] = { index: noteIndex, tick, el: clickedEl };
        
        if (currentMode === 'start') {
            selectionMode = 'end';
        } else if (currentMode === 'end') {
            if (selectedNotes.start.index > selectedNotes.end.index) {
                [selectedNotes.start, selectedNotes.end] = [selectedNotes.end, selectedNotes.start];
            }
            selectionMode = 'peak';
            await fetchApexCandidates();
        } else if (currentMode === 'peak') {
            selectionMode = 'start';
        }

        updateSelectionUI();
    }
    
    async function fetchApexCandidates() {
        statusMessage.textContent = '⏳ 頂点候補を推定中...';
        clearApexCandidatesHighlights();

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
            
            const noteElements = Array.from(document.querySelectorAll(".abcjs-note"));
            result.apex_candidates.forEach(index => {
                if (noteElements[index]) {
                    noteElements[index].classList.add('apex-candidate');
                }
            });
            statusMessage.textContent = '✅ 黄色の頂点候補から1つ選択してください';
        } catch (err) {
            statusMessage.textContent = `⚠️ 頂点推定エラー: ${err.message}`;
        }
    }

    function updateSelectionUI() {
        document.querySelectorAll(".abcjs-note.selected, .abcjs-note.selected-end, .abcjs-note.selected-peak").forEach(el => el.classList.remove("selected", "selected-end", "selected-peak"));
        if (selectedNotes.start?.el) selectedNotes.start.el.classList.add("selected");
        if (selectedNotes.end?.el) selectedNotes.end.el.classList.add("selected-end");
        if (selectedNotes.peak?.el) selectedNotes.peak.el.classList.add("selected-peak");
        
        document.getElementById("start-note-info").textContent = selectedNotes.start ? `index=${selectedNotes.start.index} / tick=${selectedNotes.start.tick}` : "未選択";
        document.getElementById("end-note-info").textContent = selectedNotes.end ? `index=${selectedNotes.end.index} / tick=${selectedNotes.end.tick}` : "未選択";
        document.getElementById("peak-note-info").textContent = selectedNotes.peak ? `index=${selectedNotes.peak.index} / tick=${selectedNotes.peak.tick}` : "未選択";

        applyToScoreBtn.disabled = !(selectedNotes.start && selectedNotes.end && selectedNotes.peak);
    }

    resetSelectionBtn.addEventListener("click", () => {
        selectionMode = "start";
        selectedNotes = { start: null, end: null, peak: null };
        clearApexCandidatesHighlights();
        updateSelectionUI();
        statusMessage.textContent = "選択をリセットしました。";
    });

    // --- 新しい操作フロー ---

    applyToScoreBtn.addEventListener("click", () => {
        if (applyToScoreBtn.disabled) return;
        
        const phraseInfo = { start_index: selectedNotes.start.index, end_index: selectedNotes.end.index, peak_index: selectedNotes.peak.index };
        const tempoSelection = tempoPreset.value;

        const newInstruction = {
            phrase: phraseInfo,
            preset_params: PRESETS.tempo_expressions[tempoSelection].params,
            preset_name: tempoSelection,
            part_index: currentPartIndex,
            part_name: partSelector.selectedOptions[0].textContent,
        };

        const foundIndex = history.findIndex(instr => JSON.stringify(instr.phrase) === JSON.stringify(newInstruction.phrase));
        if (foundIndex !== -1) {
            history[foundIndex] = newInstruction;
        } else {
            history.push(newInstruction);
        }
        
        redoStack = []; // 新しい操作をしたらRedoスタックはクリア
        updateScoreDecorations();
        updateButtonsState();
        
        // 選択状態をリセット
        resetSelectionBtn.click();
        statusMessage.textContent = "✅ 楽譜に反映しました。音源生成ボタンでWAVを作成できます。";
    });

    undoBtn.addEventListener("click", () => {
        if (history.length === 0) return;
        const undoneAction = history.pop();
        redoStack.push(undoneAction);
        updateScoreDecorations();
        updateButtonsState();
    });

    redoBtn.addEventListener("click", () => {
        if (redoStack.length === 0) return;
        const redoneAction = redoStack.pop();
        history.push(redoneAction);
        updateScoreDecorations();
        updateButtonsState();
    });

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

    generateAudioBtn.addEventListener("click", async () => {
        const spinner = document.getElementById('loading-spinner');
        const progressArea = document.getElementById('progress-area');
        spinner.classList.remove('hidden');
        progressArea.classList.remove('hidden');
        generateAudioBtn.disabled = true;

        try {
            const res = await fetch('/generate_audio', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    history: history,
                    partIndex: currentPartIndex,
                    partName: partSelector.selectedOptions[0].textContent
                })
            });
            const { task_id } = await res.json();
            
            // ポーリングで進捗を確認
            const intervalId = setInterval(async () => {
                try {
                    const statusRes = await fetch(`/generation_status/${task_id}`);
                    const data = await statusRes.json();
                    
                    const progressBar = document.getElementById('progress-bar');
                    const progressText = document.getElementById('progress-text');

                    if (data.state === 'PROGRESS') {
                        const percentage = data.total > 0 ? (data.current / data.total) * 100 : 0;
                        progressBar.style.width = `${percentage}%`;
                        progressText.textContent = `音源生成中... (${data.message})`;
                    } else if (data.state === 'SUCCESS') {
                        clearInterval(intervalId);
                        progressBar.style.width = '100%';
                        progressText.textContent = '生成完了！';
                        statusMessage.textContent = '✅ 音源の生成が完了しました！';
                        
                        window.lastGeneratedWavPaths = data.result;
                        compareContainer.style.display = 'block';
                        saveArea.style.display = 'block';
                        flashPlayer();
                        
                        setTimeout(() => {
                             progressArea.classList.add('hidden');
                             spinner.classList.add('hidden');
                             generateAudioBtn.disabled = false;
                        }, 1500);

                    } else if (data.state === 'FAILURE') {
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
            }, 1500);

        } catch (err) {
            console.error("Generation start error:", err);
            statusMessage.textContent = '⚠️ 音源生成の開始に失敗しました。';
            spinner.classList.add('hidden');
            generateAudioBtn.disabled = false;
        }
    });
    
    function flashPlayer() {
        compareContainer.classList.remove('flash-success');
        void compareContainer.offsetWidth;
        compareContainer.classList.add('flash-success');
    }

    document.addEventListener('click', function(event) {
        if (event.target?.id === 'save-midi-btn') {
            const midiPath = window.lastGeneratedWavPaths?.processed_midi_full;
            if(!midiPath) return alert("保存対象のMIDIファイルが見つかりません。");
            
            const a = document.createElement('a');
            a.href = midiPath;
            a.download = midiPath.split('/').pop();
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }
    });
});

function playWAV(type, clickedButton) {
    const wavPath = window.lastGeneratedWavPaths?.[`${type}_wav`];
    if (!wavPath) return;

    // 元音源は毎回同じなのでキャッシュバスティング不要
    const finalUrl = (type.startsWith("processed")) ? `${wavPath}?v=${new Date().getTime()}` : wavPath;

    document.querySelectorAll('.compare-block button').forEach(btn => btn.classList.remove('is-playing'));
    if (window.currentAudio) window.currentAudio.pause();
    window.currentAudio = new Audio(finalUrl);
    window.currentAudio.play().then(() => clickedButton?.classList.add('is-playing'));
    window.currentAudio.onended = () => clickedButton?.classList.remove('is-playing');
}

function stopWAV() {
    if (window.currentAudio) {
        window.currentAudio.pause();
        window.currentAudio.currentTime = 0;
        document.querySelectorAll('.compare-block button').forEach(btn => btn.classList.remove('is-playing'));
    }
}