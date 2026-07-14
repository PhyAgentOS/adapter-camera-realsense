# forge-devices-realsense-camera

Intel RealSense 深度相机接入，主要面向 D400 系列。项目提供独立 Python 采集、
Dora 节点、设备与环境检查、权限安装和 PyInstaller 打包。

## 支持范围

- 连接：USB 3 推荐，Linux
- 数据：RGB、Depth、左右 Infrared
- 官方验证工具：`realsense-viewer`、`rs-enumerate-devices`
- 参考环境：Python 3.12；SDK/依赖版本以 `uv.lock` 为准
- 硬件基线：见 [hardware_baseline.md](hardware_baseline.md)

## 安装

```bash
uv sync
uv run python scripts/check_environment.py
```

安装 librealsense、工具和 udev 规则需要 root：

```bash
sudo bash scripts/install_permissions.sh
```

脚本适用于带 `apt-get` 的 Debian/Ubuntu。安装后重新插拔设备。部署环境若通过
系统包以外的方式提供原生库，应确保动态链接器能找到 librealsense；必要时配置
`LD_LIBRARY_PATH`。

## 设备列举与 Python 采集

以下命令会访问硬件：

```bash
uv run python scripts/list_devices.py
uv run realsense_camera list-devices --json
uv run python examples/python_list_devices/run_list_devices.py

uv run python examples/python_capture_sample/run_capture_sample.py \
  --config config/sensor.example.yaml --all-streams
```

默认配置位于 `config/sensor.example.yaml`。无参数运行 CLI 时进入 Dora 节点模式：

```bash
uv run realsense_camera --config config/sensor.example.yaml
```

snapshot 子命令：

```bash
uv run realsense_camera snapshot --config config/sensor.example.yaml \
  --all-streams --output sample_output/capture.jpg
```

彩色图保存为 JPEG，红外图保存为 PNG，深度保存为 float32 米制 NPY。

## Dora example

```bash
cd examples/dora_sensor_stream
dora build dataflow.yaml --uv
dora run dataflow.yaml --uv
```

链路为 `realsense_camera -> test_sink`。sink 解码 `Image`/`CompressedImage` 并打印
计数、尺寸、编码和接收时间。配置 FPS 时同步修改 dataflow tick：
30 FPS 对应 `millis/33`。

## 输出协议

- `image/color`：`forge_msgs.Image` `rgb8`；配置 `jpeg/mjpeg` 时为
  `forge_msgs.CompressedImage` `jpeg`
- `image/depth`：`forge_msgs.Image` `32FC1`，float32，单位米，0 表示无效值
- `image/ir_left`、`image/ir_right`：`Image` `mono8` 或 `16UC1`
- 图像尺寸来自实际采集/对齐结果
- Dora 消息接收时间由下游本机记录；相机帧时间戳目前只用于节点日志，未写入消息头
- depth 对齐 color 时使用 color 坐标系；IR 保持各自原生坐标系

## 配置

关键字段：

- `device_serial` / `device_index`：设备选择
- `connect_delay_ms`、`init_timeout_sec`、`prewarm_frames`：启动行为
- `align_to`：`disable` 或 `color`
- `output_*`：Dora topic
- `color.data_flow`：开关、尺寸、FPS、SDK format、JPEG 质量
- `depth` 或 `stereo_module`：深度/IR profile、控制项、有效范围和滤波
- `min_mm` / `max_mm`：输入配置仍用毫米表达阈值；输出始终为米

完整字段与注释见 `config/sensor.example.yaml`；参数验证见
[parameter_validation.md](parameter_validation.md)。profile、控制项和滤波通常需要
重启采集会话后生效。

## 打包

```bash
bash scripts/build_pyinstaller.sh
dist/realsense_camera --help
```

二进制名称统一为 `realsense_camera`，spec 位于
`scripts/realsense_camera.spec`，默认配置会打入 `config/sensor.example.yaml`。

## 无硬件验证

```bash
uv run pytest -q
uv run python -m compileall -q src scripts examples tests
uv run realsense_camera --help
uv run realsense_camera snapshot --help
uv run python scripts/check_environment.py
```

`check_environment.py` 不枚举或打开设备。实机基线与参数结果见
`hardware_baseline.md`、`parameter_validation.md`。

## 排障

- `No module named pyrealsense2`：执行 `uv sync`
- `Device or resource busy` / 首帧超时：结束残留节点进程；节点会自动
  `hardware_reset` 重试一次。优先用 SDK 复位，避免盲目 `usbreset`
- 无设备/权限错误：运行权限安装脚本，重新插拔后用 `rs-enumerate-devices` 验证
- profile resolve 失败：先在 `realsense-viewer` 验证分辨率、FPS、format 组合
- 丢帧或初始化超时：确认 USB 3 带宽，减少同时启用的流或降低 profile
- Dora 无输出：确认 tick 与 FPS 匹配，并检查 `sensor_node.yaml` topic

## 已知限制

- D435I 短测基线已记录；长稳压测、全 profile 矩阵和绝对深度精度仍待补
- 仅验证过的 D400 配置可作为生产基线，其他型号需重新探测
- 暂不支持运行中动态改参
- `examples/realsense_camera_viewer` 为兼容可视化示例（依赖 PATH 中的
  `image_viewer`）；标准交付链路是 `examples/dora_sensor_stream`
