import os, json, re, time, webbrowser
import requests
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QLineEdit, QScrollArea, QFrame, QGridLayout
)
from PyQt5.QtGui import QPixmap, QCursor
from PyQt5.QtCore import Qt

# =================== 配置 ===================
BASE_URL = "https://bbs.wtfxxjr.top/api/users?page[number]={}"
AVATAR_DIR = "assets/avatar/"
COOKIE_FILE = "cookie.json"
DEFAULT_AVATAR = "https://d.feiliupan.com/t/103549985525600256/user.png"

os.makedirs(AVATAR_DIR, exist_ok=True)

# =================== 工具函数 ===================
def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', name)

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

def load_cookie():
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("cookie", "")
    return ""

def save_cookie(cookie):
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump({"cookie": cookie}, f, ensure_ascii=False, indent=4)

def crawl_users(cookie):
    headers = {"User-Agent": "CensusApp"}
    if cookie:
        headers["Cookie"] = cookie

    users = []
    page = 1
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
        page += 1
        time.sleep(0.3)
    return users

# =================== 界面类 ===================
class CensusApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WTFXXJr论坛用户获取工具(WTFXXJr Forum Member Collector)")
        self.resize(1280, 720)
        self.cookie = load_cookie()
        self.sort_asc = True
        self.sort_key = "reg_time"  # reg_time 或 posts
        self.users = []
        self.selected_id = None

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

        self.sort_reg_btn = QPushButton("注册时间 ↓")
        self.sort_reg_btn.clicked.connect(self.toggle_reg_sort)
        self.sort_post_btn = QPushButton("发帖数 ↓")
        self.sort_post_btn.clicked.connect(self.toggle_post_sort)

        top_layout.addWidget(self.cookie_input, 3)
        top_layout.addWidget(save_btn, 1)
        top_layout.addWidget(update_btn, 1)
        top_layout.addWidget(self.search_input, 2)
        top_layout.addWidget(self.sort_reg_btn, 1)
        top_layout.addWidget(self.sort_post_btn, 1)

        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.user_grid = QGridLayout()
        container_widget = QWidget()
        container_widget.setLayout(self.user_grid)
        self.scroll_area.setWidget(container_widget)

        # 主布局
        main_layout = QVBoxLayout()
        self.count_label = QLabel("总人数：0")
        self.count_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.count_label)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.scroll_area)
        self.setLayout(main_layout)

    def save_cookie_action(self):
        cookie = self.cookie_input.text().strip()
        save_cookie(cookie)
        self.cookie = cookie

    def update_data(self):
        self.users = crawl_users(self.cookie)
        self.render_users()

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

    def render_users(self):
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

    def build_card(self, user):
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setStyleSheet("QFrame { background: #fdfdfd; border-radius: 8px; padding:5px; }")
        layout = QVBoxLayout()

        # 头像
        pixmap = QPixmap(user["avatar"])
        pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        avatar_label = QLabel()
        avatar_label.setPixmap(pixmap)
        avatar_label.setAlignment(Qt.AlignCenter)

        # 信息标签
        name_label = QLabel(f"<b>{user['name']}</b>")
        name_label.setAlignment(Qt.AlignCenter)
        reg_label = QLabel(f"注册：{user['reg_time']}")
        reg_label.setAlignment(Qt.AlignCenter)
        post_label = QLabel(f"发帖数：{user['posts']}")
        post_label.setAlignment(Qt.AlignCenter)

        # 点击整个卡片逻辑
        def card_click(event):
            if self.selected_id == user["id"]:
                webbrowser.open(f"https://bbs.wtfxxjr.top/u/{user['id']}")
                self.selected_id = None
                frame.setStyleSheet("QFrame { background: #fdfdfd; border-radius: 8px; padding:5px; }")
            else:
                self.selected_id = user["id"]
                frame.setStyleSheet("QFrame { background: #E3F2FD; border-radius: 8px; padding:5px; }")

        frame.mousePressEvent = card_click

        layout.addWidget(avatar_label)
        layout.addWidget(name_label)
        layout.addWidget(reg_label)
        layout.addWidget(post_label)
        frame.setLayout(layout)
        frame.setCursor(QCursor(Qt.PointingHandCursor))
        return frame

# =================== 启动 ===================
if __name__ == "__main__":
    app = QApplication([])
    win = CensusApp()
    win.show()
    app.exec_()
