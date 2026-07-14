# Sample output

硬件验收后可在此记录脱敏的输出摘要，不提交大型图像或录包。

期望 Dora sink 输出示例：

```text
topic=image/color count=30 type=Image size=640x480 encoding=rgb8 received_at=...
topic=image/depth count=30 type=Image size=640x480 encoding=32FC1 received_at=...
```

深度数组为 float32 米，0 表示无效深度。Python `--all-streams` 示例将深度保存为
`*_depth_m.npy`，可用 `numpy.load` 读取。
