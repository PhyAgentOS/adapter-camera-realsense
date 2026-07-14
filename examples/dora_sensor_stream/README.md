# Dora 传感器流示例

此示例由 RealSense 节点和测试消费节点组成。测试 sink 同时支持
`forge_msgs.Image` 与 `forge_msgs.CompressedImage`，并周期打印 topic、计数、
尺寸、编码和本机接收时间。

```bash
cd examples/dora_sensor_stream
dora build dataflow.yaml --uv
dora run dataflow.yaml --uv
```

默认 tick 为 33 ms，对应 30 FPS。修改 `sensor_node.yaml` 的 FPS 时，应同步修改
`dataflow.yaml` 的 tick。运行会访问相机；无硬件环境不要执行。

深度 topic `image/depth` 固定为 `Image`，编码 `32FC1`，像素单位为米；0 表示无效深度。
