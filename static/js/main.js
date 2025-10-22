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

    // ============================================
    // 1️. ファイルアップロード
    // ============================================
    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        // 処理の開始時に、前の結果（比較エリアと保存エリア）を非表示にする
        compareContainer.style.display = "none";
        saveArea.style.display = "none";
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
    // すべての加工をリセットするボタンの処理
    // ============================================
    resetMidiBtn.addEventListener("click", async () => {
        if (!confirm("本当にすべての加工をリセットしますか？この操作は元に戻せません。")) {
            return;
        }

        statusMessage.textContent = "⏳ リセット中...";
        try {
            const res = await fetch("/reset_midi", { method: "POST" });
            const result = await res.json();
            if (result.error) throw new Error(result.error);
            
            statusMessage.textContent = `✅ ${result.message}`;
            alert(result.message);

            // 適用結果が表示されていたらクリアする
            compareContainer.style.display = "none";
            saveArea.style.display = "none";

        } catch (err) {
            console.error(err);
            statusMessage.textContent = `⚠️ リセットエラー: ${err.message}`;
        }
    });

    // ============================================
    // 7️. 「適用」ボタンクリック
    // ============================================
    applyBtn.addEventListener("click", async () => {
        // ... (関数の先頭部分は変更なし) ...
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
        const presetParams = {
            base_cc2: PRESETS.tempo_expressions[tempoSelection]?.base_cc2 || 0,
            peak_cc2: PRESETS.tempo_expressions[tempoSelection]?.peak_cc2 || 0,
            onset_ms: PRESETS.tempo_expressions[tempoSelection]?.onset_ms || 0
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
            window.lastFlaskResponse = result;

            // 「聴き比べ」エリアと「保存」エリアの両方を表示する
            compareContainer.style.display = "block";
            saveArea.style.display = "block";

            // ★★★ ここからが変更点 ★★★
            // 1. ステータスメッセージを、より分かりやすく更新
            statusMessage.textContent = "✅ 新しい音源を生成しました。再生して確認できます。";

            // 2. 聴き比べエリアに .flash-success クラスを追加してアニメーションを開始
            compareContainer.classList.add('flash-success');

            // 3. アニメーションが終わった後（1.5秒後）に、クラスを削除する
            //    （こうしないと、次に適用した時にアニメーションが再生されない）
            setTimeout(() => {
                compareContainer.classList.remove('flash-success');
            }, 1500); // CSSで設定したアニメーションの時間と合わせる

        } catch (err) {
            console.error(err);
            statusMessage.textContent = `⚠️ エラー: ${err.message}`;
        }
    });

    // ============================================
    // MIDI保存ボタンの処理
    // ============================================
    document.addEventListener('click', function(event) {
        if (event.target && event.target.id === 'save-midi-btn') {
            const midiUrl = window.lastFlaskResponse?.processed_full;
            if (!midiUrl) {
                alert("保存対象のMIDIファイルが見つかりません。");
                return;
            }
            const filename = midiUrl.split('/').pop();
            const a = document.createElement('a');
            a.href = midiUrl;
            a.download = filename;
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
        if (type === "processed_single") wavUrl = lastFlaskResponse?.processed_single_wav;
        else if (type === "original_single") wavUrl = lastFlaskResponse?.original_single_wav;
        else if (type === "processed_full") wavUrl = lastFlaskResponse?.processed_full_wav;
        else if (type === "original_full") wavUrl = lastFlaskResponse?.original_full_wav;

        if (!wavUrl) {
            console.warn("⚠️ WAVファイルのURLが取得できませんでした。");
            return;
        }

        const cacheBustingUrl = `${wavUrl}?v=${new Date().getTime()}`;

        document.querySelectorAll('.compare-block button').forEach(btn => {
            btn.classList.remove('is-playing');
        });

        if (window.currentAudio) {
            window.currentAudio.pause();
            window.currentAudio.currentTime = 0;
        }

        window.currentAudio = new Audio(cacheBustingUrl);
        window.currentAudio.play()
            .then(() => {
                console.log("🎧 WAV再生開始:", cacheBustingUrl);
                if (clickedButton) {
                    clickedButton.classList.add('is-playing');
                }
            })
            .catch(err => console.error("⚠️ WAV再生エラー:", err));

        window.currentAudio.onended = function() {
            console.log("🎵 再生終了");
            if (clickedButton) {
                clickedButton.classList.remove('is-playing');
            }
        };

    } catch (err) {
        console.error("⚠️ playWAVでエラー:", err);
    }
}

function stopWAV() {
    if (window.currentAudio) {
        window.currentAudio.pause();
        window.currentAudio.currentTime = 0;
        console.log("⏹ WAV再生停止");

        document.querySelectorAll('.compare-block button').forEach(btn => {
            btn.classList.remove('is-playing');
        });
    }
}