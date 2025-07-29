import os, json, re, time, webbrowser
import requests
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QLineEdit, QScrollArea, QFrame, QGridLayout, QProgressBar, QListWidget, QListWidgetItem, QDialog, QTextEdit,
    QMessageBox, QFileDialog, QSlider, QComboBox, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QSplashScreen
)
from PyQt5.QtGui import QPixmap, QImage, QBrush, QPalette, QPainter, QColor, QFont, QCursor, QLinearGradient, QPen
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal

import cv2  

# =================== 配置 ===================
BASE_URL = "https://bbs.wtfxxjr.top/api/users?page[number]={}"
# 添加帖子API基础URL
POSTS_URL = "https://bbs.wtfxxjr.top/api/discussions?filter[author]={}&page[number]={}"
# 添加获取所有帖子的URL
ALL_POSTS_URL = "https://bbs.wtfxxjr.top/api/discussions?page[number]={}"
AVATAR_DIR = "assets/avatar/"
COOKIE_FILE = "cookie.json"
DEFAULT_AVATAR = "https://d.feiliupan.com/t/103549985525600256/user.png"

os.makedirs(AVATAR_DIR, exist_ok=True)

# =================== 工具函数 ===================
def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', name)

# 使用线程优化头像下载
class AvatarDownloadThread(QThread):
    finished = pyqtSignal(str, str)  # username, path
    
    def __init__(self, url, username):
        super().__init__()
        self.url = url
        self.username = username
    
    def run(self):
        if not self.url:
            self.url = DEFAULT_AVATAR
        filename = sanitize_filename(self.username) + ".png"
        local_path = os.path.join(AVATAR_DIR, filename)
        if os.path.exists(local_path):
            self.finished.emit(self.username, local_path)
            return
        try:
            r = requests.get(self.url, timeout=10)
            if r.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(r.content)
                self.finished.emit(self.username, local_path)
                return
        except:
            pass
        self.finished.emit(self.username, DEFAULT_AVATAR)

def download_avatar(url, username):
    if not url:
        url = DEFAULT_AVATAR
    filename = sanitize_filename(username) + ".png"
    local_path = os.path.join(AVATAR_DIR, filename)
    if os.path.exists(local_path):
        return local_path
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(r.content)
            return local_path
    except:
        pass
    return DEFAULT_AVATAR

# 使用缓存机制优化头像加载
avatar_cache = {}

def get_avatar_pixmap(avatar_path, size):
    cache_key = (avatar_path, size)
    if cache_key in avatar_cache:
        return avatar_cache[cache_key]
    
    pixmap = QPixmap(avatar_path)
    pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    
    # 创建圆形遮罩
    rounded_pixmap = QPixmap(pixmap.size())
    rounded_pixmap.fill(Qt.transparent)
    painter = QPainter(rounded_pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QBrush(pixmap))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, pixmap.width(), pixmap.height())
    painter.end()
    
    avatar_cache[cache_key] = rounded_pixmap
    return rounded_pixmap

def load_cookie():
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("cookie", "")
    return ""

def save_cookie(cookie):
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump({"cookie": cookie}, f, ensure_ascii=False, indent=4)

# 添加用户数据爬取线程
class UserCrawlThread(QThread):
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(list)  # users list
    
    def __init__(self, cookie):
        super().__init__()
        self.cookie = cookie
    
    def run(self):
        headers = {"User-Agent": "CensusApp"}
        if self.cookie:
            headers["Cookie"] = self.cookie

        users = []
        page = 1
        total = 0
        # 先获取总页数
        url = BASE_URL.format(1)
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            meta = resp.json().get("meta", {})
            total = meta.get("total", 0)
        while True:
            url = BASE_URL.format(page)
            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                break
            data = resp.json().get("data", [])
            if not data:
                break
            for u in data:
                user_id = u["id"]
                if user_id == "4":
                    continue
                attr = u["attributes"]
                users.append({
                    "id": user_id,
                    "name": attr["username"],
                    "avatar": download_avatar(attr.get("avatarUrl"), attr["username"]),
                    "reg_time": attr["joinTime"][:10],
                    "posts": attr.get("discussionCount", 0) + attr.get("commentCount", 0)
                })
                self.progress.emit(len(users), total)
            page += 1
            time.sleep(0.3)
        self.finished.emit(users)

