import tkinter as tk
try:
    import ctypes
    # 我們仍然保留 DPI 感知設定，這很重要
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

BG_COLOR = "#022140"
TEXT_COLOR = "#F2F2F2"
WIN_WIDTH = 350
WIN_HEIGHT = 150

try:
    root = tk.Tk()
    root.title("Splash_WeighIn_12345") 
    root.overrideredirect(True) 
    root.config(bg=BG_COLOR, bd=2, relief="solid")

    label = tk.Label(
        root, 
        text="韻動國際過磅系統 啟動中...\n\n請稍候，正在初始化硬體", 
        fg=TEXT_COLOR, 
        bg=BG_COLOR, 
        font=("Microsoft JhengHei", 14)
    )
    label.pack(pady=20, expand=True)

    # --- ▼▼▼ 【核心修改】: 使用 Tkinter 內建的置中指令 ▼▼▼ ---
    
    # 1. 先設定好我們想要的視窗大小
    root.geometry(f"{WIN_WIDTH}x{WIN_HEIGHT}")
    
    # 2. 強制更新視窗，讓它 "知道" 自己的大小
    root.update_idletasks()
    
    # 3. 呼叫 Tcl/Tk 引擎的內部 'PlaceWindow' 指令
    #    '. center' 的意思是 '將根視窗 (.) 放到螢幕中央 (center)'
    root.eval('tk::PlaceWindow . center')
    
    # --- ▲▲▲ 修改結束 ▲▲▲ ---

    root.attributes('-topmost', True)
    root.mainloop()

except Exception as e:
    pass