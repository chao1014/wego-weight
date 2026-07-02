# register_gui.py
# -*- coding: utf-8 -*-

import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from packaging_tools.license_verifier import get_license_path

class RegistrationWindow:
    def __init__(self, root, module_name, machine_id, error_detail):
        self.root = root
        self.module_name = module_name
        self.machine_id = machine_id
        self.success = False
        
        self.root.title("過磅系統 - 設備授權註冊")
        self.root.geometry("520x280")
        self.root.resizable(False, False)
        
        self.setup_ui(error_detail)
        
    def setup_ui(self, error_detail):
        # 主面板
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 標題
        title_label = ttk.Label(
            main_frame, 
            text="⚠️ 系統未獲得授權，或授權已過期", 
            font=("Microsoft JhengHei", 12, "bold"),
            foreground="red"
        )
        title_label.pack(anchor=tk.W, pady=(0, 10))
        
        # 錯誤詳情
        detail_label = ttk.Label(
            main_frame, 
            text=f"錯誤狀態: {error_detail}",
            font=("Microsoft JhengHei", 9)
        )
        detail_label.pack(anchor=tk.W, pady=(0, 10))
        
        # 機器碼框架
        machine_frame = ttk.LabelFrame(main_frame, text="本機設備機器碼 (綁定硬體指紋)", padding="8")
        machine_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.code_entry = ttk.Entry(machine_frame, font=("Consolas", 10))
        self.code_entry.insert(0, self.machine_id)
        self.code_entry.config(state="readonly")
        self.code_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        copy_btn = ttk.Button(machine_frame, text="複製機器碼", command=self.copy_machine_code)
        copy_btn.pack(side=tk.RIGHT)
        
        # 說明提示
        hint_label = ttk.Label(
            main_frame, 
            text="請複製上方機器碼提供給管理員，獲取「license.lic」授權檔。",
            font=("Microsoft JhengHei", 9),
            foreground="gray"
        )
        hint_label.pack(anchor=tk.W, pady=(0, 15))
        
        # 控制按鈕區
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        
        self.import_btn = ttk.Button(btn_frame, text="📥 匯入授權檔 (license.lic)", command=self.import_license)
        self.import_btn.pack(side=tk.LEFT, ipady=3)
        
        close_btn = ttk.Button(btn_frame, text="關閉退出", command=self.root.destroy)
        close_btn.pack(side=tk.RIGHT, ipady=3)
        
    def copy_machine_code(self):
        """複製機器碼至系統剪貼簿"""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.machine_id)
        messagebox.showinfo("成功", "機器碼已成功複製至剪貼簿！\n請將其發送給系統管理員以取得授權。")
        
    def import_license(self):
        """讓使用者選擇並載入授權檔"""
        file_path = filedialog.askopenfilename(
            title="選取授權檔案",
            filetypes=[("授權檔案", "*.lic"), ("所有檔案", "*.*")]
        )
        if not file_path:
            return
            
        target_path = get_license_path()
        target_dir = os.path.dirname(target_path)
        
        # 建立目錄以防萬一
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
            
        try:
            # 複製授權檔到預期位置
            shutil.copy2(file_path, target_path)
            
            # 即時進行一次本機校驗，確認新導入的授權是否合法
            from packaging_tools.license_verifier import load_and_verify
            is_valid, err_code, detail, _ = load_and_verify(self.module_name)
            
            if is_valid:
                messagebox.showinfo("註冊成功", "🎯 設備授權驗證通過！系統即將啟動。")
                self.success = True
                self.root.destroy()
            else:
                # 若導入的檔案依然驗證不通過，刪除之，防佔用無效檔案
                if os.path.exists(target_path):
                    os.remove(target_path)
                messagebox.showerror("驗證失敗", f"導入的授權檔無效，請聯繫管理員。\n錯誤: {detail}")
        except Exception as e:
            messagebox.showerror("導入失敗", f"無法寫入授權檔: {e}")

def show_registration_window(module_name, machine_id, error_detail):
    """
    對外呼叫介面，彈出註冊視窗。
    回傳: 註冊成功 (True) 或 取消 (False)
    """
    root = tk.Tk()
    app = RegistrationWindow(root, module_name, machine_id, error_detail)
    root.mainloop()
    return app.success
