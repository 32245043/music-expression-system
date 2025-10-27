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

    //　再生プレイヤー
    const compareContainer = document.getElementById("compare-container");
    const saveArea = document.getElementById("save-area");

    // --- グローバル変数 ---
    let selectionMode = "start"; // "start", "end", "peak"のどれか
    let selectedNotes = { start: null, end: null, peak: null };
    let allPartAbcData = {}; //全パートのABCデータを保持
    let allNoteMaps = {};    // 全パートのノートマップを保持
    let currentPartIndex = null;

    // WAV再生用にサーバーからのレスポンスを保持する
    window.lastFlaskResponse = {};
    let currentAudio = null;

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

                // === 1. フレーズ全体のハイライトを描画 ===
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
                if (lineNotes.length > 0) {
                    drawHighlightForLine(lineNotes, group, svgRect);
                }

                // === 2. 頂点音符のハイライトを重ねて描画 ===
                const peakRect = peakNoteEl.getBoundingClientRect();
                const peakHighlight = document.createElementNS("http://www.w3.org/2000/svg", "rect");
                const padding = 2;
                peakHighlight.setAttribute("x", peakRect.left - svgRect.left - padding);
                peakHighlight.setAttribute("y", peakRect.top - svgRect.top - padding);
                peakHighlight.setAttribute("width", peakRect.width + (padding * 2));
                peakHighlight.setAttribute("height", peakRect.height + (padding * 2));
                peakHighlight.classList.add('phrase-peak-highlight');
                group.appendChild(peakHighlight);

                // === 3. 発想標語のテキストを描画 ===
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

    // 指定された音符の配列から1行分のハイライトを作成するヘルパー関数
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
            throw new Error(result.error);
        }
        if (result.message) {
             alert(result.message);
             statusMessage.textContent = `✅ ${result.message}`;
        }
        window.lastFlaskResponse = result;
        if (result.history_empty) {
            compareContainer.style.display = "none";
            saveArea.style.display = "none";
            updateScoreDecorations([]);
        } else {
            compareContainer.style.display = "block";
            saveArea.style.display = "block";
            flashPlayer();
            updateScoreDecorations(result.history);
        }
    }

    // ============================================
    // 1️. ファイルアップロード
    // ============================================
    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        compareContainer.style.display = "none";
        saveArea.style.display = "none";
        statusMessage.textContent = "⌛ ファイルをアップロード中...";
        const formData = new FormData(uploadForm);
        try {
            const res = await fetch("/upload", { method: "POST", body: formData });
            const result = await res.json();
            if (result.error) throw new Error(result.error);
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
            statusMessage.textContent = "✅ ファイル読み込み完了。パートを選択してください。";
        } catch (err) {
            console.error(err);
            statusMessage.textContent = "⚠️ エラー: " + err.message;
        }
    });

    // ============================================
    // 2️. パート選択
    // ============================================
    partSelector.addEventListener("change", async () => {
        const partIndex = parseInt(partSelector.value);
        currentPartIndex = partIndex;
        if (isNaN(partIndex)) return;
        const abcText = allPartAbcData[partIndex];
        if (!abcText) return;
        const noteMapFilename = partSelector.selectedOptions[0].dataset.noteMap;
        if (noteMapFilename) {
            const res = await fetch(`/output/${noteMapFilename}`);
            if (res.ok) {
                allNoteMaps[partIndex] = await res.json();
            }
        }
        renderScore(abcText);
    });

    // ============================================
    // 3️. 楽譜描画
    // ============================================
    function renderScore(abcText) {
        scoreDisplay.innerHTML = "";
        ABCJS.renderAbc("score-display", abcText, { add_classes: true, staffwidth: 900, clickListener: (abcElem, tuneNumber, classes, analysis, drag, mouseEvent) => {
            const clickedEl = mouseEvent.target.closest(".abcjs-note");
            if (clickedEl) handleNoteClick(clickedEl);
        }});
        setTimeout(() => { updateScoreDecorations(window.lastFlaskResponse?.history); }, 200);
        statusMessage.textContent = "✅ 音符をクリックして範囲を指定できます。";
    }

    // ============================================
    // 4️. 音符クリック
    // ============================================
    function handleNoteClick(clickedEl) {
        const noteElements = Array.from(document.querySelectorAll(".abcjs-note"));
        const noteIndex = noteElements.indexOf(clickedEl);
        if (noteIndex === -1) return;
        const noteMap = allNoteMaps[currentPartIndex];
        const tick = noteMap && noteMap[noteIndex] ? noteMap[noteIndex].tick : null;
        const currentMode = selectionMode;
        const nextMode = (currentMode === "start") ? "end" : (currentMode === "end" ? "peak" : "start");
        selectedNotes[currentMode] = { index: noteIndex, tick, el: clickedEl };
        selectionMode = nextMode;
        updateSelectionUI();
    }

    // ============================================
    // 5️. UI更新
    // ============================================
    function updateSelectionUI() {
        document.querySelectorAll(".abcjs-note.selected, .abcjs-note.selected-end, .abcjs-note.selected-peak").forEach(el => el.classList.remove("selected", "selected-end", "selected-peak"));
        if (selectedNotes.start?.el) selectedNotes.start.el.classList.add("selected");
        if (selectedNotes.end?.el) selectedNotes.end.el.classList.add("selected-end");
        if (selectedNotes.peak?.el) selectedNotes.peak.el.classList.add("selected-peak");
        document.getElementById("start-note-info").textContent = selectedNotes.start ? `index=${selectedNotes.start.index} / tick=${selectedNotes.start.tick}` : "未選択";
        document.getElementById("peak-note-info").textContent = selectedNotes.peak ? `index=${selectedNotes.peak.index} / tick=${selectedNotes.peak.tick}` : "未選択";
        document.getElementById("end-note-info").textContent = selectedNotes.end ? `index=${selectedNotes.end.index} / tick=${selectedNotes.end.tick}` : "未選択";
        applyBtn.disabled = !(selectedNotes.start && selectedNotes.end && selectedNotes.peak);
    }

    // ============================================
    // 6️. 選択リセット
    // ============================================
    resetSelectionBtn.addEventListener("click", () => {
        selectionMode = "start";
        selectedNotes = { start: null, end: null, peak: null };
        updateSelectionUI();
        statusMessage.textContent = "選択をリセットしました。";
    });

    undoBtn.addEventListener("click", async () => {
        const undoSpinner = document.getElementById("undo-spinner");
        undoSpinner.classList.remove("hidden");
        undoBtn.disabled = true;
        resetMidiBtn.disabled = true;
        statusMessage.textContent = "⏳ 元に戻しています...";
        try {
            const res = await fetch("/undo", { method: "POST" });
            const result = await res.json();
            handleServerResponse(result);
        } catch (err) {
            console.error(err);
            statusMessage.textContent = `⚠️ Undoエラー: ${err.message}`;
        } finally {
            undoSpinner.classList.add("hidden");
            undoBtn.disabled = false;
            resetMidiBtn.disabled = false;
        }
    });

    resetMidiBtn.addEventListener("click", async () => {
        if (!confirm("本当にすべての加工をリセットしますか？この操作は元に戻せません。")) return;
        const resetSpinner = document.getElementById("reset-spinner");
        resetSpinner.classList.remove("hidden");
        resetMidiBtn.disabled = true;
        undoBtn.disabled = true;
        statusMessage.textContent = "⏳ リセット中...";
        try {
            const res = await fetch("/reset_midi", { method: "POST" });
            const result = await res.json();
            handleServerResponse(result);
        } catch (err) {
            console.error(err);
            statusMessage.textContent = `⚠️ リセットエラー: ${err.message}`;
        } finally {
            resetSpinner.classList.add("hidden");
            resetMidiBtn.disabled = false;
            undoBtn.disabled = false;
        }
    });

    // ============================================
    // 7️. 「適用」ボタンクリック
    // ============================================
    applyBtn.addEventListener("click", async () => {
        if (!selectedNotes.start || !selectedNotes.end || !selectedNotes.peak) {
            alert("開始・終了・頂点を順に選択してください。");
            return;
        }
        const loadingSpinner = document.getElementById("loading-spinner");
        loadingSpinner.classList.remove("hidden");
        applyBtn.disabled = true;
        statusMessage.textContent = "⏳ MIDIを加工してWAVを生成中...";
        try {
            const partIndex = currentPartIndex;
            const phraseInfo = { start_index: selectedNotes.start.index, end_index: selectedNotes.end.index, peak_index: selectedNotes.peak.index };
            const tempoSelection = tempoPreset.value;
            const presetParams = PRESETS.tempo_expressions[tempoSelection].params;
            const partName = partSelector.selectedOptions[0].textContent;
            const res = await fetch("/process", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ partIndex, partName, phrase: phraseInfo, presetParams, presetName: tempoSelection })
            });
            const result = await res.json();
            handleServerResponse(result);
        } catch (err) {
            console.error(err);
            statusMessage.textContent = `⚠️ エラー: ${err.message}`;
        } finally {
            loadingSpinner.classList.add("hidden");
            applyBtn.disabled = !(selectedNotes.start && selectedNotes.end && selectedNotes.peak);
        }
    });
    
    function flashPlayer() {
        compareContainer.classList.remove('flash-success');
        void compareContainer.offsetWidth;
        compareContainer.classList.add('flash-success');
    }

    // ============================================
    // MIDI保存ボタンの処理
    // ============================================
    document.addEventListener('click', function(event) {
        if (event.target && event.target.id === 'save-midi-btn') {
            const wavPath = window.lastFlaskResponse?.processed_full_wav;
            if(!wavPath) {
                alert("保存対象のMIDIファイルが見つかりません。");
                return;
            }
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

// ============================================================
// WAV再生
// ============================================================
function playWAV(type, clickedButton) {
    try {
        let wavUrl = "";
        if (type === "processed_single") wavUrl = window.lastFlaskResponse?.processed_single_wav;
        else if (type === "original_single") wavUrl = window.lastFlaskResponse?.original_single_wav;
        else if (type === "processed_full") wavUrl = window.lastFlaskResponse?.processed_full_wav;
        else if (type === "original_full") wavUrl = window.lastFlaskResponse?.original_full_wav;
        if (!wavUrl) return;
        const cacheBustingUrl = `${wavUrl}?v=${new Date().getTime()}`;
        document.querySelectorAll('.compare-block button').forEach(btn => btn.classList.remove('is-playing'));
        if (window.currentAudio) {
            window.currentAudio.pause();
        }
        window.currentAudio = new Audio(cacheBustingUrl);
        window.currentAudio.play().then(() => {
            if (clickedButton) clickedButton.classList.add('is-playing');
        });
        window.currentAudio.onended = function() {
            if (clickedButton) clickedButton.classList.remove('is-playing');
        };
    } catch (err) {
        console.error("⚠️ playWAVでエラー:", err);
    }
}

function stopWAV() {
    if (window.currentAudio) {
        window.currentAudio.pause();
        window.currentAudio.currentTime = 0;
        document.querySelectorAll('.compare-block button').forEach(btn => btn.classList.remove('is-playing'));
    }
}