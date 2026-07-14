# 硬件基线

- 验证日期：2026-07-14
- 设备：Intel RealSense D435I（USB ID `8086:0b3a`，Product Line D400）
- 唯一识别：运行时用 `list-devices` / `rs-enumerate-devices` 读取；示例配置不固化序列号
- 连接：USB 3.2
- 固件：`5.15.1.55`（`rs-enumerate-devices` / `list-devices` 一致）
- SDK：`pyrealsense2 2.58.2`（Python 3.12）；本机系统包另有
  `librealsense2 2.57.6`（工具链），节点以 venv 内 pyrealsense2 为准
- 系统：Linux 6.17.0-35-generic x86_64；需 RealSense udev 规则
- 官方工具：`rs-enumerate-devices`、`realsense-viewer` 可用
- 数据通道：Color、Depth、Infrared 1/2
- 实测参数：四路 640×480@30；Color `rgb8`，Depth `z16→32FC1` 米，IR `y8`
- 输出：Color `Image(rgb8)`；Depth `Image(32FC1)` 米；IR `Image(mono8)`
- 实测样本：Color `(480, 640, 3) uint8`；Depth `(480, 640) float32`，
  有效像素约 96%，中位数约 0.29 m（近距离桌面场景，非标定结论）
- Dora 短测：`examples/dora_sensor_stream` 约 17–20 s，三路（右 IR 关闭）
  均到约 660 帧，约 30fps；编码 `rgb8` / `32FC1` / `mono8`
- 恢复：部分 stop/start 会出现首帧超时或 `errno=16`；节点会
  `hardware_reset` 后自动重试一次。裸 `usbreset` 可能把设备留在坏状态，
  优先用 SDK `hardware_reset`

已知风险：USB 带宽、固件/profile 差异、Dora tick 与相机 FPS 不一致；
快速连续 reopen 在本机 D435I 上不稳定，依赖硬件复位兜底。长稳压测与绝对
深度精度未覆盖。
