#!/bin/bash
################################################################################
# Ruantong 转换器极简打包脚本
# 用途: 打包最小化的转换器，不包含工厂模式和架构细节
# 使用: bash scripts/package_ruantong_converter_minimal.sh [output_dir]
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

OUTPUT_DIR="${1:-./ruantong_converter_minimal}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE_NAME="ruantong_converter_minimal_${TIMESTAMP}"
PACKAGE_DIR="${OUTPUT_DIR}/${PACKAGE_NAME}"

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      Ruantong 转换器极简打包工具（无工厂模式）                  ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📦 输出目录: ${PACKAGE_DIR}${NC}"
echo ""

mkdir -p "${PACKAGE_DIR}"

echo -e "${YELLOW}🔨 Step 1: 创建简化的基类...${NC}"

# 创建简化版基类（去掉工厂模式）
cat > "${PACKAGE_DIR}/base_converter.py" << 'EOFBASE'
"""
LeRobot格式转换器基类（简化版）
去除了工厂模式和配置管理系统，专注于核心转换逻辑
"""
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

import numpy as np
import yaml
from lerobot.datasets.lerobot_dataset import LeRobotDataset

from exceptions import (
    ConfigError,
    CriticalDataError,
    DataQualityError,
)


class LerobotFormatConverter(ABC):
    """LeRobot格式转换器基类（简化版）
    
    提供核心转换功能，不包含工厂模式和配置加载系统
    """
    
    def __init__(
        self,
        dataset_path: str,
        output_path: str,
        converter_config: dict,
        repo_id: str,
        logger: logging.Logger | None = None,
        video_backend: str = "pyav",
        image_writer_processes: int = 4,
        image_writer_threads: int = 4,
    ) -> None:
        """初始化转换器
        
        Args:
            dataset_path: 原始数据集路径
            output_path: 输出路径
            converter_config: 转换器配置字典
            repo_id: 数据集ID
            logger: 日志记录器
            video_backend: 视频后端 ('pyav' 或 'torchvision')
            image_writer_processes: 图像写入进程数
            image_writer_threads: 每个进程的线程数
        """
        self.dataset_path = Path(dataset_path)
        self.output_path = Path(output_path)
        self.converter_config = converter_config
        self.repo_id = repo_id
        self.logger = logger or logging.getLogger(__name__)
        self.video_backend = video_backend
        self.image_writer_processes = image_writer_processes
        self.image_writer_threads = image_writer_threads
        
        # 从配置中提取基本参数
        self.fps = converter_config.get("fps", 30)
        
        # 初始化 LeRobot 数据集
        self.lerobot_dataset = None
        
        # 获取任务和episode路径
        self.tasks = self._get_tasks()
        self.path_task_dict = self._get_dataset_task_paths()
        
        if self.logger:
            self.logger.info(f"✅ Initialized converter for {len(self.tasks)} tasks, "
                           f"{len(self.path_task_dict)} episodes")
    
    @abstractmethod
    def _get_tasks(self) -> list[str]:
        """获取数据集中的所有任务列表"""
        pass
    
    @abstractmethod
    def _get_dataset_task_paths(self) -> dict[Path, str]:
        """获取所有episode目录路径及其对应的任务名
        
        Returns:
            dict: {episode_path: task_name}
        """
        pass
    
    @abstractmethod
    def _get_episode_frames_num(self, episode_path: Path, task: str) -> int:
        """获取episode的帧数"""
        pass
    
    @abstractmethod
    def _get_frame_image(
        self, 
        episode_path: Path, 
        frame_idx: int, 
        cam_name: str, 
        task: str
    ) -> np.ndarray:
        """获取指定帧的图像"""
        pass
    
    @abstractmethod
    def _get_frame_state(
        self, 
        episode_path: Path, 
        frame_idx: int, 
        task: str
    ) -> np.ndarray:
        """获取指定帧的状态数据"""
        pass
    
    @abstractmethod
    def _get_frame_action(
        self, 
        episode_path: Path, 
        frame_idx: int, 
        task: str
    ) -> np.ndarray:
        """获取指定帧的动作数据"""
        pass
    
    def get_episodes_num(self) -> int:
        """获取总episode数量"""
        return len(self.path_task_dict)
    
    def convert(self, is_test: bool = False) -> Iterator[tuple[str, int, int]]:
        """转换数据集
        
        Args:
            is_test: 是否测试模式（只转换少量数据）
            
        Yields:
            (task, task_ep_idx, global_ep_idx): 成功转换的episode信息
        """
        # 创建 LeRobot 数据集
        self.lerobot_dataset = LeRobotDataset.create(
            repo_id=self.repo_id,
            fps=self.fps,
            root=self.output_path,
            video_backend=self.video_backend,
            image_writer_processes=self.image_writer_processes,
            image_writer_threads_per_process=self.image_writer_threads,
        )
        
        try:
            # 按任务分组episode
            task_episodes = {}
            for ep_path, task in self.path_task_dict.items():
                if task not in task_episodes:
                    task_episodes[task] = []
                task_episodes[task].append(ep_path)
            
            # 测试模式：只处理前2个任务，每个任务1个episode
            if is_test:
                task_episodes = {
                    task: eps[:1] 
                    for task, eps in list(task_episodes.items())[:2]
                }
                if self.logger:
                    self.logger.info("🧪 TEST MODE: Processing limited episodes")
            
            # 转换每个任务的episodes
            global_ep_idx = 0
            for task, episodes in task_episodes.items():
                for task_ep_idx, ep_path in enumerate(episodes):
                    try:
                        # 转换单个episode
                        self._convert_episode(ep_path, task, task_ep_idx, global_ep_idx, is_test)
                        yield task, task_ep_idx, global_ep_idx
                        global_ep_idx += 1
                        
                    except (CriticalDataError, DataQualityError) as e:
                        # 数据质量问题，跳过这个episode
                        if self.logger:
                            self.logger.warning(f"⚠️  Skipping episode {global_ep_idx}: {e}")
                        global_ep_idx += 1
                        continue
                    
                    except ConfigError:
                        # 配置错误，停止转换
                        raise
                    
                    except Exception as e:
                        # 其他错误，记录并跳过
                        if self.logger:
                            self.logger.error(f"❌ Error in episode {global_ep_idx}: {e}")
                        global_ep_idx += 1
                        continue
        finally:
            # 清理资源
            if self.lerobot_dataset:
                self.lerobot_dataset.consolidate()
                if hasattr(self.lerobot_dataset, 'stop_image_writer'):
                    self.lerobot_dataset.stop_image_writer()
    
    def _convert_episode(
        self, 
        episode_path: Path, 
        task: str, 
        task_ep_idx: int, 
        global_ep_idx: int,
        is_test: bool = False
    ) -> None:
        """转换单个episode
        
        Args:
            episode_path: episode路径
            task: 任务名
            task_ep_idx: 任务内的episode索引
            global_ep_idx: 全局episode索引
            is_test: 是否测试模式
        """
        # 获取帧数
        num_frames = self._get_episode_frames_num(episode_path, task)
        
        # 测试模式：只处理前11帧
        if is_test:
            num_frames = min(11, num_frames)
        
        # 转换每一帧
        for frame_idx in range(num_frames):
            frame_data = {}
            
            # 获取图像
            for cam_config in self.converter_config.get("observation", {}).get("camera", []):
                cam_name = cam_config["cam_name"]
                feature_name = cam_config["cam_name_in_feature"]
                
                try:
                    image = self._get_frame_image(episode_path, frame_idx, cam_name, task)
                    frame_data[feature_name] = image
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Failed to get image {cam_name} at frame {frame_idx}: {e}")
                    continue
            
            # 获取状态
            try:
                state = self._get_frame_state(episode_path, frame_idx, task)
                frame_data["observation.state"] = state
            except Exception as e:
                raise CriticalDataError(f"Failed to get state at frame {frame_idx}: {e}")
            
            # 获取动作
            try:
                action = self._get_frame_action(episode_path, frame_idx, task)
                frame_data["action"] = action
            except Exception as e:
                raise CriticalDataError(f"Failed to get action at frame {frame_idx}: {e}")
            
            # 添加到数据集
            self.lerobot_dataset.add_frame(frame_data)
        
        # 保存episode
        self.lerobot_dataset.save_episode(task=task, task_index=task_ep_idx)
        
        if self.logger:
            self.logger.debug(f"✅ Converted episode {global_ep_idx}: {episode_path.name}")
