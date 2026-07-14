# Python 单样本采集

在项目根目录运行：

```bash
uv run python examples/python_capture_sample/run_capture_sample.py \
  --config config/sensor.example.yaml --all-streams
```

彩色图写为 JPEG，深度图写为 float32 米制 NPY，红外图写为 PNG。
