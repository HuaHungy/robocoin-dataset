# 智平方数据集验证工具 - 快速开始

## 工具位置
```bash
scripts/dataset_statistics/zhipingfang_dataset_validator.py
```

## 快速使用

### 1. 测试运行（推荐）
```bash
# 首先运行 dry-run 模式，不会移动任何文件
python scripts/dataset_statistics/zhipingfang_dataset_validator.py --dry-run
```

### 2. 正式运行
```bash
# 确认测试结果无误后，正式运行
python scripts/dataset_statistics/zhipingfang_dataset_validator.py
```

### 3. 查看报告
```bash
# 报告会自动生成在智平方目录下
cat /mnt/nas/synnas/docker2/外部数据/智平方/validation_report_*.txt
```

## 检测内容

### ✅ 自动检测项目
1. **数据路径完整性**
   - 所有 H5 文件的数据集路径是否一致
   - 采用"少数服从多数"原则识别异常文件

2. **数据非空检测**
   - 确认数据集包含实际数据（不为全零）
   - 采用采样策略提高检测效率

3. **Shape 一致性**
   - 同一路径组下的时间维度是否一致
   - 自动忽略 metadata 等 scalar 数据

4. **版本匹配**
   - 检查 device_model_annotation.yaml 中的版本
   - 当发现多版本数据时发出警告

### 📊 输出结果
- **控制台**: 实时进度和统计信息
- **TXT报告**: 详细的异常文件列表和原因
- **Error目录**: 自动移动异常文件（保留目录结构）

## 检测逻辑

### 数据路径一致性示例
```
场景: 30000 个 H5 文件

多数派 (29500 个文件):
  ✓ action
  ✓ observations/camera/rgb/chest/video
  ✓ observations/camera/rgb/head/video
  ✓ observations/qpos
  ✓ observations/qvel

异常文件 (500 个文件):
  ✗ 缺少: observations/camera/rgb/head/video
  ✗ 多出: observations/extra_sensor/data

处理: 这 500 个文件被移动到 error/ 目录
```

### Shape 一致性示例
```
✓ 正常情况:
  observations/camera/rgb/head/video_index: (477,)    # 477 帧
  observations/camera/rgb/chest/video_index: (477,)   # 同样 477 帧
  observations/qpos: (477, 7)                          # 同样 477 帧
  
✗ 异常情况:
  observations/camera/rgb/head/video_index: (477,)
  observations/camera/rgb/chest/video_index: (360,)   # 不同的帧数！
  
处理: 该文件被标记为异常
```

## 版本警告示例

```
⚠️  检测到 2 种不同的数据结构版本
   多数派占比: 25000/30000 (83.3%)
   
⚠️  建议检查 device_model_annotation.yaml 中的 version 字段
   可能存在版本配置错误的情况
```

当看到此警告时，应该：
1. 检查实际的数据路径差异
2. 确认哪个 version 应该使用
3. 更新 device_model_annotation.yaml 中的 version 字段

## 异常文件处理

### 文件移动规则
```
原始位置:
  /mnt/nas/synnas/docker2/外部数据/智平方/
    30k数采-第一批/task1/episode_0001.h5

移动后:
  /mnt/nas/synnas/docker2/外部数据/智平方/error/
    30k数采-第一批/task1/episode_0001.h5
```

### 恢复异常文件
如果需要恢复被移动的文件：
```bash
# 查看 error 目录内容
ls -R /mnt/nas/synnas/docker2/外部数据/智平方/error/

# 移回特定文件
mv "/mnt/nas/synnas/docker2/外部数据/智平方/error/30k数采-第一批/task1/episode_0001.h5" \
   "/mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批/task1/"
```

## 性能预估

| 文件数量 | 预计时间 | 内存占用 |
|---------|---------|----------|
| 10,000  | 3-5分钟  | < 500MB  |
| 30,000  | 8-12分钟 | < 1GB    |
| 50,000  | 15-20分钟| < 1.5GB  |

*实际时间取决于：
- 文件大小
- 数据集数量
- 磁盘 I/O 速度

## 常见问题

### Q: 为什么我的文件被标记为异常？
A: 检查报告中的"错误原因"部分，通常是以下几种情况：
- 数据集路径与大多数文件不一致
- 同一文件内时间维度不统一
- 文件损坏无法读取

### Q: 能否不移动文件，只生成报告？
A: 使用 `--dry-run` 参数：
```bash
python scripts/dataset_statistics/zhipingfang_dataset_validator.py --dry-run
```

### Q: 如何处理版本警告？
A: 
1. 查看报告中的路径差异详情
2. 与团队确认正确的 version
3. 更新相应的 device_model_annotation.yaml
4. 重新运行验证

### Q: 可以批量处理多个子目录吗？
A: 工具会自动递归查找所有 device_model_annotation.yaml 文件及其周围的 H5 文件。
无需手动分批处理。

## 下一步

验证完成后，可以进行正常的数据转换：

```bash
# 使用转换工具
python scripts/format_converters/tolerobot/convert2lerobot.py \
    --config examples/configs/converter_config_zhipingfang_dual_arm_no_pose_compressed_video.yaml \
    --input-path /mnt/nas/synnas/docker2/外部数据/智平方/30k数采-第一批 \
    --output-path outputs/lerobot_converter/zhipingfang_validated
```

## 相关文档

- 📖 [详细使用指南](./zhipingfang_validator_guide.md)
- 🔧 [智平方转换配置](./ZHIPINGFANG_DUAL_ARM_NO_POSE_COMPRESSED_VIDEO.md)
- 🎥 [压缩视频格式](./COMPRESSED_VIDEO_FORMAT_SUPPORT.md)

## 支持

如有问题，请参考：
1. 生成的 validation_report_*.txt 报告
2. 完整的使用指南文档
3. 项目 issue 或联系开发团队