# 添加爬取用户帖子的函数
def crawl_user_posts(cookie, user_id, username, progress_callback=None):
    headers = {"User-Agent": "CensusApp"}
    if cookie:
        headers["Cookie"] = cookie

    posts = []
    page = 1
    total = 0
    # 先获取总页数
    url = POSTS_URL.format(user_id, 1)
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            meta = resp.json().get("meta", {})
            total = meta.get("total", 0)
    except:
        pass

    while True:
        url = POSTS_URL.format(user_id, page)
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                break
            data = resp.json().get("data", [])
            if not data:
                break
            for p in data:
                attr = p["attributes"]
                posts.append({
                    "id": p["id"],
                    "title": attr.get("title", "无标题"),
                    "created_at": attr["createdAt"][:10] if attr.get("createdAt") else "未知",
                    "comment_count": attr.get("commentCount", 0)
                })
                if progress_callback:
                    progress_callback(len(posts), total, f"正在爬取 {username} 的帖子...")
            page += 1
            time.sleep(0.3)
        except:
            break
    return posts

# 添加爬取所有帖子的函数
def crawl_all_posts(cookie, progress_callback=None):
    headers = {"User-Agent": "CensusApp"}
    if cookie:
        headers["Cookie"] = cookie

    posts = []
    page = 1
    total = 0
    # 先获取总页数
    url = ALL_POSTS_URL.format(1)
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            meta = resp.json().get("meta", {})
            total = meta.get("total", 0)
    except:
        pass

    while True:
        url = ALL_POSTS_URL.format(page)
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                break
            data = resp.json().get("data", [])
            if not data:
                break
            for p in data:
                attr = p["attributes"]
                posts.append({
                    "id": p["id"],
                    "title": attr.get("title", "无标题"),
                    "created_at": attr["createdAt"][:10] if attr.get("createdAt") else "未知",
                    "comment_count": attr.get("commentCount", 0)
                })
                if progress_callback:
                    progress_callback(len(posts), total, "正在爬取所有帖子...")
            page += 1
            time.sleep(0.3)
        except:
            break
    return posts

# =================== 界面类 ===================


class CensusApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WTFXXJr论坛用户获取工具(WTFXXJr Forum Member Collector)")
        self.resize(1920, 1080)
        self.cookie = load_cookie()
        self.sort_asc = True
        self.sort_key = "reg_time"  # reg_time 或 posts
        self.users = []
        self.selected_id = None
        # 添加视图模式属性
        self.view_mode = "card"  # "card" 或 "table"
        # 添加帖子数据存储
        self.user_posts = {}
        # 添加所有帖子数据存储
        self.all_posts = []
        # 添加爬取线程
        self.crawl_thread = None

        # 设置主窗口半透明背景
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                    stop: 0 #f0f8ff, stop: 1 #e6e6fa);
                font-family: "Microsoft YaHei", sans-serif;
            }
        """)

        # 延迟初始化UI，先显示启动画面
        QTimer.singleShot(1500, self.init_ui)  # 1.5秒后初始化主界面

    def init_ui(self):
        # 顶部布局
        top_layout = QHBoxLayout()
        self.cookie_input = QLineEdit()
        self.cookie_input.setPlaceholderText("请输入 Cookie")
        self.cookie_input.setText(self.cookie)
        save_btn = QPushButton("保存 Cookie")
        save_btn.clicked.connect(self.save_cookie_action)
        update_btn = QPushButton("更新数据")
        update_btn.clicked.connect(self.update_data)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索用户名...")
        self.search_input.textChanged.connect(self.render_users)
        
        # 添加查看所有帖子按钮
        self.view_all_posts_btn = QPushButton("查看所有帖子")
        self.view_all_posts_btn.clicked.connect(self.display_all_posts)

        self.sort_reg_btn = QPushButton("注册时间 ↓")
        self.sort_reg_btn.clicked.connect(self.toggle_reg_sort)
        self.sort_post_btn = QPushButton("发帖数 ↓")
        self.sort_post_btn.clicked.connect(self.toggle_post_sort)

        # 加大顶部控制栏按钮样式
        glass_css = """
        QPushButton {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                stop: 0 rgba(255, 255, 255, 0.9), stop: 1 rgba(230, 230, 250, 0.8));
            border: 1px solid rgba(255,255,255,0.5);
            border-radius: 12px;
            color: #333;
            font-weight: bold;
            font-size: 16px;
            padding: 12px 24px;
            backdrop-filter: blur(10px);
            box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.1);
        }
        QPushButton:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                stop: 0 rgba(255, 255, 255, 1), stop: 1 rgba(240, 248, 255, 0.9));
            box-shadow: 3px 3px 8px rgba(0, 0, 0, 0.15);
        }
        QPushButton:pressed {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                stop: 0 rgba(230, 230, 250, 0.9), stop: 1 rgba(220, 220, 240, 0.8));
        }
        """
        
        # 加大顶部控制栏输入框样式
        input_glass_css = """
        QLineEdit {
            background: rgba(255,255,255,0.7);
            border: 1px solid rgba(255,255,255,0.5);
            border-radius: 12px;
            color: #333;
            font-size: 16px;
            padding: 12px 24px;
            backdrop-filter: blur(10px);
            box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.1);
        }
        QLineEdit:focus {
            background: rgba(255,255,255,0.9);
            border: 1px solid rgba(100, 149, 237, 0.7);
            box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.15);
        }
        """
        
        self.view_all_posts_btn.setStyleSheet(glass_css)
        
        # 添加视图切换按钮
        self.view_toggle_btn = QPushButton("切换到表格视图")
        self.view_toggle_btn.clicked.connect(self.toggle_view_mode)
        self.view_toggle_btn.setStyleSheet(glass_css)

        save_btn.setStyleSheet(glass_css)
        update_btn.setStyleSheet(glass_css)
        self.sort_reg_btn.setStyleSheet(glass_css)
        self.sort_post_btn.setStyleSheet(glass_css)
        self.cookie_input.setStyleSheet(input_glass_css)
        self.search_input.setStyleSheet(input_glass_css)

        top_layout.addWidget(self.cookie_input, 3)
        top_layout.addWidget(save_btn, 1)
        top_layout.addWidget(update_btn, 1)
        top_layout.addWidget(self.search_input, 2)
        top_layout.addWidget(self.view_all_posts_btn, 1)  # 添加按钮到布局
        top_layout.addWidget(self.sort_reg_btn, 1)
        top_layout.addWidget(self.sort_post_btn, 1)
        top_layout.addWidget(self.view_toggle_btn, 1)  # 添加视图切换按钮到布局

        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        # 隐藏垂直滚动条
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.3);
                width: 15px;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical {
                background: rgba(100, 149, 237, 0.6);
                border-radius: 7px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(70, 130, 180, 0.8);
            }
        """)
        self.user_grid = QGridLayout()
        self.user_grid.setSpacing(20)
        container_widget = QWidget()
        container_widget.setLayout(self.user_grid)
        self.scroll_area.setWidget(container_widget)

        # 添加表格视图
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(5)
        self.table_widget.setHorizontalHeaderLabels(["ID", "用户名", "注册时间", "发帖数", "操作"])
        self.table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 设置为只读
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)  # 设置整行选择
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)  # 自动调整列宽
        self.table_widget.hide()  # 默认隐藏表格视图
        self.table_widget.setStyleSheet("""
            QTableWidget {
                background: rgba(255, 255, 255, 0.8);
                border-radius: 15px;
                font-size: 16px;
                padding: 10px;
                gridline-color: rgba(200, 200, 200, 0.5);
            }
            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid rgba(200, 200, 200, 0.3);
            }
            QHeaderView::section {
                background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                    stop: 0 rgba(100, 149, 237, 0.8), stop: 1 rgba(70, 130, 180, 0.8));
                color: white;
                font-weight: bold;
                padding: 12px;
                border: none;
                border-radius: 0px;
            }
            QTableWidget::item:selected {
                background-color: rgba(100, 149, 237, 0.3);
            }
        """)

        # 主布局
        main_layout = QVBoxLayout()
        self.count_label = QLabel("总人数：0")
        self.count_label.setAlignment(Qt.AlignCenter)
        self.count_label.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: #333;
                padding: 10px;
                background: rgba(255, 255, 255, 0.7);
                border-radius: 10px;
                margin: 5px;
            }
        """)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("爬取进度：%v/%m")
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 10px;
                text-align: center;
                font-size: 16px;
                font-weight: bold;
                background-color: rgba(255, 255, 255, 0.5);
                height: 30px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                    stop: 0 #4CAF50, stop: 1 #8BC34A);
                border-radius: 8px;
            }
        """)
        self.progress_bar.hide()
        main_layout.addWidget(self.count_label)
        main_layout.addWidget(self.progress_bar)  # 用进度条替换原来的标签
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.scroll_area)
        main_layout.addWidget(self.table_widget)  # 添加表格到主布局
        self.setLayout(main_layout)

        self.progress_bar.mouseDoubleClickEvent = self.show_cmd_dialog

        # 添加帖子进度条
        self.posts_progress_bar = QProgressBar()
        self.posts_progress_bar.setMinimum(0)
        self.posts_progress_bar.setMaximum(100)
        self.posts_progress_bar.setValue(0)
        self.posts_progress_bar.setFormat("帖子爬取进度：%v/%m")
        self.posts_progress_bar.setAlignment(Qt.AlignCenter)
        self.posts_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 10px;
                text-align: center;
                font-size: 16px;
                font-weight: bold;
                background-color: rgba(255, 255, 255, 0.5);
                height: 30px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                    stop: 0 #2196F3, stop: 1 #03A9F4);
                border-radius: 8px;
            }
        """)
        self.posts_progress_bar.hide()
        main_layout.addWidget(self.posts_progress_bar)
        
        # 添加所有帖子进度条
        self.all_posts_progress_bar = QProgressBar()
        self.all_posts_progress_bar.setMinimum(0)
        self.all_posts_progress_bar.setMaximum(100)
        self.all_posts_progress_bar.setValue(0)
        self.all_posts_progress_bar.setFormat("所有帖子爬取进度：%v/%m")
        self.all_posts_progress_bar.setAlignment(Qt.AlignCenter)
        self.all_posts_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 10px;
                text-align: center;
                font-size: 16px;
                font-weight: bold;
                background-color: rgba(255, 255, 255, 0.5);
                height: 30px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                    stop: 0 #FF9800, stop: 1 #FFC107);
                border-radius: 8px;
            }
        """)
        self.all_posts_progress_bar.hide()
        main_layout.addWidget(self.all_posts_progress_bar)

        # 检测cookie栏行为，如果有cookie信息就尝试更新
        self.cookie_input.textChanged.connect(self.check_cookie_and_update)

        # 如果启动时有cookie，自动更新
        if self.cookie:
            self.update_data()

    def toggle_reg_sort(self):
        self.sort_key = "reg_time"
        self.sort_asc = not self.sort_asc
        self.sort_reg_btn.setText(f"注册时间 {'↓' if self.sort_asc else '↑'}")
        self.sort_post_btn.setText("发帖数 ↓")
        self.render_users()

    def toggle_post_sort(self):
        self.sort_key = "posts"
        self.sort_asc = not self.sort_asc
        self.sort_post_btn.setText(f"发帖数 {'↓' if self.sort_asc else '↑'}")
        self.sort_reg_btn.setText("注册时间 ↓")
        self.render_users()

    def toggle_view_mode(self):
        """切换视图模式：卡片视图 <-> 表格视图"""
        if self.view_mode == "card":
            self.view_mode = "table"
            self.view_toggle_btn.setText("切换到卡片视图")
            self.scroll_area.hide()
            self.table_widget.show()
            self.populate_table()
        else:
            self.view_mode = "card"
            self.view_toggle_btn.setText("切换到表格视图")
            self.table_widget.hide()
            self.scroll_area.show()
            self.render_users()

    def populate_table(self):
        """填充表格数据"""
        # 清空现有数据
        self.table_widget.setRowCount(0)
        
        # 筛选+排序
        kw = self.search_input.text().lower()
        users = [u for u in self.users if kw in u["name"].lower()]
        if self.sort_key == "reg_time":
            users.sort(key=lambda x: datetime.strptime(x["reg_time"], "%Y-%m-%d"), reverse=not self.sort_asc)
        else:
            users.sort(key=lambda x: x["posts"], reverse=not self.sort_asc)
        
        # 设置行数 (修改：从5列改为4列，移除操作列)
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(["ID", "用户名", "注册时间", "发帖数"])
        self.table_widget.setRowCount(len(users))
        
        # 填充数据
        for row, user in enumerate(users):
            # ID列
            id_item = QTableWidgetItem(user["id"])
            id_item.setTextAlignment(Qt.AlignCenter)
            self.table_widget.setItem(row, 0, id_item)
            
            # 用户名列
            name_item = QTableWidgetItem(user["name"])
            name_item.setTextAlignment(Qt.AlignCenter)
            self.table_widget.setItem(row, 1, name_item)
            
            # 注册时间列
            reg_item = QTableWidgetItem(user["reg_time"])
            reg_item.setTextAlignment(Qt.AlignCenter)
            self.table_widget.setItem(row, 2, reg_item)
            
            # 发帖数列
            posts_item = QTableWidgetItem(str(user["posts"]))
            posts_item.setTextAlignment(Qt.AlignCenter)
            self.table_widget.setItem(row, 3, posts_item)
            
        
        self.count_label.setText(f"总人数：{len(users)}")

    def open_user_page(self, user_id):
        """打开用户页面"""
        webbrowser.open(f"https://bbs.wtfxxjr.top/u/{user_id}")

    def render_users(self):
        # 根据当前视图模式决定如何渲染
        if self.view_mode == "card":
            # 清空原有元素
            for i in reversed(range(self.user_grid.count())):
                item = self.user_grid.itemAt(i)
                if item.widget():
                    item.widget().deleteLater()

            # 筛选+排序
            kw = self.search_input.text().lower()
            users = [u for u in self.users if kw in u["name"].lower()]
            if self.sort_key == "reg_time":
                users.sort(key=lambda x: datetime.strptime(x["reg_time"], "%Y-%m-%d"), reverse=not self.sort_asc)
            else:
                users.sort(key=lambda x: x["posts"], reverse=not self.sort_asc)

            # 渲染成网格
            row, col = 0, 0
            for u in users:
                card = self.build_card(u)
                self.user_grid.addWidget(card, row, col)
                col += 1
                if col >= 4:  # 每行 4 个
                    col = 0
                    row += 1

            self.count_label.setText(f"总人数：{len(users)}")
        else:
            # 表格模式下更新表格
            self.populate_table()

    def build_card(self, user):
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        # 设置半透明卡片样式，减小内边距但加大字体
        frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                    stop: 0 rgba(255, 255, 255, 0.85), stop: 1 rgba(240, 248, 255, 0.85));
                border-radius: 15px;
                padding: 20px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.5);
                box-shadow: 3px 3px 10px rgba(0, 0, 0, 0.1);
            }}
            QFrame:hover {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                    stop: 0 rgba(255, 255, 255, 0.95), stop: 1 rgba(240, 248, 255, 0.95));
                box-shadow: 5px 5px 15px rgba(0, 0, 0, 0.15);
            }}
        """)
        # 添加选中状态标记
        frame._is_selected = False
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # 头像（改为圆形并减小尺寸）
        size = 120  # 减小头像尺寸
        rounded_pixmap = get_avatar_pixmap(user["avatar"], size)
        
        avatar_label = QLabel()
        avatar_label.setPixmap(rounded_pixmap)
        avatar_label.setAlignment(Qt.AlignCenter)

        # 信息标签，进一步加大字体
        name_text = f"<b><span style='font-size: 24px;'>{user['name']}</span></b>"  # 加大字体
        if user['name'] == 'iXiangPro':
            name_text = f"<b><span style='font-size: 24px; color: black; text-shadow: -1px -1px 0 red, 1px -1px 0 red, -1px 1px 0 red, 1px 1px 0 red;'>{user['name']}</span> <span style='font-size: 20px; color: red;'>[管理员]</span></b>"
        elif user['name'] in ['player_youtiao', 'xizhuo61626']:
            name_text = f"<b><span style='font-size: 24px;'>{user['name']}</span> <span style='font-size: 20px; color: purple;'>[版主]</span></b>"
        
        name_label = QLabel(name_text)
        name_label.setAlignment(Qt.AlignCenter)
        reg_label = QLabel(f"<span style='font-size: 18px;'>注册：{user['reg_time']}</span>")  # 加大字体
        reg_label.setAlignment(Qt.AlignCenter)
        post_label = QLabel(f"<span style='font-size: 18px;'>发帖数：{user['posts']}</span>")  # 加大字体
        post_label.setAlignment(Qt.AlignCenter)

        def card_click(event):
            if event.button() == Qt.LeftButton:
                if self.selected_id == user["id"]:
                    webbrowser.open(f"https://bbs.wtfxxjr.top/u/{user['id']}")
                    self.selected_id = None
                    frame._is_selected = False
                    frame.setStyleSheet(f"""
                        QFrame {{
                            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                                stop: 0 rgba(255, 255, 255, 0.85), stop: 1 rgba(240, 248, 255, 0.85));
                            border-radius: 15px;
                            padding: 20px;
                            backdrop-filter: blur(10px);
                            border: 1px solid rgba(255, 255, 255, 0.5);
                            box-shadow: 3px 3px 10px rgba(0, 0, 0, 0.1);
                        }}
                        QFrame:hover {{
                            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                                stop: 0 rgba(255, 255, 255, 0.95), stop: 1 rgba(240, 248, 255, 0.95));
                            box-shadow: 5px 5px 15px rgba(0, 0, 0, 0.15);
                        }}
                    """)
                else:
                    self.selected_id = user["id"]
                    frame._is_selected = True
                    frame.setStyleSheet(f"""
                        QFrame {{
                            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                                stop: 0 rgba(227, 242, 253, 0.9), stop: 1 rgba(187, 222, 251, 0.9));
                            border-radius: 15px;
                            padding: 20px;
                            backdrop-filter: blur(10px);
                            border: 2px solid rgba(100, 149, 237, 0.8);
                            box-shadow: 3px 3px 10px rgba(0, 0, 0, 0.15);
                        }}
                        QFrame:hover {{
                            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                                stop: 0 rgba(227, 242, 253, 1), stop: 1 rgba(187, 222, 251, 1));
                            box-shadow: 5px 5px 15px rgba(0, 0, 0, 0.2);
                        }}
                    """)
        frame.mousePressEvent = card_click

        layout.addWidget(avatar_label)
        layout.addWidget(name_label)
        layout.addWidget(reg_label)
        layout.addWidget(post_label)
        frame.setLayout(layout)
        frame.setCursor(QCursor(Qt.PointingHandCursor))
        return frame

    def show_cmd_dialog(self, event): 
        if event.type() == event.MouseButtonDblClick:
            msg = QMessageBox()
            msg.setWindowTitle("运行中的命令行")
            msg.setText("正在爬取用户数据...\n如需查看详细日志请在命令行窗口查看。")
            msg.exec_()

    def check_cookie_and_update(self):
        cookie = self.cookie_input.text().strip()
        if cookie:
            self.cookie = cookie
            self.update_data()

    def save_cookie_action(self):
        cookie = self.cookie_input.text().strip()
        save_cookie(cookie)
        self.cookie = cookie

    def update_data(self):
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("爬取进度：%v/%m")
        self.progress_bar.show()

        # 使用线程进行数据爬取
        if self.crawl_thread and self.crawl_thread.isRunning():
            self.crawl_thread.quit()
            self.crawl_thread.wait()
            
        self.crawl_thread = UserCrawlThread(self.cookie)
        self.crawl_thread.progress.connect(self.update_progress)
        self.crawl_thread.finished.connect(self.on_crawl_finished)
        self.crawl_thread.start()

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        QApplication.processEvents()

    def on_crawl_finished(self, users):
        self.users = users
        self.progress_bar.setFormat("爬取完成！")
        QTimer.singleShot(2000, self.progress_bar.hide)  # 2秒后隐藏进度条
        self.render_users()
        
        # 在后台爬取所有帖子
        self.crawl_all_posts_background()

    def crawl_all_posts_background(self):
        """后台爬取所有论坛帖子"""
        def progress_callback(current, total, message=None):
            # 后台爬取，不显示进度条
            QApplication.processEvents()

        self.all_posts = crawl_all_posts(self.cookie, progress_callback)
        # 爬取完成后关联帖子与用户
        self.associate_posts_with_users(self.all_posts)

    def crawl_all_posts(self):
        """查看所有帖子（原爬取所有帖子功能）"""
        # 直接显示已爬取的帖子
        self.display_all_posts()

    def associate_posts_with_users(self, posts):
        """将帖子与用户关联"""
        # 清空之前的关联
        for user in self.users:
            user['post_list'] = []
            
        # 建立用户ID到用户对象的映射
        user_map = {user['id']: user for user in self.users}
        
        # 为每个帖子找到对应的用户
        for post in posts:
            user_id = post.get('userId')  # 假设API返回中包含userId字段
            if user_id and user_id in user_map:
                user_map[user_id]['post_list'].append(post)
                
        # 更新用户发帖数（如果需要）
        for user in self.users:
            if 'post_list' in user:
                user['posts'] = len(user['post_list'])

    def display_all_posts(self):
        """显示所有帖子对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("所有帖子")
        dialog.resize(1280, 720)
        dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                    stop: 0 #f0f8ff, stop: 1 #e6e6fa);
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # 添加标题
        title_label = QLabel(f"所有帖子 (共{len(self.all_posts)}篇)")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                font-size: 22px; 
                font-weight: bold; 
                color: #333;
                padding: 15px;
                background: rgba(255, 255, 255, 0.8);
                border-radius: 12px;
                margin: 10px;
            }
        """)
        layout.addWidget(title_label)
        
        # 添加排序按钮
        sort_layout = QHBoxLayout()
        sort_layout.addStretch()
        self.sort_time_btn = QPushButton("按时间排序 ↓")
        self.sort_time_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                    stop: 0 rgba(255, 255, 255, 0.9), stop: 1 rgba(230, 230, 250, 0.8));
                border: 1px solid rgba(255,255,255,0.5);
                border-radius: 10px;
                color: #333;
                font-weight: bold;
                font-size: 15px;
                padding: 10px 20px;
                backdrop-filter: blur(10px);
                box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.1);
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                    stop: 0 rgba(255, 255, 255, 1), stop: 1 rgba(240, 248, 255, 0.9));
                box-shadow: 3px 3px 8px rgba(0, 0, 0, 0.15);
            }
        """)
        self.sort_time_btn.clicked.connect(lambda: self.toggle_post_time_sort(posts_table, title_label))
        self.sort_time_btn.setProperty("sort_order", True)  # True = ascending
        sort_layout.addWidget(self.sort_time_btn)
        sort_layout.addStretch()
        layout.addLayout(sort_layout)
        
        # 添加表格显示帖子
        posts_table = QTableWidget()
        posts_table.setColumnCount(4)
        posts_table.setHorizontalHeaderLabels(["ID", "标题", "发布时间", "评论数"])
        posts_table.setRowCount(len(self.all_posts))
        posts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        posts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        posts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # 美化表格
        posts_table.setStyleSheet("""
            QTableWidget {
                background: rgba(255, 255, 255, 0.85);
                border-radius: 15px;
                font-size: 16px;
                padding: 10px;
                gridline-color: rgba(200, 200, 200, 0.5);
                margin: 10px;
            }
            QTableWidget::item {
                padding: 12px;
                border-bottom: 1px solid rgba(200, 200, 200, 0.3);
            }
            QHeaderView::section {
                background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                    stop: 0 rgba(100, 149, 237, 0.9), stop: 1 rgba(70, 130, 180, 0.9));
                color: white;
                font-weight: bold;
                padding: 15px;
                border: none;
                border-radius: 0px;
            }
            QTableWidget::item:selected {
                background-color: rgba(100, 149, 237, 0.4);
            }
        """)
        
        # 添加双击事件处理，打开帖子详情页面
        def open_post_detail(item):
            if item.column() >= 0:  # 点击任意列都可打开详情
                row = item.row()
                post_id = self.all_posts[row]["id"]
                webbrowser.open(f"https://bbs.wtfxxjr.top/d/{post_id}")
        
        posts_table.itemDoubleClicked.connect(open_post_detail)
        
        # 填充数据
        self.populate_posts_table(posts_table, self.all_posts)
        
        layout.addWidget(posts_table)
        
        # 添加关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                    stop: 0 rgba(255, 255, 255, 0.9), stop: 1 rgba(230, 230, 250, 0.8));
                border: 1px solid rgba(255,255,255,0.5);
                border-radius: 12px;
                color: #333;
                font-weight: bold;
                font-size: 16px;
                padding: 12px 30px;
                backdrop-filter: blur(10px);
                box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.1);
                margin: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, 
                    stop: 0 rgba(255, 255, 255, 1), stop: 1 rgba(240, 248, 255, 0.9));
                box-shadow: 3px 3px 8px rgba(0, 0, 0, 0.15);
            }
        """)
        close_btn.clicked.connect(dialog.close)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def toggle_post_time_sort(self, table, title_label):
        """切换帖子时间排序"""
        sort_btn = self.sort_time_btn
        ascending = sort_btn.property("sort_order")
        sort_btn.setProperty("sort_order", not ascending)
        
        # 更新按钮文本
        sort_btn.setText(f"按时间排序 {'↑' if ascending else '↓'}")
        
        # 对帖子进行排序
        sorted_posts = sorted(self.all_posts, 
                             key=lambda x: x["created_at"], 
                             reverse=not ascending)
        
        # 更新表格内容
        self.populate_posts_table(table, sorted_posts)
        
        # 更新标题
        title_label.setText(f"所有帖子 (共{len(sorted_posts)}篇)")
    
    def populate_posts_table(self, table, posts_data):
        """填充帖子表格数据"""
        table.setRowCount(len(posts_data))
        
        for row, post in enumerate(posts_data):
            # ID列
            id_item = QTableWidgetItem(post["id"])
            id_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, id_item)
            
            # 标题列
            title_item = QTableWidgetItem(post["title"])
            title_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 1, title_item)
            
            # 发布时间列
            date_item = QTableWidgetItem(post["created_at"])
            date_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 2, date_item)
            
            # 评论数列
            comment_item = QTableWidgetItem(str(post["comment_count"]))
            comment_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 3, comment_item)
    
# =================== 启动 ===================
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    
    # 创建启动画面
    splash_pix = QPixmap(500, 400)
    splash_pix.fill(QColor(70, 130, 180))
    
    # 在启动画面中添加文字
    splash_painter = QPainter(splash_pix)
    splash_painter.setRenderHint(QPainter.Antialiasing)
    
    # 绘制背景渐变
    gradient = QLinearGradient(0, 0, 0, 400)
    gradient.setColorAt(0, QColor(70, 130, 180))
    gradient.setColorAt(1, QColor(100, 149, 237))
    splash_painter.fillRect(splash_pix.rect(), gradient)
    
    # 绘制大写的"W"
    font = QFont("Microsoft YaHei", 72, QFont.Bold)
    splash_painter.setFont(font)
    splash_painter.setPen(Qt.white)
    splash_painter.drawText(splash_pix.rect(), Qt.AlignCenter, "W")
    
    # 绘制底部文字
    font = QFont("Microsoft YaHei", 16, QFont.Bold)
    splash_painter.setFont(font)
    splash_painter.setPen(Qt.white)
    splash_painter.drawText(splash_pix.rect(), Qt.AlignHCenter | Qt.AlignBottom | Qt.AlignCenter, 
                           "WTFXXJr论坛用户获取工具\n正在启动...")
    splash_painter.end()
    
    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.setMask(splash_pix.mask())
    
    # 添加启动动画文本和进度条
    splash.setStyleSheet("""
        QSplashScreen {
            color: white;
            font-size: 20px;
            font-weight: bold;
        }
    """)
    
    splash.show()
    
    win = CensusApp()
    splash.finish(win)
    win.show()
    
    sys.exit(app.exec_())
