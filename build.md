# 迅雷去重助手 - 打包文档

## 快速打包

双击运行 `build.bat` 即可自动打包，输出文件在 `dist/ThunderDedupe.exe`。

---

## 环境要求

- Python 3.10+ (推荐 3.13)
- PyQt6
- PyInstaller

### 推荐环境

```
D:\Anaconda\envs\checkcode
```

---

## 安装依赖

```bash
# 激活环境
conda activate checkcode

# 安装 PyQt6
pip install PyQt6

# 安装 PyInstaller
pip install pyinstaller
```

---

## 打包命令

### 方式一：使用打包脚本（推荐）

```bash
# Windows 下双击运行
build.bat

# 或在命令行运行
.\build.bat
```

### 方式二：手动命令

```bash
cd e:\pythonProject\checkCode\thunder-dedupe

D:\Anaconda\envs\checkcode\Scripts\pyinstaller.exe \
    --onefile \
    --windowed \
    --name "ThunderDedupe" \
    --distpath "dist" \
    --clean \
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/sqlite3.dll;." \
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/liblzma.dll;." \
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/LIBBZ2.dll;." \
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/libmpdec-4.dll;." \
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/libexpat.dll;." \
    --add-binary "D:/Anaconda/envs/checkcode/Library/bin/ffi.dll;." \
    src/main.py
```

---

## 参数说明

| 参数 | 说明 |
|------|------|
| `--onefile` | 打包成单个 exe 文件 |
| `--windowed` | 不显示控制台窗口 |
| `--name "ThunderDedupe"` | 输出文件名 |
| `--distpath "dist"` | 输出目录 |
| `--clean` | 清理缓存后重新打包 |
| `--add-binary` | 添加 DLL 依赖文件 |

---

## 需要包含的 DLL 文件

以下 DLL 文件位于 `D:\Anaconda\envs\checkcode\Library\bin\` 目录：

| DLL 文件 | 用途 |
|---------|------|
| sqlite3.dll | SQLite 数据库支持 |
| liblzma.dll | LZMA 压缩支持 |
| LIBBZ2.dll | BZ2 压缩支持 |
| libmpdec-4.dll | 高精度数学运算 |
| libexpat.dll | XML 解析 |
| ffi.dll | 外部函数接口 |

---

## 输出文件

```
dist/
└── ThunderDedupe.exe    # 约 40MB
```

---

## 运行测试

```bash
# 直接运行
dist\ThunderDedupe.exe

# 或双击 exe 文件
```

---

## 常见问题

### 1. 打包失败：ModuleNotFoundError

确保安装了所有依赖：
```bash
pip install PyQt6 websockets
```

### 2. 运行失败：DLL load failed

确保包含了所有 DLL 文件，检查 `--add-binary` 参数。

### 3. 打包后体积过大

PyInstaller 会包含整个 Python 环境，正常情况下约 40MB。如果超过 100MB，检查是否误包含了不需要的库。

### 4. 杀毒软件报毒

PyInstaller 打包的 exe 可能被杀毒软件误报，添加白名单即可。

---

## 打包配置文件

如果需要自定义打包配置，可以修改 `build.bat` 文件中的参数。

### 常用自定义选项

```bash
# 添加图标
--icon="path/to/icon.ico"

# 添加版本信息
--version-file="version.txt"

# 排除不需要的模块（减小体积）
--exclude-module matplotlib
--exclude-module numpy
--exclude-module pandas
```

---

## 目录结构

```
thunder-dedupe/
├── src/                    # 源代码
│   ├── main.py            # 入口文件
│   ├── ui/                # 界面模块
│   ├── core/              # 核心模块
│   ├── db/                # 数据库模块
│   ├── network/           # 网络模块
│   └── utils/             # 工具模块
├── extension/              # 浏览器扩展
│   ├── chrome/
│   └── edge/
├── dist/                   # 打包输出目录
│   └── ThunderDedupe.exe
├── build/                  # 构建临时文件
├── build.bat              # 打包脚本
├── build.md               # 本文档
└── build.spec             # PyInstaller 配置文件（自动生成）
```

---

## 发布清单

打包完成后，发布包应包含：

1. `ThunderDedupe.exe` - 主程序
2. `extension/chrome/` - Chrome 扩展（可选）
3. `extension/edge/` - Edge 扩展（可选）

---

## 更新日志

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-04-06 | 1.0.0 | 初始打包配置 |