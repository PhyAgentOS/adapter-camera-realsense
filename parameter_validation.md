# 参数验证

## 无硬件验证

- `config/sensor.example.yaml` 可被 `RealSenseConfig` 加载。
- width、height、fps 必须大于 0。
- JPEG 质量范围为 1–100。
- rotate 仅接受 0、90、180、270。
- `max_mm` 必须大于 `min_mm`。
- `align_to` 仅接受 `disable` 或 `color`。
- Depth 消息为 `32FC1` 米；snapshot 全流落盘使用 `float32` `.npy`。
- `stereo_module` 控件只写入 Depth 传感器路径，避免 IR 路径重复写 option。
- 采集等待可被 `close()` 打断；初始化失败（首帧超时 / busy）会
  `hardware_reset` 后重试一次。
- 单测：`uv run pytest`（12 passed）。

## 2026-07-14 实机验证

- 设备枚举成功：D435I、USB 3.2、固件 `5.15.1.55`（不记录序列号）。
- 默认配置四路快照成功：Color/Depth/IR 均为 640×480；Depth 米制有效约 96%。
- `align_to=disable/color` 均启动并产帧；当前 Color/Depth 同为 640×480 时
  Depth 尺寸均为 480×640（对齐不改变分辨率）。
- `min_mm=500` / `max_mm=1500`：近距离场景下有效深度被裁成全 0，软件裁剪生效。
- Emitter 关闭（`emitter_enabled=0`, `laser_power=0`）与恢复激光
  （`1` / `150`）读回一致；关闭后 IR 均值下降。
- Color `rotate=90` + `mirror=true`：输出尺寸变为 `(640, 480, 3)`。
- 连续采集约 5 s：时间戳持续更新（忙轮询下约 22 unique fps；Dora tick
  驱动约 30fps）。
- Dora 标准链路短测约 17–20 s：Color/Depth/IR_left 稳定约 30fps；
  `sensor_node.yaml` 关闭右 IR，已与 `dataflow.yaml` 对齐。
- STOP/`timeout` 结束后设备可重新枚举；占用残留时需结束节点进程，必要时
  `hardware_reset` 后重开成功。

动态参数更新当前未实现；修改 YAML 后需重启节点。

## 尚未完成

- 未做数十分钟长稳压测。
- 未覆盖全部可选分辨率、帧率、滤波与 advanced controls 组合。
- 未使用已知距离标定物验证绝对深度精度。
- Color/Depth 不同分辨率下的 `align_to=color` 尺寸变化未单独复测。
