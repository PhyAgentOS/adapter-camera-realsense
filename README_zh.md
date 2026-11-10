[English](README.md) | 中文

# forge-devices-realsense-camera

Intel RealSense 深度相机的 Python 采集包与 Dora 节点，主要面向 Linux 上的 D400
系列。项目支持 Color、Depth、左右 Infrared、可选 Forge PointCloud v1、设备枚举、快照和
PyInstaller 单文件发布。

- 版本：`2.0.0`
- 许可证：Apache-2.0
- 公共仓库：<https://github.com/Forgelab-Robotics/adapter-camera-realsense>
- 默认分支：`master`

## 支持范围

- Linux + USB 3（推荐）
- Python 3.11 和 3.12
- Color：`forge_msgs.Image(rgb8)` 或 `CompressedImage(jpeg)`
- Depth：`forge_msgs.Image(32FC1)`，float32，单位米，零值表示无效深度
- PointCloud：可选 Forge PointCloud v1 organized XYZ/XYZRGB 输出，默认关闭
- 左右 IR：`forge_msgs.Image(mono8)` 或 `Image(16UC1)`
- RealSense Python SDK：`pyrealsense2>=2.58.2,<3`
- 发布二进制：Linux x86_64，glibc 2.39 或更高

## 源码开发环境

安装 `uv` 以及系统的 libusb/libudev 运行时，然后使用锁文件创建环境：

```bash
uv sync --frozen
uv run python scripts/check_environment.py
uv run pytest tests -q
```

从公开 PyPI 安装的 `pyrealsense2` wheel 通常已经携带它所需的 librealsense 原生库，
因此运行 Python 包或由该 wheel 构建的单文件程序时，不要求另外安装系统
`librealsense2`。目标机仍然需要正常的 USB 内核支持、libusb/libudev 运行时以及允许
当前用户访问设备的 udev 规则和权限。

源码部署需要安装本项目提供的受限 USB 权限规则时，管理员应先审阅脚本，再执行：

```bash
sudo bash scripts/install_permissions.sh
```

该脚本不会联网、不会调用包管理器，也不会安装系统 librealsense；它只校验并原子安装
仓库内固定的 udev 规则、配置 `video` 用户组并重新加载规则。若需要
`realsense-viewer`、`rs-enumerate-devices` 等官方诊断工具，请按照 librealsense 官方文档
单独安装。执行权限脚本后重新插拔设备，并按提示重新登录。

## 发布二进制的首次初始化

GitHub Release 提供 Linux x86_64、glibc 2.39 基线的单文件归档。归档中只包含
`realsense_camera`；该标注表示发布候选在 glibc 2.39 构建机和实机上验证，不声明兼容
更旧的 glibc。安装后二进制部署使用 `init-device`，而不是从源码目录
运行管理员脚本：

```bash
sudo install -o root -g root -m 0755 realsense_camera /usr/local/bin/realsense_camera
realsense_camera init-device
```

`init-device` 是发布二进制必须提供的部署接口：检查 libusb/libudev、udev 规则和当前
用户的设备访问权限，并在需要管理员操作时给出明确提示。它不替代发行版的 USB/udev
运行时安装。重新加载规则后通常需要重新插拔相机；用户组发生变化时还需要重新登录。

源码入口和发布二进制入口应明确区分：源码 checkout 使用经过审阅的
`scripts/install_permissions.sh`；已安装的发布二进制使用 `init-device`。CI 会拒绝缺少
`init-device`、`--version` 或 `licenses` 发布接口的候选二进制。

## 基础命令

```bash
# CLI 帮助与版本
uv run realsense_camera --help
realsense_camera --version

# 设备枚举
uv run python scripts/list_devices.py
uv run realsense_camera list-devices --json
uv run python examples/python_list_devices/run_list_devices.py

# 单帧采集
uv run realsense_camera snapshot \
  --config config/sensor.example.yaml \
  --all-streams \
  --output sample_output/capture.jpg

# Dora 节点（无子命令时进入节点模式）
uv run realsense_camera --config config/sensor.example.yaml
```

彩色图保存为 JPEG，红外图保存为 PNG，深度保存为 float32 米制 NPY。

## Dora example

```bash
cd examples/dora_sensor_stream
dora build dataflow.yaml --uv
dora run dataflow.yaml --uv
```

链路为 `realsense_camera -> test_sink`。sink 对 `point_cloud` 使用 `PointCloudView`，
对图像使用 `Image`/`CompressedImage`，并打印点数、稠密标志、RGB 状态或图像尺寸与编码。
配置 30 FPS 时，dataflow tick 通常设置为 `millis/33`。

