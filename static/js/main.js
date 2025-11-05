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
    const applyBtn = document.getElementById("apply-btn");
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
    window.lastFlaskResponse = { history: [], redo_stack: [] };
    let currentAudio = null;
    let redoStack = []; // Redo操作をクライアント側で模倣するためのスタック

    function updateScoreDecorations(history) {
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
    
    function handleServerResponse(result) {
        if (result.error) {
            alert(`エラー: ${result.error}`);
            statusMessage.textContent = `⚠️ エラー: ${result.error}`;
            updateButtonsState();
            throw new Error(result.error);
        }
        statusMessage.textContent = `✅ ${result.message || '処理が完了しました。'}`;
        window.lastFlaskResponse = result;
        if (result.status !== 'processing') {
             redoStack = []; // サーバーからの同期的な応答でクライアントのRedoスタックはリセット
        }
        updateButtonsState();
        if (result.history.length === 0) {
            compareContainer.style.display = "none";
            saveArea.style.display = "none";
            updateScoreDecorations([]);
        } else {
            compareContainer.style.display = "block";
            saveArea.style.display = "block";
            updateScoreDecorations(result.history);
            if (result.status !== 'processing') {
                flashPlayer();
            }
        }
    }
    
    function updateButtonsState() {
        const history = window.lastFlaskResponse?.history || [];
        undoBtn.disabled = history.length === 0;
        redoBtn.disabled = redoStack.length === 0;
        resetMidiBtn.disabled = history.length === 0;
    }

    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        statusMessage.textContent = "⌛ ファイルをアップロード中...";
        const formData = new FormData(uploadForm);
        try {
            const res = await fetch("/upload", { method: "POST", body: formData });
            const result = await res.json();
            handleServerResponse(result);
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
        setTimeout(() => { updateScoreDecorations(window.lastFlaskResponse?.history); }, 200);
        statusMessage.textContent = "✅ 音符をクリックして範囲を指定できます。";
    }

    async function handleNoteClick(clickedEl) {
        const noteElements = Array.from(document.querySelectorAll(".abcjs-note"));
        const noteIndex = noteElements.indexOf(clickedEl);
        if (noteIndex === -1) return;

        // 頂点選択モードの時、選択範囲外のクリックは無視する
        if (selectionMode === 'peak') {
            const startIndex = selectedNotes.start.index;
            const endIndex = selectedNotes.end.index;
            if (noteIndex < startIndex || noteIndex > endIndex) {
                return;
            }
        }
        
        const noteMap = allNoteMaps[currentPartIndex];
        const tick = noteMap?.[noteIndex]?.tick ?? null;
        const currentMode = selectionMode;
        
        selectedNotes[currentMode] = { index: noteIndex, tick, el: clickedEl };
        
        if (currentMode === 'start') {
            selectionMode = 'end';
        } else if (currentMode === 'end') {
            // 開始・終了が逆なら入れ替える
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
        document.querySelectorAll(".abcjs-note.apex-candidate").forEach(el => el.classList.remove("apex-candidate"));

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
            statusMessage.textContent = '✅ 黄色の頂点候補から1つ選択してください (候補以外も選択可能です)';

        } catch (err) {
            statusMessage.textContent = `⚠️ 頂点推定エラー: ${err.message}`;
        }
    }

    function updateSelectionUI() {
        document.querySelectorAll(".abcjs-note.selected, .abcjs-note.selected-end, .abcjs-note.selected-peak").forEach(el => el.classList.remove("selected", "selected-end", "selected-peak"));
        if (selectedNotes.start?.el) selectedNotes.start.el.classList.add("selected");
        if (selectedNotes.end?.el) selectedNotes.end.el.classList.add("selected-end");
        if (selectedNotes.peak?.el) selectedNotes.peak.el.classList.add("selected-peak");
        
        document.getElementById("start-note-info").textContent = selectedNotes.start ? `index=${selectedNotes.start.index}` : "未選択";
        document.getElementById("end-note-info").textContent = selectedNotes.end ? `index=${selectedNotes.end.index}` : "未選択";
        document.getElementById("peak-note-info").textContent = selectedNotes.peak ? `index=${selectedNotes.peak.index}` : "未選択";
        
        applyBtn.disabled = !(selectedNotes.start && selectedNotes.end && selectedNotes.peak);
        
        // 頂点選択モードでなければ、候補のハイライトを消す
        if (selectionMode !== 'peak') {
            document.querySelectorAll(".abcjs-note.apex-candidate").forEach(el => el.classList.remove("apex-candidate"));
        }
    }

    resetSelectionBtn.addEventListener("click", () => {
        selectionMode = "start";
        selectedNotes = { start: null, end: null, peak: null };
        updateSelectionUI();
        statusMessage.textContent = "選択をリセットしました。";
    });

    async function handleOptimisticUpdate(endpoint, optimisticUpdateFn, spinnerId, requestBody = null) {
        const originalHistory = window.lastFlaskResponse?.history ? JSON.parse(JSON.stringify(window.lastFlaskResponse.history)) : [];
        const spinner = document.getElementById(spinnerId);
        
        optimisticUpdateFn();
        updateButtonsState();

        spinner.classList.remove("hidden");
        [undoBtn, redoBtn, resetMidiBtn, applyBtn].forEach(btn => btn.disabled = true);
        document.querySelectorAll('#compare-container button').forEach(btn => btn.disabled = true);

        try {
            const fetchOptions = {
                method: "POST",
                headers: { 'Content-Type': 'application/json' },
                ...(requestBody && { body: JSON.stringify(requestBody) })
            };
            const res = await fetch(endpoint, fetchOptions);
            const result = await res.json();
            if (result.error) throw new Error(result.error);
            handleServerResponse(result);
            checkAudioStatus([result.processed_single_wav, result.processed_full_wav]);
        } catch (err) {
            statusMessage.textContent = `⚠️ エラー: ${err.message}`;
            window.lastFlaskResponse.history = originalHistory; // 履歴を元に戻す
            redoStack = []; // エラー時はクライアントのRedoスタックもクリア
            updateScoreDecorations(originalHistory);
            updateButtonsState();
        } finally {
            spinner.classList.add("hidden");
        }
    }

    undoBtn.addEventListener("click", () => {
        if (undoBtn.disabled) return;
        handleOptimisticUpdate('/undo', () => {
            let undoneAction = window.lastFlaskResponse.history.pop();
            if (undoneAction) redoStack.push(undoneAction);
            updateScoreDecorations(window.lastFlaskResponse.history);
            statusMessage.textContent = "楽譜を元に戻しました。音源を生成中です...";
        }, 'undo-spinner');
    });
    
    redoBtn.addEventListener("click", () => {
        if (redoBtn.disabled) return;
        handleOptimisticUpdate('/redo', () => {
            let redoneAction = redoStack.pop();
            if (redoneAction) window.lastFlaskResponse.history.push(redoneAction);
            updateScoreDecorations(window.lastFlaskResponse.history);
            statusMessage.textContent = "楽譜をやり直しました。音源を生成中です...";
        }, 'redo-spinner');
    });

    resetMidiBtn.addEventListener("click", () => {
        if (resetMidiBtn.disabled) return;
        if (!confirm("本当にすべての加工をリセットしますか？この操作は元に戻せません。")) return;
        handleOptimisticUpdate('/reset_midi', () => {
            redoStack = [...window.lastFlaskResponse.history].reverse(); // 元の履歴をRedoスタックに
            window.lastFlaskResponse.history = [];
            updateScoreDecorations([]);
            statusMessage.textContent = "楽譜をリセットしました。音源を生成中です...";
        }, 'reset-spinner');
    });

    applyBtn.addEventListener("click", () => {
        if (applyBtn.disabled) return;
        const partIndex = currentPartIndex;
        const phraseInfo = { start_index: selectedNotes.start.index, end_index: selectedNotes.end.index, peak_index: selectedNotes.peak.index };
        const tempoSelection = tempoPreset.value;
        const requestBody = {
            partIndex, partName: partSelector.selectedOptions[0].textContent,
            phrase: phraseInfo, presetParams: PRESETS.tempo_expressions[tempoSelection].params, presetName: tempoSelection
        };
        handleOptimisticUpdate('/process', () => {
            const newInstruction = { phrase: phraseInfo, preset_name: tempoSelection };
            const history = window.lastFlaskResponse.history;
            const foundIndex = history.findIndex(instr => JSON.stringify(instr.phrase) === JSON.stringify(newInstruction.phrase));
            if (foundIndex !== -1) {
                 redoStack = [JSON.parse(JSON.stringify(history[foundIndex]))];
                 history[foundIndex] = newInstruction;
            } else {
                 history.push(newInstruction);
                 redoStack = [];
            }
            updateScoreDecorations(history);
            statusMessage.textContent = "楽譜に反映しました。音源を生成中です...";
        }, 'loading-spinner', requestBody);
    });
    
    function checkAudioStatus(filesToCheck) {
        const intervalId = setInterval(async () => {
            try {
                const res = await fetch('/check_audio_status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files: filesToCheck }) });
                const result = await res.json();
                if (result.status === 'ready') {
                    clearInterval(intervalId);
                    statusMessage.textContent = "✅ 音声ファイルの生成が完了しました！";
                    document.querySelectorAll('#compare-container button').forEach(btn => btn.disabled = false);
                    updateButtonsState();
                    applyBtn.disabled = !(selectedNotes.start && selectedNotes.end && selectedNotes.peak);
                    flashPlayer();
                }
            } catch (err) {
                console.error('Audio status check failed:', err);
                clearInterval(intervalId);
                updateButtonsState();
            }
        }, 2000);
    }
    
    function flashPlayer() {
        compareContainer.classList.remove('flash-success');
        void compareContainer.offsetWidth;
        compareContainer.classList.add('flash-success');
    }

    document.addEventListener('click', function(event) {
        if (event.target?.id === 'save-midi-btn') {
            const wavPath = window.lastFlaskResponse?.processed_full_wav;
            if(!wavPath) return alert("保存対象のMIDIファイルが見つかりません。");
            const midiFilename = wavPath.split('/').pop().replace('_full_processed.wav', '_full_processed.mid');
            const finalMidiUrl = `/output/midi/full_parts/processed/${midiFilename}`;
            const a = document.createElement('a');
            a.href = finalMidiUrl;
            a.download = midiFilename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }
    });
});

function playWAV(type, clickedButton) {
    const wavUrl = window.lastFlaskResponse?.[type === "processed_single" ? "processed_single_wav" : type === "original_single" ? "original_single_wav" : type === "processed_full" ? "processed_full_wav" : "original_full_wav"];
    if (!wavUrl) return;
    const cacheBustingUrl = `${wavUrl}?v=${new Date().getTime()}`;
    document.querySelectorAll('.compare-block button').forEach(btn => btn.classList.remove('is-playing'));
    if (window.currentAudio) window.currentAudio.pause();
    window.currentAudio = new Audio(cacheBustingUrl);
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