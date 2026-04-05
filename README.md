# 迅雷去重助手

一款桌面端下载去重工具，通过番号识别已下载内容，避免重复下载。

## 功能特点

- **剪贴板监控** - 自动检测复制的下载链接（magnet/thunder/ed2k）
- **抢先拦截** - 在迅雷读取剪贴板之前拦截链接，阻止重复下载
- **番号解析** - 自动从文件名/链接中提取番号
- **文件索引** - 扫描本地目录建立索引，快速检测重复
- **重复检测** - 显示重复番号及对应文件列表
- **浏览器扩展** - 支持 Chrome/Edge 扩展，网页端拦截
- **WebSocket 服务** - 提供本地 WebSocket 服务供扩展连接

## 截图

![主界面](screenshots/main.png)

## 安装

### 方式一：直接运行 exe

下载 `dist/ThunderDedupe.exe`，双击运行即可。

### 方式二：从源码运行

```bash
# 克隆仓库
git clone https://github.com/yuanchuangith/thunder-dedupe.git
cd thunder-dedupe

# 创建虚拟环境
conda create -n thunder-dedupe python=3.13
conda activate thunder-dedupe

# 安装依赖
pip install PyQt6 websockets pyperclip

# 运行
python src/main.py
```

## 使用方法

### 1. 配置扫描目录

1. 打开应用，切换到「配置」标签页
2. 点击「添加目录」选择要扫描的视频目录
3. 返回主页，点击「扫描目录」建立索引

### 2. 启动监控

1. 在主页点击「启动监控」
2. 复制下载链接时，应用会自动拦截
3. 弹出决策窗口：
   - **放行** - 恢复链接到剪贴板，允许下载
   - **拦截** - 保持剪贴板清空，阻止下载
   - **忽略** - 不做处理

### 3. 浏览器扩展（可选）

1. 打开 Chrome/Edge 浏览器
2. 进入扩展管理页面 `chrome://extensions/`
3. 开启「开发者模式」
4. 点击「加载已解压的扩展程序」
5. 选择 `extension/chrome` 或 `extension/edge` 目录
6. 在扩展设置中配置 WebSocket 端口（默认 9876）

## 目录结构

```
thunder-dedupe/
├── src/                    # 源代码
│   ├── main.py            # 入口文件
│   ├── ui/                # 界面模块
│   │   ├── main_window.py # 主窗口
│   │   ├── home_page.py   # 主页
│   │   ├── config_page.py # 配置页
│   │   ├── file_list_page.py  # 文件列表
│   │   ├── duplicate_page.py  # 重复检测
│   │   └── dialogs/       # 对话框
│   ├── core/              # 核心模块
│   │   ├── av_parser.py   # 番号解析
│   │   ├── directory_scanner.py  # 目录扫描
│   │   ├── index_manager.py  # 索引管理
│   │   └── clipboard_monitor.py  # 剪贴板监控
│   ├── network/           # 网络模块
│   │   └── websocket_server.py  # WebSocket 服务
│   ├── db/                # 数据库模块
│   │   ├── database.py    # 数据库连接
│   │   └── migrations.py  # 数据库迁移
│   └── utils/             # 工具模块
│       ├── config.py      # 配置管理
│       ├── logger.py      # 日志
│       └── single_instance.py  # 单实例检测
├── extension/             # 浏览器扩展
│   ├── chrome/            # Chrome 扩展
│   └── edge/              # Edge 扩展
├── dist/                  # 打包输出
├── build.bat              # 打包脚本
└── build.md               # 打包文档
```

## 配置说明

### 数据存储位置

应用数据存储在用户目录：

```
C:\Users\<用户名>\.thunder-dedupe\
├── thunder_dedupe.db  # 数据库
├── config.json        # 配置文件
└── logs/              # 日志文件
```

### WebSocket 端口

默认端口：`9876`

可在「配置」→「其他设置」中修改，修改后需重启 WS 服务。

## 支持的链接格式

- 磁力链接：`magnet:?xt=urn:btih:...`
- 迅雷链接：`thunder://...`
- 电驴链接：`ed2k://|file|...`
- 种子文件：`.torrent`

## 番号解析规则

支持常见番号格式：

- 标准格式：`ABC-123`
- 无横线：`ABC123`
- 带前缀：`hhd800.com@ABC-123`

可在「规则」页面自定义解析规则。

## 开发

### 环境要求

- Python 3.10+
- PyQt6
- websockets
- pyperclip

### 打包

```bash
# Windows
build.bat

# 或手动执行
pyinstaller --onefile --windowed --name "ThunderDedupe" src/main.py
```

详见 [build.md](build.md)。

## 许可证

MIT License

## 作者

[yuanchuangith](https://github.com/yuanchuangith)