## 配置

完整字段和注释位于 `config/sensor.example.yaml`。主要字段包括：

- `device_serial` / `device_index`：设备选择，优先使用 serial
- `connect_delay_ms`、`init_timeout_sec`、`prewarm_frames`：启动行为
- `align_to`：`disable` 或 `color`
- `output_*`：稳定的 Dora topic；点云 topic 默认为 `point_cloud`
- `point_cloud`：Forge PointCloud v1 开关、RGB 着色和可选坐标系标识
- `color.data_flow`：开关、尺寸、FPS、SDK format 和 JPEG 质量
- `depth` / `stereo_module`：Depth/IR profile、控制项、有效范围和滤波
- `min_mm` / `max_mm`：配置阈值使用毫米；公共 Depth 输出始终使用米

profile、设备、对齐、控制项和滤波通常需要重启采集会话后生效；当前不支持运行时动态
改参。

## 输出语义

| topic | 消息 | 编码/单位 |
| --- | --- | --- |
| `image/color` | `Image` 或 `CompressedImage` | `rgb8` 或 JPEG |
| `image/depth` | `Image` | `32FC1`，米 |
| `image/ir_left` | `Image` | `mono8` 或 `16UC1` |
| `image/ir_right` | `Image` | `mono8` 或 `16UC1` |
| `point_cloud` | Forge `PointCloud` v1 | organized float32 XYZ（米）及可选 uint8 RGB |

点云输出默认关闭；默认 topic 与配置契约如下：

```yaml
output_point_cloud: point_cloud
point_cloud:
  enabled: false
  colorize: true
  frame_id: null
```

启用 `point_cloud.enabled` 必须同时启用 Depth；`colorize: true` 还必须启用 Color。关闭
Color 进行 XYZ-only 采集时还需设置 `align_to: disable`。点云按 Depth 图像的行优先网格
组织，XYZ 均为 float32 米制坐标；无效槽位的 X、Y、Z 全部为
NaN。着色时 R/G/B 数组为 uint8，无法映射到彩色图的 RGB 为黑色；不着色时三个 RGB
数组为空。`align_to: color` 表示 XYZ 位于 Color optical frame，`align_to: disable` 表示
XYZ 位于 Depth optical frame。软件 mirror/flip/rotate 只重排 organized 槽位，不会变换
XYZ 坐标向量。

消费端 API 为 `PointCloudView`，例如
`PointCloudView.from_arrow(event["value"])`。本机 NumPy/PyArrow 路径可保持低拷贝，
但这不表示 Dora 传输链路端到端零拷贝；640×480 XYZRGB 约为 4.4 MiB/帧。

Dora 图像与点云输出会尽力附加用户 metadata `capture_timestamp_ns`。它是采集后端取得该
FrameSet 时记录的 Unix epoch 纳秒时间；同一 FrameSet 的各路输出共享该值，缓存帧重复
返回时不会重新生成。该字段是可选的最佳估计，不替代 Dora 管理的消息时间戳。
`point_cloud.frame_id` 非 `null` 时，点云还会附加可选用户 metadata `frame_id`。SDK 帧
时间戳仅用于节点日志。Depth 对齐 Color 时使用 Color 坐标系，IR 保持各自原生坐标系。

## 可选发布可观测性

仅当节点启动时环境变量 **`FORGE_OBSERVABILITY=1`** 才启用；未设置、`0`、`true` 或其他
值均关闭。默认路径不采样可观测时钟，发送调用及 `capture_timestamp_ns`/`frame_id`
metadata 与 1.x 行为兼容。

启用时，每个实际输出都是独立的新 origin。节点在 payload 构建完成后调用 Forge Common
2.1 的公共 `Observer.publish(..., new_origin=True, ...)`，由该 API 在每个 Dora
`send_output` 边界生成 `forge_publish_time_ns` 和 `forge_origin_time_ns`。origin ID 稳定且按
output 区分，例如 `realsense-camera/image/color` 与 `realsense-camera/image/depth`；不会继承
Dora `tick` origin。同一 FrameSet 的多路输出通过共同保留的业务 metadata
`capture_timestamp_ns` 关联，而不是共享 Forge origin。

