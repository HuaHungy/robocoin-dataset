#!/bin/bash
################################################################################
# Ruantong 转换器打包脚本
# 用途: 为外部用户打包最小化的 Ruantong H5+JPG 转换器
# 使用: bash scripts/package_ruantong_converter.sh [output_dir]
################################################################################

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认输出目录
OUTPUT_DIR="${1:-./ruantong_converter_package}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE_NAME="ruantong_converter_${TIMESTAMP}"
PACKAGE_DIR="${OUTPUT_DIR}/${PACKAGE_NAME}"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      Ruantong 转换器打包工具                                   ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📦 输出目录: ${PACKAGE_DIR}${NC}"
echo ""

# 创建目录结构
mkdir -p "${PACKAGE_DIR}"
mkdir -p "${PACKAGE_DIR}/example"

echo -e "${YELLOW}🔨 Step 1: 复制核心文件...${NC}"

# 1. 核心转换器文件
echo "  📄 复制 H5+JPG 转换器..."
cp src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_jpg.py \
   "${PACKAGE_DIR}/converter.py"

echo "  📄 复制基类转换器..."
cp src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter.py \
   "${PACKAGE_DIR}/base_converter.py"

# 2. 工具类
echo "  📄 复制 H5 缓存..."
cp src/robocoin_dataset/format_converter/utils/h5_file_cache.py \
   "${PACKAGE_DIR}/h5_cache.py"

echo "  📄 复制空间转换器..."
cp src/robocoin_dataset/format_converter/utils/spatial_data_convertor.py \
   "${PACKAGE_DIR}/spatial_convertor.py"

# 3. 异常和常量
echo "  📄 复制异常定义..."
cp src/robocoin_dataset/format_converter/tolerobot/exceptions.py \
   "${PACKAGE_DIR}/exceptions.py"

echo "  📄 合并常量文件..."
cat > "${PACKAGE_DIR}/constants.py" << 'EOF'
"""
常量定义
整合自 robocoin_dataset.constant 和 robocoin_dataset.format_converter.tolerobot.constant
"""

# ============================================================================
# 全局常量 (from robocoin_dataset.constant)
# ============================================================================

# 设备模型名称
DEVICE_MODEL_RUANTONG_A2D = "ruantong_a2d"

# ============================================================================
# 转换器常量 (from robocoin_dataset.format_converter.tolerobot.constant)
# ============================================================================

# 配置文件键名
LOCAL_DATASET_INFO_FILE = "local_dataset_info.yaml"
LOCAL_TASK_INFO_FILE = "local_task_info.yaml"
TASK_DESCRIPTIONS_KEY = "task_descriptions"

# LeRobot 特征名
LEROBOT_FEATURE_OBSERVATION_IMAGES = "observation.images"
LEROBOT_FEATURE_OBSERVATION_STATE = "observation.state"
LEROBOT_FEATURE_ACTION = "action"

# 转换器配置键
FPS_KEY = "fps"
OBSERVATION_KEY = "observation"
ACTION_KEY = "action"
CAMERA_KEY = "camera"
STATE_KEY = "state"

# 相机配置键
CAM_NAME_KEY = "cam_name"
CAM_NAME_IN_FEATURE_KEY = "cam_name_in_feature"
CAMERA_INDEX_KEY = "camera_index"
RESOLUTION_KEY = "resolution"

# State/Action 配置键
H5_PATH_KEY = "h5_path"
LEROBOT_FEATURE_KEY = "lerobot_feature"
RANGE_FROM_KEY = "range_from"
RANGE_TO_KEY = "range_to"
SPATIAL_CONVERTOR_KEY = "spatial_data_convertor_name"

# 其他
EPISODE_CHUNK_SIZE = 1000  # Episode 分块大小
EOF

echo ""
echo -e "${YELLOW}🔨 Step 2: 复制配置文件...${NC}"

# 复制 Ruantong 配置文件
echo "  ⚙️  复制默认配置..."
cp scripts/format_converters/tolerobot/configs/converter_config_ruantong.yaml \
   "${PACKAGE_DIR}/config_default.yaml"

if [ -f scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt01_no_depth.yaml ]; then
    echo "  ⚙️  复制 GT01 配置..."
    cp scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt01_no_depth.yaml \
       "${PACKAGE_DIR}/config_gt01.yaml"
fi

if [ -f scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt02_new.yaml ]; then
    echo "  ⚙️  复制 GT02 配置..."
    cp scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt02_new.yaml \
       "${PACKAGE_DIR}/config_gt02.yaml"
fi

echo ""
echo -e "${YELLOW}🔨 Step 3: 创建入口脚本...${NC}"

