# JavSP 开发与维护指南 (Gemini CLI Edition)

本手册由 Gemini CLI 总结，详尽记录了 JavSP 的系统架构、实现原理，以及在 2026 年网络环境下进行大规模重构与单文件化（v1.8.2）过程中的实战经验。

---

## 1. 项目概览与模块介绍

JavSP 是一个工业级的元数据刮削器，核心目标是将凌乱的影片文件按照多站点聚合的元数据进行标准化整理。

### 核心目录结构
- **`javsp/`**: 源代码根目录。
  - **`web/`**: 爬虫核心。通过 `__init__.py` 中的 `CRAWLER_MAP` 实施静态注册。
  - **`cropper/`**: 封面裁剪引擎（Slimeface）。
  - **`datatype.py`**: 定义 `Movie`, `MovieInfo` 等核心数据模型及文件整理逻辑。
  - **`config.py`**: 基于 Pydantic V2 和 ConfZ 的强类型配置中心。
  - **`func.py`**: 业务逻辑函数（UI、更新检查、版本控制）。
- **`tools/`**: 工程工具链。
  - **`build_exe.py`**: **关键构建脚本**。具备环境自适应能力的 PyInstaller 驱动器。
  - **`version.py`**: 动态版本捕获工具。
- **`unittest/`**: 单元测试体系。包含了具备“自愈能力”的爬虫测试框架。

---

## 2. 实现原理

### 2.1 聚合刮削机制
程序采用多线程并行刮削模式。根据影片 ID（DVDID 或 CID），从配置的抓取器队列中并行获取数据，并根据字段缺失情况进行多站点互补，最终汇聚成一份完整的 `MovieInfo`。

### 2.2 静态注册表架构
为了兼容 PyInstaller 单文件打包，所有爬虫模块必须在 `javsp/web/__init__.py` 中显式导入。这确保了：
1. 打包工具能 100% 静态分析出依赖树。
2. 运行时不再依赖不稳定的 `importlib` 动态加载。

### 2.3 自适应打包技术
单文件版（One-File EXE）在启动时会将资源解压到系统的临时目录 `_MEIPASS`。JavSP 通过 `resource_path` 包装器和 `__main__.py` 中的 Tcl/Tk 环境变量重定向补丁，实现了对复杂环境（如 Conda）下底层运行库的完美自愈加载。

---

## 3. 开发流程与经验总结

### 3.1 爬虫开发军规
- **反爬适配**：针对现代站点的 Next.js (RSC) 或动态加载架构，应优先通过拦截搜索结果页或分析 JSON Payload 获取 CID，而非死磕空壳详情页。
- **编码宽容**：处理 Getchu 等日系站点时，必须强制指定 `euc-jp` 解码，严禁依赖系统默认编码。
- **容错优先**：任何抓取逻辑必须包裹异常处理，严禁因单个字段（如剧照下载）失败而中断全局任务。

### 3.2 CI/CD 稳定化经验
- **弃用 Poetry 锁文件校验**：在 GitHub Actions 等受限环境下，由于 `pyproject.toml` 经常变动，应统一使用 `pip install .` 模式，避开 `poetry.lock` 的严格哈希冲突。
- **自愈式测试**：测试脚本应能智能识别“环境网络导致的 403”与“代码逻辑回归”，并自动将前者标记为 `skip`，确保 CI 状态的真实可靠。

---

## 4. 必坑指南（实战沉淀）

### 🚨 避坑 1：PyInstaller & Conda 的 DLL 地狱
**问题**：在 Conda 环境打包后，`_ssl`, `_ctypes`, `_sqlite3` 等模块常报 `DLL load failed`。
**对策**：在 `tools/build_exe.py` 中实施“暴力采集策略”，扫描 `Library/bin` 目录并将所有核心 DLL 全部强制打入包内。

### 🚨 避坑 2：Tcl/Tk 资源定位消失
**问题**：单文件版启动时提示 `Can't find a usable init.tcl`。
**对策**：
1. 在打包时动态获取 `tkinter.Tcl().eval('info library')` 的真实路径。
2. 在 `__main__.py` 顶部使用递归扫描算法探测 `_MEIPASS` 下的 `tcl_tk` 目录，并动态设置 `TCL_LIBRARY` 环境变量。

### 🚨 避坑 3：Pydantic V2 兼容性
**问题**：代码中直接调用模型对象的 `.values()` 或属性访问在 V2 中会报错。
**对策**：始终先执行 `.model_dump()` 将其转换为字典后再进行遍历操作。

### 🚨 避坑 4：单文件环境下的 exit()
**问题**：打包后使用 `exit()` 会导致 `NameError`。
**对策**：在全工程范围内禁用内置 `exit()`，必须且只能使用 `sys.exit()`。

### 🚨 避坑 5：Windows 控制台的编码陷阱
**问题**：打印 Emoji 或特殊 Unicode 字符会导致 CI 环境下的 `UnicodeEncodeError`。
**对策**：在构建脚本和主程序入口处强制执行 `sys.stdout.reconfigure(encoding='utf-8')` 或移除装饰性非 ASCII 字符。

---

## 5. 维护者后续指引

若需更新版本并发布：
1. 修改 `pyproject.toml` 中的版本号或推送新的 Git Tag。
2. 在本地执行 `python tools/build_exe.py` 进行**实战冒烟测试**（处理真实目录，确认 UI 弹出）。
3. 确认无误后推送 `master` 并刷新标签，GitHub Actions 会自动根据 `build_exe.py` 产出三平台单文件包。

---
**Maintainer**: Au3C2  
**Legacy**: Reconstructed from Yuukiy/JavSP  
**Build Tool**: PyInstaller (Custom Adaptive Logic)
