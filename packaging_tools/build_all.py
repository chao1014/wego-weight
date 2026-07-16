# build_all.py
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import subprocess

# 定義目錄結構
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # weight 根目錄
PACKAGING_DIR = os.path.join(BASE_DIR, "packaging_tools")
BUILD_DIR = os.path.join(BASE_DIR, "build")
DIST_DIR = os.path.join(BASE_DIR, "dist")
WEIGH_IN_DIR = os.path.join(DIST_DIR, "WeighIn")
BACKUP_DIR = os.path.join(BASE_DIR, "build_backup_temp")

def backup_weigh_data():
    """備份現有的授權、資料庫與照片等關鍵資料"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    backed_up = []
    
    # 1. 備份關鍵檔案
    for filename in ["license.lic", ".sys_time.dat", "weigh_in.db"]:
        src_file = os.path.join(WEIGH_IN_DIR, filename)
        if os.path.exists(src_file):
            try:
                shutil.copy2(src_file, os.path.join(BACKUP_DIR, filename))
                backed_up.append(filename)
            except Exception as e:
                print(f"  - [WARN] 備份 {filename} 失敗: {e}")
                
    # 2. 備份 photos 目錄
    photos_src = os.path.join(WEIGH_IN_DIR, "photos")
    if os.path.exists(photos_src):
        try:
            photos_dst = os.path.join(BACKUP_DIR, "photos")
            if os.path.exists(photos_dst):
                shutil.rmtree(photos_dst)
            shutil.copytree(photos_src, photos_dst)
            backed_up.append("photos/")
        except Exception as e:
            print(f"  - [WARN] 備份 photos 目錄失敗: {e}")
            
    if backed_up:
        print(f"  - 已自動備份關鍵資料: {', '.join(backed_up)}")

def restore_weigh_data():
    """還原備份的關鍵資料"""
    if not os.path.exists(BACKUP_DIR):
        return
    
    restored = []
    os.makedirs(WEIGH_IN_DIR, exist_ok=True)
    
    # 1. 還原檔案
    for filename in ["license.lic", ".sys_time.dat", "weigh_in.db"]:
        src_file = os.path.join(BACKUP_DIR, filename)
        if os.path.exists(src_file):
            try:
                dst_file = os.path.join(WEIGH_IN_DIR, filename)
                if os.path.exists(dst_file):
                    os.remove(dst_file)
                shutil.copy2(src_file, dst_file)
                restored.append(filename)
            except Exception as e:
                print(f"  - [WARN] 還原 {filename} 失敗: {e}")
                
    # 2. 還原 photos 目錄
    photos_src = os.path.join(BACKUP_DIR, "photos")
    if os.path.exists(photos_src):
        try:
            photos_dst = os.path.join(WEIGH_IN_DIR, "photos")
            if os.path.exists(photos_dst):
                for root, dirs, files in os.walk(photos_src):
                    rel_dir = os.path.relpath(root, photos_src)
                    target_dir = photos_dst if rel_dir == "." else os.path.join(photos_dst, rel_dir)
                    os.makedirs(target_dir, exist_ok=True)
                    for file in files:
                        s_file = os.path.join(root, file)
                        d_file = os.path.join(target_dir, file)
                        if os.path.exists(d_file):
                            os.remove(d_file)
                        shutil.move(s_file, d_file)
            else:
                shutil.copytree(photos_src, photos_dst)
            restored.append("photos/")
        except Exception as e:
            print(f"  - [WARN] 還原 photos 目錄失敗: {e}")
            
    if restored:
        print(f"  - 已自動還原關鍵資料: {', '.join(restored)}")
        
    # 清理備份資料夾
    try:
        shutil.rmtree(BACKUP_DIR)
    except Exception:
        pass

def install_requirements():
    """檢查並安裝 PyInstaller 與 PyArmor"""
    # 1. 檢查 PyInstaller
    try:
        import PyInstaller
        print("[OK] 偵測到已安裝 PyInstaller。")
    except ImportError:
        print("[!] 未偵測到 PyInstaller，正在嘗試安裝...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            print("[OK] PyInstaller 安裝成功！")
        except Exception as e:
            print(f"[ERR] 安裝 PyInstaller 失敗，請手動執行 pip install pyinstaller。錯誤: {e}")
            sys.exit(1)
            
    # 2. 檢查 PyArmor
    try:
        startupinfo = None
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        subprocess.check_output("pyarmor --version", shell=True, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
        print("[OK] 偵測到已安裝 PyArmor。")
    except Exception:
        print("[!] 未偵測到 PyArmor，正在嘗試安裝...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyarmor"])
            print("[OK] PyArmor 安裝成功！")
        except Exception as e:
            print(f"[ERR] 安裝 PyArmor 失敗，請手動執行 pip install pyarmor。錯誤: {e}")
            sys.exit(1)

def clean_previous_builds():
    """清理先前的 build 與 dist 資料夾，並強制結束可能的殘留進程"""
    print("[*] 正在強制終止可能被鎖定的過磅進程...")
    exes = ["WeighIn"]
    for exe in exes:
        try:
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.run(f"taskkill /F /IM {exe}.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
        except Exception:
            pass

    print("[*] 正在清理先前的編譯暫存...")
    for dir_path in [BUILD_DIR, DIST_DIR]:
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
                print(f"  - 已刪除舊資料夾: {os.path.basename(dir_path)}")
            except Exception as e:
                print(f"  - 無法刪除 {dir_path} (可能仍有檔案被系統鎖定): {e}")

def extract_imports_from_files(file_paths):
    """
    從給定的 Python 檔案列表中，自動提取所有的 import 宣告。
    """
    import_lines = []
    for path in file_paths:
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('import ') or stripped.startswith('from '):
                    if '..' not in stripped and ' .' not in stripped and not stripped.startswith('from .'):
                        import_lines.append(stripped)
    return list(set(import_lines)) # 去重

def parse_modules_from_imports(import_statements):
    """
    將 import 語句解析成可以被 PyInstaller 識別的 --hidden-import 模組清單。
    安全網：對於 from a import b, c，我們把 a, a.b, a.c 通通視為潛在的 hidden-import 子模組。
    """
    modules = set()
    for stmt in import_statements:
        if stmt.startswith('import '):
            # 處理 import a, b as c
            parts = stmt[7:].split(',')
            for p in parts:
                mod = p.split('as')[0].strip()
                if mod:
                    modules.add(mod)
        elif stmt.startswith('from '):
            # 處理 from a import b, c
            parts = stmt[5:].split(' import ')
            if len(parts) >= 2:
                parent_mod = parts[0].strip()
                sub_parts = parts[1].split(',')
                modules.add(parent_mod.split('.')[0])
                modules.add(parent_mod)
                for sp in sub_parts:
                    sub_item = sp.split('as')[0].strip()
                    if sub_item:
                        modules.add(f"{parent_mod}.{sub_item}")
    return list(modules)

def run_pyinstaller(script_name, exe_name, is_gui=True):
    """執行 PyArmor 混淆並透過 PyInstaller 打包。若混淆失敗則自動降級為一般打包。"""
    script_path = os.path.join(BASE_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"[ERR] 找不到腳本: {script_name}，跳過打包。")
        return False
        
    startupinfo = None
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    # 1. 嘗試 PyArmor 加密混淆
    print(f"[*] 正在準備安全加固打包 {script_name}...")
    obf_out_dir = os.path.join(BUILD_DIR, "obf", exe_name)
    if os.path.exists(obf_out_dir):
        shutil.rmtree(obf_out_dir)
    os.makedirs(obf_out_dir, exist_ok=True)
    
    pyarmor_cmd = [
        "pyarmor", "gen",
        "-O", obf_out_dir,
        script_name,
        "packaging_tools\\license_verifier.py",
        "packaging_tools\\register_gui.py",
        "packaging_tools\\updater.py"
    ]
    
    use_obfuscated = False
    hidden_imports = []
    
    try:
        # 自動提取所有依賴，在 PyInstaller 參數中傳入 --hidden-import，防止加密後丟失
        import_stmts = extract_imports_from_files([
            script_path, 
            os.path.join(BASE_DIR, "packaging_tools", "license_verifier.py"),
            os.path.join(BASE_DIR, "packaging_tools", "register_gui.py"),
            os.path.join(BASE_DIR, "packaging_tools", "updater.py")
        ])
        hidden_imports = parse_modules_from_imports(import_stmts)
        
        # 為了測試或避開 Windows 封鎖，此處暫時強制停用 PyArmor
        print("  - [INFO] 已強制停用 PyArmor 加密，直接使用標準 PyInstaller 打包...")
        use_obfuscated = False
    except Exception as e:
        print(f"  - [WARN] 依賴提取失敗: {e}")
        use_obfuscated = False

    # 2. 設定打包源檔案與命令
    cmd = [
        "pyinstaller",
        "--clean",
        "-y",
        "--paths", BASE_DIR,
        "--specpath", PACKAGING_DIR,
        "--workpath", BUILD_DIR,
        "--distpath", DIST_DIR,
        "--name", exe_name,
        "--onedir" # 顯式使用 onedir 打包模式
    ]

    # 若是使用混淆代碼，將先前解析出來的所有 hidden imports 傳給 PyInstaller 進行打包
    if use_obfuscated:
        target_script = os.path.join(obf_out_dir, script_name)
        for mod in hidden_imports:
            cmd.append(f"--hidden-import={mod}")
    else:
        target_script = script_path

    if is_gui:
        cmd.append("--noconsole")
        
    cmd.append(target_script)
    
    try:
        subprocess.check_call(cmd, cwd=BASE_DIR, startupinfo=startupinfo)
        tag = "已混淆加密" if use_obfuscated else "標準安全"
        print(f"[OK] 成功打包 {exe_name} ({tag})！")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERR] 打包 {exe_name} 失敗！錯誤碼: {e.returncode}")
        return False

def copy_static_resources():
    """複製靜態檔案與範本到過磅系統打包後的資料夾"""
    print("[*] 正在複製靜態資源與設定檔範本...")
    
    target_dist = os.path.join(DIST_DIR, "WeighIn")
    if not os.path.exists(target_dist):
        print(f"[ERR] 找不到發布目錄: {target_dist}，無法複製資源。")
        return

    # 1. 複製資料夾資源：templates, static, labels
    resources_to_copy = ["templates", "static", "labels"]
    for res_name in resources_to_copy:
        src_path = os.path.join(BASE_DIR, res_name)
        if os.path.exists(src_path):
            dst_path = os.path.join(target_dist, res_name)
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)
            print(f"  - 資源 {res_name} 已成功複製。")
            
    # 2. 建立空的相片儲存資料夾 (photos)
    photos_dir = os.path.join(target_dist, "photos")
    os.makedirs(photos_dir, exist_ok=True)
    print("  - 空相片目錄 (photos/) 已建立。")

    # 3. 複製預設設定檔 config.json 
    config_src = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(config_src):
        config_dst = os.path.join(target_dist, "config.json")
        shutil.copy2(config_src, config_dst)
        print("  - 設定檔 config.json 已複製。")

def main():
    print("==========================================")
    print("      過磅系統 一鍵加固打包腳本 v2.5")
    print("==========================================")
    
    install_requirements()
    
    # 備份現有的授權與關鍵資料
    backup_weigh_data()
    
    clean_previous_builds()
    
    # 打包主程式 main.py 為 WeighIn.exe (無主控台)
    success = run_pyinstaller("main.py", "WeighIn", is_gui=True)
            
    if success:
        copy_static_resources()
        
        # 還原關鍵資料
        restore_weigh_data()
        
        print("\n==========================================")
        print(f"[OK] 打包流程結束！成功生成過磅程式。")
        print(f"    最終發布檔案位於: {DIST_DIR}")
        print("==========================================")
    else:
        # 即使打包失敗也還原
        restore_weigh_data()
        print("\n[ERR] 打包失敗，未成功生成程式。")

if __name__ == "__main__":
    main()