# 创建入口脚本
cat > "${PACKAGE_DIR}/convert.py" << 'EOFSCRIPT'
#!/usr/bin/env python3
"""
Ruantong H5+JPG to LeRobot Format Converter
Standalone version for external users

使用方法:
    # 测试模式（只转换前2个episode）
    python convert.py \\
        --dataset-path /path/to/ruantong/dataset \\
        --output-path /path/to/output \\
        --config config_default.yaml \\
        --is-test

    # 正式转换
    python convert.py \\
        --dataset-path /path/to/ruantong/dataset \\
        --output-path /path/to/output \\
        --config config_default.yaml \\
        --repo-id my_ruantong_dataset
"""
import argparse
from pathlib import Path
import logging
import sys

def setup_logging(level=logging.INFO):
    """配置日志输出"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

def validate_inputs(dataset_path, output_path, config_path):
    """验证输入参数"""
    errors = []
    
    if not Path(dataset_path).exists():
        errors.append(f"Dataset path not found: {dataset_path}")
    
    if not Path(config_path).exists():
        errors.append(f"Config file not found: {config_path}")
    
    output_parent = Path(output_path).parent
    if not output_parent.exists():
        errors.append(f"Output parent directory not found: {output_parent}")
    
    return errors

def main():
    parser = argparse.ArgumentParser(
        description='Convert Ruantong H5+JPG dataset to LeRobot format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试模式
  python convert.py --dataset-path ./data --output-path ./output --config config_default.yaml --is-test
  
  # 正式转换
  python convert.py --dataset-path ./data --output-path ./output --config config_default.yaml
        """
    )
    
    parser.add_argument('--dataset-path', type=str, required=True,
                        help='Path to Ruantong dataset directory')
    parser.add_argument('--output-path', type=str, required=True,
                        help='Output directory for LeRobot format')
    parser.add_argument('--config', type=str, required=True,
                        help='Path to converter config YAML file')
    parser.add_argument('--repo-id', type=str, default='ruantong_dataset',
                        help='Repository ID for the dataset (default: ruantong_dataset)')
    parser.add_argument('--is-test', action='store_true',
                        help='Test mode: only convert first 2 episodes')
    parser.add_argument('--video-backend', type=str, default='pyav',
                        choices=['pyav', 'torchvision'],
                        help='Video backend to use (default: pyav)')
    parser.add_argument('--image-processes', type=int, default=4,
                        help='Number of image writer processes (default: 4)')
    parser.add_argument('--image-threads', type=int, default=4,
                        help='Number of image writer threads per process (default: 4)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logging(log_level)
    
    # Validate inputs
    logger.info("🔍 Validating inputs...")
    errors = validate_inputs(args.dataset_path, args.output_path, args.config)
    if errors:
        logger.error("❌ Validation failed:")
        for error in errors:
            logger.error(f"   - {error}")
        sys.exit(1)
    
    # Load config
    logger.info(f"📋 Loading config from {args.config}...")
    try:
        import yaml
        with open(args.config) as f:
            config = yaml.safe_load(f)
        logger.info(f"   FPS: {config.get('fps', 'N/A')}")
        logger.info(f"   Cameras: {len(config.get('observation', {}).get('camera', []))}")
    except Exception as e:
        logger.error(f"❌ Failed to load config: {e}")
        sys.exit(1)
    
    # Import converter
    logger.info("📦 Loading converter modules...")
    try:
        from converter import LerobotFormatConverterH5Jpg
    except ImportError as e:
        logger.error(f"❌ Failed to import converter: {e}")
        logger.error("   Make sure all required files are in the same directory:")
        logger.error("   - converter.py")
        logger.error("   - base_converter.py")
        logger.error("   - h5_cache.py")
        logger.error("   - exceptions.py")
        logger.error("   - constants.py")
        logger.error("   - spatial_convertor.py")
        sys.exit(1)
    
    # Create converter
    logger.info("🔧 Initializing converter...")
    logger.info(f"   Dataset: {args.dataset_path}")
    logger.info(f"   Output: {args.output_path}")
    logger.info(f"   Repo ID: {args.repo_id}")
    logger.info(f"   Mode: {'TEST' if args.is_test else 'FORMAL'}")
    
    try:
        converter = LerobotFormatConverterH5Jpg(
            dataset_path=args.dataset_path,
            output_path=args.output_path,
            converter_config=config,
            repo_id=args.repo_id,
            device_model='ruantong_a2d',
            logger=logger,
            video_backend=args.video_backend,
            image_writer_processes=args.image_processes,
            image_writer_threads=args.image_threads,
        )
    except Exception as e:
        logger.error(f"❌ Failed to initialize converter: {e}")
        logger.error("   Check:")
        logger.error("   1. Dataset path exists and has correct structure")
        logger.error("   2. Config file matches your data format")
        logger.error("   3. All required files are present")
        sys.exit(1)
    
    # Get total episodes
    try:
        total_episodes = converter.get_episodes_num()
        logger.info(f"📊 Total episodes found: {total_episodes}")
        
        if total_episodes == 0:
            logger.error("❌ No episodes found in dataset!")
            logger.error("   Check dataset structure:")
            logger.error("   dataset/task/episode/aligned_joints.h5")
            logger.error("   dataset/task/episode/camera/0/cam_*.jpg")
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to count episodes: {e}")
        sys.exit(1)
    
    # Convert
    logger.info("🚀 Starting conversion...")
    logger.info("=" * 60)
    
    converted = 0
    skipped = 0
    
    try:
        from tqdm import tqdm
        
        estimated_total = min(2, total_episodes) if args.is_test else total_episodes
        
        with tqdm(total=estimated_total, desc="Converting", unit="episode") as pbar:
            for task, task_ep_idx, global_ep_idx in converter.convert(is_test=args.is_test):
                logger.debug(f"✅ Converted: task={task}, episode={task_ep_idx}, global={global_ep_idx}")
                converted += 1
                pbar.update(1)
        
        skipped = total_episodes - converted
        
    except KeyboardInterrupt:
        logger.warning("\\n⚠️  Conversion interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\\n❌ Conversion failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)
    
    # Summary
    logger.info("=" * 60)
    logger.info("📊 Conversion Summary:")
    logger.info(f"   Total episodes: {total_episodes}")
    logger.info(f"   Converted: {converted}")
    logger.info(f"   Skipped: {skipped}")
    
    if converted > 0:
        success_rate = (converted / total_episodes) * 100
        logger.info(f"   Success rate: {success_rate:.1f}%")
    
    # Save metadata
    if not args.is_test and converted > 0:
        logger.info("💾 Saving metadata...")
        try:
            converter.save_episode_source_mapping()
            converter.save_original_data_paths()
            logger.info("   ✅ Metadata saved")
        except Exception as e:
            logger.warning(f"   ⚠️  Failed to save metadata: {e}")
    
    # Final message
    logger.info("=" * 60)
    if converted > 0:
        logger.info("🎉 Conversion completed successfully!")
        logger.info(f"📂 Output location: {args.output_path}")
    else:
        logger.error("❌ No episodes were converted")
        sys.exit(1)

if __name__ == '__main__':
    main()
EOFSCRIPT

chmod +x "${PACKAGE_DIR}/convert.py"

echo ""
echo -e "${YELLOW}🔨 Step 4: 创建 requirements.txt...${NC}"

cat > "${PACKAGE_DIR}/requirements.txt" << 'EOF'
# Ruantong Converter Dependencies
# Install with: pip install -r requirements.txt

# Core dependencies
numpy>=1.24.0
h5py>=3.8.0
Pillow>=9.5.0
PyYAML>=6.0

# LeRobot (required!)
lerobot>=2.0.0

# Video processing
pyav>=11.0.0

# Progress bar
tqdm>=4.65.0

# Optional: for better performance
# torch>=2.0.0  # If you have CUDA-enabled GPU
EOF

echo ""
echo -e "${YELLOW}🔨 Step 5: 创建 README.md...${NC}"

cp docs/RUANTONG_STANDALONE_CONVERTER_GUIDE.md "${PACKAGE_DIR}/README.md"

echo ""
echo -e "${YELLOW}🔨 Step 6: 创建快速开始指南...${NC}"

cat > "${PACKAGE_DIR}/QUICK_START.md" << 'EOF'
# 快速开始指南

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 准备数据

确保你的数据集结构如下：

```
your_dataset/
├── task1/
│   ├── episode_0/
│   │   ├── aligned_joints.h5
│   │   ├── meta_info.json
│   │   └── camera/
│   │       ├── 0/
│   │       │   ├── cam_high.jpg
│   │       │   ├── cam_left_wrist.jpg
│   │       │   └── cam_right_wrist.jpg
│   │       └── 1/
│   │           └── ...
│   └── episode_1/
│       └── ...
└── task2/
    └── ...
```

## 3. 测试转换（推荐）

先用测试模式验证一切正常：

```bash
python convert.py \
    --dataset-path /path/to/your/dataset \
    --output-path /tmp/test_output \
    --config config_default.yaml \
    --is-test
```

预期输出：
- 只转换前2个episode
- 检查是否有错误
- 验证输出格式

## 4. 正式转换

如果测试成功，开始正式转换：

```bash
python convert.py \
    --dataset-path /path/to/your/dataset \
    --output-path /path/to/output \
    --config config_default.yaml \
    --repo-id my_ruantong_dataset
```

## 5. 检查结果

```bash
ls -lh /path/to/output/
```

应该看到：
- `data/` - 转换后的数据
- `meta_data/` - 元数据
- `videos/` - 视频文件（如果启用）

## 常见问题

### Q: 提示找不到模块
A: 确保所有 .py 文件都在同一目录下

### Q: H5 文件打不开
A: 检查文件权限和完整性

### Q: 图像找不到
A: 检查相机名称是否匹配配置文件

### Q: 维度不匹配
A: 使用以下命令检查实际维度：
```python
import h5py
with h5py.File('aligned_joints.h5', 'r') as f:
    print(f['arm/pose'].shape)
```
然后更新配置文件中的 `range_to`

## 获取帮助

```bash
python convert.py --help
```

详细文档请查看 `README.md`
EOF

echo ""
echo -e "${YELLOW}🔨 Step 7: 修复导入路径...${NC}"

# 修复 converter.py 中的导入
sed -i 's/from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter/from base_converter/g' \
    "${PACKAGE_DIR}/converter.py"
sed -i 's/from robocoin_dataset.format_converter.utils.h5_file_cache/from h5_cache/g' \
    "${PACKAGE_DIR}/converter.py"

# 修复 base_converter.py 中的导入
sed -i 's/from robocoin_dataset.constant import/from constants import/g' \
    "${PACKAGE_DIR}/base_converter.py"
sed -i 's/from robocoin_dataset.format_converter.tolerobot.constant import/from constants import/g' \
    "${PACKAGE_DIR}/base_converter.py"
sed -i 's/from robocoin_dataset.format_converter.tolerobot.exceptions import/from exceptions import/g' \
    "${PACKAGE_DIR}/base_converter.py"
sed -i 's/from robocoin_dataset.format_converter.utils.spatial_data_convertor import/from spatial_convertor import/g' \
    "${PACKAGE_DIR}/base_converter.py"

# 修复 h5_cache.py 中的导入
sed -i 's/from robocoin_dataset.format_converter.tolerobot.exceptions import/from exceptions import/g' \
    "${PACKAGE_DIR}/h5_cache.py"

echo ""
echo -e "${YELLOW}🔨 Step 8: 创建打包信息...${NC}"

cat > "${PACKAGE_DIR}/PACKAGE_INFO.txt" << EOF
Ruantong Converter Package
==========================

生成时间: ${TIMESTAMP}
版本: v1.0
来源: RoboCoin Dataset Project

文件清单:
- convert.py              : 入口脚本
- converter.py            : H5+JPG 转换器（Ruantong 专用）
- base_converter.py       : 转换器基类
- h5_cache.py             : H5 文件缓存工具
- exceptions.py           : 异常定义
- constants.py            : 常量定义（合并版）
- spatial_convertor.py    : 空间数据转换器
- config_default.yaml     : 默认配置文件
- config_gt01.yaml        : GT01 版本配置（如果存在）
- config_gt02.yaml        : GT02 版本配置（如果存在）
- requirements.txt        : Python 依赖清单
- README.md               : 详细使用文档
- QUICK_START.md          : 快速开始指南

使用步骤:
1. pip install -r requirements.txt
2. python convert.py --help
3. python convert.py --dataset-path ... --output-path ... --config config_default.yaml --is-test

注意事项:
- 必须安装 lerobot 库（HuggingFace）
- 数据集必须符合 Ruantong H5+JPG 格式
- 建议先用 --is-test 模式测试

技术支持:
如遇问题，请提供以下信息：
1. 完整错误日志
2. 数据集结构（tree -L 3）
3. H5 文件结构（h5dump -n）
4. 配置文件内容
EOF

echo ""
echo -e "${GREEN}✅ 打包完成！${NC}"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📦 包位置: ${PACKAGE_DIR}${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 列出文件
echo -e "${YELLOW}📋 包内文件:${NC}"
ls -lh "${PACKAGE_DIR}" | awk '{if(NR>1) print "   " $9 " (" $5 ")"}'
echo ""

# 创建 zip 文件
echo -e "${YELLOW}🗜️  创建 ZIP 文件...${NC}"
cd "${OUTPUT_DIR}"
zip -r "${PACKAGE_NAME}.zip" "${PACKAGE_NAME}" > /dev/null
ZIP_SIZE=$(du -h "${PACKAGE_NAME}.zip" | cut -f1)
echo -e "${GREEN}   ✅ ${PACKAGE_NAME}.zip (${ZIP_SIZE})${NC}"
echo ""

# 最终说明
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🎉 打包成功！${NC}"
echo ""
echo -e "${YELLOW}📤 发送给用户:${NC}"
echo -e "   ${PACKAGE_NAME}.zip"
echo ""
echo -e "${YELLOW}📖 用户使用步骤:${NC}"
echo -e "   1. 解压: unzip ${PACKAGE_NAME}.zip"
echo -e "   2. 进入: cd ${PACKAGE_NAME}"
echo -e "   3. 安装依赖: pip install -r requirements.txt"
echo -e "   4. 查看帮助: python convert.py --help"
echo -e "   5. 阅读文档: cat README.md 或 QUICK_START.md"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

