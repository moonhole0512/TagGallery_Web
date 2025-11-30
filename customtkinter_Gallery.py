import customtkinter as ctk
import sqlite3
from PIL import Image, ImageTk
from CTkMessagebox import CTkMessagebox
import os
import math
import subprocess
import NAIimageViwer
import traceback
import ctypes

ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class FullscreenImageViewer:
    def __init__(self, master, image_list, current_index):
        self.master = master
        self.image_list = image_list
        self.current_index = current_index

        # DPI 인식 설정
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        
        # 실제 화면 해상도 가져오기
        user32 = ctypes.windll.user32
        self.screen_width = user32.GetSystemMetrics(0)
        self.screen_height = user32.GetSystemMetrics(1)

        # 창 설정
        self.master.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        self.master.overrideredirect(True)  # 창 테두리 제거
        self.master.lift()
        self.master.wm_attributes("-topmost", True)
        #self.master.focus_force()

        self.master.bind("<Escape>", self.close_viewer)
        self.master.bind("<Right>", self.next_image)
        self.master.bind("<Left>", self.previous_image)

        self.canvas = ctk.CTkCanvas(self.master, highlightthickness=0, bg="black")
        self.canvas.pack(fill=ctk.BOTH, expand=True)

        self.current_image = None
        self.show_current_image()
        
        # 포커스를 설정하기 위한 추가 코드
        self.master.after(0, self.set_focus)

    def set_focus(self):
        self.master.focus_force()
        self.master.focus_set()

    def show_current_image(self):
        img_path = self.image_list[self.current_index][2]
        if not os.path.exists(img_path):
            print(f"이미지 파일을 찾을 수 없습니다: {img_path}")
            return

        try:
            with Image.open(img_path) as img:
                # 이미지 크기 조정
                img_ratio = img.width / img.height
                screen_ratio = self.screen_width / self.screen_height

                if img_ratio > screen_ratio:
                    new_width = self.screen_width
                    new_height = int(new_width / img_ratio)
                else:
                    new_height = self.screen_height
                    new_width = int(new_height * img_ratio)

                img = img.resize((new_width, new_height), Image.LANCZOS)
                self.current_image = ImageTk.PhotoImage(img)

                # 이전 이미지 삭제
                self.canvas.delete("all")
                
                # 이미지를 중앙에 배치
                x = (self.screen_width - new_width) // 2
                y = (self.screen_height - new_height) // 2
                
                # 캔버스에 이미지 생성
                self.canvas.create_image(x, y, anchor="nw", image=self.current_image)
                
                # 캔버스 크기 조정
                self.canvas.config(width=self.screen_width, height=self.screen_height)
        except Exception as e:
            print(f"이미지를 불러오는 중 오류 발생: {e}")

    def next_image(self, event):
        self.current_index = (self.current_index + 1) % len(self.image_list)
        self.show_current_image()

    def previous_image(self, event):
        self.current_index = (self.current_index - 1) % len(self.image_list)
        self.show_current_image()

    def close_viewer(self, event):
        self.master.destroy()

class ImageGalleryApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("TagGallery_V1.0")
        self.geometry("1340x960")
        
        self.searchList = []
        self.currentPage = 1
        self.maxDisplay = 30
        
        self.dbNo = 0
        self.dbPath = ""
        self.selected_items = []
        self.selection_mode = False
        
        self.image_references = {'thumbnails': [], 'selected': []}
        self.displayed_widgets = []
        
        self.create_widgets()

    def create_widgets(self):
        # 상단 프레임 생성 
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill=ctk.X, padx=5, pady=(5, 0))

        # 삭제 버튼
        self.selection_button = ctk.CTkButton(top_frame, text="선택", command=self.toggle_selection_mode, width=50, height=28)
        self.selection_button.pack(side=ctk.LEFT, padx=(5, 5))

        # Tags 라벨과 입력 필드
        self.tag_label = ctk.CTkLabel(top_frame, text="Tags")
        self.tag_label.pack(side=ctk.LEFT)
        
        self.textbox_tags = ctk.CTkEntry(top_frame, width=680)
        self.textbox_tags.pack(side=ctk.LEFT, padx=(0, 5))
        self.textbox_tags.bind("<Return>", lambda event: self.search_images(1))
        
        # 검색 버튼
        self.search_button = ctk.CTkButton(top_frame, text="검색", command=lambda: self.search_images(1), width=50, height=28)
        self.search_button.pack(side=ctk.LEFT)

        # 정렬 콤보박스
        self.order_var = ctk.StringVar(value="DESC")
        self.order_combobox = ctk.CTkComboBox(top_frame, variable=self.order_var, values=["DESC","ASC","RANDOM"], width=100)
        self.order_combobox.pack(side=ctk.LEFT)
        
        # 플랫폼 콤보박스
        self.Platorder_var = ctk.StringVar(value="ALL")
        self.Platorder_combobox = ctk.CTkComboBox(top_frame, variable=self.Platorder_var, values=["ALL","NAI","DIF","None"], width=70)
        self.Platorder_combobox.pack(side=ctk.LEFT)
        
        self.page_label = ctk.CTkLabel(top_frame, text="")
        self.page_label.pack(side=ctk.RIGHT, padx=(5, 5))
        
        self.currentpagebox = ctk.CTkEntry(top_frame, width=50)
        self.currentpagebox.pack(side=ctk.RIGHT)
        self.currentpagebox.bind("<Return>", lambda event: self.pageinput())
        
        self.next_button = ctk.CTkButton(top_frame, text="다음", command=self.next_page, width=50, height=28)
        self.next_button.pack(side=ctk.RIGHT)

        self.pre_button = ctk.CTkButton(top_frame, text="이전", command=self.prev_page, width=50, height=28)
        self.pre_button.pack(side=ctk.RIGHT)

        # 메인 컨텐츠 영역 (이미지 영역과 선택된 이미지 영역을 포함)
        main_content = ctk.CTkFrame(self)
        main_content.pack(fill=ctk.BOTH, expand=True, padx=5, pady=5)

        # 이미지 영역 (왼쪽)
        self.img_area = ctk.CTkFrame(main_content)
        self.img_area.pack(side=ctk.LEFT, fill=ctk.BOTH, padx=(0, 5), pady=0)
        
        # 오른쪽 영역 (선택된 이미지와 태그)
        right_area = ctk.CTkFrame(main_content)
        right_area.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=0, pady=0)
        
        # 선택된 이미지 영역 (오른쪽 상단)
        self.selectimg_area = ctk.CTkFrame(right_area)
        self.selectimg_area.pack(fill=ctk.BOTH, expand=True, padx=0, pady=0)
        
        # 선택된 이미지 태그 텍스트 (오른쪽 하단)
        self.selected_img_tag_text = ctk.CTkTextbox(right_area, wrap="word")
        self.selected_img_tag_text.pack(fill=ctk.BOTH, pady=(5, 0), padx=0)

        self.search_images(0)

    def pageinput(self):
        current_value = self.currentpagebox.get()
        
        if current_value.isdigit() and int(current_value) != 0:
            self.currentPage = int(current_value)
            self.update_page()
    
    def toggle_selection_mode(self):
        print(f"Selection mode toggled. Current state: {self.selection_mode}")
        self.selection_mode = not self.selection_mode
        if self.selection_mode:
            self.selection_button.configure(text="삭제 실행")
        else:
            if self.selected_items:
                self.delete_selected_files()
            self.selection_button.configure(text="선택")
            # Clear selection and visuals after exiting mode
            self.selected_items.clear()
            self._update_selection_visuals()

    def delete_selected_files(self):
        if not self.selected_items:
            CTkMessagebox(title="삭제 오류", message="삭제할 이미지를 선택하세요.", icon="warning")
            return

        msg = f"선택한 이미지 {len(self.selected_items)}개를 휴지통으로 이동합니다."
        if CTkMessagebox(title="선택된 이미지 삭제", message=msg, icon="question", option_1="Yes", option_2="No").get() == "Yes":
            conn = sqlite3.connect("image_gallery.db")
            cursor = conn.cursor()
            try:
                for item in self.selected_items:
                    db_id = item['id']
                    path = item['path']
                    
                    cursor.execute("SELECT * FROM NAIimgInfo WHERE no = ?", (db_id,))
                    if not cursor.fetchone():
                        print(f"Warning: 레코드가 이미 삭제되었습니다. (no={db_id})")
                        continue
                    
                    if not os.path.exists(path):
                        print(f"Warning: 파일이 이미 삭제되었습니다. ({path})")
                        cursor.execute("DELETE FROM NAIimgInfo WHERE no = ?", (db_id,))
                        continue
                    
                    # Delete from DB and send to trash
                    cursor.execute("DELETE FROM NAIimgInfo WHERE no = ?", (db_id,))
                    send2trash.send2trash(path)
                    print(f"휴지통으로 이동: (no={db_id}, path={path})")

                conn.commit()
                
            except Exception as ex:
                conn.rollback()
                print(f"Error: {ex}")
                traceback.print_exc()
                CTkMessagebox(title="삭제 오류", message=f"이미지 삭제 중 오류가 발생했습니다:\n{ex}", icon="cancel")
            finally:
                conn.close()

            # Clear selection and refresh UI
            self.selected_items.clear()
            self.search_images(0)
            self.update_page()
    
    def on_image_click(self, event, dbno, path, tags):
        if self.selection_mode:
            # --- Selection Mode Logic ---
            item_data = {'id': dbno, 'path': path, 'widget': event.widget}
            
            selected_index = -1
            for i, item in enumerate(self.selected_items):
                if item['id'] == dbno:
                    selected_index = i
                    break

            if selected_index != -1:
                # Item is selected, so unselect it
                self.selected_items.pop(selected_index)
            else:
                # Item is not selected, so select it
                self.selected_items.append(item_data)
            
            self._update_selection_visuals()
        else:
            # --- Normal Mode Logic ---
            for widget in self.selectimg_area.winfo_children():
                widget.destroy()
        
            selected_img = Image.open(path)
        
            area_width = 550
            area_height = 700
        
            img_ratio = selected_img.size[0] / selected_img.size[1]
            area_ratio = area_width / area_height
        
            if img_ratio > area_ratio:
                new_width = area_width
                new_height = int(area_width / img_ratio)
            else:
                new_height = area_height
                new_width = int(area_height * img_ratio)
        
            selected_img = selected_img.resize((new_width, new_height), Image.LANCZOS)
        
            padx = (area_width - new_width) // 2
            pady = (area_height - new_height) // 2
        
            selected_img_ctk = ctk.CTkImage(light_image=selected_img, size=(new_width, new_height))
            selectimg_label = ctk.CTkLabel(self.selectimg_area, image=selected_img_ctk, text="")
            selectimg_label.image = selected_img_ctk
            selectimg_label.grid(row=0, column=0, padx=padx, pady=pady, sticky='nsew')
            selectimg_label.bind("<Double-Button-1>", self.show_big_image)
        
            self.selected_img_tag_text.delete("1.0", "end")
            self.selected_img_tag_text.insert("1.0", tags)

            self.dbNo = dbno
            self.dbPath = path


    def show_big_image(self, event):
        if self.dbPath:
            current_index = next((i for i, img in enumerate(self.searchList) if img[2] == self.dbPath), None)
            if current_index is not None:
                viewer_window = ctk.CTkToplevel(self)
                viewer_window.withdraw()
                viewer = FullscreenImageViewer(viewer_window, self.searchList, current_index)
                viewer_window.deiconify()
                viewer_window.protocol("WM_DELETE_WINDOW", viewer_window.destroy)
                # The viewer window has its own mainloop, so we don't call it here.
            else:
                print("현재 이미지를 searchList에서 찾을 수 없습니다.")
        else:
            print("선택된 이미지가 없습니다.")

    def _update_selection_visuals(self):
        selected_ids = {item['id'] for item in self.selected_items}
        for item in self.displayed_widgets:
            if item['id'] in selected_ids:
                item['widget'].configure(fg_color="blue")
            else:
                item['widget'].configure(fg_color="transparent")

    def display_images(self, image_paths):
        for widget in self.img_area.winfo_children():
            widget.destroy()
        self.image_references['thumbnails'] = []
        self.displayed_widgets = []
        for i, img_data in enumerate(image_paths):
            db_id, tags, path, *_ = img_data
            
            img = Image.open(path)
            img = img.resize((150, 150), Image.LANCZOS)
            img_ctk = ctk.CTkImage(light_image=img, size=(150, 150))
            self.image_references['thumbnails'].append(img_ctk)
            
            label = ctk.CTkLabel(self.img_area, image=img_ctk, text="")
            label.image = img_ctk
            label.grid(row=i // 5, column=i % 5, padx=1, pady=1)
            
            label.bind("<Double-Button-1>", lambda event, p=path: self.open_external_program(p))
            label.bind("<Button-1>", lambda event, id=db_id, p=path, t=tags: self.on_image_click(event, id, p, t))
            
            self.displayed_widgets.append({'id': db_id, 'widget': label})

        self._update_selection_visuals()

    def open_external_program(self, img_path):
        os.startfile(img_path)
        #program_path = ""
        #with open("settings.txt", 'r') as file:
        #    lines = file.readlines()
        #    program_path = lines[2].strip().split('=')[1]
        #
        #subprocess.Popen([program_path, img_path])

    def next_page(self):
        self.currentPage += 1
        self.update_page()

    def prev_page(self):
        if self.currentPage > 1:
            self.currentPage -= 1
            self.update_page()
#####메인 실행부#####
if __name__ == "__main__":
    try:
        print("[Classification Start]")
        NAIimageViwer.initFirstStart()
        NAIimageViwer.classification()
    except Exception as ex:
        print('Classification Error', ex)
        traceback.print_exc()
        input("에러가 발생해서 종료되었습니다. 에러문구를 확인해주세요.")
    print("[Classification done]")

    try:
        app = ImageGalleryApp()
        app.mainloop()
    except Exception as ex:
        print('Viewer Error', ex)
        traceback.print_exc()
        input("에러가 발생해서 종료되었습니다. 에러문구를 확인해주세요.")

