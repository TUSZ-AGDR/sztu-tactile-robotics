# 整条轨迹转换为 HDF5 / Entire-recording HDF5 conversion

完整的安装、ZIP 导入、转换、raw 诊断和标定后面积 / 压力分析，请阅读：

- [中文 README](README.md)
- [English README](README.en.md)

在 `lab3/tactile_analysis` 目录，激活已安装 `[cli]` 依赖的 Python 环境后：

```bash
python examples/convert_recording_to_hdf5.py \
  ./teleop_20261021T090120_798e4203.zip \
  analysis_out/real_recording.h5
```

Input may also be a directory containing `manifest.json`. All manifest streams, original tactile dtypes, validity fields, independent timestamps, and event text are retained. Use `--overwrite` only to intentionally replace an existing HDF5 file after successful conversion.

转换为 HDF5 不代表获得有效点验证、力标定、接触面积或真实压力。当前 all-false mask 数据只适合显式 raw 诊断。详细条件、命令和可运行的模拟压力示例见上述 README。
