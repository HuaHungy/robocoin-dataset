# -*- coding: utf-8 -*-
"""
LeRobot format converter for Galaxea Lite MCAP datasets.
Compatible with rosbags >= 0.10 (including 0.11.0).
Uses typestore.deserialize_cdr() instead of removed Serde class.
"""

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

# ✅ Correct imports for rosbags >= 0.10
from rosbags.typesys import get_typestore, Stores
from mcap.reader import make_reader

# Project-specific imports
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
    FEATURES_KEY,
    OBSERVATION_KEY,
    IMAGE_KEY,      # = "images"
    STATE_KEY,      # = "state"
    ACTION_KEY,     # = "action"
)
from robocoin_dataset.format_converter.tolerobot.constant import (
    CAM_NAME_KEY,
    ARGS_KEY,
    SUB_STATE_KEY,
    SUB_ACTION_KEY,
)
from robocoin_dataset.format_converter.tolerobot.time_alignment import (
    AlignmentConfig,
    create_time_aligner,
    TimeSyncAnalyzer,
)

logger = logging.getLogger(__name__)


@dataclass
class MCAPBuffer:
    """MCAP episode 数据缓冲区"""
    mcap_data: dict | None = None
    task_path: Path | None = None
    ep_idx: int | None = None


def decode_compressed_image(data: bytes, typestore, msgtype: str) -> np.ndarray:
    """Decode CDR-serialized ROS2 CompressedImage message."""
    try:
        msg = typestore.deserialize_cdr(data, msgtype)
        # CompressedImage has 'data' field containing JPEG/PNG bytes
        image = Image.open(io.BytesIO(msg.data))
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        return np.array(image, dtype=np.uint8)
    except Exception as e:
        logger.error(f"CompressedImage decode failed: {e}")
        return np.zeros((480, 640, 3), dtype=np.uint8)


def decode_image_bytes(data: bytes, typestore, msgtype: str) -> np.ndarray:
    """Decode CDR-serialized ROS2 Image message using typestore."""
    try:
        msg = typestore.deserialize_cdr(data, msgtype)
        if msg.encoding == "rgb8":
            img = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width, 3))
        elif msg.encoding == "bgr8":
            img = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width, 3))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        elif msg.encoding == "mono8":
            img = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width))
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        else:
            raise ValueError(f"Unsupported image encoding: {msg.encoding}")
        return img
    except Exception as e:
        logger.error(f"Image decode failed: {e}")
        return np.zeros((480, 640, 3), dtype=np.uint8)


