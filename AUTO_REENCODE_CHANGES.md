# 自动视频重编码功能 - 变更摘要

## 📝 变更概述

实现并集成了自动视频重编码功能，支持单机和服务器/客户端分布式系统。

## 🆕 新增文件

1. **`src/robocoin_dataset/format_converter/utils/video_reencoder.py`**
   - VideoReencoder工具类
   - 负责调用ffmpeg进行视频重编码

2. **`scripts/test_galaxea_auto_reencode.py`**
   - Galaxea数据集测试脚本
   - 验证自动重编码功能

3. **`docs/AUTO_VIDEO_REENCODE.md`**
   - 功能详细文档
   - 使用方法和最佳实践

4. **`docs/AUTO_REENCODE_INTEGRATION.md`**
   - 集成技术文档
   - 完整的实现说明

## 🔄 修改文件

### 核心转换器

1. **`src/robocoin_dataset/format_converter/tolerobot/lazy_video_reader.py`**
   ```python
   # 新增参数
   def __init__(self, ..., auto_reencode: bool = False)
   
   # 新增方法
   def _try_reencode(self) -> bool
   
   # 修改方法
   def _ensure_opened(self)  # 支持自动重编码
   def __getitem__(self, frame_idx: int)  # 支持帧读取失败时重编码
   ```

2. **`src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py`**
   ```python
   # LerobotFormatConverterFactory
   @staticmethod
   def create_converter(..., auto_reencode: bool = False)
   ```

3. **`src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_mp4.py`**
   ```python
   def __init__(self, ..., auto_reencode: bool = False)
   # 传递给 LazyVideoReader(auto_reencode=self._auto_reencode)
   ```

4. **`src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_mp4_json.py`**
   ```python
   def __init__(self, ..., auto_reencode: bool = False)
   # 传递给 LazyVideoReader(auto_reencode=self._auto_reencode)
   ```

### 单机转换器

5. **`scripts/format_converters/tolerobot/convert2lerobot.py`**
   ```python
   # 新增参数
   def convert2lerobot(..., auto_reencode: bool = False)
   
   # 新增命令行参数
   argparser.add_argument("--auto-reencode", action="store_true")
   ```

### 服务器/客户端系统

6. **`src/robocoin_dataset/format_converter/tolerobot/constant.py`**
   ```python
   # 新增常量
   AUTO_REENCODE = "auto_reencode"
   ```

7. **`scripts/format_converters/tolerobot/server.py`**
   ```python
   # 新增命令行参数
   argparser.add_argument("--auto-reencode", action="store_true")
   
   # 传递给 LeFormatConverterTaskServer
   server = LeFormatConverterTaskServer(..., auto_reencode=args.auto_reencode)
   ```

8. **`src/robocoin_dataset/format_converter/tolerobot/server.py`**
   ```python
   # 新增参数
   def __init__(self, ..., auto_reencode: bool = False)
   
   # 新增导入
   from ...constant import AUTO_REENCODE
   
   # 在任务内容中添加
   return {
       ...,
       AUTO_REENCODE: self.auto_reencode,
   }
   ```

9. **`src/robocoin_dataset/format_converter/tolerobot/client.py`**
   ```python
   # 新增导入
   from ...constant import AUTO_REENCODE
   
   # 提取任务参数
   auto_reencode = task_content.get(AUTO_REENCODE, False)
   
   # 传递给 converter
   converter = LerobotFormatConverterFactory.create_converter(
       ...,
       auto_reencode=auto_reencode,
   )
   ```

## 🎯 支持的Converter

| Converter | 状态 | 说明 |
|-----------|------|------|
| LerobotFormatConverterH5Mp4 | ✅ 已支持 | H5+MP4格式 |
| LerobotFormatConverterMp4Json | ✅ 已支持 | MP4+JSON格式 |
| LerobotFormatConverterLejuWaibu | ⚠️ 未支持 | 使用cv2.VideoCapture |

## 📊 测试覆盖

- ✅ Galaxea R1 Lite数据集（H5+MP4格式）
  - 3个AV1编码视频
  - 100%成功重编码
  - 100%转换成功率

## 🚀 使用示例

### 单机模式
```bash
python scripts/format_converters/tolerobot/convert2lerobot.py \
  --dataset_path data/galaxea_r1_lite:h5_mp4_version \
  --output_path outputs/galaxea_output \
  --device_model galaxea_r1_lite \
  --device_model_version h5_mp4_version \
  --factory_config_path scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
  --repo_id test/galaxea \
  --log_dir outputs/conversion_logs \
  --auto-reencode  # ← 新增参数
```

### 服务器/客户端模式
```bash
# Server
python scripts/format_converters/tolerobot/server.py \
  --db-file=db/datasets.db \
  --host=0.0.0.0 \
  --port=8765 \
  --converter-factory-config-path=scripts/format_converters/tolerobot/configs/converter_factory_config.yaml \
  --log-path=/path/to/logs \
  --convert-root-path=/path/to/output \
  --auto-reencode  # ← 新增参数

# Client（无需额外参数）
python scripts/format_converters/tolerobot/single_client.py \
  --host=127.0.0.1 \
  --port=8765
```

## ⚙️ 依赖

**必需**：
- ffmpeg - 用于视频重编码

**安装**：
```bash
# Linux
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

## 📝 配置选项

### VideoReencoder
```python
VideoReencoder(
    temp_dir=Path("/tmp/robocoin_reencoded"),  # 临时目录
    codec="libx264",                            # 编码器
    crf=23,                                     # 压缩质量(0-51)
    logger=logger                               # 日志记录器
)
```

### LazyVideoReader
```python
LazyVideoReader(
    video_path=video_path,
    logger=logger,
    convert_to_rgb=True,
    auto_reencode=True  # ← 启用自动重编码
)
```

## 🐛 已知问题

1. **LerobotFormatConverterLejuWaibu 未集成**
   - 原因：直接使用cv2.VideoCapture而非LazyVideoReader
   - 影响：Leju Waibu格式数据集无法使用自动重编码
   - 解决方案：未来重构为使用LazyVideoReader

## 🔮 未来改进

1. **短期**
   - [ ] Leju Waibu格式支持
   - [ ] 编码参数配置化

2. **长期**
   - [ ] 重编码进度报告
   - [ ] 批量预处理工具
   - [ ] 多种编码器支持

## ✅ 验收标准

- [x] VideoReencoder工具类实现
- [x] LazyVideoReader集成
- [x] H5+MP4 Converter支持
- [x] MP4+JSON Converter支持
- [x] Factory模式支持
- [x] 单机转换器支持
- [x] 服务器端支持
- [x] 客户端支持
- [x] 常量定义
- [x] Galaxea测试通过
- [x] 文档完善
- [x] 向后兼容性验证

## 📚 相关文档

1. **功能文档**：`docs/AUTO_VIDEO_REENCODE.md`
2. **集成文档**：`docs/AUTO_REENCODE_INTEGRATION.md`
3. **测试脚本**：`scripts/test_galaxea_auto_reencode.py`
4. **本摘要**：`AUTO_REENCODE_CHANGES.md`

## 🎉 总结

自动视频重编码功能已完整集成，支持：
- ✅ 单机转换模式
- ✅ 服务器/客户端分布式模式
- ✅ H5+MP4和MP4+JSON格式
- ✅ 自动检测和修复AV1编码问题
- ✅ 100%向后兼容

核心价值：将视频编码问题从"必须提前处理"变为"运行时自动修复"。

