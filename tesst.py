# coding:utf-8
import sys

# 导入PyQt6基础模块
from PyQt6.QtCore import Qt, pyqtSignal, QEasingCurve, QUrl
from PyQt6.QtGui import QIcon, QDesktopServices
from PyQt6.QtWidgets import (QLabel, QHBoxLayout, QVBoxLayout,
                             QApplication, QFrame, QWidget)

# 导入Fluent风格组件
from qfluentwidgets import (NavigationBar, NavigationItemPosition,
                            MessageBox, isDarkTheme, setTheme, Theme,
                            setThemeColor, SearchLineEdit, PopUpAniStackedWidget,
                            getFont)
from qfluentwidgets import FluentIcon as FIF  # Fluent风格图标

# 导入无边框窗口支持
from qframelesswindow import FramelessWindow, TitleBar

# 导入QT Designer生成的UI类（请确保该文件存在）
# 该文件由QT Designer设计并通过pyuic6转换而来
from UI_main import Ui_Form


class DesignerWidgetWrapper(QWidget):
    """
    包装QT Designer生成的UI组件，使其能正确集成到Fluent导航体系中

    作用：
    1. 保留Designer设计的布局和样式
    2. 提供导航系统所需的唯一标识
    3. 确保界面尺寸和布局策略正确继承
    """

    def __init__(self, designer_widget: QWidget, parent=None):
        super().__init__(parent=parent)

        # 复用Designer组件的布局（避免重新设计布局）
        self.setLayout(designer_widget.layout())

        # 继承原组件的大小策略（防止界面变形）
        self.setSizePolicy(designer_widget.sizePolicy())

        # 使用原组件的objectName作为导航标识
        # 注意：这是Fluent导航系统识别界面的关键
        self.setObjectName(designer_widget.objectName())


class StackedWidget(QFrame):
    """
    带动画效果的堆栈窗口组件

    作用：
    1. 管理多个界面的切换
    2. 提供平滑的页面切换动画
    3. 当页面切换时发送信号，用于同步导航栏状态
    """
    # 页面切换时触发的信号，传递新页面的索引
    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # 创建水平布局
        self.hBoxLayout = QHBoxLayout(self)
        # 创建带弹出动画的堆栈组件（Fluent风格特色）
        self.view = PopUpAniStackedWidget(self)

        # 消除布局边距，使界面紧凑
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        # 将动画堆栈组件添加到布局中
        self.hBoxLayout.addWidget(self.view)

        # 当内部页面切换时，向外发送信号
        self.view.currentChanged.connect(self.currentChanged)

    def addWidget(self, widget):
        """向堆栈中添加页面"""
        self.view.addWidget(widget)

    def widget(self, index: int):
        """根据索引获取页面"""
        return self.view.widget(index)

    def setCurrentWidget(self, widget, popOut=False):
        """
        切换到指定页面

        参数:
            widget: 要切换到的页面组件
            popOut: 是否使用弹出动画（默认使用平滑过渡）
        """
        if not popOut:
            # 平滑切换动画（300ms）
            self.view.setCurrentWidget(widget, duration=300)
        else:
            # 弹出式动画（200ms，加速曲线）
            self.view.setCurrentWidget(
                widget, True, False, 200, QEasingCurve.Type.InQuad)

    def setCurrentIndex(self, index, popOut=False):
        """根据索引切换到指定页面"""
        self.setCurrentWidget(self.view.widget(index), popOut)


