import sys
import json
import os
import shutil
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QPushButton, QLabel, QLineEdit, QListWidget, 
                            QListWidgetItem, QFileDialog, QMessageBox, QProgressBar,
                            QCheckBox, QTextEdit, QSplitter, QGroupBox, QGridLayout, QComboBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QIcon

class FileProcessThread(QThread):
    """后台文件处理线程，用于扫描歌单和本地歌曲文件夹，避免阻塞主界面"""
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    finished_signal = pyqtSignal(list)

    def __init__(self, playlist_path, songs_folder, cache_path=None):
        super().__init__()
        self.playlist_path = playlist_path
        self.songs_folder = songs_folder
        self.cache_path = cache_path  # LocalCache.saver 路径，可选

    def run(self):
        try:
            self.status_updated.emit("正在读取歌单文件...")
            # 读取歌单文件
            with open(self.playlist_path, 'r', encoding='utf-8') as f:
                playlist_data = json.load(f)
            songs = playlist_data.get('songs', [])
            playlist_title = playlist_data.get('playlistTitle', '未知歌单')
            song_name_set = set(song.get('songName', '') for song in songs)
            song_hash_map = {song.get('songName', ''): song.get('hash', '') for song in songs}
            total_songs = len(songs)
            self.status_updated.emit(f"正在扫描 {total_songs} 首歌曲...（歌单名：{playlist_title}）")

            # 读取 LocalCache.saver，建立hash到id/描述的映射
            cache_info = {}
            if self.cache_path and os.path.exists(self.cache_path):
                try:
                    with open(self.cache_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    for doc in cache_data.get('docs', []):
                        for version in doc.get('versions', []):
                            cache_info[version.get('hash', '').lower()] = {
                                'id': doc.get('id', ''),
                                'name': doc.get('name', ''),
                                'description': doc.get('description', ''),
                            }
                except Exception as e:
                    self.status_updated.emit(f"LocalCache.saver 读取失败: {e}")

            # 扫描本地歌曲文件夹，提取info.dat和难度信息
            local_song_map = {}  # _songName -> 歌曲信息字典
            for folder in os.listdir(self.songs_folder):
                folder_path = os.path.join(self.songs_folder, folder)
                if not os.path.isdir(folder_path):
                    continue
                info_dat = os.path.join(folder_path, 'info.dat')
                if not os.path.exists(info_dat):
                    continue
                try:
                    with open(info_dat, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                    local_song_name = info.get('_songName', '')
                    author = info.get('_songAuthorName', '')
                    # 获取所有实际存在的难度
                    difficulties = []
                    for dset in info.get('_difficultyBeatmapSets', []):
                        for diff in dset.get('_difficultyBeatmaps', []):
                            diff_name = diff.get('_difficulty')
                            if diff_name and diff_name not in difficulties:
                                difficulties.append(diff_name)
                    # 检查是否有.egg文件
                    egg_ok = any(f.endswith('.egg') for f in os.listdir(folder_path))
                    # 通过歌单hash反查hash
                    hash_guess = None
                    for song in songs:
                        if song.get('songName', '') == local_song_name:
                            hash_guess = song.get('hash', '')
                            break
                    local_song_map[local_song_name] = {
                        'folder': folder_path,
                        'egg_ok': egg_ok,
                        'author': author,
                        'difficulties': difficulties,
                        'hash': hash_guess
                    }
                except Exception:
                    continue

            # 生成歌单顺序的歌曲信息列表
            song_info_list = []
            for i, song in enumerate(songs):
                progress = int((i + 1) / total_songs * 100) if total_songs else 100
                self.progress_updated.emit(progress)
                song_name = song.get('songName', '')
                song_hash = song.get('hash', '').lower()
                local_info = local_song_map.get(song_name)
                exists = False
                folder = ""
                author = ""
                difficulties = []
                if local_info and local_info['egg_ok']:
                    exists = True
                    folder = local_info['folder']
                    author = local_info['author']
                    difficulties = local_info['difficulties']

                # LocalCache.saver 信息
                cache = cache_info.get(song_hash, {})
                cache_id = cache.get('id', '')
                cache_desc = cache.get('description', '')

                song_info_list.append({
                    'name': song_name,         # 歌名
                    'hash': song_hash,         # 歌曲hash
                    'exists': exists,          # 是否存在本地
                    'path': folder,            # 歌曲文件夹路径
                    'author': author,          # 歌手名
                    'difficulties': difficulties, # 实际存在的所有难度
                    'cache_id': cache_id,      # LocalCache.saver中的id
                    'cache_desc': cache_desc   # LocalCache.saver中的描述
                })

            self.status_updated.emit("扫描完成！")
            self.finished_signal.emit(song_info_list)

        except Exception as e:
            self.status_updated.emit(f"错误: {str(e)}")

class BeatSaberPlaylistManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.playlist_path = ""     # 歌单文件路径
        self.songs_folder = ""      # 歌曲文件夹路径
        self.song_list = []         # 歌曲信息列表
        self.backup_enabled = True  # 是否启用备份
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle('Beat Saber 歌单管理器 v2.0')
        self.setGeometry(100, 100, 1000, 700)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 文件选择区域
        file_group = QGroupBox("文件选择")
        file_layout = QGridLayout()
        
        # 歌单文件选择控件
        self.playlist_label = QLabel("歌单文件：")
        self.playlist_edit = QLineEdit()
        self.playlist_edit.setPlaceholderText("请选择 .bplist 歌单文件")
        self.playlist_btn = QPushButton("浏览")
        self.playlist_btn.clicked.connect(self.select_playlist)
        
        file_layout.addWidget(self.playlist_label, 0, 0)
        file_layout.addWidget(self.playlist_edit, 0, 1)
        file_layout.addWidget(self.playlist_btn, 0, 2)
        
        # 歌曲文件夹选择控件
        self.folder_label = QLabel("歌曲文件夹：")
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("请选择歌曲存放文件夹")
        self.folder_btn = QPushButton("浏览")
        self.folder_btn.clicked.connect(self.select_folder)
        
        file_layout.addWidget(self.folder_label, 1, 0)
        file_layout.addWidget(self.folder_edit, 1, 1)
        file_layout.addWidget(self.folder_btn, 1, 2)
        
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # 控制按钮区域
        control_layout = QHBoxLayout()
        
        # 扫描按钮
        self.scan_btn = QPushButton("扫描歌曲")
        self.scan_btn.clicked.connect(self.scan_songs)
        self.scan_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        
        # 删除前备份复选框
        self.backup_checkbox = QCheckBox("删除前备份")
        self.backup_checkbox.setChecked(True)
        
        # 全选/取消全选按钮
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all)
        self.select_none_btn = QPushButton("取消全选")
        self.select_none_btn.clicked.connect(self.select_none)
        
        # 筛选下拉框
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("全部显示")
        self.filter_combo.addItem("普通不含困难")
        self.filter_combo.addItem("困难不含普通")
        self.filter_combo.addItem("不含普通和困难")
        self.filter_combo.currentIndexChanged.connect(self.update_song_list)
        
        # 排序下拉框
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("歌单顺序")
        self.sort_combo.addItem("歌名升序")
        self.sort_combo.addItem("歌名降序")
        self.sort_combo.addItem("作者升序")
        self.sort_combo.addItem("作者降序")
        self.sort_combo.currentIndexChanged.connect(self.update_song_list)
        
        # 仅显示缺失歌曲复选框
        self.only_missing_checkbox = QCheckBox("仅显示缺失歌曲")
        self.only_missing_checkbox.stateChanged.connect(self.update_song_list)
        
        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索歌名或作者")
        self.search_edit.textChanged.connect(self.update_song_list)
        
        # 控件加入布局
        control_layout.addWidget(self.scan_btn)
        control_layout.addWidget(self.backup_checkbox)
        control_layout.addWidget(self.filter_combo)
        control_layout.addWidget(self.sort_combo)
        control_layout.addWidget(self.only_missing_checkbox)
        control_layout.addWidget(self.search_edit)
        control_layout.addStretch()
        control_layout.addWidget(self.select_all_btn)
        control_layout.addWidget(self.select_none_btn)
        
        main_layout.addLayout(control_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 歌曲列表区域
        list_group = QGroupBox("歌曲列表")
        list_layout = QVBoxLayout()
        
        self.song_list_widget = QListWidget()
        self.song_list_widget.setAlternatingRowColors(True)
        list_layout.addWidget(self.song_list_widget)
        
        list_group.setLayout(list_layout)
        splitter.addWidget(list_group)
        
        # 信息显示区域
        info_group = QGroupBox("详细信息")
        info_layout = QVBoxLayout()
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(200)
        info_layout.addWidget(self.info_text)
        
        info_group.setLayout(info_layout)
        splitter.addWidget(info_group)
        
        splitter.setSizes([700, 300])
        main_layout.addWidget(splitter)
        
        # 状态栏
        self.status_label = QLabel("就绪")
        main_layout.addWidget(self.status_label)
        
        # 删除按钮
        delete_layout = QHBoxLayout()
        delete_layout.addStretch()
        
        self.delete_btn = QPushButton("删除选中歌曲")
        self.delete_btn.clicked.connect(self.delete_selected)
        self.delete_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; }")
        self.delete_btn.setEnabled(False)
        
        delete_layout.addWidget(self.delete_btn)
        main_layout.addLayout(delete_layout)
        
        # 设置样式
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin: 3px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                padding: 8px;
                border-radius: 4px;
                border: 1px solid #ddd;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
    
    def select_playlist(self):
        """选择歌单文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择歌单文件", "", "Playlist files (*.bplist);;JSON files (*.json)")
        if file_path:
            self.playlist_path = file_path
            self.playlist_edit.setText(file_path)
            self.update_scan_button_state()
    
    def select_folder(self):
        """选择歌曲文件夹"""
        folder_path = QFileDialog.getExistingDirectory(self, "选择歌曲文件夹")
        if folder_path:
            self.songs_folder = folder_path
            self.folder_edit.setText(folder_path)
            self.update_scan_button_state()
    
    def update_scan_button_state(self):
        """根据路径是否填写，决定扫描按钮是否可用"""
        self.scan_btn.setEnabled(bool(self.playlist_path and self.songs_folder))
    
    def scan_songs(self):
        """启动后台线程扫描歌曲"""
        if not self.playlist_path or not self.songs_folder:
            QMessageBox.warning(self, "警告", "请先选择歌单文件和歌曲文件夹！")
            return

        # 自动查找 LocalCache.saver（与主程序同级）
        cache_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "LocalCache.saver")
        if not os.path.exists(cache_path):
            cache_path = None  # 不存在则不传

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.scan_btn.setEnabled(False)

        self.scan_thread = FileProcessThread(self.playlist_path, self.songs_folder, cache_path=cache_path)
        self.scan_thread.progress_updated.connect(self.progress_bar.setValue)
        self.scan_thread.status_updated.connect(self.status_label.setText)
        self.scan_thread.finished_signal.connect(self.on_scan_finished)
        self.scan_thread.start()
    
    def on_scan_finished(self, song_list):
        """扫描完成后，刷新界面和信息"""
        self.song_list = song_list
        self.update_song_list()
        
        # 隐藏进度条
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        
        # 更新信息显示
        total_songs = len(song_list)
        existing_songs = sum(1 for song in song_list if song['exists'])
        missing_songs = total_songs - existing_songs
        
        info_text = f"""扫描完成！
总歌曲数：{total_songs}
存在的歌曲：{existing_songs}
缺失的歌曲：{missing_songs}

提示：
- 绿色：歌曲文件存在
- 红色：歌曲文件缺失
- 勾选要删除的歌曲，点击"删除选中歌曲"按钮"""
        
        self.info_text.setText(info_text)
    
    def update_song_list(self):
        """根据筛选、排序、搜索等条件刷新歌曲列表显示"""
        self.song_list_widget.clear()
        filter_mode = self.filter_combo.currentIndex()
        sort_mode = self.sort_combo.currentIndex()
        only_missing = self.only_missing_checkbox.isChecked()
        keyword = self.search_edit.text().strip().lower()

        # 排序
        song_list = self.song_list.copy()
        if sort_mode == 1:
            song_list.sort(key=lambda x: x['name'])
        elif sort_mode == 2:
            song_list.sort(key=lambda x: x['name'], reverse=True)
        elif sort_mode == 3:
            song_list.sort(key=lambda x: x.get('author', ''))
        elif sort_mode == 4:
            song_list.sort(key=lambda x: x.get('author', ''), reverse=True)

        for song in song_list:
            difficulties = song.get('difficulties', [])
            show = True

            # 仅显示缺失歌曲
            if only_missing and song['exists']:
                continue

            # 筛选条件
            if filter_mode == 1:
                show = 'Normal' in difficulties and 'Hard' not in difficulties
            elif filter_mode == 2:
                show = 'Hard' in difficulties and 'Normal' not in difficulties
            elif filter_mode == 3:
                show = 'Normal' not in difficulties and 'Hard' not in difficulties

            if not show:
                continue

            # 搜索关键字过滤
            if keyword:
                if keyword not in song['name'].lower() and keyword not in song.get('author', '').lower():
                    continue

            author = song.get('author', '')
            diff_str = '/'.join(difficulties)
            cache_id = song.get('cache_id', '')
            display_text = f"{song['name']}"
            if author:
                display_text += f" - {author}"
            if diff_str:
                display_text += f" [{diff_str}]"
            if cache_id:
                display_text += f" (ID:{cache_id})"

            item = QListWidgetItem()
            item.setData(Qt.UserRole, song['hash'])  # 关键：存储hash，便于删除时一一对应
            checkbox = QCheckBox(display_text)
            if song['exists']:
                checkbox.setStyleSheet("color: green;")
            else:
                checkbox.setStyleSheet("color: red;")
            desc = song.get('cache_desc', '')
            if desc:
                item.setToolTip(desc)
            self.song_list_widget.addItem(item)
            self.song_list_widget.setItemWidget(item, checkbox)
    
    def select_all(self):
        """全选所有歌曲"""
        for i in range(self.song_list_widget.count()):
            item = self.song_list_widget.item(i)
            checkbox = self.song_list_widget.itemWidget(item)
            checkbox.setChecked(True)
    
    def select_none(self):
        """取消全选"""
        for i in range(self.song_list_widget.count()):
            item = self.song_list_widget.item(i)
            checkbox = self.song_list_widget.itemWidget(item)
            checkbox.setChecked(False)
    
    def delete_selected(self):
        """删除选中的歌曲（包括本地文件夹和歌单信息）"""
        # 获取选中的歌曲hash
        selected_hashes = []
        for i in range(self.song_list_widget.count()):
            item = self.song_list_widget.item(i)
            checkbox = self.song_list_widget.itemWidget(item)
            if checkbox.isChecked():
                song_hash = item.data(Qt.UserRole)
                selected_hashes.append(song_hash)

        if not selected_hashes:
            QMessageBox.information(self, "提示", "请先选择要删除的歌曲！")
            return

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除选中的 {len(selected_hashes)} 首歌曲吗？\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        # 根据hash查找song对象，确保与显示一一对应
        songs_to_delete = [song for song in self.song_list if song['hash'] in selected_hashes]

        # 执行删除
        self.perform_delete(songs_to_delete)
    
    def perform_delete(self, songs_to_delete):
        """执行删除操作，并进行备份"""
        deleted_count = 0
        error_count = 0

        # 备份文件夹与程序同级
        backup_folder = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "backup")
        os.makedirs(backup_folder, exist_ok=True)

        # 备份歌单文件（只备份一次，已有则不重复备份）
        playlist_backup_path = os.path.join(backup_folder, os.path.basename(self.playlist_path))
        if self.backup_checkbox.isChecked() and not os.path.exists(playlist_backup_path):
            try:
                shutil.copy2(self.playlist_path, playlist_backup_path)
            except Exception as e:
                QMessageBox.warning(self, "备份失败", f"歌单文件备份失败: {str(e)}")

        for song in songs_to_delete:
            try:
                if song['exists']:
                    # 备份歌曲文件夹（已有则不重复备份）
                    if self.backup_checkbox.isChecked():
                        backup_path = os.path.join(backup_folder, os.path.basename(song['path']))
                        if not os.path.exists(backup_path):
                            shutil.copytree(song['path'], backup_path)
                    # 删除文件夹
                    shutil.rmtree(song['path'])
                    deleted_count += 1
            except Exception as e:
                error_count += 1
                print(f"删除失败: {song['name']} - {str(e)}")

        # 更新歌单文件，移除已删除歌曲
        self.update_playlist_file([song['hash'] for song in songs_to_delete])

        # 显示结果
        QMessageBox.information(
            self, "删除完成", 
            f"删除完成！\n成功删除：{deleted_count} 首\n失败：{error_count} 首")

        # 重新扫描
        self.scan_songs()
    
    def update_playlist_file(self, deleted_hashes):
        """更新歌单文件，移除已删除歌曲，并保存到原歌单文件"""
        try:
            with open(self.playlist_path, 'r', encoding='utf-8') as f:
                playlist_data = json.load(f)
            
            # 移除已删除的歌曲
            original_songs = playlist_data.get('songs', [])
            updated_songs = [song for song in original_songs if song.get('hash') not in deleted_hashes]
            
            playlist_data['songs'] = updated_songs
            
            # 保存更新后的歌单
            with open(self.playlist_path, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            QMessageBox.warning(self, "错误", f"操作失败: {str(e)}")
            # 可选：写入日志文件
            with open("error.log", "a", encoding="utf-8") as logf:
                logf.write(f"{str(e)}\n")

def main():
    """程序入口"""
    app = QApplication(sys.argv)
    app.setApplicationName("Beat Saber 歌单管理器")
    
    window = BeatSaberPlaylistManager()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