EOFBASE

echo ""
echo -e "${YELLOW}🔨 Step 2: 复制核心文件...${NC}"

# H5+JPG 转换器
echo "  📄 复制 H5+JPG 转换器..."
cp src/robocoin_dataset/format_converter/tolerobot/lerobot_format_converter_h5_jpg.py \
   "${PACKAGE_DIR}/converter.py"

# 工具类
echo "  📄 复制 H5 缓存..."
cp src/robocoin_dataset/format_converter/utils/h5_file_cache.py \
   "${PACKAGE_DIR}/h5_cache.py"

echo "  📄 复制异常定义..."
cp src/robocoin_dataset/format_converter/tolerobot/exceptions.py \
   "${PACKAGE_DIR}/exceptions.py"

# 常量（简化版，只保留必需的）
echo "  📄 创建简化常量..."
cat > "${PACKAGE_DIR}/constants.py" << 'EOFCONST'
"""常量定义（简化版）"""

# 设备模型
DEVICE_MODEL_RUANTONG_A2D = "ruantong_a2d"

# 配置键名
FPS_KEY = "fps"
OBSERVATION_KEY = "observation"
ACTION_KEY = "action"
CAMERA_KEY = "camera"
STATE_KEY = "state"

# 相机配置
CAM_NAME_KEY = "cam_name"
CAM_NAME_IN_FEATURE_KEY = "cam_name_in_feature"
CAMERA_INDEX_KEY = "camera_index"
RESOLUTION_KEY = "resolution"