class CustomTitleBar(TitleBar):
    """
    自定义标题栏组件（Fluent风格）

    包含：
    1. 窗口图标
    2. 窗口标题
    3. 搜索框
    4. 窗口控制按钮（最小化/最大化/关闭）
    """

    def __init__(self, parent):
        super().__init__(parent)

        # 设置标题栏高度
        self.setFixedHeight(48)

        # 移除默认的窗口控制按钮（后续重新布局）
        self.hBoxLayout.removeWidget(self.minBtn)
        self.hBoxLayout.removeWidget(self.maxBtn)
        self.hBoxLayout.removeWidget(self.closeBtn)

        # 1. 添加窗口图标
        self.iconLabel = QLabel(self)
        self.iconLabel.setFixedSize(18, 18)  # 图标大小
        self.hBoxLayout.insertSpacing(0, 20)  # 左侧留白
        # 将图标插入到布局中（左对齐、垂直居中）
        self.hBoxLayout.insertWidget(
            1, self.iconLabel, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # 监听窗口图标变化事件，同步更新
        self.window().windowIconChanged.connect(self.setIcon)

        # 2. 添加窗口标题
        self.titleLabel = QLabel(self)
        self.titleLabel.setObjectName('titleLabel')  # 用于QSS样式设置
        # 将标题插入到布局中（左对齐、垂直居中）
        self.hBoxLayout.insertWidget(
            2, self.titleLabel, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # 监听窗口标题变化事件，同步更新
        self.window().windowTitleChanged.connect(self.setTitle)

        # 3. 添加搜索框（Fluent风格特色）
        self.searchLineEdit = SearchLineEdit(self)
        self.searchLineEdit.setPlaceholderText('搜索应用、游戏、电影、设备等')
        self.searchLineEdit.setFixedWidth(400)  # 搜索框宽度
        self.searchLineEdit.setClearButtonEnabled(True)  # 启用清除按钮

        # 4. 重新布局窗口控制按钮
        self.vBoxLayout = QVBoxLayout()
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setSpacing(0)  # 按钮间无间距
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)  # 无内边距
        self.buttonLayout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 按钮居上

        # 添加窗口控制按钮
        self.buttonLayout.addWidget(self.minBtn)
        self.buttonLayout.addWidget(self.maxBtn)
        self.buttonLayout.addWidget(self.closeBtn)

        # 将按钮布局添加到垂直布局
        self.vBoxLayout.addLayout(self.buttonLayout)
        self.vBoxLayout.addStretch(1)  # 拉伸空白区域，使按钮居上
        self.hBoxLayout.addLayout(self.vBoxLayout, 0)  # 加入右侧布局

    def setTitle(self, title):
        """更新标题文本"""
        self.titleLabel.setText(title)
        self.titleLabel.adjustSize()  # 自动调整大小以适应文本

    def setIcon(self, icon):
        """更新窗口图标"""
        self.iconLabel.setPixmap(QIcon(icon).pixmap(18, 18))

    def resizeEvent(self, e):
        """窗口大小变化时，调整搜索框位置使其居中"""
        self.searchLineEdit.move((self.width() - self.searchLineEdit.width()) // 2, 8)
        super().resizeEvent(e)


class Window(FramelessWindow):
    """
    主窗口类，整合所有组件实现完整功能

    功能：
    1. 加载QT Designer设计的UI界面
    2. 实现Fluent风格导航栏与界面切换
    3. 提供完整的窗口功能（标题、图标、大小调整等）
    """

    def __init__(self):
        super().__init__()

        # 设置自定义标题栏
        self.setTitleBar(CustomTitleBar(self))

        # 主题设置（可选）
        # setTheme(Theme.DARK)  # 启用深色主题
        # setThemeColor('#0078d4')  # 设置主题色

        # 创建主布局（水平布局）
        self.hBoxLayout = QHBoxLayout(self)

        # 创建导航栏（左侧）
        self.navigationBar = NavigationBar(self)

        # 创建堆栈窗口（右侧内容区）
        self.stackWidget = StackedWidget(self)

        # 加载QT Designer设计的UI界面
        self.load_designer_ui()

        # 初始化布局
        self.initLayout()

        # 初始化导航栏（关联界面）
        self.initNavigation()

        # 初始化窗口基本设置
        self.initWindow()

    def load_designer_ui(self):
        """
        加载QT Designer生成的UI文件

        关键逻辑：
        1. 使用成员变量保存临时容器，避免被Python垃圾回收
        2. 从Designer的stackedWidget中提取页面
        3. 用包装类处理页面，使其适配Fluent导航系统
        """
        # 创建临时容器保存Designer的UI（关键：用成员变量延长生命周期）
        # 解决"RuntimeError: wrapped C/C++ object has been deleted"错误
        self.designer_container = QWidget()

        # 初始化Designer生成的UI类，将UI加载到临时容器
        self.designer_ui = Ui_Form()
        self.designer_ui.setupUi(self.designer_container)

        # 从Designer的stackedWidget中提取页面（根据实际UI调整索引）
        # 索引0：第一个页面
        self.home_page = self.designer_ui.stackedWidget.widget(0)
        # 索引1：第二个页面
        self.app_page = self.designer_ui.stackedWidget.widget(1)

        # 用包装类处理页面，使其适配Fluent导航系统
        self.home_interface = DesignerWidgetWrapper(self.home_page, self)
        self.app_interface = DesignerWidgetWrapper(self.app_page, self)

        # 如果有更多页面，可以继续提取
        # self.video_page = self.designer_ui.stackedWidget.widget(2)
        # self.video_interface = DesignerWidgetWrapper(self.video_page, self)

    def initLayout(self):
        """初始化主布局，排列导航栏和内容区"""
        self.hBoxLayout.setSpacing(0)  # 组件间无间距
        # 顶部留48px空间给标题栏
        self.hBoxLayout.setContentsMargins(0, 48, 0, 0)
        # 添加导航栏到左侧
        self.hBoxLayout.addWidget(self.navigationBar)
        # 添加内容区到右侧
        self.hBoxLayout.addWidget(self.stackWidget)
        # 内容区占满剩余空间
        self.hBoxLayout.setStretchFactor(self.stackWidget, 1)

    def initNavigation(self):
        """
        初始化导航栏，将界面与导航项关联

        每个导航项包含：
        - 对应的界面组件
        - 显示图标
        - 显示文本
        - 位置（顶部/底部）
        """
        # 添加主页（使用Designer的第一个页面）
        self.addSubInterface(
            self.home_interface,  # 对应的界面
            FIF.HOME,  # 图标
            '主页',  # 显示文本
            selectedIcon=FIF.HOME_FILL  # 选中状态的图标
        )

        # 添加应用页（使用Designer的第二个页面）
        self.addSubInterface(
            self.app_interface,  # 对应的界面
            FIF.APPLICATION,  # 图标
            '应用'  # 显示文本
        )

        # 可以添加更多界面（示例）
        # self.addSubInterface(
        #     self.video_interface,
        #     FIF.VIDEO,
        #     '视频'
        # )

        # 添加底部导航项：库
        # 创建一个空界面作为示例
        self.library_interface = QWidget(self)
        self.library_interface.setObjectName('library-interface')
        self.addSubInterface(
            self.library_interface,  # 对应的界面
            FIF.BOOK_SHELF,  # 图标
            '库',  # 显示文本
            NavigationItemPosition.BOTTOM,  # 位置：底部
            FIF.LIBRARY_FILL  # 选中状态的图标
        )

        # 添加帮助按钮（不可选中，点击弹窗）
        self.navigationBar.addItem(
            routeKey='Help',  # 路由键（唯一标识）
            icon=FIF.HELP,  # 图标
            text='帮助',  # 显示文本
            onClick=self.showMessageBox,  # 点击事件
            selectable=False,  # 不可选中
            position=NavigationItemPosition.BOTTOM  # 位置：底部
        )

        # 绑定界面切换信号，同步导航栏选中状态
        self.stackWidget.currentChanged.connect(self.onCurrentInterfaceChanged)

        # 默认选中第一个界面（主页）
        self.navigationBar.setCurrentItem(self.home_interface.objectName())

    def initWindow(self):
        """初始化窗口基本设置"""
        # 设置窗口初始大小
        self.resize(900, 700)

        # 设置窗口图标（容错处理）
        try:
            self.setWindowIcon(QIcon(':/qfluentwidgets/images/logo.png'))
        except:
            self.setWindowIcon(QIcon())  # 无图标时使用默认图标

        # 设置窗口标题
        self.setWindowTitle('Fluent窗口 + QT Designer')

        # 允许标题栏使用样式表
        self.titleBar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        # 窗口居中显示
        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

        # 加载QSS样式表
        self.setQss()

    def addSubInterface(self, interface, icon, text: str,
                        position=NavigationItemPosition.TOP, selectedIcon=None):
        """
        将界面添加到导航系统

        参数:
            interface: 界面组件
            icon: 未选中状态的图标
            text: 显示文本
            position: 导航项位置（顶部/底部）
            selectedIcon: 选中状态的图标
        """
        # 将界面添加到堆栈窗口
        self.stackWidget.addWidget(interface)

        # 向导航栏添加项，并关联点击事件
        self.navigationBar.addItem(
            routeKey=interface.objectName(),  # 用界面的唯一标识作为路由键
            icon=icon,  # 图标
            text=text,  # 显示文本
            onClick=lambda: self.switchTo(interface),  # 点击时切换到该界面
            selectedIcon=selectedIcon,  # 选中状态的图标
            position=position  # 位置
        )

    def setQss(self):
        """加载QSS样式表，设置界面风格"""
        # 根据当前主题（亮色/暗色）加载对应的样式
        color = 'dark' if isDarkTheme() else 'light'
        try:
            # 尝试加载样式文件
            with open(f'resource/{color}/demo.qss', encoding='utf-8') as f:
                self.setStyleSheet(f.read())
        except:
            # 没有样式文件时不设置（不影响功能）
            pass

    def switchTo(self, widget):
        """切换到指定界面"""
        self.stackWidget.setCurrentWidget(widget)

    def onCurrentInterfaceChanged(self, index):
        """当界面切换时，更新导航栏的选中状态"""
        widget = self.stackWidget.widget(index)
        self.navigationBar.setCurrentItem(widget.objectName())

    def showMessageBox(self):
        """显示帮助对话框"""
        w = MessageBox(
            '支持作者🥰',
            '个人开发不易，如果这个项目帮助到了您，可以考虑请作者喝一瓶快乐水🥤。',
            self
        )
        w.yesButton.setText('来啦老弟')
        w.cancelButton.setText('下次一定')

        # 如果点击了"来啦老弟"，打开支持链接
        if w.exec():
            QDesktopServices.openUrl(QUrl("https://afdian.net/a/zhiyiYo"))


if __name__ == '__main__':
    # 程序入口
    app = QApplication(sys.argv)  # 创建应用实例
    w = Window()  # 创建主窗口
    w.show()  # 显示窗口
    sys.exit(app.exec())  # 启动事件循环
