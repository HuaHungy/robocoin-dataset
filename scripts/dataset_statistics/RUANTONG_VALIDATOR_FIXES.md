# 软通验证器修复说明

## 修复日期
2025年10月20日

## 修复的问题

### 1. ✅ 配置检测增强
**问题**: 配置问题检测报告需要更清晰地区分不同类型的配置错误

**修复内容**:
- **相机配置问题**: 明确标注为"❌ 相机配置问题"，提供相机名称
- **H5路径配置问题**: 明确标注为"❌ H5路径配置问题"，提供具体路径和H5结构查看命令
- **H5文件损坏**: 标注为数据质量问题，而非配置问题
- **其他配置问题**: 提供通用检查步骤

**配置检测已包含**:
- ✅ H5路径检测 (从 action.sub_action 和 state.sub_state 提取)
- ✅ 相机图片检测 (从 observation.images 提取)
- ✅ 自动从 factory config 查找对应的 converter config

### 2. ✅ 权限问题处理
**问题**: 移动文件时遇到 `[Errno 13] Permission denied` 错误

**修复内容**:
- 添加创建error目录的权限检查
- 添加移动文件的权限检查
- 提供清晰的权限错误提示
- 建议使用 sudo 或修改权限

**错误提示示例**:
```
❌ 无权限创建error目录: /path/to/error
   请检查目录权限或使用sudo运行

❌ 无权限移动: /path/to/episode
   源: /path/to/episode
   目标: /path/to/error/episode
   请检查目录权限或使用sudo运行
```

## 配置检测报告格式

验证器会生成详细的配置问题报告 (`validation_config_issues.txt`)，包含：

### 相机配置问题示例
```
错误类型: 缺失: hand_left_color.jpg (第1帧)
出现次数: 1523/1600 (95.2%)
问题分析: 此错误出现在95.2%的episodes中，很可能是device_model_annotation.yaml或converter config配置错误

建议措施:
  ❌ 相机配置问题: hand_left_color
  1. 检查 converter config 的 observation.images 中是否错误配置了 hand_left_color
  2. 检查 device_model_annotation.yaml 中的 device_model_version
  3. 确认该数据集是否真的包含 hand_left_color 相机
  4. 对比其他正常的数据集版本，看是否版本标注错误
```

### H5路径配置问题示例
```
错误类型: H5缺少路径: action/gripper
出现次数: 1523/1600 (95.2%)
问题分析: 此错误出现在95.2%的episodes中，很可能是device_model_annotation.yaml或converter config配置错误

建议措施:
  ❌ H5路径配置问题: action/gripper
  1. 检查 converter config 的 action/state 配置中的 h5_path: action/gripper
  2. 使用以下命令查看实际的H5文件结构:
     python3 -c "import h5py; f=h5py.File('aligned_joints.h5'); f.visit(print)"
  3. 确认 device_model_version 是否正确对应了该数据的H5结构
  4. 如果H5结构已变更，需要更新converter config或创建新版本配置
```

## 使用建议

### 处理权限问题
**选项1: 使用sudo**
```bash
sudo python3 scripts/dataset_statistics/ruantong_preconversion_validator_v2.py \
  --dataset-path /mnt/nas/synnas/docker2/外部数据/软通天擎 \
  --workers 8 \
  --move-errors
```

**选项2: 修改权限**
```bash
# 递归修改目录权限（谨慎使用）
sudo chmod -R u+w /mnt/nas/synnas/docker2/外部数据/软通天擎

# 或者只修改特定子目录
sudo chmod -R u+w /mnt/nas/synnas/docker2/外部数据/软通天擎/gt01
```

### 查看H5文件结构
```bash
# 方法1: 使用Python
python3 -c "import h5py; f=h5py.File('aligned_joints.h5', 'r'); f.visit(print)"

# 方法2: 使用h5dump（如果安装了hdf5-tools）
h5dump -n aligned_joints.h5
```

### 验证工作流程
1. **首次运行**: 不带 `--move-errors`，生成报告
   ```bash
   python3 scripts/dataset_statistics/ruantong_preconversion_validator_v2.py \
     --dataset-path /path/to/dataset \
     --workers 8
   ```

2. **检查报告**: 查看 `validation_config_issues.txt`
   - 如果有配置问题（错误率≥90%），修正配置文件
   - 如果只是零散的数据问题，继续第3步

3. **移动错误数据**: 带 `--move-errors` 重新运行
   ```bash
   sudo python3 scripts/dataset_statistics/ruantong_preconversion_validator_v2.py \
     --dataset-path /path/to/dataset \
     --workers 8 \
     --move-errors
   ```

## 技术细节

### 配置加载优先级
1. 命令行指定的 `--config`
2. 从 factory config 自动查找（基于 device_model + version）
3. 回退到默认配置

### 配置问题判定标准
- 错误率 ≥ 90%: 认为是配置问题
- 配置问题的episodes不会被移动到error文件夹
- 需要修正配置后重新验证

### 错误移动规则
- ✅ 移动: 零散的数据质量问题（<10%错误率）
- ⏭️ 跳过: 配置问题（≥90%错误率）

## 注意事项

1. **权限问题**: NAS挂载的目录可能有特殊权限设置，建议使用sudo或联系管理员
2. **配置问题优先**: 如果检测到配置问题，应该先修正配置，而不是移动文件
3. **备份重要**: 移动文件前确保有备份，虽然只是移动到error/子目录
4. **批量处理**: 使用 `--workers` 参数调整并行度（建议4-8个进程）
