# Dora 传感器流示例

此示例由 RealSense 节点和测试消费节点组成。测试 sink 按 topic 使用
`forge_msgs.PointCloudView` 解码 Forge PointCloud v1，并继续支持
`forge_msgs.Image` 与 `forge_msgs.CompressedImage`。它会周期打印点云点数、
`is_dense`、RGB 状态，或图像尺寸与编码，以及本机接收时间。

```bash
cd examples/dora_sensor_stream
dora build dataflow.yaml --uv
dora run dataflow.yaml --uv
```

`dataflow.yaml` 声明并将 `point_cloud` 从 RealSense 节点路由到测试 sink。全局功能默认
关闭，但此硬件验证示例在 `sensor_node.yaml` 中启用点云和 RGB 着色，因此 Depth 与
Color 必须同时保持启用。

默认 tick 为 33 ms，对应 30 FPS。修改 `sensor_node.yaml` 的 FPS 时，应同步修改
`dataflow.yaml` 的 tick。运行会访问相机；无硬件环境不要执行。

深度 topic `image/depth` 固定为 `Image`，编码 `32FC1`，像素单位为米；0 表示无效深度。
点云 topic `point_cloud` 为 organized float32 XYZ 米制网格，并带 uint8 RGB；默认
640×480 XYZRGB 约为 4.4 MiB/帧。本机 `PointCloudView` 的 NumPy/PyArrow 视图为低拷贝，
不代表 Dora 链路端到端零拷贝。点云与同一 FrameSet 图像共享可选
`capture_timestamp_ns` metadata；设置非 null `point_cloud.frame_id` 可附加可选
`frame_id` metadata。
