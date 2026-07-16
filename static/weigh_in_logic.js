document.addEventListener('DOMContentLoaded', async () => {

    // --- DOM 元素 ---
    const settingsScreen = document.getElementById('settings-screen');
    const weighInScreen = document.getElementById('weigh-in-screen');
    const startButton = document.getElementById('start-button');
    const exportResultsBtn = document.getElementById('export-offline-results-btn');
    const modeRadios = document.querySelectorAll('input[name="mode"]');
    const onlineSettings = document.getElementById('online-settings');
    const offlineSettings = document.getElementById('offline-settings');
    const refreshEventsBtn = document.getElementById('refresh-events-btn');
    
    const serverIpInput = document.getElementById('server-ip');
    const eventSelect = document.getElementById('event-select');
    const dataFileInput = document.getElementById('data-file');
    const fileNameDisplay = document.getElementById('file-name-display');
    const printerSelect = document.getElementById('printer-select');
    const cameraSelect = document.getElementById('camera-select');
    const scalePortInput = document.getElementById('scale-port-input');    
    const categoryFilterInput = document.getElementById('category-filter');
    const globalPlayerSearch = document.getElementById('global-player-search');

    const categoryList = document.querySelector('#category-list .list-group');
    const playerList = document.querySelector('#player-list .list-group');
    const weightRangeEl = document.getElementById('weight-range');
    const weightDisplayEl = document.getElementById('weight-display');
    const statusDisplayEl = document.getElementById('status-display');
    const currentPlayerInfoEl = document.getElementById('current-player-info');
    const logList = document.getElementById('log-list');
    const resyncNotificationArea = document.getElementById('resync-notification-area');
    const cameraImage = document.getElementById('camera-image');
    const savedPhotoImage = document.getElementById('saved-photo-image');
    const savedPhotoPlaceholder = document.getElementById('saved-photo-placeholder-text');
    const historyDisplay = document.getElementById('history-display'); 
    const randomWeighInBtn = document.getElementById('random-weigh-in-btn');    
    const add100gBtn = document.getElementById('add-100g-btn');
    const customConfirmOverlay = document.getElementById('custom-confirm-overlay');
    const customConfirmBox = document.getElementById('custom-confirm-box');
    const customConfirmMessage = document.getElementById('custom-confirm-message');
    let customConfirmYesBtn = document.getElementById('custom-confirm-yes');
    let customConfirmNoBtn = document.getElementById('custom-confirm-no');
    const forceSyncButton = document.getElementById('force-sync-button');
    const clearCacheButton = document.getElementById('clear-cache-button');
    const deleteEventModal = document.getElementById('delete-event-modal-overlay');
    const deleteEventList = document.getElementById('delete-event-list');
    const deleteSelectedBtn = document.getElementById('delete-selected-btn');
    const deleteAllBtn = document.getElementById('delete-all-btn');
    const deleteCancelBtn = document.getElementById('delete-cancel-btn');
    const passwordModalOverlay = document.getElementById('password-modal-overlay');
    const passwordInput = document.getElementById('password-input');
    const passwordErrorMessage = document.getElementById('password-error-message');
    const passwordSubmitBtn = document.getElementById('password-submit-btn');
    const passwordCancelBtn = document.getElementById('password-cancel-btn');
    const serverStatusIndicator = document.getElementById('server-status-indicator');
    let serverCheckInterval = null;
    let isServerOnline = false; // 追蹤伺服器是否處於連線狀態
    const printCopiesInput = document.getElementById('print-copies-input');
    const savePhotoRadios = document.querySelectorAll('input[name="save-photo-mode"]');
    const cameraSelectContainer = document.getElementById('camera-select-container');

    printCopiesInput.addEventListener('change', (e) => {
        if (e.target.value === '0') {
            printerSelectContainer.classList.add('hidden');
        } else {
            printerSelectContainer.classList.remove('hidden');
        }
    });

    // 監聽照片儲存開關，關閉時隱藏攝影機選單
    savePhotoRadios.forEach(radio => {
        radio.addEventListener('change', async (e) => {
            if (e.target.value === 'true') {
                cameraSelectContainer.classList.remove('hidden');
            } else {
                cameraSelectContainer.classList.add('hidden');
                // 呼叫 Python 後端徹底關閉攝影機串流
                try {
                    await fetch('/api/camera/control', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action: 'stop' })
                    });
                    log('已斷開攝影機連結，釋放系統資源。');
                } catch (err) {
                    console.error("無法斷開攝影機", err);
                }
            }
        });
    });

    // --- 變數 ---
    let weightInterval = null;
    let activePlayer = null;
    let activeCategory = null;
    let isRandomWeighInMode = false; // 追蹤是否為隨機過磅模式
    let isPlus100gActive = false; // 【新】追蹤+100g開關是否開啟     

    // --- 函式 ---
    function showNotification(message, type = 'error') {
        const existingNotification = document.getElementById('custom-notification');
        if (existingNotification) {
            existingNotification.remove();
        }
    
        const notification = document.createElement('div');
        notification.id = 'custom-notification';
        notification.textContent = message;
        notification.className = `notification ${type}`; // 'error' 或 'success'
    
        document.body.appendChild(notification);
    
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);
    
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.parentElement.removeChild(notification);
                }
            }, 500);
        }, 3000); // 顯示 3 秒
    }

    /**
     * 【全新】檢查伺服器連線狀態的函式
     */
    async function checkServerStatus() {
        if (!serverStatusIndicator) return;
    
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000);
    
        try {
            const response = await fetch('/api/server_connection_status', {
                signal: controller.signal
            });
            clearTimeout(timeoutId);
    
            if (!response.ok) {
                // 本地 'main.py' 服務出錯
                serverStatusIndicator.textContent = '● 本地服務異常';
                serverStatusIndicator.className = 'status-error';
                isServerOnline = false; // 標記為離線
                return;
            }
    
            const result = await response.json();
    
            if (result.status === 'online') {
                // --- ▼▼▼ 核心修改：檢查是否「剛剛」恢復連線 ▼▼▼ ---
                if (isServerOnline === false) {
                    // 狀態從「離線」變為「連線」
                    log('偵測到伺服器連線已恢復。');
                    serverStatusIndicator.textContent = '● 正在同步...'; // 顯示同步中
                    serverStatusIndicator.className = 'status-checking';
                    
                    try {
                        // 觸發重傳 API
                        log('正在嘗試重傳未同步的過磅記錄...');
                        const retryResponse = await fetch('/api/retry_failed_syncs', { method: 'POST' });
                        const retryResult = await retryResponse.json();
                        
                        if (retryResult.synced_count > 0) {
                            log(`成功重傳 ${retryResult.synced_count} 筆記錄！`);
                            
                            // --- ▼▼▼ 【修改後的通知邏輯】 ▼▼▼ ---
                            if (resyncNotificationArea) {
                                // 1. 設置文字
                                resyncNotificationArea.textContent = `成功重傳 ${retryResult.synced_count} 筆記錄！`;
                                // 2. 顯示 (觸發 CSS transition)
                                resyncNotificationArea.classList.add('show');
                                
                                // 3. 設置 4 秒後自動消失
                                setTimeout(() => {
                                    resyncNotificationArea.classList.remove('show');
                                    // 為了讓淡出效果跑完，延遲 0.5 秒再清空文字
                                    setTimeout(() => {
                                         if (resyncNotificationArea) {
                                            resyncNotificationArea.textContent = '';
                                         }
                                    }, 500); 
                                }, 4000); // 顯示 4 秒
                            }
                            // --- ▲▲▲ 【修改結束】 ▲▲▲ ---

                        } else {
                            log('重傳檢查完畢，無待辦事項。');
                        }
                        
                    } catch (e) {
                        log(`呼叫重傳 API 時失敗: ${e}`);
                    }
                    
                    // 無論重傳是否成功，都將狀態更新為「正常」
                    serverStatusIndicator.textContent = '● 伺服器連線正常';
                    serverStatusIndicator.className = 'status-ok';
                    
                } else {
                    // 狀態本來就是「連線」，保持不變
                    serverStatusIndicator.textContent = '● 伺服器連線正常';
                    serverStatusIndicator.className = 'status-ok';
                }
                isServerOnline = true; // 確保狀態為 true
                // --- ▲▲▲ 修改結束 ▲▲▲ ---
    
            } else if (result.status === 'error') {
                // 'main.py' 說它連不上伺服器
                serverStatusIndicator.textContent = `● 伺服器無回應 (${result.message})`;
                serverStatusIndicator.className = 'status-error';
                isServerOnline = false; // 標記為離線
            } else if (result.status === 'offline') {
                // 'main.py' 說現在是離線模式
                serverStatusIndicator.textContent = '● 離線模式';
                serverStatusIndicator.className = 'status-checking';
                isServerOnline = false; // 離線模式也算 'offline'
            }
    
        } catch (error) {
            // 'fetch' 本身失敗 (本地 main.py 關閉了)
            clearTimeout(timeoutId);
            serverStatusIndicator.textContent = '● 本地服務無回應';
            serverStatusIndicator.className = 'status-error';
            isServerOnline = false; // 標記為離線
        }
    }

    /**
     * 【全新】執行完整的伺服器資料同步
     * @returns {Promise<boolean>} 回傳 true 代表同步成功, false 代表失敗
     */
    async function startFullSync() {
        log('正在從伺服器同步所有資料，請稍候...');
        log('（這可能需要 1-2 分鐘，請勿關閉程式）');
        
        // 禁用按鈕，防止重複點擊
        if (forceSyncButton) forceSyncButton.disabled = true;
        
        try {
            const syncResponse = await fetch('/api/data/sync_from_server', {
                method: 'POST'
            });
            const syncResult = await syncResponse.json();
            
            if (!syncResponse.ok) {
                alert(`同步失敗: ${syncResult.message}`);
                log(`錯誤: 同步失敗 - ${syncResult.message}`);
                return false; // 同步失敗
            }
            
            log(syncResult.message); // 顯示 "同步完成！..."
            showNotification(syncResult.message, 'success'); // 彈出成功提示
            return true; // 同步成功

        } catch (error) {
            alert(`同步過程中發生連線錯誤: ${error}`);
            log(`錯誤: 同步請求失敗 - ${error}`);
            return false; // 同步失敗
        } finally {
            // 無論成功或失敗，都重新啟用按鈕
            if (forceSyncButton) forceSyncButton.disabled = false;
        }
    }

    async function fetchEventInfo() {
        try {
            const response = await fetch('/api/event_info');
            if (!response.ok) return;
            const eventInfo = await response.json();

            const categoryPanelHeader = document.querySelector('#category-list .panel-header');

            if (eventInfo && eventInfo.name && categoryPanelHeader) {
                categoryPanelHeader.textContent = `${eventInfo.name} - 組別清單`;
            }

        } catch (error) {
            log('無法獲取線上賽事資訊');
            const categoryPanelHeader = document.querySelector('#category-list .panel-header');
            if (categoryPanelHeader) {
                categoryPanelHeader.textContent = '組別清單';
            }
        }
    }

    async function populateEvents() {
        const serverIp = serverIpInput.value.trim().replace(/\/+$/, '');
        if (!serverIp) {
            eventSelect.innerHTML = '<option value="">請先輸入伺服器IP</option>';
            return;
        }

        await fetch('/api/config/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server_ip: serverIp })
        });
        
        eventSelect.innerHTML = '<option value="">載入中...</option>';
        try {
            const response = await fetch('/api/events');
            const events = await response.json();

            if (events.error) {
                eventSelect.innerHTML = `<option value="">${events.error}</option>`;
                return;
            }

            eventSelect.innerHTML = '<option value="">請選擇賽事</option>';
            events.forEach(event => {
                const option = document.createElement('option');
                option.value = event.name; 
                option.textContent = event.name;
                eventSelect.appendChild(option);
            });
            
            const configResponse = await fetch('/api/config/load');
            const config = await configResponse.json();
            if (config.event_name) {
                eventSelect.value = config.event_name;
            }

        } catch (error) {
            eventSelect.innerHTML = '<option value="">獲取賽事列表失敗</option>';
            console.error('Error populating events:', error);
        }
    }


    async function loadDevices() {
        try {
            const response = await fetch('/api/devices');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const devices = await response.json();

            printerSelect.innerHTML = '<option value="">請選擇印表機</option>';
            devices.printers.forEach(printer => {
                const option = document.createElement('option');
                option.value = printer;
                option.textContent = printer;
                printerSelect.appendChild(option);
            });

            cameraSelect.innerHTML = '<option value="">請選擇攝影機</option>';
            devices.cameras.forEach(camera => {
                const option = document.createElement('option');
                option.value = camera.id;
                option.textContent = camera.name;
                cameraSelect.appendChild(option);
            });
            log('設備列表已載入');
        } catch (error) {
            log('錯誤：無法載入設備列表');
            console.error('Error loading devices:', error);
        }
    }

    async function loadAndApplyConfig() {
        try {
            await loadDevices(); 
            
            const response = await fetch('/api/config/load');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const config = await response.json();
    
            serverIpInput.value = config.server_ip || '';
            const modeToSelect = config.mode === 'offline' ? 'mode-offline' : 'mode-online';
            document.getElementById(modeToSelect).checked = true;
            document.getElementById(modeToSelect).dispatchEvent(new Event('change', { bubbles: true }));
    
            scalePortInput.value = config.scale_port || 'COM3';
            const simModeValue = config.scale_simulation ? 'true' : 'false';
            const simRadio = document.querySelector(`input[name="sim-mode"][value="${simModeValue}"]`);
            if (simRadio) simRadio.checked = true;
            
            if (config.mode === 'online' && config.server_ip) {
                log('偵測到連線模式與IP，啟動時將自動載入賽事...');
                await populateEvents();
            }
    
            setTimeout(() => {
                if (config.printer) printerSelect.value = config.printer;
                if (config.camera !== null) cameraSelect.value = config.camera;
                if (config.event_name) {
                    eventSelect.value = config.event_name;
                }
                
                // 載入列印數量與拍照設定
                if (config.print_copies !== undefined) {
                    printCopiesInput.value = config.print_copies;
                    printCopiesInput.dispatchEvent(new Event('change')); 
                }
                const savePhotoVal = config.save_photo !== false ? 'true' : 'false';
                const photoRadio = document.querySelector(`input[name="save-photo-mode"][value="${savePhotoVal}"]`);
                if (photoRadio) {
                    photoRadio.checked = true;
                    photoRadio.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }, 500);
    
            log('系統設定已載入');
        } catch (error) {
            log(`錯誤：無法載入系統設定 - ${error.message}`);
            console.error('Error loading config:', error);
        }
    }
    
    async function saveCurrentConfig() {
        const selectedMode = document.querySelector('input[name="mode"]:checked').value;
        const savePhoto = document.querySelector('input[name="save-photo-mode"]:checked').value === 'true';
        const printCopies = parseInt(printCopiesInput.value, 10);
        
        const config = {
            mode: selectedMode,
            server_ip: serverIpInput.value,
            event_name: eventSelect.value, 
            printer: printerSelect.value,
            camera: (savePhoto && cameraSelect.value !== "") ? parseInt(cameraSelect.value, 10) : null,
            scale_port: scalePortInput.value,
            scale_simulation: document.querySelector('input[name="sim-mode"]:checked').value === 'true',
            save_photo: savePhoto,
            print_copies: isNaN(printCopies) ? 0 : printCopies
        };

        try {
            const response = await fetch('/api/config/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            if (!response.ok) throw new Error('儲存失敗');
            log('系統設定已儲存');
            
            if (config.camera === null) {
                cameraImage.src = '';
                cameraImage.style.display = 'none';
            } else {
                cameraImage.style.display = 'block';
                cameraImage.src = `/api/camera_feed?t=${new Date().getTime()}`;
            }
        } catch (error) {
            log('錯誤：無法儲存設定');
            console.error('Error saving config:', error);
        }
    }
    
    async function renderCategories() {
        try {
            const response = await fetch('/api/categories');
            const categories = await response.json();

            if (categories.error) {
                alert(`載入組別失敗: ${categories.error}`);
                log(`錯誤: 無法載入組別列表 - ${categories.error}`);
                return;
            }
            
            categoryList.innerHTML = '';
            categories.forEach(cat => {
                const li = document.createElement('li');
                li.textContent = cat.name;
                li.dataset.categoryId = cat.id;
                if (cat.min_weight !== null) li.dataset.minWeight = cat.min_weight;
                if (cat.max_weight !== null) li.dataset.maxWeight = cat.max_weight;
                categoryList.appendChild(li);
            });
            log(`成功載入 ${categories.length} 個組別`);
        } catch (error) {
            log('錯誤: 無法載入組別列表');
            console.error('Error fetching categories:', error);
        }
    }

    async function renderPlayers(categoryId) {
        try {
           const response = await fetch(`/api/players?category_id=${categoryId}`);
           const unsortedPlayers = await response.json(); // 獲取未排序的資料
            
           if (unsortedPlayers.error) {
                alert(`載入選手失敗: ${unsortedPlayers.error}`);
                log(`錯誤: 無法載入選手列表 - ${unsortedPlayers.error}`);
                return;
           }
           
           // --- ▼▼▼ 核心修改：加入與競賽管理系統相同的排序邏輯 ▼▼▼ ---
           const players = unsortedPlayers.sort((a, b) => 
                (a.team.localeCompare(b.team, 'zh-Hant')) || 
                (a.name.localeCompare(b.name, 'zh-Hant'))
           );
           // --- ▲▲▲ 核心修改結束 ▲▲▲ ---
    
           playerList.innerHTML = '';
           players.forEach(player => {
               const li = document.createElement('li');
               li.dataset.playerId = player.id;
               li.dataset.bib = player.bib;
               li.dataset.name = player.name;
               li.dataset.team = player.team;
               
               const info = document.createElement('span');
               info.textContent = `${player.bib || ''}-${player.name || ''}-${player.team || ''}`;
               
               const status = document.createElement('span');
               
               let statusKeyToShow;
               if (isRandomWeighInMode) {
                   statusKeyToShow = player.has_random_weigh_in ? 'random_completed' : 'pending';
               } else {
                   statusKeyToShow = player.status || 'pending';
               }
               
               status.textContent = `(${translateStatus(statusKeyToShow)})`;
               status.className = `player-status status-${statusKeyToShow}`;
               
               li.appendChild(info);
               li.appendChild(status);
               playerList.appendChild(li);
           });
       } catch (error) {
           log('錯誤: 無法載入選手列表');
           console.error('Error fetching players:', error);
       }
    }
    
    function translateStatus(status) {
        if (status === 'passed' || status === '通過') return '通過';
        if (status === 'failed' || status === '未通過') return '未通過';
        
        // --- 【核心修改】---
        if (status === 'random_completed') return '已抽磅';
    
        if (isRandomWeighInMode) {
            return '未抽磅';
        } else {
            return '未過磅';
        }
    }

    function checkWeightStatus(weight, categoryData) {
        if (isNaN(weight) || !categoryData || categoryData.maxWeight === undefined || categoryData.minWeight === undefined) {
            statusDisplayEl.textContent = '--';
            statusDisplayEl.className = 'status-display-box';
            return;
        }

        let isPassed = false;
        if (isRandomWeighInMode) {
            const randomMinWeight = 10;
            // 【新】套用小數點第二位無條件為 9 的規則
            let rawMax = Math.floor(categoryData.maxWeight) * 1.05;
            let randomMaxWeight = parseFloat((Math.floor(rawMax * 10) / 10 + 0.09).toFixed(2));
            if (isPlus100gActive) {
                randomMaxWeight = parseFloat((randomMaxWeight + 0.1).toFixed(2));
            }
            isPassed = weight >= randomMinWeight && weight <= randomMaxWeight;
        } else {
            isPassed = weight >= categoryData.minWeight && weight <= categoryData.maxWeight;
        }

        if (isPassed) {
            statusDisplayEl.textContent = '通過';
            statusDisplayEl.className = 'status-display-box passed';
        } else {
            statusDisplayEl.textContent = '未通過';
            statusDisplayEl.className = 'status-display-box failed';
        }
    }

    /**
     * 根據當前模式（正常或隨機）更新介面顯示
     */
    function updateUIForMode() {
        if (!activePlayer || !activeCategory) {
            return;
        }

        // 提示文字的邏輯保持不變
        const historyCount = historyDisplay.children.length;
        let infoPrefix = '';

        if (isRandomWeighInMode) {
            infoPrefix = "隨機過磅：";
        } else {
            infoPrefix = `第 ${historyCount + 1} 次過磅:`;
        }
        currentPlayerInfoEl.textContent = `${infoPrefix} ${activePlayer.bib}-${activePlayer.name}-${activePlayer.team}`;

        const minWeight = activeCategory.minWeight;
        const maxWeight = activeCategory.maxWeight;
        
        if (maxWeight !== undefined && minWeight !== undefined) {
            if (isRandomWeighInMode) {
                const randomMinWeight = 10;
                // 【新】套用小數點第二位無條件為 9 的規則
                let rawMax = Math.floor(maxWeight) * 1.05;
                let randomMaxWeight = parseFloat((Math.floor(rawMax * 10) / 10 + 0.09).toFixed(2));
                if (isPlus100gActive) {
                    randomMaxWeight = parseFloat((randomMaxWeight + 0.1).toFixed(2));
                }
                weightRangeEl.parentElement.querySelector('span').textContent = '體重範圍：';
                weightRangeEl.textContent = `${randomMinWeight.toFixed(2)} - ${randomMaxWeight.toFixed(2)} kg`;
            } else {
                weightRangeEl.parentElement.querySelector('span').textContent = '體重範圍：'; // 恢復提示文字
                // 【核心修正】補上正常模式下應顯示的體重範圍
                weightRangeEl.textContent = `${minWeight.toFixed(2)} - ${maxWeight.toFixed(2)} kg`;
            }
        } else {
            weightRangeEl.textContent = 'N/A';
        }
        
        // 觸發一次體重狀態的重新判斷
        checkWeightStatus(parseFloat(weightDisplayEl.textContent), activeCategory);
    }


    function updateMainDisplay(playerData, categoryData) {
        activePlayer = playerData;
        activeCategory = categoryData;
        
        updateUIForMode();
    
        weightDisplayEl.textContent = '-- kg';
        statusDisplayEl.className = 'status-display-box';
    
        cameraImage.src = `/api/camera_feed?t=${new Date().getTime()}`; 
        savedPhotoImage.src = ''; 
        savedPhotoPlaceholder.style.display = 'block';

        if (isRandomWeighInMode) {
            historyDisplay.innerHTML = '<p>未抽磅</p>';
        } else {
            updateHistoryDisplay(playerData.id);
        }
    
        startWeightFetching(categoryData);
    }
    
    function startWeightFetching(categoryData) {
        if (weightInterval) clearInterval(weightInterval);
        weightInterval = setInterval(async () => {
            try {
                const response = await fetch('/api/weight');
                const data = await response.json();
                const weight = data.weight;

                weightDisplayEl.textContent = `${weight.toFixed(2)} kg`;
                
                checkWeightStatus(weight, categoryData);

            } catch (error) {
                console.error("無法獲取體重:", error);
                stopWeightFetching();
            }
        }, 200);
    }

    function stopWeightFetching() {
        if (weightInterval) {
            clearInterval(weightInterval);
            weightInterval = null;
        }
    }
    
    function log(message) {
        const li = document.createElement('li');
        const timestamp = new Date().toLocaleTimeString('en-GB');
        li.textContent = `[${timestamp}] ${message}`;
        if(logList) {
            logList.appendChild(li);
            logList.scrollTop = logList.scrollHeight;
        }
    }

    function showCustomConfirm(message, onConfirm) {
        customConfirmMessage.textContent = message;

        const newYesBtn = customConfirmYesBtn.cloneNode(true);
        customConfirmYesBtn.parentNode.replaceChild(newYesBtn, customConfirmYesBtn);

        const newNoBtn = customConfirmNoBtn.cloneNode(true);
        customConfirmNoBtn.parentNode.replaceChild(newNoBtn, customConfirmNoBtn);

        customConfirmYesBtn = newYesBtn;
        customConfirmNoBtn = newNoBtn;

        const closeConfirm = () => {
            customConfirmOverlay.classList.remove('active');
        };

        newYesBtn.addEventListener('click', () => {
            onConfirm();
            closeConfirm();
        });

        newNoBtn.addEventListener('click', () => {
            log('使用者取消了操作。');
            closeConfirm();
        });

        customConfirmOverlay.addEventListener('click', (event) => {
            if (event.target === customConfirmOverlay) {
                closeConfirm();
            }
        });

        customConfirmOverlay.classList.add('active');
    }

    async function updateHistoryDisplay(playerId) {
        try {
            const historyResponse = await fetch(`/api/player/history/${playerId}`);
            const historyResult = await historyResponse.json();
            
            if (historyResult.error) {
                log(`查詢歷史記錄失敗: ${historyResult.error}`);
                historyDisplay.innerHTML = '<p>查詢歷史記錄失敗</p>';
                return;
            }

            const playerLi = playerList.querySelector(`li[data-player-id="${playerId}"]`);
            if (playerLi) {
                const playerData = playerLi.dataset;
                let infoPrefix = '';
                if (isRandomWeighInMode) {
                    infoPrefix = "隨機過磅：";
                } else {
                    infoPrefix = `第 ${historyResult.next_attempt_number} 次過磅:`;
                }
                currentPlayerInfoEl.textContent = `${infoPrefix} ${playerData.bib}-${playerData.name}-${playerData.team}`;
            }

            historyDisplay.innerHTML = ''; 
            if (historyResult.history && historyResult.history.length > 0) {
                historyResult.history.forEach((rec, index) => {
                    const p = document.createElement('p');
                    const statusText = rec.status === 'passed' ? '通過' : '未通過';
                    const time = new Date(rec.timestamp).toLocaleTimeString('en-GB');

                    const recordPrefix = rec.is_random ? '隨機過磅' : `第 ${index + 1} 次`;
                    p.textContent = `${recordPrefix}: ${rec.weight.toFixed(2)}kg (${statusText}) @ ${time}`;

                    historyDisplay.appendChild(p);
                });
            } else {
                if (!isRandomWeighInMode) {
                    historyDisplay.innerHTML = '<p>尚無過磅記錄</p>';
                }
            }
            
            historyDisplay.scrollTop = historyDisplay.scrollHeight;

        } catch (error) {
            log(`查詢歷史記錄失敗: ${error}`);
            historyDisplay.innerHTML = '<p>查詢歷史記錄失敗</p>';
        }
    }

    function filterCategories() {
        const filterText = categoryFilterInput.value.toLowerCase().trim();
        const categories = categoryList.querySelectorAll('li');

        categories.forEach(li => {
            const categoryName = li.textContent.toLowerCase();
            if (categoryName.includes(filterText)) {
                li.style.display = 'flex';
            } else {
                li.style.display = 'none';
            }
        });
    }

    // --- 事件監聽 ---    
    if(exportResultsBtn) {
        exportResultsBtn.addEventListener('click', async () => {
            log('正在產生匯出資料，請稍候...');
            try {
                const response = await fetch('/api/export_results');
                if (!response.ok) {
                    const errorResult = await response.json();
                    throw new Error(errorResult.message || '從伺服器獲取資料失敗');
                }

                const jsonData = await response.json();
                const jsonString = JSON.stringify(jsonData, null, 4); 

                log('資料已產生，正在呼叫儲存對話框...');

                const result = await window.pywebview.api.save_file_dialog(jsonString);

                if (result.status === 'success') {
                    log(`檔案已成功儲存至: ${result.path}`);
                    alert(`檔案已成功儲存！\n路徑: ${result.path}`);
                } else if (result.status === 'cancelled') {
                    log('使用者取消儲存操作。');
                } else {
                    log(`儲存失敗: ${result.message}`);
                    alert(`儲存檔案時發生錯誤:\n${result.message}`);
                }

            } catch (error) {
                log(`匯出失敗: ${error.message}`);
                alert(`匯出過程中發生錯誤:\n${error.message}`);
            }
        });
    }

    refreshEventsBtn.addEventListener('click', () => {
        log('手動點擊重新整理賽事列表...');
        populateEvents();
    });
    
    serverIpInput.addEventListener('change', populateEvents);      

    modeRadios.forEach(radio => {
        radio.addEventListener('change', async (e) => {
            if (e.target.value === 'online') {
                onlineSettings.classList.remove('hidden');
                offlineSettings.classList.add('hidden');
                forceSyncButton.classList.remove('hidden'); // <-- 【修改】顯示按鈕
            } else {
                onlineSettings.classList.add('hidden');
                offlineSettings.classList.remove('hidden');
                forceSyncButton.classList.add('hidden'); // <-- 【修改】隱藏按鈕
            }
            await saveCurrentConfig();
            log(`模式已切換為: ${e.target.value} 並已儲存設定。`);
        });
    });

    forceSyncButton.addEventListener('click', async () => {
        const selectedMode = document.querySelector('input[name="mode"]:checked').value;
        if (selectedMode !== 'online') {
            showNotification('此功能僅在「連線模式」下可用', 'error');
            return;
        }
        
        showCustomConfirm("您確定要強制同步所有資料嗎？\n這會覆蓋本地快取，並可能需要 1-2 分鐘。", async () => {
            log('使用者手動觸發「強制同步資料」...');
            await startFullSync(); // 呼叫我們的新函式
        });
    });

    /**
     * 【新】開啟「選擇賽事以刪除」的面板
     * (此函式在密碼驗證成功後被呼叫)
     */
    async function showDeleteEventModal() {
        log('密碼正確，開啟「清除資料」面板...');
        try {
            // 1. 呼叫 API 獲取賽事列表
            const response = await fetch('/api/data/local_events');
            if (!response.ok) throw new Error('無法獲取本地賽事列表');
            const events = await response.json();

            // 2. 填充列表
            deleteEventList.innerHTML = ''; // 清空舊列表
            if (events.length === 0) {
                deleteEventList.innerHTML = '<p style="text-align: center;">資料庫中沒有可清除的資料。</p>';
                deleteSelectedBtn.disabled = true;
                deleteAllBtn.disabled = true;
            } else {
                const ul = document.createElement('ul');
                events.forEach(event => {
                    const li = document.createElement('li');
                    const label = document.createElement('label');
                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.value = event;
                    
                    label.appendChild(checkbox);
                    if (event === "未分類的舊資料") {
                        label.appendChild(document.createTextNode(` ${event} (您過去10場比賽的資料)`));
                    } else {
                        label.appendChild(document.createTextNode(` ${event}`));
                    }
                    li.appendChild(label);
                    ul.appendChild(li);
                });
                deleteEventList.appendChild(ul);
                deleteSelectedBtn.disabled = false;
                deleteAllBtn.disabled = false;
            }
            
            // 3. 顯示 Modal
            deleteEventModal.classList.add('active');
            
        } catch (error) {
            log(`開啟清除面板失敗: ${error.message}`);
            showNotification(`開啟清除面板失敗: ${error.message}`, 'error');
        }
    }

    clearCacheButton.addEventListener('click', () => {
        // 重置狀態，以免S次開啟殘留 "密碼錯誤"
        const passwordInput = document.getElementById('password-input');
        const passwordErrorMessage = document.getElementById('password-error-message');
        
        passwordInput.value = '';
        passwordErrorMessage.textContent = '';
        
        // 顯示密碼 Modal
        const passwordModalOverlay = document.getElementById('password-modal-overlay');
        passwordModalOverlay.classList.add('active');
        
        // 自動聚焦到輸入框，方便使用者
        passwordInput.focus();
    });

    function closeDeleteModal() {
        deleteEventModal.classList.remove('active');
    }
    
    // 執行刪除的通用函式
    async function handleClearData(payload, confirmMessage) {
        
        // --- ▼▼▼ 核心修正 ▼▼▼ ---
        // 1. 立刻關閉「賽事選擇」視窗
        closeDeleteModal(); 
        // --- ▲▲▲ 修正結束 ▲▲▲ ---

        // 2. 接著才顯示「防呆確認」視窗
        showCustomConfirm(confirmMessage, async () => {
            log(`正在執行清除... Payload: ${JSON.stringify(payload)}`);
            try {
                const response = await fetch('/api/data/clear_selective', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.message);
                
                log(result.message);
                showNotification(result.message, 'success');
                // closeDeleteModal(); // <--- 已移到函式最開頭
                
                // 重新整理賽事列表 (如果是連線模式)
                if (document.getElementById('mode-online').checked) {
                    populateEvents();
                }
            } catch (error) {
                log(`清除資料失敗: ${error.message}`);
                showNotification(`清除資料失敗: ${error.message}`, 'error');
            }
        });
    }

    // [全部刪除] 按鈕
    deleteAllBtn.addEventListener('click', () => {
        handleClearData(
            { delete_all: true }, 
            "您確定要「永久刪除」所有本地資料嗎？\n\n此操作不可撤銷。"
        );
    });

    // [刪除所選] 按鈕
    deleteSelectedBtn.addEventListener('click', () => {
        const selectedCheckboxes = deleteEventList.querySelectorAll('input[type="checkbox"]:checked');
        const selectedEvents = Array.from(selectedCheckboxes).map(cb => cb.value);

        if (selectedEvents.length === 0) {
            showNotification('請至少選擇一個項目', 'error');
            return;
        }

        handleClearData(
            { delete_all: false, events_to_delete: selectedEvents },
            `您確定要「永久刪除」所選的 ${selectedEvents.length} 個項目嗎？\n\n此操作不可撤銷。`
        );
    });
    
    // [取消] 按鈕
    deleteCancelBtn.addEventListener('click', closeDeleteModal);
    
    // 點擊背景關閉
    deleteEventModal.addEventListener('click', (e) => {
        if (e.target === deleteEventModal) {
            closeDeleteModal();
        }
    });

    document.querySelector('.file-input-label').addEventListener('click', async () => {
        try {
            const filePath = await window.pywebview.api.open_file_dialog();
            if (filePath) {
                fileNameDisplay.textContent = filePath.split(/[\\/]/).pop();
                fileNameDisplay.dataset.fullPath = filePath;
                fileNameDisplay.style.color = 'var(--text-color)';
            }
        } catch(e) {
            console.error("File dialog error", e);
            log("無法開啟檔案選擇對話框");
        }
    });

    startButton.addEventListener('click', async () => {
        await saveCurrentConfig();
        const scalePort = scalePortInput.value;
        const scaleSimulation = document.querySelector('input[name="sim-mode"]:checked').value === 'true';
        log('正在初始化磅秤...');
        try {
            const initResponse = await fetch('/api/scale/initialize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    scale_port: scalePort,
                    scale_simulation: scaleSimulation
                })
            });

            const initResult = await initResponse.json();
            if (!initResponse.ok) {
                alert(`磅秤初始化失敗: ${initResult.message}`);
                log(`錯誤: 磅秤初始化失敗 - ${initResult.message}`);
                return;
            }
            log(initResult.message);
        } catch (error) {
            alert(`無法連接後端以初始化磅秤: ${error}`);
            log(`錯誤: 初始化磅秤時請求失敗 - ${error}`);
            return;
        }
        
        const selectedMode = document.querySelector('input[name="mode"]:checked').value;
        if (selectedMode === 'online') {
            
            log('連線模式啟動，正在檢查本地資料庫...');
            let needsSync = false;
            
            try {
                // 1. 呼叫新 API 檢查本地資料
                const checkResponse = await fetch('/api/data/check_local');
                const checkResult = await checkResponse.json();
                
                if (checkResult.players_count === 0 || checkResult.categories_count === 0) {
                    log('本地資料庫為空，將執行首次完整同步。');
                    needsSync = true;
                } else {
                    log(`偵測到本地快取 ( ${checkResult.categories_count} 組別, ${checkResult.players_count} 選手 )。`);
                    log('略過自動同步。如需更新，請返回設定頁點選 [強制同步資料]。');
                }
                
            } catch (e) {
                log(`檢查本地資料失敗: ${e}。為求安全，將執行完整同步。`);
                needsSync = true;
            }
            
            // 2. 如果需要 (例如首次啟動)，才執行同步
            if (needsSync) {
                const syncSuccess = await startFullSync(); // 呼叫我們的重用函式
                if (!syncSuccess) {
                    log('首次同步失敗，無法啟動。');
                    return; // 停止啟動
                }
            }
            
            // 3. (原有的邏輯)
            await fetchEventInfo();
            if (serverCheckInterval) clearInterval(serverCheckInterval);
            serverStatusIndicator.style.display = 'inline-block';
            checkServerStatus();
            serverCheckInterval = setInterval(checkServerStatus, 10000);
            setupWebSocket();            
        }

        else { // Offline Mode
            const filePath = fileNameDisplay.dataset.fullPath;
            if (!filePath) {
                log('錯誤: 請先選擇一個資料檔');
                showNotification('離線模式下，請先「選擇檔案」再開始過磅！');
                return;
            }
            log(`正在從離線檔案匯入資料: ${filePath}`);
            try {
                const response = await fetch('/api/data/load_offline', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: filePath })
                });
                const result = await response.json();
                log(result.message);
                if (!response.ok) {
                    alert(`匯入失敗: ${result.message}`);
                    return;
                }
            } catch (error) {
                log(`前端 fetch 錯誤: ${error}`);
                alert(`無法連接到後端服務，請檢查程式是否仍在執行。\n錯誤: ${error}`);
                return;
            }
            
            if (serverStatusIndicator) serverStatusIndicator.style.display = 'none';
        }
        settingsScreen.classList.add('hidden');
        weighInScreen.classList.remove('hidden');
        cameraImage.src = `/api/camera_feed?t=${new Date().getTime()}`;
        await renderCategories();
        playerList.innerHTML = '';
        
        weightRangeEl.textContent = '--';
        weightDisplayEl.textContent = '-- kg';
        statusDisplayEl.textContent = '--';
        statusDisplayEl.className = 'status-display-box';
        currentPlayerInfoEl.textContent = '請從左側選擇選手';
        historyDisplay.innerHTML = '';
        savedPhotoImage.src = '';
        savedPhotoPlaceholder.style.display = 'block';
        
        activePlayer = null;
        activeCategory = null;
        
        stopWeightFetching();
        
        log('已進入過磅頁面，請選擇一個組別開始。');
    });
    
    categoryList.addEventListener('click', async (e) => {
        const li = e.target.closest('li');
        if (li) {
            stopWeightFetching();
            const categoryId = li.dataset.categoryId;
            document.querySelectorAll('#category-list li').forEach(el => el.classList.remove('active'));
            li.classList.add('active');            
            
            activeCategory = {
                id: categoryId,
                minWeight: parseFloat(li.dataset.minWeight),
                maxWeight: parseFloat(li.dataset.maxWeight)
            };
            
            playerList.innerHTML = '';
            weightRangeEl.textContent = '--';
            currentPlayerInfoEl.textContent = '請從下方選擇選手';
            weightDisplayEl.textContent = '-- kg';
            statusDisplayEl.textContent = '--';
            statusDisplayEl.className = 'status-display-box';
            historyDisplay.innerHTML = '';

            await renderPlayers(categoryId);
            log(`已選擇組別: ${li.textContent}`);
        }
    });

    playerList.addEventListener('click', async (e) => {
        const li = e.target.closest('li');
        // 排除找不到符合選手的提示文字被點擊
        if (li && li.dataset.playerId) { 
            
            let targetCategoryId = li.dataset.categoryId;
            let activeCategoryLi = categoryList.querySelector(`li[data-category-id="${targetCategoryId}"]`);

            // 自動在左側「選中」該選手所屬的組別 (視覺回饋)
            if (activeCategoryLi) {
                document.querySelectorAll('#category-list li').forEach(el => el.classList.remove('active'));
                activeCategoryLi.classList.add('active');
            }

            const playerData = {
                id: li.dataset.playerId,
                bib: li.dataset.bib,
                name: li.dataset.name,
                team: li.dataset.team
            };

            // 安全地解析體重，過濾掉 "null" 或 "undefined" 字串
            const safeParseFloat = (val, backupVal) => {
                const parsed = parseFloat(val);
                return (isNaN(parsed) || val === "null") ? parseFloat(backupVal || 0) : parsed;
            };

            const categoryData = {
                id: targetCategoryId,
                minWeight: safeParseFloat(li.dataset.minWeight, activeCategoryLi ? activeCategoryLi.dataset.minWeight : 0),
                maxWeight: safeParseFloat(li.dataset.maxWeight, activeCategoryLi ? activeCategoryLi.dataset.maxWeight : 0)
            };
            
            document.querySelectorAll('#player-list li').forEach(el => el.classList.remove('active'));
            li.classList.add('active');
            log(`已選擇選手: ${playerData.name}`);

            try {
                updateMainDisplay(playerData, categoryData);
                await updateHistoryDisplay(playerData.id);
                const photoResponse = await fetch(`/api/player/photo_exists/${playerData.id}`);
                const photoResult = await photoResponse.json();
                if (photoResult.exists) {
                    savedPhotoImage.src = `${photoResult.photo_url}?t=${new Date().getTime()}`;
                    savedPhotoPlaceholder.style.display = 'none';
                } else {
                    savedPhotoImage.src = '';
                    savedPhotoPlaceholder.style.display = 'block';
                }
                
                // 【核心體驗】點擊選手後，立刻將游標鎖定回搜尋框
                if (globalPlayerSearch) {
                    globalPlayerSearch.focus();
                }

            } catch (error) {
                log(`處理選手選擇時發生錯誤: ${error}`);
            }
        }
    });
    
    document.addEventListener('keyup', (e) => {
        if (e.key === 'Escape' && !weighInScreen.classList.contains('hidden')) {
            stopWeightFetching();

            if (ws) {
                ws.close();
                ws = null;
            }

            if (serverCheckInterval) {
                clearInterval(serverCheckInterval);
                serverCheckInterval = null;
            }

            settingsScreen.classList.remove('hidden');
            weighInScreen.classList.add('hidden');
            log('返回系統設置畫面。');
        }
    });

    randomWeighInBtn.addEventListener('click', () => {
        if (!isRandomWeighInMode) {
            showCustomConfirm("您確定要開啟「隨機過磅」模式嗎？", () => {
                isRandomWeighInMode = true;
                randomWeighInBtn.classList.add('active');
                log(`隨機過磅模式已 開啟`);

                updateUIForMode();
                if (activeCategory && activeCategory.id) {
                    renderPlayers(activeCategory.id);
                }
            });
        } else {
            isRandomWeighInMode = false;
            randomWeighInBtn.classList.remove('active');
            log(`隨機過磅模式已 關閉`);

            isPlus100gActive = false;
            add100gBtn.classList.remove('active');

            updateUIForMode();
            if (activeCategory && activeCategory.id) {
                renderPlayers(activeCategory.id);
            }
        }
    });

    const saveButton = document.getElementById('save-button');
    saveButton.addEventListener('click', async () => {
        if (!activePlayer) {
            alert("請先選擇一位選手！");
            return;
        }

        const currentWeightText = weightDisplayEl.textContent;
        const currentStatus = statusDisplayEl.textContent;

        if (currentWeightText.includes('--') || currentStatus.includes('--')) {
            alert("無法儲存，體重或狀態無效。");
            return;
        }

        const weight = parseFloat(currentWeightText);
        const status = (currentStatus === '通過') ? 'passed' : 'failed';
        
        const apiUrl = isRandomWeighInMode 
            ? '/api/player/save_random_weigh_in'
            : '/api/player/save_weigh_in';

        // 【核心修正】準備要傳送的資料 payload
        const payload = { id: activePlayer.id, weight: weight, status: status };

        // 【核心修正】如果是隨機模式，則計算並加上體重上限
        if (isRandomWeighInMode) {
            // 增加一個檢查，確保 activeCategory.maxWeight 是有效的數字
            if (activeCategory && !isNaN(activeCategory.maxWeight)) {
                // 【新】套用小數點第二位無條件為 9 的規則
                let rawMax = Math.floor(activeCategory.maxWeight) * 1.05;
                let randomMaxWeight = parseFloat((Math.floor(rawMax * 10) / 10 + 0.09).toFixed(2));
                if (isPlus100gActive) {
                    randomMaxWeight = parseFloat((randomMaxWeight + 0.1).toFixed(2));
                }
                // 將計算結果（保留兩位小數）加入 payload
                payload.upper_limit = parseFloat(randomMaxWeight.toFixed(2));
            } else {
                // 如果找不到或無效，則傳送 null
                payload.upper_limit = null;
                log('警告：無法計算隨機過磅的體重上限，因為找不到有效的組別最大體重。');
            }
        }

        log(`準備儲存選手 ${activePlayer.name} 的[${isRandomWeighInMode ? '隨機' : '正常'}]過磅結果...`);

        try {
            const saveResponse = await fetch(apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload) // 使用我們剛剛建立的 payload
            });

            const saveResult = await saveResponse.json();
            if (!saveResponse.ok) { throw new Error(saveResult.message || '儲存至伺服器失敗'); }

            log(`伺服器回覆: ${saveResult.message}`);
            
            if (saveResult.photo_url) {
                savedPhotoImage.src = `${saveResult.photo_url}?t=${new Date().getTime()}`;
                savedPhotoPlaceholder.style.display = 'none';
            }
            if (!isRandomWeighInMode) {
                const playerLi = playerList.querySelector(`li[data-player-id="${activePlayer.id}"]`);
                if (playerLi) {
                    const statusSpan = playerLi.querySelector('.player-status');
                    if (statusSpan) {
                        statusSpan.textContent = `(${translateStatus(status)})`;
                        statusSpan.className = `player-status status-${status}`;
                    }
                }
            }
            await updateHistoryDisplay(activePlayer.id);

            // 讀取設定的數量
            const printCopies = parseInt(printCopiesInput.value, 10) || 0;
            
            if (saveResult.history_id && printCopies > 0) {
                log(`準備列印標籤 (History ID: ${saveResult.history_id}, 數量: ${printCopies})...`);
                const printResponse = await fetch(`/api/print_label/${saveResult.history_id}`, { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ copies: printCopies }) // 傳送列印數量
                });
                const printResult = await printResponse.json();
                if (!printResponse.ok) {
                    alert(`列印失敗: ${printResult.message}`);
                    log(`列印失敗: ${printResult.message}`);
                } else {
                    log('標籤已成功發送至印表機佇列');
                }
            } else if (printCopies === 0) {
                log('已設定不列印標籤，略過列印步驟。');
            }

            if (globalPlayerSearch) {
                globalPlayerSearch.select();
            }

        } catch (error) {
            log(`儲存或列印過程中發生錯誤: ${error.message}`);
            alert(`操作失敗: ${error.message}`);
        }
    });

    const reprintButton = document.getElementById('reprint-button');
    reprintButton.addEventListener('click', async () => {
        if (!activePlayer) {
            alert("請先選擇一位選手，才能進行重印！");
            return;
        }
        log(`準備重印選手 ${activePlayer.name} 的上一張標籤...`);
        try {
            const historyResponse = await fetch(`/api/player/history/${activePlayer.id}`);
            const historyResult = await historyResponse.json();
            if (!historyResult.history || historyResult.history.length === 0) {
                alert("這位選手沒有任何過磅記錄可供重印。");
                log(`選手 ${activePlayer.name} 無歷史記錄，無法重印。`);
                return;
            }
            const latestRecord = historyResult.history[historyResult.history.length - 1];
            const latestHistoryId = latestRecord.id;
            
            const printCopies = parseInt(printCopiesInput.value, 10) || 0;
            const copiesToPrint = printCopies > 0 ? printCopies : 1;
            
            log(`找到最新一筆記錄 ID: ${latestHistoryId}，正在傳送至印表機...`);
            const printResponse = await fetch(`/api/print_label/${latestHistoryId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ copies: copiesToPrint })
            });
            const printResult = await printResponse.json();
            if (!printResponse.ok) { throw new Error(printResult.message); }
            log(`標籤 (ID: ${latestHistoryId}) 已成功重印。`);
        } catch (error) {
            log(`重印過程中發生錯誤: ${error.message}`);
            alert(`重印失敗: ${error.message}`);
        }
    });

    add100gBtn.addEventListener('click', () => {
        if (!isRandomWeighInMode) {
            showNotification('此功能僅在「隨機過磅模式」下可用', 'error');
            return;
        }

        isPlus100gActive = !isPlus100gActive;
        add100gBtn.classList.toggle('active', isPlus100gActive);
        log(`全域上限+100g模式已 ${isPlus100gActive ? '開啟' : '關閉'}`);

        if (activePlayer) {
            updateUIForMode();
            const currentWeight = parseFloat(weightDisplayEl.textContent);
            if (!isNaN(currentWeight)) {
                checkWeightStatus(currentWeight, activeCategory);
            }
        }
    });

    categoryFilterInput.addEventListener('input', filterCategories);

    let searchTimeout = null;
    globalPlayerSearch.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();

        // 如果清空搜尋框，恢復顯示目前選擇組別的選手
        if (!query) {
            if (activeCategory && activeCategory.id) {
                renderPlayers(activeCategory.id);
            } else {
                playerList.innerHTML = ''; 
            }
            return;
        }

        // 使用 300ms 延遲，避免打字太快一直狂發請求
        searchTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/players/search?q=${encodeURIComponent(query)}`);
                const results = await response.json();

                if (results.error) {
                    log(`搜尋發生錯誤: ${results.error}`);
                    return;
                }

                playerList.innerHTML = '';
                if (results.length === 0) {
                    playerList.innerHTML = '<li style="justify-content: center; color: #888; cursor: default;">找不到符合的選手</li>';
                    return;
                }

                // 渲染成兩行式設計
                results.forEach(player => {
                    const li = document.createElement('li');
                    li.classList.add('search-result-item');
                    li.dataset.playerId = player.id;
                    li.dataset.bib = player.bib;
                    li.dataset.name = player.name;
                    li.dataset.team = player.team;
                    li.dataset.categoryId = player.category_id; // 隱藏綁定組別ID
                    li.dataset.minWeight = player.min_weight;
                    li.dataset.maxWeight = player.max_weight;

                    // 第一行：組別名稱
                    const catSpan = document.createElement('span');
                    catSpan.className = 'search-result-cat';
                    catSpan.textContent = `${player.category_name || '未知組別'}`;

                    // 第二行：選手資訊與狀態 (使用 Flexbox 讓狀態靠右)
                    const infoContainer = document.createElement('div');
                    infoContainer.style.display = 'flex';
                    infoContainer.style.justifyContent = 'space-between'; // 兩端對齊
                    infoContainer.style.alignItems = 'center';
                    infoContainer.style.width = '100%';

                    // 基本資訊文字 (移除多餘空格，與一般列表格式一致)
                    const infoText = document.createElement('span');
                    infoText.textContent = `${player.bib || ''}-${player.name || ''}-${player.team || ''}`;

                    // 狀態標籤
                    const statusSpan = document.createElement('span');
                    let statusKeyToShow = player.status || 'pending';
                    statusSpan.textContent = `(${translateStatus(statusKeyToShow)})`;
                    statusSpan.className = `player-status status-${statusKeyToShow}`;

                    // 將文字與狀態放入容器
                    infoContainer.appendChild(infoText);
                    infoContainer.appendChild(statusSpan);

                    li.appendChild(catSpan);
                    li.appendChild(infoContainer);
                    playerList.appendChild(li);
                });

            } catch (error) {
                console.error("搜尋選手失敗", error);
            }
        }, 300);
    });

    function closePasswordModal() {
        passwordModalOverlay.classList.remove('active');
        passwordInput.value = '';
        passwordErrorMessage.textContent = '';
    }

    // 處理密碼 Modal 的「確定」按鈕
    passwordSubmitBtn.addEventListener('click', async () => {
        const password = passwordInput.value;
        const correctPassword = "42867428"; // 您指定的密碼

        if (password === correctPassword) {
            closePasswordModal();
            await showDeleteEventModal(); // 驗證成功，呼叫我們剛才建立的函式
        } else {
            log('密碼輸入錯誤。');
            passwordErrorMessage.textContent = '密碼錯誤！'; // 顯示錯誤訊息
            passwordInput.value = '';
            passwordInput.focus();
        }
    });

    // 支援在輸入框按 Enter 鍵
    passwordInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            passwordSubmitBtn.click();
        }
    });

    // 處理「取消」按鈕
    passwordCancelBtn.addEventListener('click', closePasswordModal);
    
    // 處理點擊背景關閉
    passwordModalOverlay.addEventListener('click', (e) => {
        if (e.target === passwordModalOverlay) {
            closePasswordModal();
        }
    });

    document.addEventListener('click', (e) => {
        // 1. 確保目前是在「過磅畫面」才執行鎖定 (如果在設定畫面就不干擾)
        if (weighInScreen && !weighInScreen.classList.contains('hidden')) {
            
            // 2. 防呆例外：如果點擊的目標是「組別搜尋框」或是其他文字輸入框，就不要搶走游標
            if (e.target.id === 'category-filter' || e.target.tagName === 'INPUT') {
                return; // 中斷執行，讓游標乖乖留在被點擊的輸入框裡
            }

            // 3. 如果點擊的是按鈕、清單、背景等其他地方，一律把游標抓回全域搜尋框
            if (globalPlayerSearch) {
                globalPlayerSearch.focus();
            }
        }
    });

    let ws = null;
    function setupWebSocket() {
        // 從目前的伺服器 IP 設定中提取主機名
        const serverIp = serverIpInput.value.trim().replace(/\/+$/, '');
        if (!serverIp || document.getElementById('mode-offline').checked) return;

        try {
            // 轉換 http 為 ws
            const wsUrl = serverIp.replace('http', 'ws') + '/ws/events';
            log(`正在嘗試建立即時同步連線: ${wsUrl}`);
            
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                log('● 即時同步連線已建立。');
            };

            ws.onmessage = async (event) => {
                try {
                    const payload = JSON.parse(event.data);
                    
                    // 監聽單一選手更新事件
                    if (payload.type === 'player_updated' && payload.data) {
                        
                        // 1. 呼叫輕量級 API 寫入本地資料庫
                        const syncResponse = await fetch('/api/data/silent_single_sync', { 
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload.data)
                        });
                        const syncResult = await syncResponse.json();
                        
                        if (syncResult.status === 'success') {
                            // 2. 如果目前畫面上剛好在顯示這名選手所屬的組別，才重新渲染畫面
                            // 這樣即使其他組別在過磅，我這邊的畫面也不會一直閃爍！
                            if (activeCategory && activeCategory.id) {
                                if (globalPlayerSearch && globalPlayerSearch.value.trim()) {
                                    globalPlayerSearch.dispatchEvent(new Event('input')); // 刷新搜尋結果
                                } else {
                                    renderPlayers(activeCategory.id); // 刷新該組別清單
                                }
                            }
                        }
                    }
                    
                    // (可選) 如果主系統做了架構大改(如更改組別名稱)，收到全域更新時再考慮重新整理
                    // 但平常過磅時就不會觸發這個了
                    if (payload.type === 'event_list_updated') {
                         log('賽事架構有重大變更，請考慮手動點擊「同步資料」按鈕。');
                    }

                } catch (e) {
                    console.error("解析 WebSocket 訊息失敗", e);
                }
            };

            ws.onclose = () => {
                console.log('WebSocket 連線中斷，3秒後嘗試重連...');
                setTimeout(setupWebSocket, 3000); // 自動重連
            };

            ws.onerror = (err) => {
                console.error('WebSocket 發生錯誤:', err);
                ws.close();
            };
        } catch (err) {
            console.error('初始化 WebSocket 失敗:', err);
        }
    }
    
    // --- 程式啟動時執行的初始化 ---
    await loadAndApplyConfig();
});