class RBMCAPToLeRobotConverter(LerobotFormatConverter):
    """MCAP格式转换器 - 基于rosbags typestore"""
    
    def __init__(
        self, 
        dataset_path, 
        output_path, 
        converter_config, 
        repo_id, 
        device_model,
        logger=None, 
        video_backend="pyav", 
        image_writer_processes=4, 
        image_writer_threads=4,
        alignment_config=None,
        **kwargs
    ):
        # Initialize typestore for ROS 2 Foxy
        self.typestore = get_typestore(Stores.ROS2_FOXY)
        self._register_custom_msg_types()
        
        # MCAP buffer for caching episode data
        self.mcap_buffer: MCAPBuffer = MCAPBuffer()
        
        # 配置时间对齐策略
        temp_logger = logger or logging.getLogger(__name__)
        if alignment_config is None:
            # 根据设备模型选择合适的对齐配置
            if device_model and "galaxea" in device_model.lower():
                alignment_config = AlignmentConfig.galaxea_config()
            else:
                # 默认使用应急策略以保证兼容性
                alignment_config = AlignmentConfig.emergency_config()
        self.alignment_config = alignment_config
        self.time_aligner = create_time_aligner(alignment_config, temp_logger)
        self.sync_analyzer = TimeSyncAnalyzer(temp_logger)
        
        super().__init__(
            dataset_path, 
            output_path, 
            converter_config, 
            repo_id, 
            device_model,
            logger or logging.getLogger(__name__), 
            video_backend,
            image_writer_processes, 
            image_writer_threads,
            **kwargs
        )
        
        # 如果logger在super()调用后发生了变化，重新初始化组件
        if self.logger != temp_logger:
            self.time_aligner = create_time_aligner(alignment_config, self.logger)
            self.sync_analyzer = TimeSyncAnalyzer(self.logger)
        
        self.fps = converter_config.get("fps", 30)

    def _register_custom_msg_types(self):
        """Register custom message types if available."""
        try:
            from galaxea_msgs.msg import JointStateExtended
            from rosbags.typesys.types import register_types
            register_types(self.typestore, JointStateExtended.__msgdict__)
        except ImportError:
            # 使用模块级别的logger，因为此时self.logger可能还未初始化
            logger.debug("galaxea_msgs not found; skipping custom message registration.")
        except Exception as e:
            # 使用模块级别的logger，因为此时self.logger可能还未初始化
            logger.warning(f"Failed to register custom message types: {e}")

    def _prevalidate_files(self) -> None:
        """验证MCAP数据集文件结构"""
        validation_warnings = []
        critical_errors = []
        
        for task_path in self.path_task_dict.keys():
            try:
                if not task_path.exists():
                    critical_errors.append(
                        f"❌ MCAP任务路径不存在: {task_path}"
                    )
                    continue
                
                if not task_path.is_dir():
                    critical_errors.append(
                        f"❌ MCAP路径不是目录: {task_path}"
                    )
                    continue
                
                # 查找MCAP文件：支持多种结构
                # 1. task_path/raw.mcap (单个文件)
                # 2. task_path/*.mcap (直接mcap文件)
                # 3. task_path/episode_*/*.mcap (episode目录)
                # 4. task_path/*/raw.mcap 或 task_path/*/*.mcap (任意子目录)
                mcap_files = list(task_path.glob("*.mcap"))
                if not mcap_files:
                    # 检查episode_*子目录
                    episode_dirs = [d for d in task_path.iterdir() if d.is_dir() and d.name.startswith("episode_")]
                    for ep_dir in episode_dirs:
                        ep_mcap = list(ep_dir.glob("*.mcap"))
                        if ep_mcap:
                            mcap_files.extend(ep_mcap)
                
                if not mcap_files:
                    # 检查所有子目录中的mcap文件（支持RB250714009_*_RAW这样的目录）
                    subdirs = [d for d in task_path.iterdir() if d.is_dir()]
                    for subdir in subdirs:
                        subdir_mcap = list(subdir.glob("*.mcap"))
                        if subdir_mcap:
                            mcap_files.extend(subdir_mcap)
                
                if not mcap_files:
                    # 列出所有子目录帮助调试
                    subdirs = [d.name for d in task_path.iterdir() if d.is_dir()][:10]
                    files = [f.name for f in task_path.iterdir() if f.is_file()][:10]
                    critical_errors.append(
                        f"❌ MCAP文件缺失\n"
                        f"📁 目录: {task_path}\n"
                        f"📄 期望文件: *.mcap 或 raw.mcap\n"
                        f"📂 子目录 (前10个): {subdirs}\n"
                        f"📄 文件 (前10个): {files}\n"
                        f"💡 提示: MCAP文件可能在子目录中"
                    )
                    continue
                
                # 验证MCAP文件可读
                for mcap_file in mcap_files[:3]:  # 只验证前3个
                    try:
                        with open(mcap_file, "rb") as f:
                            reader = make_reader(f)
                            # 尝试读取第一个消息
                            next(reader.iter_messages(), None)
                    except Exception as e:
                        validation_warnings.append(
                            f"MCAP文件可能损坏: {mcap_file}, error: {e}"
                        )
                        
            except Exception as e:
                critical_errors.append(
                    f"❌ MCAP路径验证异常\n"
                    f"📁 路径: {task_path}\n"
                    f"⚠️ 错误: {e}"
                )
        
        if critical_errors:
            error_msg = (
                f"❌ MCAP数据集验证失败：发现{len(critical_errors)}个critical错误\n"
                + "\n\n".join(f"{i+1}. {err}" for i, err in enumerate(critical_errors[:5]))
            )
            if self.logger:
                self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        if validation_warnings and self.logger:
            self.logger.info(f"MCAP validation completed with {len(validation_warnings)} warnings")
            for warning in validation_warnings[:5]:
                self.logger.info(f"  - {warning}")

    def _get_mcap_file(self, task_path: Path, ep_idx: int) -> Optional[Path]:
        """获取指定episode的MCAP文件路径"""
        if not task_path.exists():
            if self.logger:
                self.logger.warning(f"Task path does not exist: {task_path}")
            return None
        
        # 收集所有可能的MCAP文件（按优先级排序）
        all_mcap_files = []
        
        # 方式1: task_path下的mcap文件列表（直接文件）
        try:
            direct_mcap = sorted(task_path.glob("*.mcap"))
            all_mcap_files.extend(direct_mcap)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error globbing direct mcap files in {task_path}: {e}")
        
        # 方式2: task_path/raw.mcap (单个文件)
        raw_mcap = task_path / "raw.mcap"
        if raw_mcap.exists() and raw_mcap not in all_mcap_files:
            all_mcap_files.append(raw_mcap)
        
        # 方式3: 检查episode_*目录结构
        try:
            episode_dirs = sorted([
                d for d in task_path.iterdir() 
                if d.is_dir() and d.name.startswith("episode_")
            ])
            for ep_dir in episode_dirs:
                ep_mcap = sorted(ep_dir.glob("*.mcap"))
                all_mcap_files.extend(ep_mcap)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error checking episode dirs in {task_path}: {e}")
        
        # 方式4: 检查所有子目录中的mcap文件（支持RB250714009_*_RAW这样的目录）
        try:
            subdirs = sorted([d for d in task_path.iterdir() if d.is_dir()])
            for subdir in subdirs:
                # 跳过已经处理过的episode_*目录
                if subdir.name.startswith("episode_"):
                    continue
                subdir_mcap = sorted(subdir.glob("*.mcap"))
                all_mcap_files.extend(subdir_mcap)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error checking subdirs in {task_path}: {e}")
        
        # 去重并排序
        all_mcap_files = sorted(set(all_mcap_files), key=lambda p: str(p))
        
        # 返回对应索引的文件
        if all_mcap_files:
            if ep_idx < len(all_mcap_files):
                return all_mcap_files[ep_idx]
            # 如果ep_idx超出范围但有文件，返回第一个（兼容ep_idx=0的情况）
            if ep_idx == 0 and len(all_mcap_files) > 0:
                return all_mcap_files[0]
        
        return None

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务目录下的episode数量"""
        if not task_path.exists():
            if self.logger:
                self.logger.warning(f"Task path does not exist: {task_path}")
            return 0
        
        # 收集所有MCAP文件（使用与_get_mcap_file相同的逻辑）
        all_mcap_files = set()
        
        try:
            # 方式1: task_path下的直接mcap文件
            direct_mcap = task_path.glob("*.mcap")
            all_mcap_files.update(direct_mcap)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error globbing direct mcap files in {task_path}: {e}")
        
        # 方式2: raw.mcap
        raw_mcap = task_path / "raw.mcap"
        if raw_mcap.exists():
            all_mcap_files.add(raw_mcap)
        
        try:
            # 方式3: episode_*目录中的mcap文件
            episode_dirs = [
                d for d in task_path.iterdir() 
                if d.is_dir() and d.name.startswith("episode_")
            ]
            for ep_dir in episode_dirs:
                ep_mcap = ep_dir.glob("*.mcap")
                all_mcap_files.update(ep_mcap)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error checking episode dirs in {task_path}: {e}")
        
        try:
            # 方式4: 所有子目录中的mcap文件（支持RB250714009_*_RAW这样的目录）
            subdirs = [d for d in task_path.iterdir() if d.is_dir()]
            for subdir in subdirs:
                # 跳过已经处理过的episode_*目录
                if subdir.name.startswith("episode_"):
                    continue
                subdir_mcap = subdir.glob("*.mcap")
                all_mcap_files.update(subdir_mcap)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error checking subdirs in {task_path}: {e}")
        
        if all_mcap_files:
            count = len(all_mcap_files)
            if self.logger:
                self.logger.debug(f"Found {count} MCAP files in {task_path}")
            return count
        
        if self.logger:
            self.logger.warning(
                f"No MCAP files found in task_path: {task_path}\n"
                f"  Directory contents: {[f.name for f in task_path.iterdir()][:20]}"
            )
        
        return 0

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """通过统计MCAP消息数量估算帧数"""
        mcap_file = self._get_mcap_file(task_path, ep_idx)
        if not mcap_file or not mcap_file.exists():
            return 0
        
        # 从配置提取需要的topics
        image_topics = set()
        state_topics = set()
        action_topics = set()
        
        # 提取图像topics
        for img_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]:
            args = img_config.get(ARGS_KEY, {})
            mcap_topic = args.get("mcap_topic")
            if mcap_topic:
                image_topics.add(mcap_topic)
        
        # 提取状态topics
        for sub_state in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY].get(SUB_STATE_KEY, []):
            args = sub_state.get(ARGS_KEY, {})
            mcap_topic = args.get("mcap_topic")
            if mcap_topic:
                state_topics.add(mcap_topic)
        
        # 提取动作topics
        for sub_action in self.converter_config[FEATURES_KEY][ACTION_KEY].get(SUB_ACTION_KEY, []):
            args = sub_action.get(ARGS_KEY, {})
            mcap_topic = args.get("mcap_topic")
            if mcap_topic:
                action_topics.add(mcap_topic)
        
        # 统计消息数量
        counts = {}
        target_topics = image_topics | state_topics | action_topics
        
        try:
            with open(mcap_file, "rb") as f:
                reader = make_reader(f)
                for schema, channel, _ in reader.iter_messages():
                    topic = channel.topic
                    if topic in target_topics:
                        counts[topic] = counts.get(topic, 0) + 1
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error counting messages in {mcap_file}: {e}")
            return 0
        
        # 返回最短的序列长度（最保守的估算）
        lengths = [counts[t] for t in target_topics if t in counts and counts[t] > 0]
        
        # 记录各topic的消息数量，用于调试
        if self.logger and lengths:
            image_lengths = {t: counts.get(t, 0) for t in image_topics if t in counts}
            state_lengths = {t: counts.get(t, 0) for t in state_topics if t in counts}
            action_lengths = {t: counts.get(t, 0) for t in action_topics if t in counts}
            
            min_length = min(lengths)
            max_length = max(lengths) if lengths else 0
            
            self.logger.debug(
                f"Episode {ep_idx} message counts:\n"
                f"  Images: {dict(image_lengths)}\n"
                f"  States: {dict(state_lengths)}\n"
                f"  Actions: {dict(action_lengths)}\n"
                f"  Min: {min_length}, Max: {max_length}, "
                f"Using {min_length} frames (limited by images if they are the minimum)"
            )
            
            # 如果图像消息数量明显少于状态/动作消息，发出警告
            if image_lengths and state_lengths and action_lengths:
                min_image = min(image_lengths.values())
                min_state_action = min(
                    list(state_lengths.values()) + list(action_lengths.values())
                )
                if min_image < min_state_action * 0.8:  # 图像消息少于80%
                    self.logger.warning(
                        f"⚠️  Episode {ep_idx}: Image messages ({min_image}) are significantly "
                        f"fewer than state/action messages ({min_state_action}). "
                        f"This will limit frames to {min_image}. "
                        f"Expected duration: {min_image/30:.1f}s (at 30Hz) vs {min_state_action/200:.1f}s (at 200Hz)."
                    )
        
        return min(lengths) if lengths else 0

    def _get_episode_mcap_data(self, task_path: Path, ep_idx: int, is_test: bool = False) -> dict:
        """读取并解析MCAP文件，返回按topic组织的数据"""
        # 检查缓存
        if (self.mcap_buffer.task_path == task_path and 
            self.mcap_buffer.ep_idx == ep_idx and 
            self.mcap_buffer.mcap_data is not None):
            return self.mcap_buffer.mcap_data
        
        mcap_file = self._get_mcap_file(task_path, ep_idx)
        if not mcap_file or not mcap_file.exists():
            error_msg = (
                f"MCAP file not found for task_path={task_path}, ep_idx={ep_idx}\n"
                f"  Searched locations:\n"
                f"    - {task_path / 'raw.mcap'}\n"
                f"    - {task_path}/*.mcap\n"
                f"    - {task_path}/episode_*/raw.mcap\n"
            )
            if self.logger:
                self.logger.error(error_msg)
            # 返回空字典会导致后续错误，但这是预期的
            return {}
        
        # 提取配置中的topics
        topic_configs = {}
        
        # 图像topics
        for img_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]:
            cam_name = img_config.get(CAM_NAME_KEY)
            args = img_config.get(ARGS_KEY, {})
            mcap_topic = args.get("mcap_topic")
            if cam_name and mcap_topic:
                topic_configs[mcap_topic] = {
                    "type": "image",
                    "cam_name": cam_name,
                    "msg_type": "CompressedImage"  # 默认
                }
        
        # 状态topics
        for sub_state in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY].get(SUB_STATE_KEY, []):
            args = sub_state.get(ARGS_KEY, {})
            mcap_topic = args.get("mcap_topic")
            if mcap_topic:
                topic_configs[mcap_topic] = {
                    "type": "state",
                    "range_from": args.get("range_from", 0),
                    "range_to": args.get("range_to"),
                }
        
        # 动作topics
        for sub_action in self.converter_config[FEATURES_KEY][ACTION_KEY].get(SUB_ACTION_KEY, []):
            args = sub_action.get(ARGS_KEY, {})
            mcap_topic = args.get("mcap_topic")
            if mcap_topic:
                topic_configs[mcap_topic] = {
                    "type": "action",
                    "range_from": args.get("range_from", 0),
                    "range_to": args.get("range_to"),
                }
        
        # 读取MCAP文件，提取消息和时间戳
        raw_topic_messages = {topic: [] for topic in topic_configs.keys()}
        
        try:
            with open(mcap_file, "rb") as f:
                reader = make_reader(f)
                for schema, channel, message in reader.iter_messages():
                    topic = channel.topic
                    if topic in topic_configs:
                        # 保存时间戳和数据（不解码）
                        raw_topic_messages[topic].append({
                            'timestamp': message.log_time,  # 时间戳（纳秒）
                            'schema': schema,
                            'data': message.data
                        })
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error reading MCAP file {mcap_file}: {e}")
            return {}
        
        # 检查是否有数据
        if not any(raw_topic_messages.values()):
            if self.logger:
                self.logger.warning(f"No messages found in MCAP file {mcap_file}")
            return {}
        
        # 准备对齐数据：对齐器期望 {topic: [{'timestamp': xxx, 'data': xxx}, ...]}
        # 这里data字段保存完整的消息信息，以便对齐后能正确解码
        topic_messages_for_alignment = {}
        for topic, messages in raw_topic_messages.items():
            if not messages:
                continue
            topic_messages_for_alignment[topic] = [
                {
                    'timestamp': msg['timestamp'],
                    'data': msg  # 保存完整的消息信息（包含schema和data bytes）
                }
                for msg in messages
            ]
        
        # 分析时间同步质量（可选）
        if self.logger and topic_messages_for_alignment:
            try:
                sync_report = self.sync_analyzer.analyze_topic_messages(topic_messages_for_alignment)
                self.logger.debug(
                    f"Episode {ep_idx} time sync quality: {sync_report.overall_quality_score:.3f}, "
                    f"recommended strategy: {sync_report.recommended_strategy}"
                )
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Error analyzing sync quality: {e}")
        
        # 执行时间对齐
        try:
            aligned_messages = self.time_aligner.align_topics(topic_messages_for_alignment)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error aligning topics: {e}")
                self.logger.warning("Falling back to emergency alignment (truncate to minimum length)")
            # 如果对齐失败，回退到简单的截断策略
            aligned_messages = {}
            min_length = min(len(msgs) for msgs in raw_topic_messages.values() if msgs)
            for topic, messages in raw_topic_messages.items():
                if messages:
                    aligned_messages[topic] = messages[:min_length]
        
        # 处理对齐后的消息：转换为numpy数组
        processed_data = {}
        
        for topic, aligned_data in aligned_messages.items():
            if not aligned_data or topic not in topic_configs:
                continue
            
            config = topic_configs[topic]
            # aligned_data是经过对齐的数据列表，每个元素是消息信息dict（对齐器返回的是data字段）
            # 由于我们传递的data是整个消息信息dict，所以这里aligned_data的每个元素就是消息信息dict
            messages = aligned_data
            
            if config["type"] == "image":
                # 处理图像消息
                images = []
                for msg_info in messages:
                    try:
                        # msg_info可能是原始消息信息dict，或者是经过对齐器处理的
                        if isinstance(msg_info, dict) and 'schema' in msg_info:
                            schema_name = msg_info['schema'].name
                            data_bytes = msg_info['data']
                        else:
                            # 如果对齐器已经提取了data字段，可能需要特殊处理
                            # 这里假设对齐器保留了原始结构
                            continue
                        
                        if 'CompressedImage' in schema_name:
                            img = decode_compressed_image(
                                data_bytes, 
                                self.typestore, 
                                schema_name
                            )
                        else:
                            img = decode_image_bytes(
                                data_bytes, 
                                self.typestore, 
                                schema_name
                            )
                        images.append(img)
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(f"Failed to decode image from {topic}: {e}")
                        images.append(np.zeros((480, 640, 3), dtype=np.uint8))
                
                # 使用cam_name作为key，但topic作为实际存储key
                processed_data[topic] = images
            
            elif config["type"] == "state":
                # 处理状态消息（JointState, Imu等）
                states = []
                for msg_info in messages:
                    try:
                        # 提取schema和data
                        if isinstance(msg_info, dict) and 'schema' in msg_info:
                            schema_name = msg_info['schema'].name
                            data_bytes = msg_info['data']
                        else:
                            continue
                        
                        msg = self.typestore.deserialize_cdr(
                            data_bytes, 
                            schema_name
                        )
                        
                        # 处理JointState
                        # 注意：只提取position，velocity和effort在配置中不需要
                        # 如果需要velocity/effort，会在配置中单独定义
                        if hasattr(msg, 'position'):
                            state_array = np.array(list(msg.position), dtype=np.float32)
                        # 处理Imu
                        elif hasattr(msg, 'linear_acceleration'):
                            acc = msg.linear_acceleration
                            gyro = msg.angular_velocity
                            state_array = np.array([
                                acc.x, acc.y, acc.z,
                                gyro.x, gyro.y, gyro.z
                            ], dtype=np.float32)
                        # 处理其他类型
                        else:
                            state_array = np.array([], dtype=np.float32)
                        
                        states.append(state_array)
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(f"Failed to decode state from {topic}: {e}")
                        # 如果知道期望维度，使用零数组填充
                        range_from = config.get("range_from", 0)
                        range_to = config.get("range_to")
                        expected_dim = (range_to - range_from) if range_to else None
                        if expected_dim:
                            states.append(np.zeros(expected_dim, dtype=np.float32))
                        else:
                            states.append(np.array([], dtype=np.float32))
                
                # 验证并统一state维度：使用配置中的期望维度
                if states and len(states) > 0:
                    # 优先使用配置中的期望维度
                    expected_dim_from_config = None
                    if 'range_to' in config and 'range_from' in config:
                        range_from = config.get('range_from', 0)
                        range_to = config.get('range_to')
                        if range_to is not None:
                            expected_dim_from_config = range_to - range_from
                    
                    # 如果没有配置维度，使用第一个数组的实际维度
                    if expected_dim_from_config is None:
                        expected_dim_from_config = len(states[0]) if len(states[0]) > 0 else None
                    
                    if expected_dim_from_config is not None:
                        for i, state in enumerate(states):
                            if len(state) != expected_dim_from_config:
                                if self.logger and i == 0:  # 只记录第一次
                                    self.logger.debug(
                                        f"State dimension mismatch in topic {topic}: "
                                        f"frame {i} has {len(state)} dims, "
                                        f"expected {expected_dim_from_config} (from config)"
                                    )
                                # 填充或截断到期望维度
                                if len(state) < expected_dim_from_config:
                                    states[i] = np.pad(
                                        state, (0, expected_dim_from_config - len(state)), 
                                        mode='constant', constant_values=0.0
                                    )
                                else:
                                    states[i] = state[:expected_dim_from_config]
                
                processed_data[topic] = states
            
            elif config["type"] == "action":
                # 处理动作消息（JointState, TwistStamped等）
                actions = []
                expected_dim = config.get("range_to") or config.get("range_from", 0)
                if expected_dim and isinstance(expected_dim, int):
                    range_from = config.get("range_from", 0)
                    expected_dim = expected_dim - range_from
                
                for msg_info in messages:
                    try:
                        # 提取schema和data
                        if isinstance(msg_info, dict) and 'schema' in msg_info:
                            schema_name = msg_info['schema'].name
                            data_bytes = msg_info['data']
                        else:
                            continue
                        
                        msg = self.typestore.deserialize_cdr(
                            data_bytes, 
                            schema_name
                        )
                        
                        # 处理JointState (positions)
                        if hasattr(msg, 'position'):
                            action_array = np.array(list(msg.position), dtype=np.float32)
                        # 处理TwistStamped
                        elif hasattr(msg, 'twist'):
                            twist = msg.twist
                            # 确保twist有linear和angular属性
                            if hasattr(twist, 'linear') and hasattr(twist, 'angular'):
                                linear = [twist.linear.x, twist.linear.y, twist.linear.z]
                                angular = [twist.angular.x, twist.angular.y, twist.angular.z]
                                action_array = np.array(linear + angular, dtype=np.float32)
                            else:
                                if self.logger:
                                    self.logger.warning(
                                        f"TwistStamped message missing linear/angular fields "
                                        f"for topic {topic}"
                                    )
                                action_array = np.array([], dtype=np.float32)
                        # 处理其他类型
                        else:
                            action_array = np.array([], dtype=np.float32)
                        
                        # 验证维度（如果知道期望维度）
                        if expected_dim and len(action_array) != expected_dim:
                            if self.logger:
                                self.logger.warning(
                                    f"Action dimension mismatch for topic {topic}: "
                                    f"expected {expected_dim}, got {len(action_array)}"
                                )
                        
                        actions.append(action_array)
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(
                                f"Failed to decode action from {topic}: {e}. "
                                f"Schema: {msg_info.get('schema', {}).get('name', 'unknown')}"
                            )
                        # 如果知道期望维度，使用零数组填充
                        if expected_dim:
                            actions.append(np.zeros(expected_dim, dtype=np.float32))
                        else:
                            actions.append(np.array([], dtype=np.float32))
                
                # 验证并统一维度：使用配置中的期望维度而不是第一个数组的实际维度
                if actions and len(actions) > 0:
                    # 优先使用配置中的期望维度
                    expected_dim_from_config = None
                    if 'range_to' in config and 'range_from' in config:
                        range_from = config.get('range_from', 0)
                        range_to = config.get('range_to')
                        if range_to is not None:
                            expected_dim_from_config = range_to - range_from
                    
                    # 如果没有配置维度，使用第一个数组的实际维度
                    if expected_dim_from_config is None:
                        expected_dim_from_config = len(actions[0]) if len(actions[0]) > 0 else None
                    
                    if expected_dim_from_config is not None:
                        for i, act in enumerate(actions):
                            if len(act) != expected_dim_from_config:
                                if self.logger and i == 0:  # 只记录第一次
                                    self.logger.debug(
                                        f"Action dimension mismatch in topic {topic}: "
                                        f"frame {i} has {len(act)} dims, "
                                        f"expected {expected_dim_from_config} (from config)"
                                    )
                                # 填充或截断到期望维度
                                if len(act) < expected_dim_from_config:
                                    actions[i] = np.pad(
                                        act, (0, expected_dim_from_config - len(act)), 
                                        mode='constant', constant_values=0.0
                                    )
                                else:
                                    actions[i] = act[:expected_dim_from_config]
                
                processed_data[topic] = actions
                
                # 记录提取的信息
                if self.logger and actions:
                    dim = len(actions[0]) if actions else 0
                    self.logger.debug(
                        f"Extracted {len(actions)} action messages from {topic}, "
                        f"dimension: {dim}"
                    )
        
        # 验证并记录提取的数据信息（用于调试维度问题）
        if self.logger:
            # 统计action topics的维度信息
            action_topic_configs = {
                cfg.get(ARGS_KEY, {}).get("mcap_topic"): cfg
                for cfg in self.converter_config[FEATURES_KEY][ACTION_KEY].get(SUB_ACTION_KEY, [])
            }
            
            action_summary = []
            total_action_dims = 0
            for topic, cfg in action_topic_configs.items():
                if topic in processed_data and processed_data[topic]:
                    actions = processed_data[topic]
                    if actions:
                        dim = len(actions[0]) if len(actions[0]) > 0 else 0
                        count = len(actions)
                        range_from = cfg.get(ARGS_KEY, {}).get("range_from", 0)
                        range_to = cfg.get(ARGS_KEY, {}).get("range_to")
                        expected_dim = (range_to - range_from) if range_to else dim
                        
                        action_summary.append(
                            f"  {topic}: {count} msgs, {dim} dims "
                            f"(expected: {expected_dim}, slice: [{range_from}:{range_to}])"
                        )
                        total_action_dims += expected_dim
            
            if action_summary:
                self.logger.debug(
                    f"Action extraction summary for episode {ep_idx}:\n" + 
                    "\n".join(action_summary) + 
                    f"\n  Total expected action dims: {total_action_dims}"
                )
        
        # 缓存结果
        self.mcap_buffer.mcap_data = processed_data
        self.mcap_buffer.task_path = task_path
        self.mcap_buffer.ep_idx = ep_idx
        
        return processed_data

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> any:
        """准备图像缓冲区"""
        return self._get_episode_mcap_data(task_path, ep_idx, is_test)

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> any:
        """准备状态缓冲区"""
        return self._get_episode_mcap_data(task_path, ep_idx, is_test)

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> any:
        """准备动作缓冲区"""
        return self._get_episode_mcap_data(task_path, ep_idx, is_test)

    def _get_frame_image(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        images_buffer: any = None,
        sample_only: bool = False,
    ) -> np.ndarray:
        """获取单帧图像"""
        if images_buffer is None:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)
        
        # 检查buffer是否为空（可能是找不到MCAP文件）
        if not images_buffer:
            mcap_file = self._get_mcap_file(task_path, ep_idx)
            error_msg = (
                f"❌ MCAP图像缓冲区为空\n"
                f"📁 Task path: {task_path}\n"
                f"🔢 Episode index: {ep_idx}\n"
            )
            if mcap_file and mcap_file.exists():
                error_msg += f"📄 MCAP文件存在: {mcap_file}\n"
                error_msg += "💡 可能原因：MCAP文件中没有找到配置的话题"
            else:
                error_msg += "📄 MCAP文件不存在\n"
                error_msg += "   已搜索的位置:\n"
                error_msg += f"     - {task_path / 'raw.mcap'}\n"
                error_msg += f"     - {task_path}/*.mcap\n"
                error_msg += f"     - {task_path}/episode_*/raw.mcap\n"
            raise ValueError(error_msg)
        
        mcap_topic = args_dict.get("mcap_topic")
        if not mcap_topic:
            raise ValueError(f"Missing mcap_topic in args_dict: {args_dict}")
        
        if mcap_topic not in images_buffer:
            available_topics = sorted(images_buffer.keys())
            error_msg = (
                f"❌ MCAP图像话题未找到\n"
                f"📹 请求的话题: {mcap_topic}\n"
                f"📊 缓冲区中的话题数量: {len(available_topics)}\n"
            )
            if available_topics:
                error_msg += f"📋 可用话题 (前10个): {available_topics[:10]}\n"
            else:
                error_msg += "⚠️  缓冲区中没有找到任何话题\n"
                error_msg += "💡 可能原因：\n"
                error_msg += "   1. MCAP文件格式不正确\n"
                error_msg += "   2. MCAP文件中没有配置所需的话题\n"
                error_msg += "   3. 话题名称拼写错误"
            raise ValueError(error_msg)
        
        images = images_buffer[mcap_topic]
        if not images:
            raise ValueError(
                f"❌ MCAP图像列表为空\n"
                f"📹 话题: {mcap_topic}\n"
                f"💡 该话题在MCAP文件中没有消息"
            )
        
        if frame_idx >= len(images):
            raise ValueError(
                f"❌ MCAP图像帧索引超出范围\n"
                f"📹 话题: {mcap_topic}\n"
                f"🔢 请求索引: {frame_idx}\n"
                f"📊 可用范围: 0-{len(images)-1}"
            )
        
        return images[frame_idx]

    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: any = None,
    ) -> np.ndarray:
        """获取单帧状态数据"""
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        
        mcap_topic = args_dict.get("mcap_topic")
        range_from = args_dict.get("range_from", 0)
        range_to = args_dict.get("range_to")
        
        if not mcap_topic:
            raise ValueError(f"Missing mcap_topic in args_dict: {args_dict}")
        
        if mcap_topic not in sub_states_buffer:
            available_topics = sorted(sub_states_buffer.keys())
            raise ValueError(
                f"❌ MCAP状态话题未找到\n"
                f"📊 请求的话题: {mcap_topic}\n"
                f"📋 可用话题: {available_topics[:10]}"
            )
        
        states = sub_states_buffer[mcap_topic]
        if frame_idx >= len(states):
            raise ValueError(
                f"❌ MCAP状态帧索引超出范围\n"
                f"📊 话题: {mcap_topic}\n"
                f"🔢 请求索引: {frame_idx}\n"
                f"📊 可用范围: 0-{len(states)-1}"
            )
        
        state_array = states[frame_idx]
        
        # 检查数组维度
        if len(state_array) == 0:
            error_msg = (
                f"❌ MCAP状态数组为空\n"
                f"📊 话题: {mcap_topic}\n"
                f"🔢 帧索引: {frame_idx}\n"
                f"💡 可能是消息解码失败或消息格式不正确"
            )
            if self.logger:
                self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 处理切片范围：如果数据长度小于配置的range_to，使用实际长度并用零填充
        actual_range_to = range_to
        expected_dim = range_to - range_from if range_to is not None else None
        
        if range_to is not None and range_to > len(state_array):
            if self.logger and frame_idx == 0:
                self.logger.warning(
                    f"⚠️  MCAP状态数据长度不足，将用零填充\n"
                    f"   话题: {mcap_topic}\n"
                    f"   配置切片: [{range_from}:{range_to}]\n"
                    f"   实际数组长度: {len(state_array)}\n"
                    f"   将使用: [{range_from}:{len(state_array)}] + 零填充"
                )
            actual_range_to = len(state_array)
        
        # 提取数据
        if actual_range_to is not None:
            result = state_array[range_from:actual_range_to]
        else:
            result = state_array[range_from:]
        
        # 如果维度不足，用零填充到期望维度
        if expected_dim is not None and len(result) < expected_dim:
            padding_size = expected_dim - len(result)
            result = np.pad(
                result, 
                (0, padding_size), 
                mode='constant', 
                constant_values=0.0
            )
            if self.logger and frame_idx == 0:
                self.logger.warning(
                    f"⚠️  MCAP状态维度不足，已用零填充\n"
                    f"   话题: {mcap_topic}\n"
                    f"   原始维度: {len(state_array[range_from:actual_range_to])}\n"
                    f"   期望维度: {expected_dim}\n"
                    f"   填充后维度: {len(result)}"
                )
        elif expected_dim is not None and len(result) > expected_dim:
            # 如果维度超出，截断
            result = result[:expected_dim]
            if self.logger and frame_idx == 0:
                self.logger.warning(
                    f"⚠️  MCAP状态维度超出，已截断\n"
                    f"   话题: {mcap_topic}\n"
                    f"   原始维度: {len(state_array[range_from:actual_range_to])}\n"
                    f"   期望维度: {expected_dim}"
                )
        
        return result

    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: any = None,
    ) -> np.ndarray:
        """获取单帧动作数据"""
        if sub_actions_buffer is None:
            sub_actions_buffer = self._prepare_episode_actions_buffer(task_path, ep_idx)
        
        mcap_topic = args_dict.get("mcap_topic")
        range_from = args_dict.get("range_from", 0)
        range_to = args_dict.get("range_to")
        expected_dim = range_to - range_from if range_to is not None else None
        
        if not mcap_topic:
            raise ValueError(f"Missing mcap_topic in args_dict: {args_dict}")
        
        if mcap_topic not in sub_actions_buffer:
            available_topics = sorted(sub_actions_buffer.keys())
            error_msg = (
                f"❌ MCAP动作话题未找到\n"
                f"🎯 请求的话题: {mcap_topic}\n"
                f"📋 缓冲区中的话题数量: {len(available_topics)}\n"
            )
            if available_topics:
                error_msg += f"📋 可用话题 (前10个): {available_topics[:10]}"
            raise ValueError(error_msg)
        
        actions = sub_actions_buffer[mcap_topic]
        if not actions:
            raise ValueError(
                f"❌ MCAP动作列表为空\n"
                f"🎯 话题: {mcap_topic}\n"
                f"💡 该话题在MCAP文件中没有消息"
            )
        
        if frame_idx >= len(actions):
            raise ValueError(
                f"❌ MCAP动作帧索引超出范围\n"
                f"🎯 话题: {mcap_topic}\n"
                f"🔢 请求索引: {frame_idx}\n"
                f"📊 可用范围: 0-{len(actions)-1}"
            )
        
        action_array = actions[frame_idx]
        
        # 检查数组维度
        if len(action_array) == 0:
            error_msg = (
                f"❌ MCAP动作数组为空\n"
                f"🎯 话题: {mcap_topic}\n"
                f"🔢 帧索引: {frame_idx}\n"
                f"💡 可能是消息解码失败或消息格式不正确"
            )
            if self.logger:
                self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 处理切片范围：如果数据长度小于配置的range_to，使用实际长度并用零填充
        actual_range_to = range_to
        if range_to is not None and range_to > len(action_array):
            if self.logger:
                self.logger.warning(
                    f"⚠️  MCAP动作数据长度不足，将用零填充\n"
                    f"   话题: {mcap_topic}\n"
                    f"   帧索引: {frame_idx}\n"
                    f"   配置切片: [{range_from}:{range_to}]\n"
                    f"   实际数组长度: {len(action_array)}\n"
                    f"   将使用: [{range_from}:{len(action_array)}] + 零填充"
                )
            actual_range_to = len(action_array)
        
        # 提取数据
        if actual_range_to is not None:
            result = action_array[range_from:actual_range_to]
        else:
            result = action_array[range_from:]
        
        # 如果维度不足，用零填充到期望维度
        if expected_dim is not None and len(result) < expected_dim:
            padding_size = expected_dim - len(result)
            result = np.pad(
                result, 
                (0, padding_size), 
                mode='constant', 
                constant_values=0.0
            )
            if self.logger and frame_idx == 0:  # 只在第一帧记录，避免日志过多
                self.logger.warning(
                    f"⚠️  MCAP动作维度不足，已用零填充\n"
                    f"   话题: {mcap_topic}\n"
                    f"   原始维度: {len(action_array[range_from:actual_range_to])}\n"
                    f"   期望维度: {expected_dim}\n"
                    f"   填充后维度: {len(result)}\n"
                    f"   (此警告只显示一次)"
                )
        elif expected_dim is not None and len(result) > expected_dim:
            # 如果维度超出，截断
            result = result[:expected_dim]
            if self.logger and frame_idx == 0:
                self.logger.warning(
                    f"⚠️  MCAP动作维度超出，已截断\n"
                    f"   话题: {mcap_topic}\n"
                    f"   原始维度: {len(action_array[range_from:actual_range_to])}\n"
                    f"   期望维度: {expected_dim}\n"
                    f"   截断后维度: {len(result)}\n"
                    f"   (此警告只显示一次)"
                )
        
        return result

    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 MCAP episode 的源文件信息"""
        try:
            mcap_file = self._get_mcap_file(task_path, ep_idx)
            if mcap_file and mcap_file.exists():
                return {
                    "format": "MCAP",
                    "mcap_file": str(mcap_file.relative_to(self.dataset_path)),
                    "absolute_path": str(mcap_file.absolute()),
                }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        return {}

    def _cleanup_episode_resources(self):
        """清理episode资源（释放MCAP buffer）"""
        self.mcap_buffer.mcap_data = None
        self.mcap_buffer.task_path = None
        self.mcap_buffer.ep_idx = None


# 别名，用于配置文件中的类名引用
LerobotFormatConverterLiteMcap = RBMCAPToLeRobotConverter
