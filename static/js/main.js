// ============================================================
// 🎵 ABCJS + Flask note_map連携版 main.js（WAV再生対応 完全版）
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    const uploadForm = document.getElementById("upload-form");
    const partSelector = document.getElementById("part-selector");
    const scoreDisplay = document.getElementById("score-display");
    const statusMessage = document.getElementById("status-message");
    const applyBtn = document.getElementById("apply-btn");
    const tempoPreset = document.getElementById("tempo-preset");
    const adjectivePreset = document.getElementById("adjective-preset");
    const resetSelectionBtn = document.getElementById("reset-selection-btn");

    // 🎧 比較再生プレイヤー
    const compareContainer = document.getElementById("compare-container");

    let selectionMode = "start";
    let selectedNotes = { start: null, end: null, peak: null };
    let allPartAbcData = {};
    let allNoteMaps = {};
    let currentPartIndex = null;

    // ✅ WAV再生用グローバル
    window.lastFlaskResponse = {};
    let currentAudio = null;

    // ============================================
    // 1️⃣ ファイルアップロード
    // ============================================
    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
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
    // 2️⃣ パート選択
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
                console.log("✅ note_map loaded:", allNoteMaps[partIndex].length, "notes");
            }
        }
        renderScore(abcText);
    });

    // ============================================
    // 3️⃣ 楽譜描画
    // ============================================
    function renderScore(abcText) {
        scoreDisplay.innerHTML = "";
        ABCJS.renderAbc("score-display", abcText, {
            add_classes: true,
            staffwidth: 900,
            clickListener: (abcElem, tuneNumber, classes, analysis, drag, mouseEvent) => {
                setTimeout(() => handleNoteClick(abcElem, tuneNumber, classes, analysis, drag, mouseEvent), 200);
            }
        });
        statusMessage.textContent = "✅ 音符をクリックして範囲を指定できます。";
    }

    // ============================================
    // 4️⃣ 音符クリック処理
    // ============================================
    function handleNoteClick(abcElem, tuneNumber, classes, analysis, drag, mouseEvent) {
        const clickedEl = mouseEvent.target.closest(".abcjs-note");
        if (!clickedEl) return;
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
    // 5️⃣ UI更新
    // ============================================
    function updateSelectionUI() {
        document.querySelectorAll(".abcjs-note.selected, .abcjs-note.selected-end, .abcjs-note.selected-peak")
            .forEach(el => el.classList.remove("selected", "selected-end", "selected-peak"));

        if (selectedNotes.start?.el) selectedNotes.start.el.classList.add("selected");
        if (selectedNotes.end?.el) selectedNotes.end.el.classList.add("selected-end");
        if (selectedNotes.peak?.el) selectedNotes.peak.el.classList.add("selected-peak");

        document.getElementById("start-note-info").textContent =
            selectedNotes.start ? `index=${selectedNotes.start.index} / tick=${selectedNotes.start.tick ?? "?"}` : "未選択";
        document.getElementById("peak-note-info").textContent =
            selectedNotes.peak ? `index=${selectedNotes.peak.index} / tick=${selectedNotes.peak.tick ?? "?"}` : "未選択";
        document.getElementById("end-note-info").textContent =
            selectedNotes.end ? `index=${selectedNotes.end.index} / tick=${selectedNotes.end.tick ?? "?"}` : "未選択";

        applyBtn.disabled = !(selectedNotes.start && selectedNotes.end && selectedNotes.peak);
    }

    // ============================================
    // 6️⃣ リセット
    // ============================================
    resetSelectionBtn.addEventListener("click", () => {
        selectionMode = "start";
        selectedNotes = { start: null, end: null, peak: null };
        document.querySelectorAll(".abcjs-note.selected, .abcjs-note.selected-end, .abcjs-note.selected-peak")
            .forEach(el => el.classList.remove("selected", "selected-end", "selected-peak"));
        applyBtn.disabled = true;
        statusMessage.textContent = "選択をリセットしました。";
        document.getElementById("start-note-info").textContent = "未選択";
        document.getElementById("peak-note-info").textContent = "未選択";
        document.getElementById("end-note-info").textContent = "未選択";
    });

    // ============================================
    // 7️⃣ 「適用」ボタン
    // ============================================
    applyBtn.addEventListener("click", async () => {
        if (!selectedNotes.start || !selectedNotes.end || !selectedNotes.peak) {
            alert("開始・終了・頂点を順に選択してください。");
            return;
        }
        if (currentPartIndex === null) {
            alert("パートを選択してください。");
            return;
        }

        const partIndex = currentPartIndex;
        const noteMap = allNoteMaps[partIndex];
        if (!noteMap) {
            alert("note_mapが読み込まれていません。");
            return;
        }

        const startIdx = selectedNotes.start.index;
        const endIdx = selectedNotes.end.index;
        const peakIdx = selectedNotes.peak.index;
        if (startIdx >= endIdx) {
            alert("終了位置は開始位置より後にしてください。");
            return;
        }

        const tempoSelection = tempoPreset.value;
        const adjSelection = adjectivePreset.value;
        const presetParams = {
            base_cc2: (PRESETS.tempo_expressions[tempoSelection]?.base_cc2 || 0) +
                      (PRESETS.adjective_expressions[adjSelection]?.base_cc2 || 0),
            peak_cc2: (PRESETS.tempo_expressions[tempoSelection]?.peak_cc2 || 0) +
                      (PRESETS.adjective_expressions[adjSelection]?.peak_cc2 || 0)
        };

        const phraseInfo = { start_index: startIdx, end_index: endIdx, peak_index: peakIdx };
        const partName = partSelector.selectedOptions[0].textContent;

        statusMessage.textContent = "⏳ MIDIを加工中...";
        try {
            const res = await fetch("/process", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ partIndex, partName, phrase: phraseInfo, presetParams })
            });

            const result = await res.json();
            console.log("🎵 Flask response:", result);
            window.lastFlaskResponse = result; // ✅ WAV再生用URLを保持

            compareContainer.style.display = "block";
            statusMessage.textContent = "✅ WAVを聴き比べできます。";
        } catch (err) {
            console.error(err);
            statusMessage.textContent = `⚠️ エラー: ${err.message}`;
        }
    });
});

// ============================================================
// 🎧 WAV再生関数（Tone.js不要）
// ============================================================
function playWAV(type) {
    try {
        let wavUrl = "";
        if (type === "processed_single") wavUrl = lastFlaskResponse?.processed_single_wav;
        else if (type === "original_single") wavUrl = lastFlaskResponse?.original_single_wav;
        else if (type === "processed_full") wavUrl = lastFlaskResponse?.processed_full_wav;
        else if (type === "original_full") wavUrl = lastFlaskResponse?.original_full_wav;

        if (!wavUrl) {
            console.warn("⚠️ WAVファイルのURLが取得できませんでした。");
            return;
        }

        // 再生中の音を止める
        if (window.currentAudio) {
            window.currentAudio.pause();
            window.currentAudio.currentTime = 0;
        }

        // 新規Audioで再生
        window.currentAudio = new Audio(wavUrl);
        window.currentAudio.play()
            .then(() => console.log("🎧 WAV再生開始:", wavUrl))
            .catch(err => console.error("⚠️ WAV再生エラー:", err));

    } catch (err) {
        console.error("⚠️ playWAVでエラー:", err);
    }
}

function stopWAV() {
    if (window.currentAudio) {
        window.currentAudio.pause();
        window.currentAudio.currentTime = 0;
        console.log("⏹ WAV再生停止");
    }
}
