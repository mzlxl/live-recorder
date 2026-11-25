# 直播录制系统（自用）

定时检查主播主页是否开播，开播后自动进入直播间，通过**系统音**录制直播音频（不抓流，规避风控）。

## 特性

- 任务配置页：主播主页 + 检查频率下拉（5/10/15/20/30/45/60/90/120 分钟）+ 扫描时段（时分、可跨天），启用/停用
- 产物汇总：每个任务对应产物列表，在线试听、下载
- 平台抽象：当前支持抖音，可扩展 B站/快手等
- 系统音录制：macOS=BlackHole / 浏览器内采集，Windows=VB-Cable / WASAPI 回环 / 浏览器内采集，Linux=PulseAudio monitor / 浏览器内采集；纯浏览器自动化，不碰流

## 目录结构

```
live-recorder-system/
├── app/
│   ├── main.py          # FastAPI 入口 + REST API
│   ├── db.py            # SQLite 数据层（任务/产物）
│   ├── scheduler.py     # APScheduler 定时调度
│   ├── executor.py      # 录制执行器（核心流程）
│   ├── stealth.py       # 浏览器指纹隐藏
│   ├── platforms/       # 平台抽象层（douyin）
│   └── recorder/        # 系统音录制层（mac/windows）
├── web/                 # 前端管理页
├── config.py            # 全局配置
├── run.py               # 启动入口
└── storage/             # 运行时数据（db + 音频产物）
```

## 安装

```bash
# 1. Python 3.10+，创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装浏览器
python -m playwright install chromium

# 4. 安装系统音虚拟声卡（二选一，见下）
```

### macOS：BlackHole

```bash
brew install blackhole-2ch
# 重启 Mac 后，在「音频 MIDI 设置」新建「多输出设备」= 内置扬声器 + BlackHole 2ch，
# 把系统输出切到该多输出设备（这样你也能同时听到直播声音）
```

### Windows：声卡（可选）

未安装 VB-Cable 也能录制：系统会自动用 Windows WASAPI 回环采集默认扬声器的系统输出；
若回环不可用则退回浏览器内音频采集。已安装 VB-Audio Virtual Cable 时，把「播放」默认设备设为 CABLE Input 即自动切换为虚拟声卡采集。

macOS/Linux 未配置虚拟声卡时会自动使用浏览器内音频采集，无需额外驱动。
录制优先使用系统 Chrome/Edge（Playwright 自带 Chromium 缺少 H.264/AAC 解码器，直播画面会停在「加载中」）：
Windows 自动探测常见安装路径，macOS 探测 `/Applications`，Linux 通过 `PATH` 探测 `google-chrome`/`chromium` 等。
可用 `RECORDER_BROWSER` 指定浏览器路径或 PATH 中的命令名。

### Linux：PulseAudio/PipeWire（轻量部署，headless 无需显示器）

```bash
# 1. 安装依赖
sudo apt install -y ffmpeg pulseaudio
python -m playwright install --with-deps chromium

# 2. 创建虚拟 sink（虚拟声卡）
pactl load-module module-null-sink sink_name=recording

# 3. 启动（自动 headless 模式）
export PULSE_SOURCE=recording.monitor
python run.py
```

## 启动

```bash
python run.py
# 打开 http://127.0.0.1:8000
```

## 使用

1. 页面「新增任务」：填主播主页（抖音主页形如 `https://www.douyin.com/user/MS4w...`）、检查频率（5~120 分钟下拉）、扫描时段（仅时分，结束早于开始即跨至次日）
2. 系统按频率检查主页是否开播，开播即进入直播间录制，下播自动停止
3. 「产物」区按任务查看录制结果，在线试听/下载

## 自动化验证

```bash
python verify_recording.py            # 两种采集模式：采集 → 转码 → 解码/音量/播放检查
python verify_recording.py --file 路径 # 只验证某个产物能否正常打开播放
```

## 关键配置（config.py / 环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| RECORDER_PORT | 8000 | 服务端口 |
| RECORDER_MAX_DURATION | 43200(12h) | 单次录制时长上限（秒） |
| RECORDER_POLL_INTERVAL | 30 | 下播轮询间隔（秒） |
| RECORDER_HEADLESS | Linux=1 其他=0 | 是否 headless（无头）运行浏览器 |
| RECORDER_FFMPEG | 自动探测 | ffmpeg 路径，PATH 中找不到时手动指定 |
| RECORDER_BROWSER | 自动探测 | 浏览器可执行文件路径或 PATH 中的命令名（系统 Chrome/Edge 优先） |
| VBCABLE_DEVICE | 自动探测 | Windows 采集设备名，如 `CABLE Output (VB-Audio Virtual Cable)`，自动匹配失败时手动指定 |
| BLACKHOLE_DEVICE | none:BlackHole 2ch | macOS 采集设备名（avfoundation 格式） |
| PULSE_SOURCE | recording.monitor | Linux 录制源（PulseAudio monitor） |

## 架构说明（轻量）

单进程架构：`python run.py` 一个 uvicorn 进程同时提供 REST API、前端静态页、定时调度与录制执行，无需前后端分离、无需数据库服务（SQLite 单文件）、无需消息队列。部署仅需 Python + ffmpeg + chromium + 一个虚拟声卡驱动。

## 说明与风险

- 本系统为**自用**录制工具，仅录直播音频，不抓流、不绕过平台防盗链
- 录制他人直播内容仍涉及著作权，请勿传播或商用
- 浏览器自动化仍可能有残余风控风险，已做指纹隐藏 + 低频调度；建议检查频率 ≥10 分钟
