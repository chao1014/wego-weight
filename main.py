# main.py (已升級為支援賽事下拉選單 v5)
import webview
from flask import Flask, render_template, jsonify, request, send_from_directory, Response
import json
import os
import sqlite3
import serial
import threading
import time
import random
from pygrabber.dshow_graph import FilterGraph
import win32print
import logging
import cv2
import base64
import win32api
import subprocess
import qrcode
from weasyprint import HTML, CSS
import datetime
import requests
from PIL import Image, ImageWin
import win32ui
import fitz 
from flask import Response

# --- 0. 日誌設定 ---
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# --- 應用程式設定 ---
CONFIG_FILE = 'config.json'
DB_FILE = 'weigh_in.db'

# --- 1. 核心類別 (維持不變) ---
class ScaleReader:
    def __init__(self):
        self.weight = 0.0
        self.port = None
        self.baudrate = 9600
        self.is_running = False
        self.is_simulating = False
        self.thread = None
        self.ser = None
    def _read_loop_real(self):
        while self.is_running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    # 1. 讀取原始資料
                    line = self.ser.readline().decode('ascii').strip()
                    
                    # 2. 用逗號分割字串
                    parts = line.split(',')
                    
                    # 3. 檢查資料是否是我们預期的格式 (以 US,GS, 開頭)
                    if len(parts) >= 3 and parts[0] == 'US' and parts[1] == 'GS':
                        # 取得包含體重的部分，例如 "   10.54kg"
                        weight_str_raw = parts[2]
                        
                        # 移除前後多餘的空格 -> "10.54kg"
                        weight_str_cleaned = weight_str_raw.strip()
                        
                        # 移除 "kg" 單位 (不分大小寫) -> "10.54"
                        weight_str_no_unit = weight_str_cleaned.lower().replace('kg', '')
                        
                        # 將純數字的字串轉換為浮點數
                        self.weight = float(weight_str_no_unit)
                        
                time.sleep(0.05)
            except Exception as e:
                logging.error(f"讀取或解析磅秤資料時發生錯誤: {e}", exc_info=True)
                self.weight = -1 # 發生錯誤時回傳 -1
                time.sleep(1)
    def _read_loop_simulation(self):
        base_weight = 40.0
        while self.is_running:
            self.weight = base_weight + random.uniform(-2.0, 2.0)
            time.sleep(0.2)
    def start(self, port, simulation=False):
        if self.is_running: self.stop()
        self.is_simulating = simulation
        self.port = port
        if self.is_simulating:
            self.is_running = True
            self.thread = threading.Thread(target=self._read_loop_simulation, daemon=True)
            self.thread.start()
            logging.info("磅秤模擬器已啟動")
            return True
        else:
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
                self.is_running = True
                self.thread = threading.Thread(target=self._read_loop_real, daemon=True)
                self.thread.start()
                logging.info(f"磅秤讀取器已在 {self.port} 啟動")
                return True
            except serial.SerialException as e:
                logging.error(f"無法開啟序列埠 {self.port}: {e}")
                self.ser = None
                return False
    def stop(self):
        self.is_running = False
        if self.thread and self.thread.is_alive(): self.thread.join(timeout=1)
        if self.ser and self.ser.is_open: self.ser.close()
        self.thread = None
        self.ser = None
        logging.info("磅秤讀取器/模擬器已停止")
    def get_weight(self):
        return self.weight
scale_reader = ScaleReader()

class CameraManager:
    def __init__(self):
        self.camera_id = 0
        self.is_running = False
        self.thread = None
        self.cap = None
        self.frame = None
        self.lock = threading.Lock()
    def _capture_loop(self):
        logging.info(f"攝影機 {self.camera_id} 抓取迴圈啟動")
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                logging.warning("無法抓取影像幀，可能攝影機已中斷"); time.sleep(0.5); continue
            with self.lock: self.frame = frame
            time.sleep(0.03)        
        logging.info(f"攝影機 {self.camera_id} 抓取迴圈已停止")
    def start(self, camera_id=0):
        if self.is_running: self.stop()
        self.camera_id = camera_id
        self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            logging.error(f"無法開啟攝影機 {self.camera_id}")
            self.cap.release()
            self.cap = None
            return False
        
        # 嘗試設定您期望的解析度 (例如 1920x1080)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
        # 【核心修改】從攝影機驅動程式讀取實際的解析度
        actual_width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        
        # 【核心修改】將實際解析度寫入日誌檔案
        logging.info(f"攝影機 {self.camera_id} 已啟動。實際擷取解析度: {int(actual_width)}x{int(actual_height)}")
        
        self.is_running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        return True
    def stop(self):
        self.is_running = False
        if self.thread and self.thread.is_alive(): self.thread.join(timeout=1)
        self.thread = None
        self.cap = None
    def get_jpeg_frame(self):
        with self.lock:
            if self.frame is None: return None            
            ret, jpeg = cv2.imencode('.jpg', self.frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
            return jpeg.tobytes() if ret else None
    def save_current_frame(self, file_path):
        with self.lock:
            if self.frame is not None:
                try:                    
                    ret, buf = cv2.imencode('.jpg', self.frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
                    if not ret: logging.error("cv2.imencode 影像編碼失敗"); return False
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, 'wb') as f: f.write(buf)
                    logging.info(f"照片已成功儲存至: {file_path}")
                    return True
                except Exception as e:
                    logging.error(f"儲存照片時發生預期外錯誤: {e}", exc_info=True); return False
        logging.warning("嘗試儲存照片，但沒有可用的影像幀 (self.frame is None)"); return False
camera_manager = CameraManager()

# --- 2. 資料庫與輔助函式 ---
def init_database():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # (原有的 categories 和 players 資料表... 保持不變)
        cursor.execute('CREATE TABLE IF NOT EXISTS categories (id TEXT PRIMARY KEY, name TEXT NOT NULL, min_weight REAL, max_weight REAL)')
        cursor.execute('CREATE TABLE IF NOT EXISTS players (id TEXT, bib TEXT, name TEXT NOT NULL, team TEXT, category_id TEXT, weight REAL, status TEXT DEFAULT "pending", PRIMARY KEY(id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS weigh_in_history (id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT, weight REAL NOT NULL, status TEXT NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, is_random BOOLEAN DEFAULT 0, upper_limit REAL, is_synced BOOLEAN DEFAULT 0)')

        # --- ▼▼▼ 核心修改：為所有資料表新增 event_name 欄位 ▼▼▼ ---
        def add_event_name_column(table_name):
            try:
                cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN event_name TEXT')
                logging.info(f"成功為 {table_name} 資料表新增 'event_name' 欄位。")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    logging.info(f"'event_name' 欄位已存在於 {table_name}，無需新增。")
                else:
                    raise e
        
        add_event_name_column('categories')
        add_event_name_column('players')
        add_event_name_column('weigh_in_history')
        # --- ▲▲▲ 修改結束 ▲▲▲ ---

        # (原有的 is_synced 欄位檢查... 保持不變)
        try:
            cursor.execute('ALTER TABLE weigh_in_history ADD COLUMN is_synced BOOLEAN DEFAULT 0')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e): raise e

        conn.commit()
        conn.close()
        logging.info("資料庫初始化成功 (已檢查 event_name 和 is_synced 欄位)")
    except Exception as e:
        logging.error(f"資料庫初始化失敗: {e}", exc_info=True)

