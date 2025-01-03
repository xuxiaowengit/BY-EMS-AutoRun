import sys
import json
import asyncio
import websockets
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                           QHBoxLayout, QPushButton, QLabel, QTextEdit, 
                           QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
                           QHeaderView)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QColor, QIcon, QFont
import traceback

# EMS监控系统客户端主窗口类
class WebSocketClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ws_worker = None  # WebSocket工作线程实例
        self.device_info = {}  # 设备ID和名称的映射关系
        self.latest_rtv_data = {}  # 存储最新的rtv数据
        
        # 添加定时器，每秒更新一次显示
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(1000)  # 1000毫秒 = 1秒
        
        # 设置窗口图标
        icon_path = "./img/ems.png"  # 图标文件路径
        try:
            from PyQt5.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            self.log(f"设置窗口图标失败: {str(e)}")
        
        self.initUI()  # 初始化UI

    # 初始化UI
    def initUI(self):
        self.setWindowTitle('BY-EMS监控系统')  # 设置窗口标题
        self.setGeometry(100, 100, 1600, 900)  # 设置窗口大小

        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # 创建左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setMaximumWidth(600)

        # 创建控制按钮
        button_layout = QHBoxLayout()  # 创建水平布局放置按钮
        
        self.connect_btn = QPushButton('连接WebSocket', self)
        self.connect_btn.clicked.connect(self.start_websocket)
        
        self.disconnect_btn = QPushButton('断开连接', self)
        self.disconnect_btn.clicked.connect(self.stop_websocket)
        self.disconnect_btn.setEnabled(False)
        
        self.refresh_btn = QPushButton('刷新数据', self)  # 添加刷新按钮
        self.refresh_btn.clicked.connect(self.refresh_data)
        self.refresh_btn.setEnabled(False)  # 初始时禁用
        
        button_layout.addWidget(self.connect_btn)
        button_layout.addWidget(self.disconnect_btn)
        button_layout.addWidget(self.refresh_btn)
        
        # 创建设备树
        self.device_tree = QTreeWidget(self)  # 设备树控件
        self.device_tree.setHeaderLabels(['设备列表'])  # 设备树标题
        self.device_tree.itemClicked.connect(self.on_tree_item_clicked)  # 设备树项点击事件

        # 创建日志显示区
        self.log_text = QTextEdit(self)  # 日志显示控件
        self.log_text.setReadOnly(True)  # 日志显示区只读
        self.log_text.setMaximumHeight(400)  # 日志显示区最大高度

        # 添加控件到左侧面板
        left_layout.addLayout(button_layout)  # 使用布局替代单独添加按钮
        left_layout.addWidget(self.device_tree)
        left_layout.addWidget(self.log_text)

        # 创建右侧数据显示列表
        self.data_list = QListWidget(self)  # 数据显示列表控件
        self.data_list.setStyleSheet("QListWidget { font-size: 14px; }")  # 设置列表样式

        # 添加面板到主布局
        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.data_list)

    # 日志记录函数
    def log(self, message):
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # 获取当前时间
        # self.log_text.append(f"{current_time} - {message}")  # 记录日志
        self.log_text.append(f"{message}")  # 记录日志

    # 启动WebSocket工作线程
    def start_websocket(self):
        try:
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.refresh_btn.setEnabled(True)  # 连接后启用刷新按钮
            self.log("正在连接WebSocket...")
            
            # 启动WebSocket工作线程
            self.ws_worker = WebSocketWorker()
            self.ws_worker.message_signal.connect(self.handle_message)
            self.ws_worker.log_signal.connect(self.log)
            self.ws_worker.start()
            
            self.update_timer.start(1000)  # 启动定时器
            
        except Exception as e:
            self.log(f"启动WebSocket连接失败: {str(e)}")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.refresh_btn.setEnabled(False)

    # 停止WebSocket工作线程
    def stop_websocket(self):
        self.update_timer.stop()  # 停止定时器
        if self.ws_worker:
            self.ws_worker.stop()
            self.ws_worker = None
        
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)  # 断开连接时禁用刷新按钮
        self.log("WebSocket连接已断开")

    # 处理WebSocket工作线程消息
    def handle_message(self, data):
        try:
            func_type = data.get('func')
            self.log(f"收到消息类型: {func_type}")
            
            if func_type == "menu":
                menu_data = data.get("data", {})
                self.log(f"处理menu数据，包含设备类型: {list(menu_data.keys())}")
                self.update_device_tree(menu_data)
                
                # 存储设备ID和名称的映射关系
                self.device_info = {}
                for device_type, devices in menu_data.items():
                    for device in devices:
                        for rtv_item in device.get("rtvList", []):
                            item_id = str(rtv_item["id"])
                            self.device_info[item_id] = {
                                "name": rtv_item.get("fieldChnName", ""),
                                "eng_name": rtv_item.get("fieldEngName", ""),
                                "device_type": device_type,
                                "device_name": device.get("chnName", ""),
                                "table_name": device.get("tableName", "")
                            }
                self.log(f"设备信息映射表已更新，共 {len(self.device_info)} 个设备点位")
                
            elif func_type == "rtv":
                rtv_data = data.get("data", [])
                self.log(f"收到rtv数据，数量: {len(rtv_data)}")
                
                # 更新数据缓存
                for item in rtv_data:
                    item_id = str(item.get("id"))
                    value = item.get("value", "N/A")
                    self.latest_rtv_data[item_id] = value
                    # self.log(f"更新数据缓存: ID={item_id}, 值={value}")
                   
                self.log(f"更新 {len(rtv_data)} 个数据缓存")   
                # 如果当前有选中的项，更新显示
                current_item = self.device_tree.currentItem()
                if current_item:
                    level = self.get_item_level(current_item)
                    rtv_ids = self.get_rtv_ids_for_item(current_item, level)
                    self.update_data_list_by_ids(rtv_ids)
                
        except Exception as e:
            self.log(f"处理消息出错: {str(e)}")

    # 更新设备树
    def update_device_tree(self, menu_data):
        try:
            self.device_tree.clear()  # 清空设备树
            
            for device_type, devices in menu_data.items():
                type_item = QTreeWidgetItem([device_type])  # 设备类型项
                self.device_tree.addTopLevelItem(type_item)  # 添加设备类型项到设备树
                
                for device in devices:
                    # 获取第一个rtv_item的ID作为设备ID
                    device_id = ""
                    if device.get("rtvList"):
                        device_id = str(device["rtvList"][0]["id"])
                    
                    device_item = QTreeWidgetItem([
                        # f"{device.get('chnName')} ({device.get('engName')})"
                        f"{device_id} - {device.get('chnName')}"
                    ])  # 设备项
                    device_item.setData(0, Qt.UserRole, device)  # 设备项数据
                    
                    # 添加子节点显示设备的详细信息
                    for rtv_item in device.get("rtvList", []):
                        rtv_item_node = QTreeWidgetItem([
                            # f"{rtv_item.get('fieldChnName')} ({rtv_item.get('fieldEngName')})"
                            f"{rtv_item['id']} - {rtv_item.get('fieldChnName')}"
                        ])  # 设备详细信息项
                        device_item.addChild(rtv_item_node)  # 添加设备详细信息项到设备项
                    
                    type_item.addChild(device_item)  # 添加设备项到设备类型项
                
                type_item.setExpanded(True)  # 设备类型项展开
                
            self.log("设备树更新完成")  # 记录日志
            
        except Exception as e:
            self.log(f"更新设备树出错: {str(e)}")  # 记录日志

    # 更新数据列表
    def update_data_list(self, rtv_data):
        try:
            self.log(f"开始更新数据列表，数据数量: {len(rtv_data)}")
            
            # 清空列表
            self.data_list.clear()

            # 按设备类型对数据进行分组
            grouped_data = {
                "d_bms": [],
                "d_pcs": [],
                "d_grid": [],
                "d_air_condition": []
            }

            # 将数据分组
            for item in rtv_data:
                try:
                    item_id = str(item.get("id"))
                    value = item.get("value", "")
                    
                    # 获取设备信息
                    device_info = self.device_info.get(item_id)
                    if not device_info:
                        self.log(f"未找到设备信息: ID={item_id}")
                        continue
                    
                    device_type = device_info.get("device_type")
                    if device_type in grouped_data:
                        grouped_data[device_type].append((item_id, device_info, value))

                except Exception as row_error:
                    self.log(f"处理数据项出错: {str(row_error)}")
                    continue

            # 按设备类型顺序显示数据
            color_map = {
                "d_bms": QColor(230, 230, 255),           # 浅蓝色 - BMS电池
                "d_pcs": QColor(255, 230, 230),           # 浅红色 - PCS
                "d_grid": QColor(255, 255, 230),          # 浅黄色 - 电网
                "d_air_condition": QColor(230, 255, 230)  # 浅绿色 - 空调
            }

            # 按顺序添加各组数据
            for device_type, items in grouped_data.items():
                if items:  # 如果该类型有数据
                    # 添加设备类型标题
                    title_item = QListWidgetItem(f"===== {device_type} =====")
                    title_item.setBackground(color_map[device_type])
                    self.data_list.addItem(title_item)

                    # 添加该类型的所有数据项
                    for item_id, device_info, value in items:
                        display_text = f"ID: {item_id:<12}  {device_info['name']:<30}  {value:<45}"
                        list_item = QListWidgetItem(display_text)
                        
                        # 设置等宽字体以便对齐
                        from PyQt5.QtGui import QFont
                        font = QFont("Courier New")  # 使用等宽字体
                        list_item.setFont(font)
                        
                        # 设置背景色
                        list_item.setBackground(color_map[device_type])
                        
                        # 添加到列表
                        self.data_list.addItem(list_item)

            self.log(f"数据列表更新完成，当前列表项数: {self.data_list.count()}")
            
        except Exception as e:
            self.log(f"更新数据列表出错: {str(e)}")

    # 设备树项点击事件
    def on_tree_item_clicked(self, item, column):
        try:
            # 获取点击项的层级
            level = self.get_item_level(item)
            self.log(f"点击项层级: {level}")
            
            # 获取需要显示的数据ID列表
            rtv_ids = self.get_rtv_ids_for_item(item, level)
            if not rtv_ids:
                return
            
            # 过滤并显示数据
            self.update_data_list_by_ids(rtv_ids)
            
        except Exception as e:
            self.log(f"处理点击事件出错: {str(e)}")

    def get_item_level(self, item):
        """获取树节点的层级（0-顶级分组，1-设备，2-数据项）"""
        level = 0
        parent = item.parent()
        while parent:
            level += 1
            parent = parent.parent()
        return level

    def get_rtv_ids_for_item(self, item, level):
        """根据点击项和层级获取需显示的数据ID列表"""
        rtv_ids = []
        
        try:
            if level == 0:  # 顶级分组
                # 获取该分组下所有数据项ID
                device_type = item.text(0)
                for i in range(item.childCount()):
                    device_item = item.child(i)
                    for j in range(device_item.childCount()):
                        rtv_item = device_item.child(j)
                        item_text = rtv_item.text(0)
                        item_id = item_text.split(" - ")[0]  # 从显示文本中提取ID
                        rtv_ids.append(int(item_id))
                        
            elif level == 1:  # 设备项
                # 获取该设备下所有数据项ID
                for i in range(item.childCount()):
                    rtv_item = item.child(i)
                    item_text = rtv_item.text(0)
                    item_id = item_text.split(" - ")[0]  # 从显示文本中提取ID
                    rtv_ids.append(int(item_id))
                    
            else:  # 数据项
                # 获取单个数据项ID
                item_text = item.text(0)
                item_id = item_text.split(" - ")[0]  # 从显示文本中提取ID
                rtv_ids.append(int(item_id))
                
            self.log(f"获取到 {len(rtv_ids)} 个数据项ID")
            return rtv_ids
            
        except Exception as e:
            self.log(f"获取数据ID出错: {str(e)}")
            return []

    def update_data_list_by_ids(self, rtv_ids):
        """根据ID列表更新右侧数据显示"""
        try:
            # 清空列表
            self.data_list.clear()

            # 按设备类型对数据进行分组
            grouped_data = {
                "d_bms": [],
                "d_pcs": [],
                "d_grid": [],
                "d_air_condition": []
            }

            # 将数据分组
            for item_id in rtv_ids:
                str_id = str(item_id)
                device_info = self.device_info.get(str_id)
                if not device_info:
                    continue
                
                # 从最近一次的rtv数据中获取值
                value = self.get_latest_value(str_id)
                device_type = device_info.get("device_type")
                
                if device_type in grouped_data:
                    grouped_data[device_type].append((str_id, device_info, value))
                    
                    
            #输出缓存池数据数量
            self.log(f"获取数据值个数:{len(rtv_ids)}")
                    
            # 显示分组数据
            color_map = {
                "d_bms": QColor(230, 230, 255),           # 浅蓝色 - BMS电池
                "d_pcs": QColor(255, 230, 230),           # 浅红色 - PCS
                "d_grid": QColor(255, 255, 230),          # 浅黄色 - 电网
                "d_air_condition": QColor(230, 255, 230)  # 浅绿色 - 空调
            }

            for device_type, items in grouped_data.items():
                if items:
                    # 添加设备类型标题
                    title_item = QListWidgetItem(f"===== {device_type} =====")
                    title_item.setBackground(color_map[device_type])
                    self.data_list.addItem(title_item)

                    # 添加数据项
                    for item_id, device_info, value in items:
                        display_text = f"ID: {item_id:<12}  {device_info['name']:<30}  {value:<45}"
                        list_item = QListWidgetItem(display_text)
                        list_item.setFont(QFont("Courier New"))
                        list_item.setBackground(color_map[device_type])
                        self.data_list.addItem(list_item)

        except Exception as e:
            self.log(f"更新数据列表出错: {str(e)}")

    def get_latest_value(self, item_id):
        """获取最新一次的数据值"""
        try:
            # 从缓存中获取最新数据
            value = self.latest_rtv_data.get(item_id, "N/A")
            # self.log(f"获取数据值: ID={item_id}, 值={value}")
            return value
        except Exception as e:
            self.log(f"获取数据值出错: {str(e)}")
            return "Error"

    # 关闭事件
    def closeEvent(self, event):
        self.stop_websocket()  # 停止WebSocket工作线程
        event.accept()  # 接受关闭事件

    def refresh_data(self):
        """手动刷新数据"""
        try:
            self.log("手动刷新数据...")
            if self.ws_worker and self.ws_worker.websocket:
                # 清空现有数据
                self.latest_rtv_data.clear()
                self.device_info.clear()
                # 重新连接
                self.stop_websocket()
                self.start_websocket()
                self.log("已发送刷新请求")
        except Exception as e:
            self.log(f"刷新数据出错: {str(e)}")

    def update_display(self):
        """定时更新显示"""
        try:
            # 如果有选中的项，更新其显示
            current_item = self.device_tree.currentItem()
            if current_item:
                level = self.get_item_level(current_item)
                rtv_ids = self.get_rtv_ids_for_item(current_item, level)
                if rtv_ids:
                    self.update_data_list_by_ids(rtv_ids)
        except Exception as e:
            pass  # 静默处理定时器的错误，避免日志刷屏

