import sys
import os
import json
import shutil
import plistlib
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit, QVBoxLayout, QWidget, QScrollArea, QMessageBox, QHBoxLayout, QCheckBox

class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文件选择器")
        self.setGeometry(100, 100, 500, 500)
        self.selected_ids = []

        self.label1 = QLabel("选择歌单文件:", self)
        self.label1.setGeometry(50, 50, 130, 20)

        self.file_path = QLineEdit(self)
        self.file_path.setGeometry(200, 50, 200, 20)

        self.button1 = QPushButton("浏览", self)
        self.button1.setGeometry(370, 50, 35, 20)
        self.button1.clicked.connect(self.get_file_path)

        self.label2 = QLabel("选择歌曲存放的文件夹:", self)
        self.label2.setGeometry(50, 80, 130, 20)

        self.folder_path = QLineEdit(self)
        self.folder_path.setGeometry(200, 80, 200, 20)

        self.button2 = QPushButton("浏览", self)
        self.button2.setGeometry(370, 80, 35, 20)
        self.button2.clicked.connect(self.get_folder_path)

        self.process_button = QPushButton("处理", self)
        self.process_button.setGeometry(50, 120, 80, 20)
        self.process_button.clicked.connect(self.process_files)

        # 创建滚动区域
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setGeometry(50, 150, 400, 200)

        # 创建滚动区域的QWidget作为滚动的内容
        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)

        # 创建垂直布局来放置文本框和勾选按钮
        self.layout = QVBoxLayout(self.scroll_content)

        self.result_text_boxes = []
        self.checkbox_list = []

        self.delete_button = QPushButton("删除", self)
        self.delete_button.setGeometry(50, 360, 80, 20)
        self.delete_button.clicked.connect(self.delete_songs)

    def get_file_path(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择歌单文件", "", "bplist (*.bplist)")
        self.file_path.setText(file_path)

    def get_folder_path(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择歌曲存放的文件夹")
        self.folder_path.setText(folder_path)

    def process_files(self):
        playlist_path = self.file_path.text()
        song_folder_path = self.folder_path.text()

        with open(playlist_path, 'r', encoding='utf-8') as file:
            content = json.load(file)
        song_hash = [song['hash'] for song in content['songs']]

        saver_file_path = sys.path[0] + '/LocalCache.saver'
        with open(saver_file_path, 'r', encoding='utf-8') as file:
            saver_file = json.load(file)

        self.clear_result_text_boxes()

        for doc in saver_file['docs']:
            id_value = doc['id']
            name_value = doc['name']
            hash_value = doc['versions'][0]['hash']
            if hash_value in song_hash:
                self.add_result_text_box(id_value, name_value)

    def add_result_text_box(self, id_value, name_value):
        hbox = QHBoxLayout()

        checkbox = QCheckBox(self)
        checkbox.id = id_value
        checkbox.stateChanged.connect(self.checkbox_state_changed)
        hbox.addWidget(checkbox)
        self.checkbox_list.append(checkbox)

        result_text_box = QTextEdit()
        result_text_box.setFixedHeight(result_text_box.fontMetrics().height())
        result_text_box.setPlainText(name_value)
        result_text_box.setReadOnly(True)
        hbox.addWidget(result_text_box)

        self.result_text_boxes.append(result_text_box)
        self.layout.addLayout(hbox)
        self.scroll_content.setLayout(self.layout)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_content)

    def clear_result_text_boxes(self):
        for text_box in self.result_text_boxes:
            text_box.deleteLater()
        self.result_text_boxes.clear()

        for checkbox in self.checkbox_list:
            checkbox.deleteLater()
        self.checkbox_list.clear()

    def checkbox_state_changed(self, state):
        checkbox = self.sender()
        id_value = checkbox.id
        if state == 2:  # 选中状态
            self.selected_ids.append(id_value)
        elif state == 0:  # 非选中状态
            self.selected_ids.remove(id_value)

    def delete_songs(self):
        song_folder_path = self.folder_path.text()
        playlist_path = self.file_path.text()

        if self.selected_ids:
            reply = QMessageBox.question(self, "确认删除", "确定要删除选中的歌曲吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                # 调用删除函数
                delete_song(song_folder_path, playlist_path, self.selected_ids)
                QMessageBox.information(self, "删除成功", "歌曲已成功删除！")
                self.selected_ids.clear()
        else:
            QMessageBox.warning(self, "未选择歌曲", "请先选择要删除的歌曲！")

def delete_song(song_folder_path, playlist_path, ids):
    # 删除文件夹及其内容
    for folder_name in os.listdir(song_folder_path):
        if folder_name.startswith(tuple(ids)):
            folder_path = os.path.join(song_folder_path, folder_name)
            if os.path.isdir(folder_path):
                shutil.rmtree(folder_path)

    # 从歌单文件中删除匹配的键值对
    with open(playlist_path, 'r+', encoding='utf-8') as file:
        content = json.load(file)
    content["songs"] = [song for song in content["songs"] if song["hash"] != ids]
    with open(playlist_path, 'r+', encoding='utf-8') as file:
        json.dump(content, file, ensure_ascii=False, indent=4)
                
def main():
    app = QApplication(sys.argv)
    win = MyWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