def save_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_config():
    default_config = {
        "mode": "offline", 
        "server_ip": "http://127.0.0.1:5000", 
        "printer": None, 
        "camera": None, 
        "scale_port": "COM3", 
        "scale_simulation": True, 
        "event_name": "", 
        "save_photo": True,
        "print_copies": 2,
        "update_source": "Y:\\競賽軟體"
    }
    if not os.path.exists(CONFIG_FILE):
        save_config(default_config)
        return default_config
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        for key, value in default_config.items():
            config.setdefault(key, value)
        return config
    except (json.JSONDecodeError, FileNotFoundError):
        save_config(default_config)
        return default_config

def get_printers():
    try:
        return [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
    except Exception as e:
        logging.warning(f"無法獲取印表機列表: {e}"); return []

def get_cameras():
    try:
        return [{"id": i, "name": name} for i, name in enumerate(FilterGraph().get_input_devices())]
    except Exception as e:
        logging.warning(f"無法使用 pygrabber 獲取攝影機列表: {e}"); return []

def get_event_id_from_name(config):
    event_name_to_find = config.get('event_name')
    if not event_name_to_find:
        raise ValueError("設定中未提供賽事名稱 (event_name)")
    
    try:        
        api_url = f"{config['server_ip']}/api/events"
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        events = response.json()
        
        for event in events:
            if event.get('name') == event_name_to_find:
                event_id = event.get('id')
                if event_id:
                    logging.info(f"成功找到賽事 '{event_name_to_find}' 的 ID: {event_id}")
                    return event_id
        
        logging.error(f"在主系統中找不到名稱為 '{event_name_to_find}' 的賽事")
        raise ValueError(f"在主系統中找不到名稱為 '{event_name_to_find}' 的賽事")

    except requests.exceptions.RequestException as e:
        logging.error(f"從主系統查詢賽事列表時失敗: {e}")
        raise ConnectionError(f"無法連接主系統查詢賽事ID: {e}")
    except (ValueError, KeyError) as e:
        logging.error(f"解析賽事列表時出錯: {e}")
        raise ValueError(f"主系統回傳的賽事列表格式不正確: {e}")


# --- 3. Flask App ---
base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
template_dir = os.path.join(base_dir, 'static')
static_dir = os.path.join(base_dir, 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# --- 4. API & 頁面路由 ---
@app.route('/api/config/load', methods=['GET'])
def api_load_config(): return jsonify(load_config())

@app.route('/api/config/save', methods=['POST'])
def api_save_config():
    # 確保此函式是更新邏輯，而非覆蓋
    current_config = load_config()
    current_config.update(request.json)
    save_config(current_config)
    
    logging.info(f"設定已儲存: {current_config}")
    return jsonify({"status": "success"})

@app.route('/api/devices', methods=['GET'])
def api_get_devices(): return jsonify({"printers": get_printers(), "cameras": get_cameras()})

@app.route('/api/camera/control', methods=['POST'])
def api_camera_control():
    data = request.json
    action = data.get('action')
    if action == 'stop':
        camera_manager.stop()
        logging.info("收到前端請求：已徹底斷開攝影機硬體連結")
        return jsonify({"status": "success", "message": "攝影機已斷開"})
    return jsonify({"status": "error", "message": "無效的指令"}), 400

# 用來獲取所有賽事列表
@app.route('/api/events', methods=['GET'])
def api_get_events():
    config = load_config()
    if config['mode'] != 'online' or not config.get('server_ip'):
        return jsonify([]) # 非連線模式或未設定IP，回傳空列表
    try:        
        api_url = f"{config['server_ip']}/api/events"
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        events = response.json()
        
        # --- 【▼▼▼ 核心修正處 ▼▼▼】 ---
        
        # 過濾列表，只保留 competition_type 為 'sparring' (對打) 的賽事
        # 您的 app.py 傳來的 events 列表中包含了 'competition_type' 欄位
        sparring_events = [
            e for e in events 
            if e.get("competition_type") == 'sparring' and e.get("id") and e.get("name")
        ]
        
        # 我們只回傳 "已過濾" 列表中的 id 和 name
        event_list = [{"id": e.get("id"), "name": e.get("name")} for e in sparring_events]
        
        # --- 【▲▲▲ 核心修正處結束 ▲▲▲】 ---

        return jsonify(event_list)
    
    except requests.exceptions.RequestException as e:
        logging.error(f"無法從主系統獲取賽事列表: {e}")
        return jsonify({"error": f"無法連接主系統: {e}"}), 500

@app.route('/api/data/load_offline', methods=['POST'])
def api_load_offline():
    file_path = request.json.get('path')
    logging.info(f"接收到離線匯入請求，檔案路徑: {file_path}")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "檔案不存在或路徑無效"}), 400
    try:
        with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
        
        # --- ▼▼▼ 修改：獲取 event_name ▼▼▼ ---
        # 優先從 JSON 檔案讀取，若無，則從 config 讀取
        event_name = data.get('event_name')
        if not event_name:
            event_name = load_config().get('event_name')
            if not event_name:
                 # 從 sample_data.json 來的範例
                event_name = "離線範例賽事"
        logging.info(f"離線匯入：使用賽事名稱 '{event_name}'")
        # --- ▲▲▲ 修改結束 ▲▲▲ ---

        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 10000")
        
        # --- ▼▼▼ 修改：刪除時指定 event_name ▼▼▼ ---
        cursor.execute("DELETE FROM players WHERE event_name = ?", (event_name,))
        cursor.execute("DELETE FROM categories WHERE event_name = ?", (event_name,))
        # --- ▲▲▲ 修改結束 ▲▲▲ ---

        # (處理 categories)
        categories_to_insert = data['categories']
        for cat in categories_to_insert: cat['event_name'] = event_name # <-- 【新增】
        cursor.executemany(
            "INSERT OR REPLACE INTO categories VALUES (:id, :name, :min_weight, :max_weight, :event_name)", 
            categories_to_insert
        )
        
        # (處理 players)
        players_to_insert = data['players']
        for p in players_to_insert: p['event_name'] = event_name # <-- 【新增】
        cursor.executemany(
            "INSERT OR REPLACE INTO players (id, bib, name, team, category_id, event_name) VALUES (:id, :bib, :name, :team, :category_id, :event_name)", 
            players_to_insert
        )
        logging.info("開始根據歷史記錄更新選手狀態...")
        cursor.execute("SELECT id FROM players")
        player_ids = [row[0] for row in cursor.fetchall()]
        update_count = 0
        for player_id in player_ids:
            cursor.execute("SELECT status, weight FROM weigh_in_history WHERE player_id = ? ORDER BY timestamp DESC LIMIT 1",(player_id,))
            latest_record = cursor.fetchone()
            if latest_record:
                latest_status, latest_weight = latest_record
                cursor.execute("UPDATE players SET status = ?, weight = ? WHERE id = ?",(latest_status, latest_weight, player_id))
                update_count += 1
        logging.info(f"狀態更新完成，共更新了 {update_count} 位選手的狀態。")
        conn.commit(); conn.close()
        message = f"成功匯入 {len(data['categories'])} 個組別, {len(data['players'])} 位選手"
        logging.info(message)
        return jsonify({"status": "success", "message": message})
    except Exception as e:
        logging.error(f"離線匯入或狀態更新失敗: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"匯入時發生未知錯誤: {e}"}), 500
    
@app.route('/api/data/silent_single_sync', methods=['POST'])
def api_silent_single_sync():
    """
    【精準同步】只更新一位選手的體重與狀態，極大降低系統與網路負載。
    """
    config = load_config()
    if config['mode'] != 'online':
        return jsonify({"status": "skipped"}), 200
    
    data = request.json
    player_id = data.get('id')
    event_name = config.get('event_name')

    if not player_id:
        return jsonify({"error": "缺少 player_id"}), 400

    # 判斷主系統傳來的是正常過磅還是隨機過磅的欄位
    weight = data.get('weight') if 'weight' in data else data.get('random_weight')
    main_status = data.get('weight_status') if 'weight_status' in data else data.get('random_weight_status')

    # 狀態翻譯 (主系統 -> 過磅系統)
    local_status = 'pending'
    if main_status == '通過': local_status = 'passed'
    elif main_status == '未通過': local_status = 'failed'

    if weight is not None and main_status is not None:
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("PRAGMA busy_timeout = 10000")
            
            # 只更新這一名選手！
            cursor.execute(
                "UPDATE players SET weight = ?, status = ? WHERE id = ? AND event_name = ?",
                (weight, local_status, player_id, event_name)
            )
            conn.commit()
            conn.close()
            
            logging.info(f"[精準同步] 選手 {player_id} 狀態已更新為 {weight}kg ({local_status})")
            return jsonify({"status": "success"})
            
        except Exception as e:
            logging.error(f"精準同步失敗: {e}")
            return jsonify({"error": str(e)}), 500
            
    return jsonify({"status": "ignored"}), 200
    
@app.route('/api/data/sync_from_server', methods=['POST'])
def api_sync_from_server():
    config = load_config()
    if config['mode'] != 'online':
        return jsonify({"status": "error", "message": "非連線模式，無需同步"}), 400
    
    event_name = config.get('event_name')
    if not event_name:
        return jsonify({"status": "error", "message": "設定中缺少 'event_name'，無法同步"}), 400
    
    logging.info(f"--- 啟動連線模式完整同步 (賽事: {event_name}) ---")
    
    try:
        # --- ▼▼▼ 階段一：網路 I/O (獲取所有資料) ▼▼▼ ---
        # (此階段完全不碰本地資料庫)
        
        event_id = get_event_id_from_name(config)
        server_ip = config['server_ip']
        logging.info(f"正在從 {server_ip} 獲取組別列表...")
        cat_api_url = f"{server_ip}/api/events/{event_id}/weighin_categories"
        cat_response = requests.get(cat_api_url, timeout=10)
        cat_response.raise_for_status()
        categories_data = cat_response.json()
        logging.info(f"成功獲取 {len(categories_data)} 個組別。")

        categories_to_insert = []
        all_players_to_insert = []
        total_players = 0

        for cat in categories_data:
            categories_to_insert.append({
                "id": cat.get('id'),
                "name": cat.get('name'),
                "min_weight": cat.get('weight_min'),
                "max_weight": cat.get('weight_max'),
                "event_name": event_name 
            })

        logging.info("開始下載所有組別的選手名單...")
        for i, cat in enumerate(categories_data):
            category_id = cat.get('id')
            if not category_id: continue
            
            logging.info(f"正在獲取組別 {i+1}/{len(categories_data)} ('{cat.get('name')}') 的選手...")
            player_api_url = f"{server_ip}/api/events/{event_id}/categories/{category_id}/players"
            player_response = requests.get(player_api_url, timeout=10)
            player_response.raise_for_status()
            players_data = player_response.json()
            
            for player in players_data:
                all_players_to_insert.append({
                    "id": player.get('id'),
                    "bib": player.get('bib'),
                    "name": player.get('name'),
                    "team": player.get('team'),
                    "category_id": category_id,
                    "event_name": event_name 
                })
            total_players += len(players_data)
        
        logging.info(f"所有網路資料已下載完畢 (共 {total_players} 位選手)。")
        
        # --- ▼▼▼ 階段二：資料庫寫入 ▼▼▼ ---
        # (此階段只寫入資料庫，不再連網)
        
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("PRAGMA busy_timeout = 10000") # 保留超時設定

            logging.info(f"正在清空本地 'categories' 和 'players' (僅限賽事: {event_name})...")
            cursor.execute("DELETE FROM players WHERE event_name = ?", (event_name,))
            cursor.execute("DELETE FROM categories WHERE event_name = ?", (event_name,))
            
            logging.info(f"正在寫入 {len(categories_to_insert)} 個組別...")
            cursor.executemany(
                "INSERT OR REPLACE INTO categories VALUES (:id, :name, :min_weight, :max_weight, :event_name)", 
                categories_to_insert
            )
            
            logging.info(f"正在寫入 {len(all_players_to_insert)} 位選手...")
            cursor.executemany(
                "INSERT OR REPLACE INTO players (id, bib, name, team, category_id, event_name) VALUES (:id, :bib, :name, :team, :category_id, :event_name)",
                all_players_to_insert
            )
            
            conn.commit() # <-- 關鍵：快速提交
            message = f"同步完成！成功寫入 {len(categories_data)} 個組別, {total_players} 位選手。"
            logging.info(message)
            return jsonify({"status": "success", "message": message})

        except Exception as db_e:
            if conn:
                conn.rollback()
            logging.error(f"同步過程中，寫入資料庫時失敗: {db_e}", exc_info=True)
            return jsonify({"status": "error", "message": f"寫入本地資料庫時出錯: {db_e}"}), 500
        finally:
            if conn:
                conn.close()

    except requests.exceptions.RequestException as e:
        # 這是 "階段一" 的網路錯誤
        logging.error(f"同步過程中，下載資料時失敗: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"無法從主系統下載資料: {e}"}), 500
    except Exception as e:
        # 這是其他未知錯誤 (例如 get_event_id_from_name)
        logging.error(f"同步過程中發生未知錯誤: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"同步時發生本地錯誤: {e}"}), 500
    
@app.route('/api/data/check_local', methods=['GET'])
def api_check_local_data():
    """
    【全新】檢查本地資料庫中是否已有資料。
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM players")
        players_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM categories")
        categories_count = cursor.fetchone()[0]
        
        conn.close()
        
        logging.info(f"本地資料庫檢查: {categories_count} 組別, {players_count} 選手。")
        
        return jsonify({
            "status": "success",
            "players_count": players_count,
            "categories_count": categories_count
        })
    except Exception as e:
        logging.error(f"檢查本地資料庫時發生錯誤: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/api/data/local_events', methods=['GET'])
def api_get_local_events():
    """
    【全新】獲取本地資料庫中儲存過的所有賽事名稱列表。
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 使用 UNION 來合併三個表的 event_name 並去重
        query = """
        SELECT event_name FROM categories
        UNION
        SELECT event_name FROM players
        UNION
        SELECT event_name FROM weigh_in_history
        """
        cursor.execute(query)
        
        # 處理結果，將 (None,) 轉換為 '未分類的舊資料'
        events = [row[0] if row[0] is not None else "未分類的舊資料" for row in cursor.fetchall()]
        
        # 再次去重 (因為 '未分類' 可能來自多個表)
        unique_events = sorted(list(set(events)))
        
        conn.close()
        return jsonify(unique_events)
        
    except Exception as e:
        logging.error(f"獲取本地賽事列表時發生錯誤: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/api/data/clear_selective', methods=['POST'])
def api_clear_selective_data():
    """
    【全新 - 替換】 選擇性清除資料。
    可以清除 'all', 'uncategorized', 或指定的賽事名稱列表。
    """
    data = request.json
    delete_all = data.get('delete_all', False)
    events_to_delete = data.get('events_to_delete', [])
    
    logging.warning(f"--- 收到選擇性清除請求: delete_all={delete_all}, events={events_to_delete} ---")
    
    try:
        scale_reader.stop() # 停止硬體
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # --- ▼▼▼ 核心修正 ▼▼▼ ---
        # 告訴 SQLite，如果資料庫被鎖定，請等待 10 秒 (10000ms) 再放棄
        cursor.execute("PRAGMA busy_timeout = 10000")
        # --- ▲▲▲ 修正結束 ▲▲▲ ---

        if delete_all:
            logging.info("正在刪除 *所有* 表中的資料 (DELETE ALL)...")
            cursor.execute("DELETE FROM players")
            cursor.execute("DELETE FROM categories")
            cursor.execute("DELETE FROM weigh_in_history")
        else:
            for event_name in events_to_delete:
                param = None # 預設給 "未分類"
                if event_name != "未分類的舊資料":
                    param = event_name # 具名賽事
                
                logging.info(f"正在刪除賽事 '{event_name}' (參數: {param}) 的資料...")
                cursor.execute("DELETE FROM players WHERE event_name IS ?", (param,))
                cursor.execute("DELETE FROM categories WHERE event_name IS ?", (param,))
                cursor.execute("DELETE FROM weigh_in_history WHERE event_name IS ?", (param,))

        # (我們在上一則訊息中修正的 VACUUM 邏輯)
        logging.info("提交刪除事務...")
        conn.commit()
        
        logging.info("正在執行 VACUUM 壓縮資料庫檔案...")
        cursor.execute("VACUUM")
        
        conn.close() # VACUUM 後關閉即可
        
        logging.info("本地資料庫已成功清除。")
        config = load_config() # 重新啟動磅秤
        scale_reader.start(config['scale_port'], simulation=config['scale_simulation'])
        return jsonify({"status": "success", "message": "所選資料已清除。"})
        
    except Exception as e:
        logging.error(f"清空本地資料庫時發生錯誤: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"清空資料庫失敗: {e}"}), 500

@app.route('/api/event_info', methods=['GET'])
def api_get_event_info():
    config = load_config()
    if config['mode'] != 'online': return jsonify({})
    try:
        event_id = get_event_id_from_name(config)
        api_url = f"{config['server_ip']}/api/events/{event_id}"
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except (ValueError, ConnectionError) as e:
        logging.error(f"無法獲取賽事資訊: {e}")
        return jsonify({"error": str(e)}), 500
    except requests.exceptions.RequestException as e:
        logging.error(f"無法獲取賽事資訊: {e}")
        return jsonify({"error": f"無法連接主系統: {e}"}), 500

@app.route('/api/categories', methods=['GET'])
def api_get_categories():
    # 邏輯簡化：永遠從本地資料庫讀取
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories")
    categories = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(categories)

@app.route('/api/players', methods=['GET'])
def api_get_players():
    category_id_str = request.args.get('category_id')
    if not category_id_str: 
        return jsonify([])

    conn = None # <-- 將 conn 移到最外層
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 10000")

        # 步驟 1: 獲取該組別所有選手的基礎資料
        cursor.execute("SELECT * FROM players WHERE category_id = ?", (category_id_str,))
        players_list = [dict(row) for row in cursor.fetchall()]
        
        # 如果沒有選手，快速返回
        if not players_list:
            return jsonify([])

        # 獲取選手 ID 列表以供 IN 查詢使用
        player_ids = tuple(p['id'] for p in players_list)
        
        # 步驟 2: 一次性獲取所有選手的「隨機過磅」狀態 (has_random_weigh_in)
        # 只要在 history 中有 is_random=1 的記錄，就代表 "已抽磅"
        cursor.execute(
            f"SELECT player_id FROM weigh_in_history WHERE is_random = 1 AND player_id IN {player_ids} GROUP BY player_id"
        )
        # 將結果存入一個 Set 中以便快速查找
        random_completed_set = {row['player_id'] for row in cursor.fetchall()}

        # 步驟 3: 一次性獲取所有選手的「最新正常過磅」狀態 (status)
        # 我們使用 ROW_NUMBER() 視窗函式來找出每個選手的 "最新" (rn = 1) 一筆 "正常" (is_random = 0) 記錄
        latest_status_query = f"""
            WITH RankedHistory AS (
                SELECT 
                    player_id, 
                    status, 
                    ROW_NUMBER() OVER(
                        PARTITION BY player_id 
                        ORDER BY timestamp DESC
                    ) as rn
                FROM weigh_in_history
                WHERE (is_random = 0 OR is_random IS NULL) AND player_id IN {player_ids}
            )
            SELECT player_id, status 
            FROM RankedHistory 
            WHERE rn = 1
        """
        cursor.execute(latest_status_query)
        # 將結果存入一個 Dict 中以便快速查找
        latest_status_dict = {row['player_id']: row['status'] for row in cursor.fetchall()}

        # 步驟 4: 在 Python 中合併資料 (此時資料庫已解鎖)
        for player in players_list:
            player_id = player.get('id')
            
            # 附加 "隨機" 狀態
            player['has_random_weigh_in'] = (player_id in random_completed_set)
            
            # 附加 "正常" 狀態 (如果 Dict 中有，就用它；否則保持資料庫中的預設值 'pending')
            if player_id in latest_status_dict:
                player['status'] = latest_status_dict[player_id]

        # 回傳已附加「狀態」的選手列表
        return jsonify(players_list)

    except Exception as e:
        # 如果發生任何錯誤，記錄它
        logging.error(f"查詢選手列表時發生錯誤 (Category ID: {category_id_str}): {e}", exc_info=True)
        return jsonify({"error": f"檢查選手狀態時發生錯誤: {e}"}), 500
    finally:
        # 關鍵：無論成功或失敗，"永遠" 關閉資料庫連線
        if conn:
            conn.close()
            logging.info(f"api_get_players: 資料庫連線已關閉 (Category ID: {category_id_str})")

@app.route('/api/players/search', methods=['GET'])
def api_search_players():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    config = load_config()
    event_name = config.get('event_name')

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 10000")

        search_term = f"%{query}%"
        
        # 關聯 players 和 categories 表，並確保只搜尋目前賽事
        sql = """
            SELECT 
                p.id, p.bib, p.name, p.team, p.category_id, p.status, 
                c.name as category_name, c.min_weight, c.max_weight
            FROM players p
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE p.event_name = ? AND (p.name LIKE ? OR p.team LIKE ? OR p.bib LIKE ?)
            LIMIT 50
        """
        cursor.execute(sql, (event_name, search_term, search_term, search_term))
        players_list = [dict(row) for row in cursor.fetchall()]

        return jsonify(players_list)

    except Exception as e:
        logging.error(f"搜尋選手時發生錯誤: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/player/save_weigh_in', methods=['POST'])
def api_save_weigh_in():
    config = load_config()
    event_name = config.get('event_name') 
    data = request.json
    player_id = data.get('id')
    weight = data.get('weight')
    status = data.get('status')
    if not all([player_id, weight is not None, status]):
        return jsonify({"status": "error", "message": "請求參數不完整"}), 400

    conn = None 
    history_id = -1
    is_synced_flag = 0 # 預設為 0 (未同步)
    
    try:
        # --- ▼▼▼ 步驟 1: 執行「本地儲存」並立即提交 ▼▼▼ ---
        local_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 10000") # 保持 10 秒超時

        cursor.execute(
            "INSERT INTO weigh_in_history (player_id, weight, status, timestamp, is_random, is_synced, event_name) VALUES (?, ?, ?, ?, 0, ?, ?)",
            (player_id, weight, status, local_timestamp, is_synced_flag, event_name)
        )
        history_id = cursor.lastrowid
        
        cursor.execute("UPDATE players SET weight = ?, status = ? WHERE id = ?", (weight, status, player_id))
        
        conn.commit() # <--【核心修正】立即提交，釋放資料庫鎖定
        logging.info(f"選手 {player_id} 的歷史記錄 (ID: {history_id}) 已寫入本地並提交。")
        # --- ▲▲▲ 本地儲存結束 ▲▲▲ ---

        # --- ▼▼▼ 步驟 2: 嘗試「網路同步」(此時資料庫已解鎖) ▼▼▼ ---
        if config['mode'] == 'online':
            try:
                event_id = get_event_id_from_name(config)
                api_url = f"{config['server_ip']}/api/events/{event_id}/weighin/save"
                payload = {"player_id": player_id, "weight": weight, "status": "通過" if status == "passed" else "未通過"}
                
                response = requests.post(api_url, json=payload, timeout=5)
                response.raise_for_status()
                
                # 如果上傳成功，開啟一個「新」的事務來更新 is_synced
                is_synced_flag = 1
                cursor.execute("UPDATE weigh_in_history SET is_synced = 1 WHERE id = ?", (history_id,))
                conn.commit() # <--【核心修正】再次提交
                logging.info(f"記錄 {history_id} 已成功同步至主系統 (is_synced=1)。")

            except Exception as e:
                logging.error(f"連線模式下儲存過磅結果至主系統失敗: {e}。記錄將保留為 is_synced=0。")
                # is_synced_flag 保持為 0，等待斷線重傳
        # --- ▲▲▲ 網路同步結束 ▲▲▲ ---

        # --- 步驟 3: 處理拍照和回傳  ---
        photo_url = None
        if config.get('save_photo', True):
            attempt_count_response = api_get_player_history(player_id)
            next_attempt_number = attempt_count_response.get_json().get('next_attempt_number', 1)
            
            safe_event_name = "".join(c for c in event_name if c.isalnum() or c in (' ', '_')).rstrip()
            photo_dir = os.path.join(os.getcwd(), 'photos', safe_event_name)
            photo_filename = f"{player_id}-{next_attempt_number}.jpg"
            photo_path = os.path.join(photo_dir, photo_filename)
            
            if camera_manager.save_current_frame(photo_path):
                photo_url = f"/photos/{safe_event_name}/{photo_filename}"
        
        return jsonify({
            "status": "success", 
            "message": "儲存成功 (同步狀態: {is_synced_flag})", 
            "photo_url": photo_url, 
            "history_id": history_id
        })

    except Exception as e:
        if conn:
            conn.rollback() # 如果發生嚴重錯誤，回滾事務
        logging.error(f"儲存本地歷史或拍照時發生錯誤: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"資料庫或檔案系統錯誤: {e}"}), 500
    finally:
        if conn:
            conn.close() # 確保連線被關閉
    
@app.route('/api/player/save_random_weigh_in', methods=['POST'])
def api_save_random_weigh_in():
    config = load_config()
    event_name = config.get('event_name')
    data = request.json
    player_id = data.get('id')
    weight = data.get('weight')
    status = data.get('status')
    upper_limit = data.get('upper_limit')
    if not all([player_id, weight is not None, status]):
        return jsonify({"status": "error", "message": "請求參數不完整"}), 400

    conn = None
    history_id = -1
    is_synced_flag = 0 # 預設為 0 (未同步)
    
    try:
        # --- ▼▼▼ 步驟 1: 執行「本地儲存」並立即提交 ▼▼▼ ---
        local_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 10000") # 保持 10 秒超時

        cursor.execute(
            "INSERT INTO weigh_in_history (player_id, weight, status, timestamp, is_random, upper_limit, is_synced, event_name) VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
            (player_id, weight, status, local_timestamp, upper_limit, is_synced_flag, event_name)
        )
        history_id = cursor.lastrowid
        
        conn.commit() # <--【核心修正】立即提交，釋放資料庫鎖定
        logging.info(f"選手 {player_id} 的【隨機過磅】歷史記錄 (ID: {history_id}) 已寫入本地並提交。")
        # --- ▲▲▲ 本地儲存結束 ▲▲▲ ---

        # --- ▼▼▼ 步驟 2: 嘗試「網路同步」(此時資料庫已解鎖) ▼▼▼ ---
        if config['mode'] == 'online':
            try:
                event_id = get_event_id_from_name(config)
                api_url = f"{config['server_ip']}/api/events/{event_id}/random_weigh_in/save"
                payload = {
                    "player_id": player_id, 
                    "weight": weight, 
                    "status": status,
                    "upper_limit": upper_limit 
                }
                response = requests.post(api_url, json=payload, timeout=5)
                response.raise_for_status()
                
                # 如果上傳成功，開啟一個「新」的事務來更新 is_synced
                is_synced_flag = 1
                cursor.execute("UPDATE weigh_in_history SET is_synced = 1 WHERE id = ?", (history_id,))
                conn.commit() # <--【核心修正】再次提交
                logging.info(f"隨機過磅記錄 {history_id} 已成功同步至主系統 (is_synced=1)。")

            except Exception as e:
                logging.error(f"連線模式下儲存【隨機過磅】結果至主系統失敗: {e}。記錄將保留為 is_synced=0。")
                # is_synced_flag 保持為 0，等待斷線重傳
        # --- ▲▲▲ 網路同步結束 ▲▲▲ ---

        # --- 步驟 3: 處理拍照和回傳 (邏輯不變) ---
        photo_url = None
        attempt_count_response = api_get_player_history(player_id)
        next_attempt_number = attempt_count_response.get_json().get('next_attempt_number', 1)
        
        safe_event_name = "".join(c for c in event_name if c.isalnum() or c in (' ', '_')).rstrip()
        photo_dir = os.path.join(os.getcwd(), 'photos', safe_event_name)
        photo_filename = f"{player_id}-{next_attempt_number}.jpg"
        photo_path = os.path.join(photo_dir, photo_filename)

        if camera_manager.save_current_frame(photo_path):
            photo_url = f"/photos/{safe_event_name}/{photo_filename}"
        
        return jsonify({
            "status": "success", 
            "message": f"隨機過磅儲存成功 (同步狀態: {is_synced_flag})", 
            "photo_url": photo_url, 
            "history_id": history_id
        })

    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"儲存隨機過磅歷史或拍照時發生錯誤: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"資料庫或檔案系統錯誤: {e}"}), 500
    finally:
        if conn:
            conn.close()
    
@app.route('/api/scale/initialize', methods=['POST'])
def api_initialize_scale():
    """
    根據前端傳來的設定，重新啟動磅秤讀取器。
    """
    data = request.json
    port = data.get('scale_port')
    simulation = data.get('scale_simulation', False)

    if not port:
        return jsonify({"status": "error", "message": "未提供磅秤序列埠 (COM Port)。"}), 400

    logging.info(f"收到磅秤重新初始化請求。模式: {'模擬' if simulation else '真實'}, 序列埠: {port}")
    
    # 核心邏輯：先停止，再用新設定啟動
    scale_reader.stop()
    success = scale_reader.start(port, simulation=simulation)
    
    if success:
        return jsonify({"status": "success", "message": "磅秤已成功初始化。"})
    else:
        logging.error(f"在序列埠 {port} 上啟動磅秤失敗。")
        return jsonify({"status": "error", "message": f"無法在 {port} 啟動磅秤。"}), 500

@app.route('/api/server_connection_status', methods=['GET'])
def api_server_connection_status():
    """
    【全新 - 修正版】
    檢查「本地後端」與「主系統伺服器」之間的連線。
    """
    config = load_config() # 
    
    # 1. 如果是離線模式，根本不需要檢查
    if config.get('mode') == 'offline':
        return jsonify({"status": "offline"})

    server_ip = config.get('server_ip')
    if not server_ip:
        return jsonify({"status": "error", "message": "未設定伺服器IP"}), 500

    # 2. 嘗試 Ping 主系統的一個已知 API (例如 /api/events) 
    #    我們使用極短的超時 (connect=1.0, read=1.0)
    try:
        # 我們從同步邏輯中知道 /api/events 是一個有效的端點 
        api_url = f"{server_ip}/api/events" 
        
        # 設定 1 秒連線超時、1 秒讀取超時
        response = requests.get(api_url, timeout=(1.0, 1.0)) # 
        
        # 只要伺服器有正確回應 (2xx 狀態碼)
        if response.ok:
            return jsonify({"status": "online"})
        else:
            # 伺服器有回應，但 API 狀態碼是 4xx/5xx
            return jsonify({"status": "error", "message": f"伺服器回應 {response.status_code}"})

    except requests.exceptions.Timeout:
        # 伺服器已關閉 -> 超時
        return jsonify({"status": "error", "message": "連線超時"})
    except requests.exceptions.ConnectionError:
        # 伺服器已關閉 -> 連線被拒絕
        return jsonify({"status": "error", "message": "連線被拒絕"})
    except Exception as e:
        # 其他未知錯誤 (例如 DNS 找不到)
        return jsonify({"status": "error", "message": str(e)})
    
@app.route('/api/retry_failed_syncs', methods=['POST'])
def api_retry_failed_syncs():
    """
    【全新 - 修正版】
    嘗試重新同步所有 'is_synced = 0' 的記錄。
    此版本修正了資料庫鎖定問題。
    """
    config = load_config()
    if config['mode'] != 'online':
        return jsonify({"status": "not_online", "message": "非連線模式，無需重試"})

    logging.info("--- 啟動重傳機制：檢查未同步的記錄 ---")
    
    conn = None
    failed_records = []
    
    # 步驟 1: 連線資料庫，"只" 獲取需要處理的列表，然後 "立刻" 關閉
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 10000")
        cursor.execute("SELECT * FROM weigh_in_history WHERE is_synced = 0 OR is_synced IS NULL")
        failed_records = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logging.error(f"重傳 API - 獲取列表時發生錯誤: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            conn.close() # <-- 關鍵！立刻釋放連線

    # 步驟 2: 如果沒有記錄，直接返回
    if not failed_records:
        logging.info("重傳檢查：沒有未同步的記錄。")
        return jsonify({"status": "nothing_to_sync", "synced_count": 0})

    logging.warning(f"重傳檢查：發現 {len(failed_records)} 筆未同步的記錄。正在開始重傳...")
    
    try:
        event_id = get_event_id_from_name(config)
        synced_count = 0
        
        # 步驟 3: 迴圈處理 "列表"，而不是 "資料庫連線"
        for record in failed_records:
            record_id = record.get('id')
            is_random = record.get('is_random')
            player_id = record.get('player_id')
            
            try:
                # 步驟 3a: 執行網路請求 (資料庫此時是解鎖的)
                if is_random:
                    api_url = f"{config['server_ip']}/api/events/{event_id}/random_weigh_in/save"
                    payload = {
                        "player_id": player_id,
                        "weight": record.get('weight'),
                        "status": record.get('status'),
                        "upper_limit": record.get('upper_limit')
                    }
                else:
                    api_url = f"{config['server_ip']}/api/events/{event_id}/weighin/save"
                    payload = {
                        "player_id": player_id,
                        "weight": record.get('weight'),
                        "status": "通過" if record.get('status') == "passed" else "未通過"
                    }
                
                response = requests.post(api_url, json=payload, timeout=5)
                response.raise_for_status()
                
                # 步驟 3b: 網路成功後，"開啟新連線" 快速更新該筆記錄
                conn_update = None
                try:
                    conn_update = sqlite3.connect(DB_FILE)
                    cursor_update = conn_update.cursor()
                    cursor_update.execute("PRAGMA busy_timeout = 10000")
                    cursor_update.execute("UPDATE weigh_in_history SET is_synced = 1 WHERE id = ?", (record_id,))
                    conn_update.commit() # <-- 關鍵！立刻提交
                    synced_count += 1
                    logging.info(f"重傳成功：記錄 ID {record_id} (選手 {player_id}) 已更新至 is_synced=1。")
                except Exception as db_e:
                    logging.error(f"重傳成功，但更新本地 is_synced 狀態時失敗 (ID: {record_id}): {db_e}")
                finally:
                    if conn_update:
                        conn_update.close() # <-- 關鍵！立刻關閉

            except requests.exceptions.RequestException as e:
                logging.error(f"重傳失敗：在嘗試同步記錄 ID {record_id} 時發生網路錯誤: {e}。終止本次重傳佇列。")
                break # 網路不通，停止嘗試，等待下次
            except Exception as e:
                logging.error(f"重傳失敗：在處理記錄 ID {record_id} 時發生非預期錯誤: {e}。跳過此筆記錄。")
                continue
        
        message = f"重傳完成：成功同步 {synced_count} / {len(failed_records)} 筆記錄。"
        logging.info(message)
        return jsonify({"status": "sync_attempted", "synced_count": synced_count, "total_failed": len(failed_records)})

    except Exception as e:
        logging.error(f"重傳 API 發生嚴重錯誤: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
    # (不需要 finally { conn.close() } 因為 conn 早就關了)

@app.route('/api/weight', methods=['GET'])
def api_get_weight(): return jsonify({"weight": scale_reader.get_weight()})

@app.route('/api/player/history/<player_id>', methods=['GET'])
def api_get_player_history(player_id):
    try:
        conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        cursor.execute("SELECT id, weight, status, timestamp, is_random FROM weigh_in_history WHERE player_id = ? ORDER BY timestamp ASC", (player_id,))
        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"history": history, "next_attempt_number": len(history) + 1})
    except Exception as e:
        logging.error(f"查詢選手 {player_id} 歷史記錄時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/player/photo_exists/<player_id>', methods=['GET'])
def api_check_photo_exists(player_id):
    # 【核心修正】讀取設定檔以獲取正確的賽事名稱
    config = load_config()
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(id) FROM weigh_in_history WHERE player_id = ?", (player_id,))
        # fetchone() 可能回傳 None，需要做檢查
        result = cursor.fetchone()
        conn.close()
        
        # 如果選手沒有任何過磅記錄，直接回傳不存在
        if result is None or result[0] == 0:
            return jsonify({"exists": False})

        latest_attempt_number = result[0]

        # 【核心修正】從設定檔中取得賽事名稱並建立安全的路徑名稱
        event_name = config.get('event_name', 'default_event')
        safe_event_name = "".join(c for c in event_name if c.isalnum() or c in (' ', '_')).rstrip()
        photo_filename = f"{player_id}-{latest_attempt_number}.jpg"
        
        # 【核心修正】組合出包含賽事資料夾的完整「實體檔案路徑」
        photo_path = os.path.join(os.getcwd(), 'photos', safe_event_name, photo_filename)

        if os.path.exists(photo_path):
            # 【核心修正】組合出包含賽事資料夾的正確「網址(URL)」
            photo_url = f"/photos/{safe_event_name}/{photo_filename}"
            return jsonify({"exists": True, "photo_url": photo_url})
        
        return jsonify({"exists": False})
    except Exception as e:
        logging.error(f"查詢選手 {player_id} 照片時發生錯誤: {e}")
        return jsonify({"exists": False, "error": str(e)}), 500

def find_player_info_from_main_system(player_id):
    config = load_config()
    try:
        event_id = get_event_id_from_name(config)
        
        # --- 效率優化 ---
        # 優先嘗試直接查詢選手的 API (需要主系統支援此 API)
        # 協同建議: 請在您的主系統 app.py 中新增 GET /api/events/<event_id>/players/<player_id>
        try:
            player_direct_api_url = f"{config['server_ip']}/api/events/{event_id}/players/{player_id}"
            response = requests.get(player_direct_api_url, timeout=3)
            if response.ok:
                player_info = response.json()
                logging.info(f"透過直接查詢 API 成功找到選手 {player_id} 的資訊。")
                return player_info
            else:
                logging.warning(f"直接查詢選手 API 失敗 (狀態碼: {response.status_code})，將嘗試遍歷組別的舊方法。")
        except requests.exceptions.RequestException as direct_e:
            logging.warning(f"直接查詢選手 API 失敗: {direct_e}，將嘗試遍歷組別的舊方法。")

        # 如果直接查詢失敗，則執行原本的遍歷方法作為備用方案
        cat_api_url = f"{config['server_ip']}/api/events/{event_id}/weighin_categories"
        cat_response = requests.get(cat_api_url, timeout=5)
        cat_response.raise_for_status(); categories = cat_response.json()
        for category in categories:
            cat_id = category.get('id')
            if not cat_id: continue
            player_api_url = f"{config['server_ip']}/api/events/{event_id}/categories/{cat_id}/players"
            player_response = requests.get(player_api_url, timeout=5)
            player_response.raise_for_status(); players = player_response.json()
            for player in players:
                if player.get('id') == player_id:
                    logging.info(f"透過遍歷組別的方式在主系統中找到了選手 {player_id} 的資訊。")
                    return player

    except (ValueError, ConnectionError, requests.exceptions.RequestException) as e:
        logging.error(f"從主系統查找選手資訊時失敗: {e}")
        return None
    return None

@app.route('/api/print_label/<int:history_id>', methods=['POST'])
def api_print_label(history_id):
    config = load_config()
    try:
        BLEED_TOP_MM    = 1.0
        BLEED_BOTTOM_MM = 1.0
        BLEED_LEFT_MM   = 1.0
        BLEED_RIGHT_MM  = 1.0

        conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        # 【修正】我們也讀取 is_synced，雖然此處不用，但保持查詢一致性
        cursor.execute("SELECT player_id, weight, timestamp FROM weigh_in_history WHERE id = ?", (history_id,))
        hist_data = cursor.fetchone()
        conn.close()
        if not hist_data: return jsonify({"status": "error", "message": "找不到該筆過磅記錄"}), 404
        
        player_id = hist_data['player_id']; record_data = dict(hist_data)
        actual_weight = record_data.get('weight')
        
        if config['mode'] == 'online':
            player_info = find_player_info_from_main_system(player_id)
            if player_info: 
                # (問題點) player_info 可能包含 'weight': None，並覆蓋 hist_data['weight']
                record_data.update(player_info) 
            else: 
                logging.warning(f"無法從主系統獲取選手 {player_id} 的詳細資訊"); record_data.update({'bib': str(player_id), 'name': 'N/A', 'team': 'N/A'})
        else:
            conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
            cursor.execute("SELECT bib, name, team FROM players WHERE id = ?", (player_id,))
            player_info = cursor.fetchone(); conn.close()
            if player_info: record_data.update(dict(player_info))

        if actual_weight is not None:
            record_data['weight'] = actual_weight

        dt_object = datetime.datetime.strptime(record_data['timestamp'].split('.')[0], '%Y-%m-%d %H:%M:%S')
        formatted_timestamp = dt_object.strftime('%Y-%m-%d %H:%M:%S')
        
        template_dir = os.path.join(os.getcwd(), 'templates')
        html_template_path = os.path.join(template_dir, 'label_template.html')
        with open(html_template_path, 'r', encoding='utf-8') as f: html_content = f.read()
        
        # --- ▼▼▼ 核心修正 ▼▼▼ ---
        
        # 1. 取得體重，此時它可能是 None (如果被覆蓋)
        weight_to_print = record_data.get('weight') 

        # 2. 檢查是否為 None。如果是，則使用 0.0 作為安全預設值
        safe_weight = weight_to_print if weight_to_print is not None else 0.0
        
        if weight_to_print is None:
             logging.warning(f"列印標籤 (History ID: {history_id}) 時 'weight' 為 None。已強制設為 0.0。")

        # 3. 使用檢查過的 safe_weight 進行格式化
        html_content = html_content.replace('$name', str(record_data.get('name', '')))
        html_content = html_content.replace('$weight', f"{safe_weight:.2f}") # <-- 已修正
        html_content = html_content.replace('$team', str(record_data.get('team', '')))
        
        # --- ▲▲▲ 修正結束 ▲▲▲ ---
        
        html_content = html_content.replace('$timestamp', formatted_timestamp)
        html_content = html_content.replace('$bib', str(record_data.get('bib', '')))
        
        qr_path = os.path.join(os.getcwd(), 'qrcode_temp.png')
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=1)
        qr.add_data(str(record_data.get('bib', ''))); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white"); img.save(qr_path)
        with open(qr_path, "rb") as image_file: encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        qr_img_tag = f'<img src="data:image/png;base64,{encoded_string}">'; html_content = html_content.replace('$qrcode_img', qr_img_tag)

        labels_folder_path = os.path.join(os.getcwd(), 'labels')
        os.makedirs(labels_folder_path, exist_ok=True)
        label_pdf_path = os.path.join(labels_folder_path, f'label_{history_id}.pdf')
        final_image_path = os.path.join(labels_folder_path, f'label_final_{history_id}.png')

        css_path = os.path.join(template_dir, 'label_style.css')
        html_doc = HTML(string=html_content, base_url=template_dir)
        html_doc.write_pdf(label_pdf_path, stylesheets=[CSS(css_path)])
        
        doc = fitz.open(label_pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=300)
        doc.close()
        content_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        printer_name = config.get('printer')
        if not printer_name:
            raise ValueError("錯誤：未在設定中指定印表機。")
        
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
        printer_dpi_x = hDC.GetDeviceCaps(88)
        printer_dpi_y = hDC.GetDeviceCaps(90)
        printable_width_px = hDC.GetDeviceCaps(8)
        printable_height_px = hDC.GetDeviceCaps(10)
        hDC.DeleteDC()
        
        bleed_top_px = int(BLEED_TOP_MM / 25.4 * printer_dpi_y)
        bleed_bottom_px = int(BLEED_BOTTOM_MM / 25.4 * printer_dpi_y)
        bleed_left_px = int(BLEED_LEFT_MM / 25.4 * printer_dpi_x)
        bleed_right_px = int(BLEED_RIGHT_MM / 25.4 * printer_dpi_x)

        final_width = printable_width_px + bleed_left_px + bleed_right_px
        final_height = printable_height_px + bleed_top_px + bleed_bottom_px

        resized_img = content_img.resize((final_width, final_height), Image.Resampling.LANCZOS)
        
        final_image = resized_img.convert("1")
        final_image.save(final_image_path)
        logging.info(f"已產生含四向出血的最終圖片: {final_image_path} (尺寸: {final_width}x{final_height})")
        
        copies_to_print = 2
        data = request.get_json(silent=True)
        if data and 'copies' in data: copies_to_print = data['copies']
            
        logging.info(f"準備使用四向出血模式 (T:{BLEED_TOP_MM}, B:{BLEED_BOTTOM_MM}, L:{BLEED_LEFT_MM}, R:{BLEED_RIGHT_MM} mm) 將任務傳送至 '{printer_name}'...")
        try:
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)
            dib = ImageWin.Dib(final_image)

            for i in range(copies_to_print):
                hDC.StartDoc(f"Label {history_id} - Copy {i+1}")
                hDC.StartPage()
                dib.draw(hDC.GetHandleOutput(), (-bleed_left_px, -bleed_top_px, final_width, final_height))
                hDC.EndPage()
                hDC.EndDoc()
                logging.info(f"第 {i+1}/{copies_to_print} 份出血標籤已成功發送。")
                if copies_to_print > 1: time.sleep(1)

            hDC.DeleteDC()
            return jsonify({"status": "success", "message": f"已成功傳送 {copies_to_print} 份出血標籤至印表機 '{printer_name}'"})
        except Exception as e:
            error_message = f"四向出血模式列印過程中發生錯誤: {e}"
            logging.error(error_message, exc_info=True)
            return jsonify({"status": "error", "message": error_message}), 500
    except Exception as e:
        logging.error(f"產生或列印標籤時發生未知錯誤: {e}", exc_info=True)
        # 【修正】將原始錯誤 e 傳遞給前端，以便看到 "unsupported format" 錯誤
        return jsonify({"status": "error", "message": f"操作失敗: {e}"}), 500

@app.route('/api/export_results', methods=['GET'])
def api_export_results():
    """
    產生一個扁平化的 JSON 陣列，其中包含所有 weigh_in_history 表中的記錄。
    【已修正】現在會包含 is_random 和 upper_limit 欄位。
    """
    logging.info("收到產生過磅結果記錄的請求 (包含隨機過磅標記與上限)。")
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 【核心修正】在查詢中加入 is_random 和 upper_limit 欄位
        cursor.execute("""
            SELECT 
                player_id, 
                weight, 
                status, 
                timestamp,
                is_random,
                upper_limit 
            FROM weigh_in_history 
            ORDER BY timestamp ASC
        """)
        
        results_list = [dict(row) for row in cursor.fetchall()]

        conn.close()
        
        logging.info(f"成功產生 {len(results_list)} 筆過磅記錄。")
        
        return jsonify(results_list)

    except Exception as e:
        logging.error(f"產生過磅結果時發生錯誤: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"產生資料失敗: {e}"}), 500


@app.route('/api/camera_feed')
def camera_feed():
    def generate():
        while True:
            frame = camera_manager.get_jpeg_frame()
            if frame is None: time.sleep(0.1); continue
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return app.response_class(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/photos/<path:path>')
def serve_photo(path):
    # 新的路徑會包含資料夾和檔案名，例如 "MyEvent/player123-1.jpg"
    return send_from_directory('photos', path)

@app.route('/')
def index(): return render_template('weigh_in_ui.html')

# --- 5. pywebview 設定 (維持不變) ---
class Api:
    def open_file_dialog(self):
        file_types = ('JSON 檔案 (*.json)', '所有檔案 (*.*)')
        result = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
        return result[0] if result else None

    # 【請加入這個新函式】
    def save_file_dialog(self, data):
        file_types = ('JSON 檔案 (*.json)',)
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested_filename = f"weigh_in_results_{timestamp_str}.json"
        
        result = window.create_file_dialog(
            webview.SAVE_DIALOG, 
            directory=os.path.expanduser('~'), # 預設開啟使用者主目錄
            allow_multiple=False, 
            file_types=file_types,
            save_filename=suggested_filename
        )

        if result:
            try:
                with open(result, 'w', encoding='utf-8') as f:
                    f.write(data)
                logging.info(f"過磅結果已成功儲存至: {result}")
                return {"status": "success", "path": result}
            except Exception as e:
                logging.error(f"儲存檔案時發生錯誤: {e}", exc_info=True)
                return {"status": "error", "message": str(e)}
        else:
            logging.info("使用者取消了儲存操作。")
            return {"status": "cancelled"}

if __name__ == '__main__':
    # 授權驗證
    lic_info = None
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from packaging_tools.license_verifier import check_and_enforce
        lic_info = check_and_enforce("weight")
    except Exception as e:
        print(f"授權模組載入失敗: {e}")
        sys.exit(1)

    logging.info("應用程式啟動")
    init_database()
    config = load_config()

    # 自動檢查更新
    update_source = config.get("update_source")
    if update_source:
        try:
            from packaging_tools.updater import check_and_update
            check_and_update("WeighIn.exe", update_source)
        except Exception as update_err:
            logging.error(f"自動更新檢查失敗: {update_err}")
    logging.info(f"磅秤模擬模式: {'開啟' if config['scale_simulation'] else '關閉'}")
    scale_reader.start(config['scale_port'], simulation=config['scale_simulation'])
    if config.get('camera') is not None and config.get('save_photo', True): 
        camera_manager.start(camera_id=config['camera'])
    api = Api()
    
    title_suffix = ""
    if isinstance(lic_info, dict):
        title_suffix = f" [已授權至: {lic_info.get('expire_date', '永久')}]"
    window = webview.create_window(f'韻動國際過磅系統{title_suffix}', app, js_api=api, resizable=True, min_size=(1024, 768), maximized=True)
    
    def on_closing():
        logging.info("視窗關閉事件觸發，開始停止背景服務...")
        camera_manager.stop()
        scale_reader.stop()
        logging.info("所有背景服務已發出停止信號。")
    window.events.closing += on_closing

    try:
        logging.info("主程式準備就緒，正在關閉啟動畫面...")
        # 執行 Windows 命令，根據我們在 splash.py 中設定的獨特標題來關閉它
        os.system('taskkill /IM pythonw.exe /FI "WINDOWTITLE eq Splash_WeighIn_12345" /F')
    except Exception as e:
        logging.warning(f"無法自動關閉啟動畫面: {e}")

    webview.start(debug=False)

    logging.info("應用程式視窗已關閉，準備完全退出。")
    logging.shutdown()

