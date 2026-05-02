import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import os
import re
import math

class SRTEditorWindow(ctk.CTkToplevel):
    def __init__(self, master, srt_path):
        super().__init__(master)
        self.title(f"SRT 字幕編輯器 - {os.path.basename(srt_path)}")
        self.geometry("900x800")
        self.srt_path = srt_path
        
        # Pagination Data
        self.all_subtitle_data = [] # Stores all dicts: {idx, start, end, text}
        self.active_widgets = []    # Stores widgets of current page
        self.current_page = 1
        self.PAGE_SIZE = 50         # 每頁顯示 50 筆
        self.total_pages = 1
        
        # 建立 UI
        self.create_widgets()
        
        # 載入 SRT
        self.load_srt()
        
        # Make modal
        self.grab_set()
        self.focus_force()

    def create_widgets(self):
        # 統一字型
        self.font_ui = ("Microsoft JhengHei UI", 15)
        self.font_bold = ("Microsoft JhengHei UI", 15, "bold")
        self.font_editor = ("Microsoft JhengHei UI", 15)

        # 頂部控制區 (Buttons)
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.pack(fill="x", padx=10, pady=5)
        
        self.save_btn = ctk.CTkButton(self.top_frame, text="儲存", command=self.save_srt, fg_color="#1E88E5", hover_color="#1565C0", font=self.font_bold)
        self.save_btn.pack(side="left", padx=5)
        
        self.reload_btn = ctk.CTkButton(self.top_frame, text="重新載入", command=self.load_srt, font=self.font_ui)
        self.reload_btn.pack(side="left", padx=5)
        
        self.close_btn = ctk.CTkButton(self.top_frame, text="關閉", command=self.destroy, fg_color="red", font=self.font_ui)
        self.close_btn.pack(side="right", padx=5)
        
        self.lbl_filename = ctk.CTkLabel(self.top_frame, text=os.path.basename(self.srt_path), font=self.font_bold)
        self.lbl_filename.pack(side="left", padx=20)
        
        self.help_btn = ctk.CTkButton(self.top_frame, text="說明 (Help)", width=100, command=self.open_help, fg_color="#4CAF50", hover_color="#388E3C", font=self.font_ui)
        self.help_btn.pack(side="right", padx=5)

        # 頂部分頁導航 (Pagination Nav Top)
        self.nav_frame = ctk.CTkFrame(self)
        self.nav_frame.pack(fill="x", padx=10, pady=2)
        
        self.btn_prev = ctk.CTkButton(self.nav_frame, text="上一頁", width=100, command=self.prev_page, font=self.font_ui)
        self.btn_prev.pack(side="left", padx=10)
        
        self.lbl_page = ctk.CTkLabel(self.nav_frame, text="第 1 / 1 頁", font=self.font_bold)
        self.lbl_page.pack(side="left", padx=20, expand=True) # Center label
        
        self.btn_next = ctk.CTkButton(self.nav_frame, text="下一頁", width=100, command=self.next_page, font=self.font_ui)
        self.btn_next.pack(side="right", padx=10)

        # 主要捲動區域 (Content)
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="字幕列表", label_font=self.font_bold)
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 底部導航
        self.nav_frame_btm = ctk.CTkFrame(self)
        self.nav_frame_btm.pack(fill="x", padx=10, pady=5)
        
        self.btn_prev_b = ctk.CTkButton(self.nav_frame_btm, text="上一頁", width=100, command=self.prev_page, font=self.font_ui)
        self.btn_prev_b.pack(side="left", padx=10)
        
        self.btn_next_b = ctk.CTkButton(self.nav_frame_btm, text="下一頁", width=100, command=self.next_page, font=self.font_ui)
        self.btn_next_b.pack(side="right", padx=10)

    def open_help(self):
        """ 開啟 SRT 編輯器指南 """
        docs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
        help_file = "srt_editor_guide.html"
        full_path = os.path.join(docs_path, help_file)
        if os.path.exists(full_path):
            os.startfile(full_path)
        else:
            messagebox.showinfo("提示", f"找不到說明文件: {help_file}")


    def load_srt(self):
        """ 讀取 SRT 檔案到記憶體，但不產生 UI """
        self.all_subtitle_data.clear()
        
        try:
            if not os.path.exists(self.srt_path):
                messagebox.showerror("錯誤", "找不到字幕檔案")
                return

            with open(self.srt_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Robust Parsing
            content = content.replace("\r\n", "\n").replace("\r", "\n")
            blocks = re.split(r'\n{2,}', content.strip())
            
            for i, block in enumerate(blocks):
                if not block.strip(): continue
                lines = block.strip().split('\n')
                if len(lines) >= 2:
                    # Heuristic parsing
                    idx = lines[0].strip()
                    time_line = lines[1].strip()
                    
                    if "-->" not in time_line:
                        found_time = False
                        for j, l in enumerate(lines):
                            if "-->" in l:
                                idx = lines[j-1].strip() if j > 0 else str(i+1)
                                time_line = l
                                text = "\n".join(lines[j+1:])
                                found_time = True
                                break
                        if not found_time: continue
                    else:
                        text = "\n".join(lines[2:])

                    try:
                        start_time, end_time = time_line.split("-->")
                        start_time = start_time.strip()
                        end_time = end_time.strip()
                    except:
                        start_time, end_time = "", ""
                    
                    # Store purely data
                    self.all_subtitle_data.append({
                        "idx": idx,
                        "start": start_time,
                        "end": end_time,
                        "text": text
                    })
            
            # Update Pagination Info
            total_items = len(self.all_subtitle_data)
            self.total_pages = math.ceil(total_items / self.PAGE_SIZE)
            if self.total_pages < 1: self.total_pages = 1
            
            self.current_page = 1
            self.render_page(self.current_page)
            
        except Exception as e:
            messagebox.showerror("錯誤", f"無法讀取 SRT 檔案:\n{e}")

    def save_current_page_data(self):
        """ 將目前頁面 UI 上的修改回寫到記憶體 (self.all_subtitle_data) """
        for widget_item in self.active_widgets:
            # widget_item is dict: {data_index, start_entry, end_entry, text_box}
            global_index = widget_item['data_index']
            
            if 0 <= global_index < len(self.all_subtitle_data):
                new_start = widget_item['start_entry'].get()
                new_end = widget_item['end_entry'].get()
                new_text = widget_item['text_box'].get("0.0", "end").strip()
                
                # Update memory
                self.all_subtitle_data[global_index]['start'] = new_start
                self.all_subtitle_data[global_index]['end'] = new_end
                self.all_subtitle_data[global_index]['text'] = new_text

    def render_page(self, page_num):
        """ 渲染指定頁面的 UI """
        # 1. Clear current UI
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.active_widgets.clear()
        
        # 2. Calculate Slice
        start_idx = (page_num - 1) * self.PAGE_SIZE
        end_idx = start_idx + self.PAGE_SIZE
        
        page_data = self.all_subtitle_data[start_idx:end_idx]
        
        # 3. Create Widgets
        for i, item in enumerate(page_data):
            global_index = start_idx + i
            self.create_block_ui(global_index, item)
            
        # 4. Update Nav UI
        self.lbl_page.configure(text=f"第 {page_num} / {self.total_pages} 頁")
        
        # Button States
        if page_num <= 1:
            self.btn_prev.configure(state="disabled")
            self.btn_prev_b.configure(state="disabled")
        else:
            self.btn_prev.configure(state="normal")
            self.btn_prev_b.configure(state="normal")
            
        if page_num >= self.total_pages:
            self.btn_next.configure(state="disabled")
            self.btn_next_b.configure(state="disabled")
        else:
            self.btn_next.configure(state="normal")
            self.btn_next_b.configure(state="normal")

    def create_block_ui(self, global_index, item_data):
        frame = ctk.CTkFrame(self.scroll_frame)
        frame.pack(fill="x", pady=2, padx=2)
        
        # UI Elements
        idx_label = ctk.CTkLabel(frame, text=f"#{item_data['idx']}", width=40, font=self.font_ui)
        idx_label.grid(row=0, column=0, padx=5, sticky="n")
        
        time_frame = ctk.CTkFrame(frame, fg_color="transparent")
        time_frame.grid(row=0, column=1, padx=5, sticky="n")
        
        start_entry = ctk.CTkEntry(time_frame, width=120, placeholder_text="00:00:00,000", font=self.font_ui)
        start_entry.insert(0, item_data['start'])
        start_entry.pack(side="top", pady=1)
        
        arrow_label = ctk.CTkLabel(time_frame, text="↓", font=self.font_ui)
        arrow_label.pack(side="top", pady=0)
        
        end_entry = ctk.CTkEntry(time_frame, width=120, placeholder_text="00:00:00,000", font=self.font_ui)
        end_entry.insert(0, item_data['end'])
        end_entry.pack(side="top", pady=1)
        
        # Textbox
        text_box = ctk.CTkTextbox(frame, height=80, width=500, font=self.font_editor)
        text_box.insert("0.0", item_data['text'])
        text_box.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")
        
        frame.grid_columnconfigure(2, weight=1)

        # Track Active Widgets
        self.active_widgets.append({
            "data_index": global_index,
            "start_entry": start_entry,
            "end_entry": end_entry,
            "text_box": text_box
        })

    def prev_page(self):
        if self.current_page > 1:
            self.save_current_page_data() # Save changes before switch
            self.current_page -= 1
            self.render_page(self.current_page)

    def next_page(self):
        if self.current_page < self.total_pages:
            self.save_current_page_data() # Save changes before switch
            self.current_page += 1
            self.render_page(self.current_page)

    def save_srt(self):
        try:
            # 1. Save current page edits first
            self.save_current_page_data()
            
            # 2. Reconstruct entire SRT from memory
            new_content = ""
            for item in self.all_subtitle_data:
                idx = item['idx']
                start = item['start']
                end = item['end']
                text = item['text']
                # Ensure spacing
                new_content += f"{idx}\n{start} --> {end}\n{text}\n\n"
            
            with open(self.srt_path, "w", encoding="utf-8") as f:
                f.write(new_content)
                
            messagebox.showinfo("成功", f"檔案已儲存！(共 {len(self.all_subtitle_data)} 句)")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"存檔失敗:\n{e}")