# WebSocket工作线程类
class WebSocketWorker(QThread):
    message_signal = pyqtSignal(dict)  # 消息信号
    log_signal = pyqtSignal(str)  # 日志信号
    refresh_signal = pyqtSignal()  # 添加刷新信号

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.websocket = None
        self.need_refresh = False  # 添加刷新标志

    async def connect_websocket(self):
        # 使用固定的token
        uri = "ws://ems.hy-power.net:8888/E6F7D5412A20?d0bdae3f37de30f0a3386ca265b9dad07111a89679add764042f12ca60d017da2bc9de82cfcb45f59151e279661e6954639c4def137595e5e7350632baced8925503b37206c533afad17ad72120a814a"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "http://ems.hy-power.net:8114",
        }

        while self.is_running:  # 添加外层循环实现重连
            try:
                async with websockets.connect(uri, extra_headers=headers) as websocket:
                    self.websocket = websocket
                    self.log_signal.emit("WebSocket连接已建立")
                    
                    # 发送初始menu订阅
                    menu_subscribe = {"func": "menu"}
                    await websocket.send(json.dumps(menu_subscribe))
                    self.log_signal.emit("已发送menu订阅请求")
                    
                    while self.is_running:
                        try:
                            # 检查是否需要刷新
                            if self.need_refresh:
                                self.need_refresh = False
                                # 重新发送menu订阅
                                menu_subscribe = {"func": "menu"}
                                await websocket.send(json.dumps(menu_subscribe))
                                self.log_signal.emit("已重新发送menu订阅请求")
                            
                            message = await websocket.recv()
                            self.log_signal.emit(f"收到原始消息: {message[:100]}...")  # 只显示前200个字符
                            
                            if isinstance(message, str):
                                data = json.loads(message)
                                self.message_signal.emit(data)
                                
                                # 如果收到menu数据，自动发送rtv订阅
                                if data.get("func") == "menu":
                                    # 从menu数据中提取所有ID
                                    rtv_ids = []
                                    menu_data = data.get("data", {})
                                    for device_type, devices in menu_data.items():
                                        for device in devices:
                                            for rtv_item in device.get("rtvList", []):
                                                rtv_ids.append(rtv_item["id"])
                                    
                                    # 发送rtv订阅消息
                                    rtv_subscribe = {
                                        "func": "rtv",
                                        "ids": rtv_ids,
                                        "period": 5
                                    }
                                    await websocket.send(json.dumps(rtv_subscribe))
                                    self.log_signal.emit(f"已发送rtv订阅请求，订阅 {len(rtv_ids)} 个ID")
                                
                        except websockets.exceptions.ConnectionClosed:
                            self.log_signal.emit("WebSocket连接已关闭，准备重连...")
                            break  # 跳出内层循环，外层循环会重新连接
                        except json.JSONDecodeError as e:
                            self.log_signal.emit(f"JSON解析错误: {str(e)}")
                        except Exception as e:
                            self.log_signal.emit(f"接收数据错误: {str(e)}")
                            
            except Exception as e:
                self.log_signal.emit(f"WebSocket连接错误: {str(e)}，3秒后重试...")
                await asyncio.sleep(3)  # 等待3秒后重试

    def run(self):
        asyncio.run(self.connect_websocket())

    def stop(self):
        """停止工作线程"""
        self.is_running = False
        self.websocket = None  # 直接清空 websocket 实例
        
    def request_refresh(self):
        """请求刷新数据"""
        self.need_refresh = True

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = WebSocketClient()
    ex.show()
    sys.exit(app.exec_())