# State/Action 配置
H5_PATH_KEY = "h5_path"
LEROBOT_FEATURE_KEY = "lerobot_feature"
RANGE_FROM_KEY = "range_from"
RANGE_TO_KEY = "range_to"
EOFCONST

echo ""
echo -e "${YELLOW}🔨 Step 3: 复制配置文件...${NC}"

# 配置文件
cp scripts/format_converters/tolerobot/configs/converter_config_ruantong.yaml \
   "${PACKAGE_DIR}/config_default.yaml"

if [ -f scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt01_no_depth.yaml ]; then
    cp scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt01_no_depth.yaml \
       "${PACKAGE_DIR}/config_gt01.yaml"
fi

if [ -f scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt02_new.yaml ]; then
    cp scripts/format_converters/tolerobot/configs/converter_config_ruantong_gt02_new.yaml \
       "${PACKAGE_DIR}/config_gt02.yaml"
fi

echo ""
echo -e "${YELLOW}🔨 Step 4: 创建简化的入口脚本...${NC}"

cat > "${PACKAGE_DIR}/convert.py" << 'EOFSCRIPT'
#!/usr/bin/env python3
"""
Ruantong H5+JPG to LeRobot Format Converter (Minimal Version)
直接实例化转换器，无工厂模式
"""
import argparse
import logging
from pathlib import Path
import sys

def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Convert Ruantong dataset to LeRobot format')
    parser.add_argument('--dataset-path', required=True, help='Dataset path')
    parser.add_argument('--output-path', required=True, help='Output path')
    parser.add_argument('--config', required=True, help='Config YAML file')
    parser.add_argument('--repo-id', default='ruantong_dataset', help='Repository ID')
    parser.add_argument('--is-test', action='store_true', help='Test mode')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    logger = setup_logging(logging.DEBUG if args.verbose else logging.INFO)
    
    # 加载配置
    logger.info(f"📋 Loading config: {args.config}")
    import yaml
    with open(args.config) as f:
        config = yaml.safe_load(f)
    
    # 导入转换器
    logger.info("📦 Loading converter...")
    from converter import LerobotFormatConverterH5Jpg
    
    # 创建转换器（直接实例化，无工厂）
    logger.info("🔧 Creating converter...")
    converter = LerobotFormatConverterH5Jpg(
        dataset_path=args.dataset_path,
        output_path=args.output_path,
        converter_config=config,
        repo_id=args.repo_id,
        logger=logger,
        video_backend='pyav',
        image_writer_processes=4,
        image_writer_threads=4,
    )
    
    # 转换
    total_episodes = converter.get_episodes_num()
    logger.info(f"📊 Total episodes: {total_episodes}")
    logger.info(f"🚀 Starting conversion ({'TEST' if args.is_test else 'FORMAL'} mode)...")
    
    converted = 0
    try:
        from tqdm import tqdm
        with tqdm(total=min(2, total_episodes) if args.is_test else total_episodes) as pbar:
            for task, task_ep_idx, global_ep_idx in converter.convert(is_test=args.is_test):
                converted += 1
                pbar.update(1)
    except KeyboardInterrupt:
        logger.warning("\\n⚠️  Interrupted by user")
        sys.exit(1)
    
    logger.info(f"🎉 Converted {converted}/{total_episodes} episodes")