每个 output 只发送一次。发送失败仍按原路径传播（PointCloud 继续按既有语义隔离并告警），
不重试也不替换异常。时钟、指标 sink 或指标日志异常只会降级为不带观测字段的业务发送，
不会阻断图像/点云。进程内指标使用 `BoundedMetricsSink` 限制 series 数量，每 5 秒记录并
reset 一次 JSON 聚合日志；不保留逐消息 origin、图像内容或高基数 ID。关闭时会尽力执行
一次 final flush，但该 flush 是 best-effort：进程被强制终止、超时或日志后端失败时不保证
最终区间可见。

```bash
FORGE_OBSERVABILITY=1 uv run realsense_camera --config config/sensor.example.yaml
```

跨机器比较 publish/receive 延迟前应确保机器时钟同步。

## 构建与许可证

```bash
bash scripts/build_pyinstaller.sh
dist/realsense_camera --version
dist/realsense_camera licenses
```

构建产物为 `dist/realsense_camera`。2.0.0 发布归档名为
`realsense_camera-v2.0.0-linux-x86_64-glibc2.39.tar.gz`。glibc 2.39 是当前选定的发布主机
基线；最终兼容性必须以当次完整 payload 的 ELF 审计为准。审计和发布流程见
`RELEASING.md`。

项目及第三方许可证必须嵌入单文件程序，并可通过 `realsense_camera licenses` 离线查看。
仓库中的 `LICENSE` 始终提供项目 Apache-2.0 文本。构建机和目标机必须使用兼容架构和
glibc；即使 librealsense 已由 `pyrealsense2` wheel 一并打包，目标机仍需要 libusb、
libudev、正确的 udev 权限和相机硬件。

## 无硬件验证

```bash
uv lock --check
uv run --frozen ruff check src tests scripts examples
uv run --frozen pytest tests -q
uv run --frozen python -m compileall -q src scripts examples tests
uv build
```

单元测试不要求连接相机。`scripts/check_environment.py` 不枚举或打开设备。发布前仍应在
目标硬件上验证设备发现、Color/Depth/IR、对齐、快照、关闭与重新打开。

## 常见问题

- `No module named pyrealsense2`：执行 `uv sync --frozen`，并确认 Python/平台有兼容 wheel。
- 无设备或权限错误：源码部署审阅并运行权限脚本；二进制部署运行
  `realsense_camera init-device`，然后重新插拔并按提示重新登录。
- `Device or resource busy` / 首帧超时：结束残留采集进程，重新插拔后再试。
- profile resolve 失败：先在 `realsense-viewer` 验证分辨率、FPS 和 format 组合。
- 丢帧或初始化超时：确认 USB 3 带宽，减少同时启用的流或降低 profile。
- Dora 无输出：确认 tick 与 FPS 匹配，并检查 dataflow 中的 topic。

## 数据与隐私

本项目默认不提供遥测，也不会自行上传相机数据。Color、Depth 和 IR 帧会发送到当前
Dora dataflow 配置的接收方；部署者负责确认 Dora/Zenoh 的网络边界、身份认证和访问
控制。`snapshot` 会把图像写入调用者指定的位置；设备枚举、诊断输出和日志可能包含设备
序列号、固件版本和 USB 信息。

相机图像、红外图、深度图和设备序列号都应按敏感数据处理。采集包含人员、屏幕、文档、
位置或私人场所的数据前，应获得适用授权，并制定保留、访问和删除策略。不要把真实场景
图像、设备录包、序列号、个人绝对路径、私有 SDK、内部 URL、凭据或密钥提交到仓库。


## Forge 2 / Dora 1 迁移

目标版本：`2.0.0`，当前为待验收改动。首轮验证组合使用 Dora 1.0.1、Forge Msgs 2.0.0、Common 2.1.0；依赖与构建工具以提交的锁文件为准。原有消息规范继续使用 `forge_msgs.v1`。

本轮要求：检查所有示例最终 YAML，使用 `dora validate <dataflow.yaml>` 验证，并实际执行消息往返。相机取流、资源释放和异常退出须分别验收；高吞吐图像链预热后连续测试至少 4 小时，覆盖慢消费者、扇出、退出与重启，记录实际内存占用。无硬件单测不能替代设备验收。

最终发布归档须先在声明支持的平台完成验收，记录源码与归档、可执行文件校验值；通过后发布同一份包，重建后重新验收。Linux 发布包仍需 Linux 验证，其他平台的开发测试不代表其已通过。

图像消费示例新增 `min_frames` 与 `expected_inputs` 配置；无帧、坏帧、缺少必需流或 Dora 错误均判失败。
