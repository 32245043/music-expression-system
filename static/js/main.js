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
    const adjectivePreset = document.getElementById("adjective-preset");
    const resetSelectionBtn = document.getElementById("reset-selection-btn");

    //　再生プレイヤー
    const compareContainer = document.getElementById("compare-container");

    // --- グローバル変数 ---
    let selectionMode = "start"; // "start", "end", "peak"のどれか
    let selectedNotes = { start: null, end: null, peak: null };
    let allPartAbcData = {}; //全パートのABCデータを保持
    let allNoteMaps = {};    // 全パートのノートマップを保持
    let currentPartIndex = null;

    // WAV再生用にサーバーからのレスポンスを保持する
    window.lastFlaskResponse = {};
    let currentAudio = null;

    // ============================================
    // 1️. ファイルアップロード
    // ============================================
    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        statusMessage.textContent = "⌛ ファイルをアップロード中...";

        const formData = new FormData(uploadForm);
        try {
            const res = await fetch("/upload", { method: "POST", body: formData });
            const result = await res.json();
            if (result.error) throw new Error(result.error);

            // サーバーからのパート情報でUIを更新
            allPartAbcData = result.all_abc_data;
            partSelector.innerHTML = "";
            result.parts.forEach((p) => {
                const opt = document.createElement("option");
                opt.value = p.index;
                opt.textContent = p.name || `Part ${p.index + 1}`;
                opt.dataset.noteMap = p.note_map; // note_mapのパスをdata属性に保存
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

        // 対応するABCデータを取得して楽譜を描画
        const abcText = allPartAbcData[partIndex];
        if (!abcText) return;

        // 対応するnote_mapをサーバーから非同期で読み込み
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
    // 3️. 楽譜描画
    // ============================================
    function renderScore(abcText) {
        scoreDisplay.innerHTML = "";
        ABCJS.renderAbc("score-display", abcText, {
            add_classes: true, // 各SVG要素にクラスを付与
            staffwidth: 900,   // 譜面の幅
            clickListener: (abcElem, tuneNumber, classes, analysis, drag, mouseEvent) => {
                // クリックイベントの伝達タイミングを考慮して少し遅延させる
                setTimeout(() => handleNoteClick(abcElem, tuneNumber, classes, analysis, drag, mouseEvent), 200);
            }
        });
        statusMessage.textContent = "✅ 音符をクリックして範囲を指定できます。";
    }

    // ============================================
    // 4️. 音符クリック
    // ============================================
    function handleNoteClick(abcElem, tuneNumber, classes, analysis, drag, mouseEvent) {
        const clickedEl = mouseEvent.target.closest(".abcjs-note");
        if (!clickedEl) return;

        // クリックされた音符が楽譜全体の何番目かを特定
        const noteElements = Array.from(document.querySelectorAll(".abcjs-note"));
        const noteIndex = noteElements.indexOf(clickedEl);
        if (noteIndex === -1) return;

        const noteMap = allNoteMaps[currentPartIndex];
        const tick = noteMap && noteMap[noteIndex] ? noteMap[noteIndex].tick : null;

        // 選択モードに応じて音符情報を保持し、次のモードへ移行
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
        // 全てのハイライトをクリア
        document.querySelectorAll(".abcjs-note.selected, .abcjs-note.selected-end, .abcjs-note.selected-peak")
            .forEach(el => el.classList.remove("selected", "selected-end", "selected-peak"));

        // 選択された音符にハイライト用のクラスを追加
        if (selectedNotes.start?.el) selectedNotes.start.el.classList.add("selected");
        if (selectedNotes.end?.el) selectedNotes.end.el.classList.add("selected-end");
        if (selectedNotes.peak?.el) selectedNotes.peak.el.classList.add("selected-peak");

        // 選択情報をテキストで表示
        document.getElementById("start-note-info").textContent =
            selectedNotes.start ? `index=${selectedNotes.start.index} / tick=${selectedNotes.start.tick ?? "?"}` : "未選択";
        document.getElementById("peak-note-info").textContent =
            selectedNotes.peak ? `index=${selectedNotes.peak.index} / tick=${selectedNotes.peak.tick ?? "?"}` : "未選択";
        document.getElementById("end-note-info").textContent =
            selectedNotes.end ? `index=${selectedNotes.end.index} / tick=${selectedNotes.end.tick ?? "?"}` : "未選択";

        // 全ての音符が選択されたら「適用」ボタンを有効化
        applyBtn.disabled = !(selectedNotes.start && selectedNotes.end && selectedNotes.peak);
    }

    // ============================================
    // 6️. 選択リセット
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
    // 7️. 「適用」ボタンクリック
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

        // 選択されたプリセットの値を合成
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
            // サーバーにMIDI加工リクエストを送信
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