if __name__ == '__main__':
    main()
EOFSCRIPT

chmod +x "${PACKAGE_DIR}/convert.py"

echo ""
echo -e "${YELLOW}🔨 Step 5: 创建文档...${NC}"

cat > "${PACKAGE_DIR}/requirements.txt" << 'EOF'
numpy>=1.24.0
h5py>=3.8.0
Pillow>=9.5.0
PyYAML>=6.0
lerobot>=2.0.0
pyav>=11.0.0
tqdm>=4.65.0
EOF

cat > "${PACKAGE_DIR}/README.md" << 'EOF'
# Ruantong Converter (Minimal Version)

简化版Ruantong H5+JPG转换器，无工厂模式和架构细节。

## 快速开始

### 1. 安装
```bash
pip install -r requirements.txt
```

### 2. 测试
```bash
python convert.py \
    --dataset-path /path/to/dataset \
    --output-path /tmp/test \
    --config config_default.yaml \
    --is-test
```

### 3. 正式转换
```bash
python convert.py \
    --dataset-path /path/to/dataset \
    --output-path /path/to/output \
    --config config_default.yaml
```

## 数据集结构

```
dataset/
├── task1/
│   └── episode_0/
│       ├── aligned_joints.h5
│       ├── meta_info.json
│       └── camera/
│           ├── 0/
│           │   ├── cam_high.jpg
│           │   ├── cam_left_wrist.jpg
│           │   └── cam_right_wrist.jpg
│           └── ...
```

## 配置调整

### 相机名称
在 `config_default.yaml` 中修改 `cam_name` 字段

### 数据维度  
检查实际维度：
```python
import h5py
with h5py.File('aligned_joints.h5', 'r') as f:
    print(f['arm/pose'].shape)
```
然后调整配置中的 `range_to`

## 常见问题

**Q: ModuleNotFoundError: lerobot**
A: `pip install lerobot`

**Q: 找不到数据**
A: 检查数据集路径和结构

**Q: 维度不匹配**
A: 检查H5数据实际维度，调整配置

## 文件说明

- `convert.py` - 主入口
- `converter.py` - H5+JPG转换器
- `base_converter.py` - 基类（简化版）
- `h5_cache.py` - H5缓存
- `exceptions.py` - 异常定义
- `constants.py` - 常量
- `config_*.yaml` - 配置文件
EOF

echo ""
echo -e "${YELLOW}🔨 Step 6: 修复导入...${NC}"

# 修复导入路径
sed -i 's/from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter/from base_converter/g' \
    "${PACKAGE_DIR}/converter.py"
sed -i 's/from robocoin_dataset.format_converter.utils.h5_file_cache/from h5_cache/g' \
    "${PACKAGE_DIR}/converter.py"
sed -i 's/from robocoin_dataset.constant import/from constants import/g' \
    "${PACKAGE_DIR}/base_converter.py" 2>/dev/null || true
sed -i 's/from robocoin_dataset.format_converter.tolerobot.constant import/from constants import/g' \
    "${PACKAGE_DIR}/base_converter.py" 2>/dev/null || true
sed -i 's/from robocoin_dataset.format_converter.tolerobot.exceptions import/from exceptions import/g' \
    "${PACKAGE_DIR}/base_converter.py" 2>/dev/null || true
sed -i 's/from robocoin_dataset.format_converter.tolerobot.exceptions import/from exceptions import/g' \
    "${PACKAGE_DIR}/h5_cache.py"

echo ""
echo -e "${GREEN}✅ 打包完成！${NC}"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📦 包位置: ${PACKAGE_DIR}${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

ls -lh "${PACKAGE_DIR}" | awk '{if(NR>1) print "   " $9 " (" $5 ")"}'
echo ""

# 创建 ZIP
echo -e "${YELLOW}🗜️  创建 ZIP..${NC}"
cd "${OUTPUT_DIR}"
zip -r "${PACKAGE_NAME}.zip" "${PACKAGE_NAME}" > /dev/null
ZIP_SIZE=$(du -h "${PACKAGE_NAME}.zip" | cut -f1)
echo -e "${GREEN}   ✅ ${PACKAGE_NAME}.zip (${ZIP_SIZE})${NC}"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🎉 极简版打包成功！${NC}"
echo -e "${YELLOW}特点: 无工厂模式、无架构细节、只有核心转换逻辑${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

