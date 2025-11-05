import io
import logging
from pathlib import Path
from typing import Any

import numpy as np
from mcap.reader import make_reader
from rosbags.typesys import Stores, get_types_from_msg, get_typestore

from robocoin_dataset.format_converter.tolerobot.constant import (
    ACTION_KEY,
    CAM_NAME_KEY,
    FEATURES_KEY,
    IMAGE_KEY,
    LEROBOT_FEATURE_KEY,
    OBSERVATION_KEY,
    STATE_KEY,
    SUB_ACTION_KEY,
    SUB_STATE_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)

try:
    from PIL import Image
except ImportError:
    Image = None

def decode_image_bytes(img_bytes: bytes, typestore) -> np.ndarray:  # noqa: ANN001
    """解码压缩的ROS图像消息
    
    Args:
        img_bytes: sensor_msgs/msg/CompressedImage消息的CDR字节
        typestore: ROS typestore用于反序列化
    
    Returns:
        np.ndarray: RGB图像数组
    """
    if Image is None:
        raise ImportError(
            "❌ MCAP图像解码失败：PIL库未安装\n"
            "📦 缺失依赖：Pillow (PIL)\n"
            "🔧 解决方法：\n"
            "   pip install Pillow\n"
            "   或\n"
            "   pip install robocoin-dataset[mcap]\n"
            "💡 说明：MCAP格式使用CompressedImage消息，需要PIL解码JPEG/PNG图像"
        )
    
    # 反序列化CompressedImage消息
    try:
        compressed_img_msg = typestore.deserialize_cdr(img_bytes, 'sensor_msgs/msg/CompressedImage')
        # compressed_img_msg.data包含JPEG/PNG压缩的图像字节
        img_data = bytes(compressed_img_msg.data)
        with Image.open(io.BytesIO(img_data)) as img:
            return np.array(img.convert("RGB"))
    except Exception:
        # 如果解码失败，返回None
        return None

def find_nearest_msg(msgs, target_time):  # noqa: ANN001, ANN201
    # msgs: list of (log_time, data)
    # 返回最近时间的消息，使用二分查找优化性能
    if not msgs:
        return None
    
    import bisect
    
    # 提取时间戳（假设msgs已按时间排序）
    times = [t for t, _ in msgs]
    
    # 使用二分查找找到最近的消息
    pos = bisect.bisect_left(times, target_time)
    
    if pos == 0:
        return msgs[0][1]
    if pos == len(msgs):
        return msgs[-1][1]
    
    # 比较前后两个时间戳，返回更近的那个
    before = times[pos - 1]
    after = times[pos]
    
    if abs(target_time - before) <= abs(after - target_time):
        return msgs[pos - 1][1]
    return msgs[pos][1]


def parse_cdr_joint_state(data: bytes) -> dict | None:
    """手动解析CDR格式的JointState消息（绕过rosbags bug）
    
    Args:
        data: CDR格式的消息字节
        
    Returns:
        包含 position/velocity/effort 的dict，解析失败返回None
    """
    import struct
    
    try:
        offset = 0
        
        # Skip CDR header (4 bytes)
        offset += 4
        
        # Parse Header
        # timestamp (8 bytes sec + 4 bytes nanosec)
        offset += 4  # sec
        offset += 4  # nanosec
        
        # frame_id string length + data
        frame_id_len = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        offset += frame_id_len
        # Align to 4 bytes
        while offset % 4 != 0:
            offset += 1
        
        # Parse name array (skip it)
        name_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        for _ in range(name_count):
            name_len = struct.unpack_from('<I', data, offset)[0]
            offset += 4
            offset += name_len
            # Align to 4 bytes
            while offset % 4 != 0:
                offset += 1
        
        # Parse position array
        pos_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        positions = []
        for _ in range(pos_count):
            pos = struct.unpack_from('<d', data, offset)[0]  # double (8 bytes)
            positions.append(pos)
            offset += 8
        
        # Parse velocity array
        vel_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        velocities = []
        for _ in range(vel_count):
            vel = struct.unpack_from('<d', data, offset)[0]
            velocities.append(vel)
            offset += 8
        
        # Parse effort array
        eff_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        efforts = []
        for _ in range(eff_count):
            eff = struct.unpack_from('<d', data, offset)[0]
            efforts.append(eff)
            offset += 8
        
        return {
            'position': positions,
            'velocity': velocities,
            'effort': efforts
        }
    except Exception:
        return None

class LerobotFormatConverterRealmanRmcAidalMcap(LerobotFormatConverter):
    def __init__(
        self,
        dataset_path: str,
        output_path: str,
        converter_config: dict,
        repo_id: str,
        device_model: str,
        logger: logging.Logger | None = None,
        video_backend: str = "pyav",
        image_writer_processes: int = 4,
        image_writer_threads: int = 4,
    ) -> None:
        # 在调用super().__init__之前初始化typestore
        self.typestore = get_typestore(Stores.ROS2_FOXY)
        
        # 注册自定义消息类型
        self._register_custom_msg_types()
        
        # 添加episode数据缓存
        # ⚠️ 警告：MCAP缓存仅用于小文件（<100MB），大文件直接解析不缓存
        # 每个episode完成后会清理缓存，避免内存泄漏
        self._episode_data_cache = {}
        self._current_episode_cache_key = None  # 🆕 跟踪当前episode的缓存key
        
        # Test 模式标志（用于限制帧数）
        self._is_test_mode = False
        self._test_mode_frames = 10  # test 模式下处理的帧数
        
        super().__init__(
            dataset_path=dataset_path,
            output_path=output_path,
            converter_config=converter_config,
            repo_id=repo_id,
            device_model=device_model,
            logger=logger,
            video_backend=video_backend,
            image_writer_processes=image_writer_processes,
            image_writer_threads=image_writer_threads,
        )

    def _register_custom_msg_types(self) -> None:
        """注册自定义ROS消息类型"""
        # 注册 rm_ros_interfaces 消息类型
        # 这些消息类型从MCAP文件的schema中提取
        
        msg_definitions = {
            'rm_ros_interfaces/msg/Jointposeorientation': """
std_msgs/Header header
geometry_msgs/Pose pose
""",
            'rm_ros_interfaces/msg/Jointspeed': """
std_msgs/Header header
float32[] joint_speed
""",
            'rm_ros_interfaces/msg/Jointacc': """
std_msgs/Header header
float32[] joint_acc
""",
            'rm_ros_interfaces/msg/Sixforce': """
std_msgs/Header header
float32 force_fx
float32 force_fy
float32 force_fz
float32 force_mx
float32 force_my
float32 force_mz
""",
            'rm_ros_interfaces/msg/Rmplusstate': """
std_msgs/Header header
int32 sys_state
int32[12] dof_state
int32[12] dof_err
int32[12] pos
int32[12] speed
int32[12] angle
int32[12] current
int32[18] normal_force
int32[18] tangential_force
int32[18] tangential_force_dir
uint32[12] tsa
uint32[12] tma
int32[18] touch_data
int32[12] force
""",
            'rm_ros_interfaces/msg/Liftpos': """
std_msgs/Header header
int32 lift_pos
""",
        }
        
        try:
            # 使用get_types_from_msg解析每个消息定义并注册
            for msg_name, msg_text in msg_definitions.items():
                msg_types = get_types_from_msg(msg_text, msg_name)
                self.typestore.register(msg_types)
        except Exception:
            # 如果已注册则忽略
            pass

    def convert(self, is_test: bool = False):  # noqa: ANN201
        """重写 convert 方法以设置 test 模式标志"""
        self._is_test_mode = is_test
        yield from super().convert(is_test=is_test)

    def _get_dataset_task_paths(self) -> dict[Path, str]:
        """重写基类方法：扫描dataset_path下包含.mcap文件的子目录作为task"""

        import yaml
        
        task_paths_dict = {}
        
        # 读取dataset根目录的local_task_info.yaml获取task_index
        local_task_info_path = self.dataset_path / "local_task_info.yaml"
        if not local_task_info_path.exists():
            raise FileNotFoundError(
                f"❌ MCAP数据集配置文件缺失\n"
                f"📁 数据集路径：{self.dataset_path}\n"
                f"📄 缺失文件：local_task_info.yaml\n"
                f"🔍 搜索位置：{local_task_info_path}\n"
                f"💡 该文件应包含：\n"
                f"   - task_index: 任务索引\n"
                f"   - 其他任务相关配置\n"
                f"📋 请确保数据集根目录包含此配置文件"
            )
        
        with open(local_task_info_path) as f:
            task_info_dict = yaml.safe_load(f)
            task_index = task_info_dict["task_index"]
            task = self.tasks[task_index]
        
        # 扫描dataset_path下的所有子目录，查找包含.mcap文件的目录
        for subdir in self.dataset_path.iterdir():
            if subdir.is_dir():
                mcap_files = list(subdir.glob("*.mcap"))
                if mcap_files:
                    # 找到包含.mcap文件的子目录，将其作为task_path
                    task_paths_dict[subdir] = task
                    self.logger.info(f"Found task path: {subdir} with {len(mcap_files)} mcap files")
        
        if not task_paths_dict:
            # 统计目录结构信息
            total_subdirs = sum(1 for p in self.dataset_path.iterdir() if p.is_dir())
            all_files = list(self.dataset_path.rglob("*"))
            file_types = {}
            for f in all_files:
                if f.is_file():
                    ext = f.suffix or "(无扩展名)"
                    file_types[ext] = file_types.get(ext, 0) + 1
            
            raise FileNotFoundError(
                f"❌ MCAP数据集目录结构错误：未找到包含MCAP文件的子目录\n"
                f"📁 数据集路径：{self.dataset_path}\n"
                f"🗂️ 目录结构统计：\n"
                f"   - 子目录数量：{total_subdirs}\n"
                f"   - 文件类型分布：{dict(sorted(file_types.items(), key=lambda x: x[1], reverse=True))}\n"
                f"🎯 期望结构：\n"
                f"   dataset/\n"
                f"   ├── local_task_info.yaml\n"
                f"   ├── episode_001/\n"
                f"   │   └── data.mcap\n"
                f"   └── episode_002/\n"
                f"       └── data.mcap\n"
                f"💡 每个episode应该在单独的子目录中，包含至少一个.mcap文件"
            )
        
        return task_paths_dict

    def _prevalidate_files(self) -> None:
        # 🆕 增加：验证所有path存在性
        for path in self.path_task_dict.keys():
            if not path.exists():
                # 显示父目录内容
                parent_dir = path.parent
                siblings = []
                if parent_dir.exists():
                    siblings = [d.name for d in parent_dir.iterdir() if d.is_dir()]
                    if len(siblings) > 15:
                        siblings = siblings[:15] + [f"... ({len(siblings) - 15} more)"]
                
                raise FileNotFoundError(
                    f"❌ Task path does not exist\n"
                    f"   📂 Task path: {path}\n"
                    f"   📂 Parent directory: {parent_dir}\n"
                    f"   📋 Available directories in parent:\n"
                    f"      {', '.join(siblings) if siblings else 'Parent directory not found'}\n"
                    f"   💡 Please check:\n"
                    f"      1. Path is correct in configuration\n"
                    f"      2. Dataset has been downloaded/extracted\n"
                    f"      3. No typos in directory names"
                )
            
            if not path.is_dir():
                raise NotADirectoryError(
                    f"❌ Task path exists but is not a directory\n"
                    f"   📂 Path: {path}\n"
                    f"   📋 Type: {('file' if path.is_file() else 'unknown')}\n"
                    f"   💡 Task path must be a directory containing MCAP files"
                )
        
        for path in self.path_task_dict.keys():
            mcap_files = list(path.rglob("*.mcap"))
            if not mcap_files:
                # 收集目录信息
                all_files = list(path.rglob("*"))
                file_count = sum(1 for f in all_files if f.is_file())
                dir_count = sum(1 for d in all_files if d.is_dir())
                file_extensions = set(f.suffix for f in all_files if f.is_file() and f.suffix)
                
                raise FileNotFoundError(
                    f"❌ Episode目录验证失败：缺少MCAP文件\n"
                    f"📁 Episode路径：{path}\n"
                    f"📊 目录内容统计：\n"
                    f"   - 文件数量：{file_count}\n"
                    f"   - 子目录数量：{dir_count}\n"
                    f"   - 文件扩展名：{sorted(file_extensions) if file_extensions else '(无)'}\n"
                    f"🔍 搜索范围：递归搜索所有子目录\n"
                    f"💡 MCAP格式要求：\n"
                    f"   - 每个episode目录必须包含至少一个.mcap文件\n"
                    f"   - 文件可以在任意深度的子目录中\n"
                    f"📋 请检查：\n"
                    f"   1. 文件扩展名是否正确（.mcap）\n"
                    f"   2. 文件是否在正确的目录中\n"
                    f"   3. 是否已完成数据录制"
                )
            
            # 🆕 增加：验证第一个MCAP文件可读性
            try:
                from mcap.reader import make_reader
                first_mcap = mcap_files[0]
                with open(first_mcap, "rb") as f:
                    reader = make_reader(f)
                    summary = reader.get_summary()
                    if summary:
                        self.logger.info(
                            f"✅ MCAP文件验证通过：{first_mcap.name}\n"
                            f"   - 文件大小：{first_mcap.stat().st_size / 1024 / 1024:.2f} MB\n"
                            f"   - 消息数量：{summary.statistics.message_count if summary.statistics else 'N/A'}\n"
                            f"   - 通道数量：{len(summary.channels) if summary.channels else 'N/A'}"
                        )
                    else:
                        self.logger.warning(
                            f"⚠️ MCAP文件无摘要信息\n"
                            f"📄 文件：{first_mcap}\n"
                            "💡 文件可能为空或格式不完整"
                        )
            except ImportError:
                self.logger.warning("⚠️ mcap库未安装，跳过MCAP文件内容验证")
            except Exception as e:
                self.logger.warning(
                    f"⚠️ 无法读取MCAP文件\n"
                    f"📄 文件：{first_mcap}\n"
                    f"⚠️ 错误：{str(e)}\n"
                    "💡 请检查MCAP文件是否损坏"
                )

    def _get_all_mcap_files(self, task_path: Path) -> list[Path]:
        """获取task下所有MCAP文件（统一的方法）
        
        策略：
        1. 先查找task_path同级的.mcap文件
        2. 如果没有，递归查找子目录
        3. 排除特定目录
        """
        skip_dirs = {
            'record', 'calibration', 'config', 'parameters', 
            'logs', 'error', '@eaDir', '__pycache__', '.git'
        }
        
        # 先尝试扁平结构
        mcap_files = list(task_path.glob("*.mcap"))
        
        if not mcap_files:
            # 递归查找
            all_mcap_files = list(task_path.rglob("*.mcap"))
            
            # 过滤排除目录
            mcap_files = []
            for mcap_file in all_mcap_files:
                relative_path = mcap_file.relative_to(task_path)
                path_parts = set(relative_path.parts[:-1])
                
                if path_parts & skip_dirs:
                    continue
                if any(part.startswith('.') or part.startswith('@') for part in relative_path.parts):
                    continue
                
                mcap_files.append(mcap_file)
        
        return sorted(mcap_files)

    def _get_episode_mcap_file(self, task_path: Path, ep_idx: int) -> Path:
        # 使用统一的方法获取所有mcap文件
        mcap_files = self._get_all_mcap_files(task_path)
        if ep_idx >= len(mcap_files):
            raise IndexError(
                f"❌ Episode索引超出范围\n"
                f"📁 任务路径：{task_path}\n"
                f"🔢 请求索引：{ep_idx}\n"
                f"📊 可用范围：0 到 {len(mcap_files) - 1} (共{len(mcap_files)}个文件)\n"
                f"📋 可用的MCAP文件：\n" +
                "\n".join(f"   [{i}] {f.name}" for i, f in enumerate(mcap_files[:10])) +
                (f"\n   ... 还有 {len(mcap_files) - 10} 个文件" if len(mcap_files) > 10 else "") +
                "\n💡 请检查：\n"
                "   1. Episode索引是否从0开始计数\n"
                "   2. 是否所有episode都已录制完成\n"
                "   3. 配置文件中的episode数量是否正确"
            )
        return mcap_files[ep_idx]

    def _get_first_frame_sample(self, mcap_file: Path) -> dict[str, np.ndarray]:
        """快速获取第一帧的图像样本，用于初始化时检测图像尺寸
        
        只读取足够的消息来获取一个完整帧，避免读取整个文件
        """
        image_topics = {img['args']['mcap_topic']: img['cam_name']
                        for img in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]}
        
        # 只需要获取每个相机的第一张图像
        sample_images = {}
        found_topics = set()
        
        with open(mcap_file, "rb") as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages():
                topic = channel.topic
                if topic in image_topics and topic not in found_topics:
                    cam_name = image_topics[topic]
                    img_arr = decode_image_bytes(message.data, self.typestore)
                    if img_arr is not None:
                        sample_images[cam_name] = img_arr
                        found_topics.add(topic)
                    
                    # 如果所有相机都找到了，停止读取
                    if len(found_topics) == len(image_topics):
                        break
        
        return sample_images

    def _parse_mcap_episode(self, mcap_file: Path, max_frames: int | None = None) -> dict[str, Any]:
        """解析 MCAP episode 数据
        
        Args:
            mcap_file: MCAP 文件路径
            max_frames: 最多解析的帧数。None表示解析全部帧（默认）
        
        Returns:
            包含 images/states/actions/frames 的dict
        """
        # 🆕 内存警告：检查文件大小
        file_size_gb = mcap_file.stat().st_size / (1024**3)
        if file_size_gb > 2.0 and max_frames is None:
            if self.logger:
                self.logger.warning(
                    f"⚠️  ⚠️  ⚠️  警告：正在解析大型MCAP文件！\n"
                    f"📄 文件: {mcap_file.name}\n"
                    f"📊 大小: {file_size_gb:.2f} GB\n"
                    f"💾 预计内存占用: ~{file_size_gb * 2:.2f} GB (可能导致系统卡死)\n"
                    f"💡 建议：\n"
                    f"   1. 使用 --is-test 模式先测试（只处理10帧）\n"
                    f"   2. 确保系统有足够内存（建议 >{file_size_gb * 3:.0f}GB）\n"
                    f"   3. 考虑分割大文件\n"
                    f"⏱️  继续执行，这可能需要很长时间..."
                )
        
        # 读取所有topic消息
        image_topics = {img['args']['mcap_topic']: img['cam_name']
                        for img in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]}
        state_subs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][SUB_STATE_KEY]
        action_subs = self.converter_config[FEATURES_KEY][ACTION_KEY][SUB_ACTION_KEY]

        # 收集所有消息
        topic_msgs = {topic: [] for topic in image_topics.keys()}
        for sub in state_subs + action_subs:
            topic = sub['args']['mcap_topic']
            topic_msgs.setdefault(topic, [])

        mode_str = f"(TEST MODE: max {max_frames} frames)" if max_frames else "(FULL MODE: all frames)"
        self.logger.info(f"Parsing MCAP file: {mcap_file.name} {mode_str}")
        with open(mcap_file, "rb") as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages():
                topic = channel.topic
                if topic in topic_msgs:
                    topic_msgs[topic].append((message.log_time, message.data))
        
        self.logger.info(f"Finished reading MCAP file, collected {sum(len(msgs) for msgs in topic_msgs.values())} messages")

        # 主对齐topic（如右臂关节）
        main_joint_topic = state_subs[0]['args']['mcap_topic']
        main_joint_msgs = topic_msgs[main_joint_topic]
        total_frames = len(main_joint_msgs)
        
        # 限制解析帧数（test模式用）
        frames = min(max_frames, total_frames) if max_frames else total_frames
        main_times = [t for t, _ in main_joint_msgs[:frames]]

        decode_mode = f"(TEST MODE: {frames}/{total_frames} frames)" if max_frames else f"({frames} frames total)"
        self.logger.info(f"Starting to decode {frames} frames with {len(image_topics)} cameras {decode_mode}")
        
        # 解析图片（对齐主topic时间戳）
        images = {cam: [] for cam in image_topics.values()}
        decode_progress_step = max(1, frames // 10) if frames >= 10 else 1  # 每10%记录一次
        
        for i, t in enumerate(main_times):
            if i % decode_progress_step == 0:
                self.logger.info(f"Decoding images: {i}/{frames} frames ({100*i//frames}%)")
            
            for topic, cam_name in image_topics.items():
                img_bytes = find_nearest_msg(topic_msgs[topic], t)
                if img_bytes is not None:
                    try:
                        img_arr = decode_image_bytes(img_bytes, self.typestore)
                    except Exception:
                        img_arr = None
                    images[cam_name].append(img_arr)
                else:
                    images[cam_name].append(None)
        
        self.logger.info("Finished decoding all images")

        # 解析状态
        # 注意：这里只提取原始数据，不应用convert_func
        # convert_func会在基类的_get_frame_states中统一应用
        
        states = []
        for i, t in enumerate(main_times):
            state_vec = []
            for sub in state_subs:
                topic = sub['args']['mcap_topic']
                from_idx = sub['args']['range_from']
                to_idx = sub['args']['range_to']
                
                data = find_nearest_msg(topic_msgs[topic], t)
                if data is not None:
                    # JointState类型 - 使用手动CDR解析（绕过rosbags bug）
                    if 'joint_states' in topic or 'gripper_pos' in topic:
                        js_dict = parse_cdr_joint_state(data)
                        if js_dict and js_dict['position']:
                            sub_data = np.array(js_dict['position'][from_idx:to_idx], dtype=np.float32)
                        else:
                            # 如果手动解析失败，尝试rosbags
                            try:
                                js = self.typestore.deserialize_cdr(data, 'sensor_msgs/msg/JointState')
                                sub_data = np.array(js.position[from_idx:to_idx], dtype=np.float32)
                            except Exception:
                                sub_data = np.array([np.nan] * (to_idx - from_idx), dtype=np.float32)
                    elif 'udp_arm_position' in topic:
                        pose = self.typestore.deserialize_cdr(data, 'rm_ros_interfaces/msg/Jointposeorientation')
                        pos = np.array([pose.pose.position.x, pose.pose.position.y, pose.pose.position.z], dtype=np.float32)
                        quat = np.array([pose.pose.orientation.x, pose.pose.orientation.y, 
                                       pose.pose.orientation.z, pose.pose.orientation.w], dtype=np.float32)
                        # 判断是否取位置还是旋转
                        # 注意：配置中range_from/to是相对于整个pose vector的
                        # 对于位置：range_from=0, range_to=3
                        # 对于旋转：range_from=3, range_to=7 (四元数4个值！)
                        if from_idx < 3:
                            # 位置数据
                            sub_data = pos[from_idx:min(to_idx, 3)]
                        else:
                            # 旋转数据 (四元数)
                            # 将四元数作为原始数据提取，让基类应用convert_func
                            sub_data = quat[from_idx-3:to_idx-3]
                    elif 'udp_six_force' in topic:
                        # 六维力传感器
                        six_force = self.typestore.deserialize_cdr(data, 'rm_ros_interfaces/msg/Sixforce')
                        force_data = np.array([
                            six_force.force_fx, six_force.force_fy, six_force.force_fz,
                            six_force.force_mx, six_force.force_my, six_force.force_mz
                        ], dtype=np.float32)
                        sub_data = force_data[from_idx:to_idx]
                    else:
                        sub_data = np.array([np.nan] * (to_idx - from_idx), dtype=np.float32)
                    
                    state_vec.extend(sub_data.tolist() if isinstance(sub_data, np.ndarray) else sub_data)
                else:
                    state_vec.extend([np.nan] * (to_idx - from_idx))
            states.append(np.array(state_vec, dtype=np.float32))

        # 解析动作（同状态）
        # 注意：这里只提取原始数据，不应用convert_func
        # convert_func会在基类的_get_frame_actions中统一应用
        
        actions = []
        for i, t in enumerate(main_times):
            action_vec = []
            for sub in action_subs:
                topic = sub['args']['mcap_topic']
                from_idx = sub['args']['range_from']
                to_idx = sub['args']['range_to']
                
                data = find_nearest_msg(topic_msgs[topic], t)
                if data is not None:
                    # JointState类型 - 使用手动CDR解析（绕过rosbags bug）
                    if 'joint_states' in topic or 'gripper_pos' in topic:
                        js_dict = parse_cdr_joint_state(data)
                        if js_dict and js_dict['position']:
                            sub_data = np.array(js_dict['position'][from_idx:to_idx], dtype=np.float32)
                        else:
                            # 如果手动解析失败，尝试rosbags
                            try:
                                js = self.typestore.deserialize_cdr(data, 'sensor_msgs/msg/JointState')
                                sub_data = np.array(js.position[from_idx:to_idx], dtype=np.float32)
                            except Exception:
                                sub_data = np.array([np.nan] * (to_idx - from_idx), dtype=np.float32)
                    elif 'udp_arm_position' in topic:
                        pose = self.typestore.deserialize_cdr(data, 'rm_ros_interfaces/msg/Jointposeorientation')
                        pos = np.array([pose.pose.position.x, pose.pose.position.y, pose.pose.position.z], dtype=np.float32)
                        quat = np.array([pose.pose.orientation.x, pose.pose.orientation.y, 
                                       pose.pose.orientation.z, pose.pose.orientation.w], dtype=np.float32)
                        # 判断是否取位置还是旋转
                        if from_idx < 3:
                            # 位置数据
                            sub_data = pos[from_idx:min(to_idx, 3)]
                        else:
                            # 旋转数据 (四元数)
                            sub_data = quat[from_idx-3:to_idx-3]
                    else:
                        sub_data = np.array([np.nan] * (to_idx - from_idx), dtype=np.float32)
                    
                    action_vec.extend(sub_data.tolist() if isinstance(sub_data, np.ndarray) else sub_data)
                else:
                    action_vec.extend([np.nan] * (to_idx - from_idx))
            actions.append(np.array(action_vec, dtype=np.float32))

        return {
            "images": images,
            "states": states,
            "actions": actions,
            "frames": frames,
        }

    def _get_episode_data(self, task_path: Path, ep_idx: int) -> dict:
        """获取episode数据，使用缓存避免重复解析
        
        ⚠️ 对于大文件（>1GB）禁用缓存以避免内存溢出
        """
        cache_key = (str(task_path), ep_idx)
        mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
        
        # 检查文件大小
        file_size_gb = mcap_file.stat().st_size / (1024**3)
        use_cache = file_size_gb < 1.0  # 只对小于1GB的文件使用缓存
        
        if not use_cache:
            if self.logger:
                self.logger.warning(
                    f"⚠️  MCAP文件较大，禁用缓存避免内存溢出\n"
                    f"📄 文件: {mcap_file.name}\n"
                    f"📊 大小: {file_size_gb:.2f} GB\n"
                    f"💡 提示: 大文件转换可能需要较长时间"
                )
            # 直接解析，不使用缓存
            return self._parse_mcap_episode(mcap_file)
        
        # 小文件使用缓存
        if cache_key not in self._episode_data_cache:
            self._episode_data_cache[cache_key] = self._parse_mcap_episode(mcap_file)
        
        # 🆕 记录当前episode的缓存key（用于后续清理）
        self._current_episode_cache_key = cache_key
        
        return self._episode_data_cache[cache_key]

    def _clear_episode_cache(self) -> None:
        """清理当前episode的缓存，释放内存
        
        🔧 内存管理：每个episode转换完成后调用此方法
        避免内存累积导致OOM
        """
        if self._current_episode_cache_key and self._current_episode_cache_key in self._episode_data_cache:
            # 获取缓存大小（估算）
            cached_data = self._episode_data_cache[self._current_episode_cache_key]
            if self.logger:
                # 简单估算内存占用（图像数量 * 相机数 * 分辨率）
                if 'images' in cached_data:
                    num_cameras = len(cached_data['images'])
                    num_frames = len(next(iter(cached_data['images'].values()))) if cached_data['images'] else 0
                    estimated_mb = num_cameras * num_frames * 0.5  # 假设每帧约0.5MB
                    self.logger.debug(
                        f"🧹 清理episode缓存: {self._current_episode_cache_key} "
                        f"(约 {estimated_mb:.1f} MB)"
                    )
            
            # 删除缓存
            del self._episode_data_cache[self._current_episode_cache_key]
            self._current_episode_cache_key = None
            
            # 强制垃圾回收（对于大对象很重要）
            import gc
            gc.collect()
    
    def _get_episode_data_minimal(self, task_path: Path, ep_idx: int, max_frames: int = 10) -> dict:
        """Test 模式专用：只解析前 N 帧数据，用于快速验证
        
        Args:
            task_path: 任务路径
            ep_idx: episode索引
            max_frames: 最多解析的帧数（默认10帧）
            
        Returns:
            包含 images/states/actions 的dict，但只有前 max_frames 帧
        """
        mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
        return self._parse_mcap_episode(mcap_file, max_frames=max_frames)
    
    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> Any:  # noqa: ANN401
        if is_test:
            # Test 模式：只解析前N帧（需要考虑 timeline_offset）
            from robocoin_dataset.format_converter.tolerobot.constant import (
                ACTION_KEY,
                FEATURES_KEY,
                TIMELINE_OFFSET_KEY,
            )
            
            timeline_offset = self.converter_config[FEATURES_KEY][ACTION_KEY].get(TIMELINE_OFFSET_KEY, 0)
            # 需要额外解析 timeline_offset 帧，因为action会访问未来的帧
            max_frames = 10 + timeline_offset
            episode_data = self._get_episode_data_minimal(task_path, ep_idx, max_frames=max_frames)
            return episode_data["images"]
        episode_data = self._get_episode_data(task_path, ep_idx)
        return episode_data["images"]

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> Any:  # noqa: ANN401
        if is_test:
            # Test 模式：只解析前N帧（需要考虑 timeline_offset）
            from robocoin_dataset.format_converter.tolerobot.constant import (
                ACTION_KEY,
                FEATURES_KEY,
                TIMELINE_OFFSET_KEY,
            )
            
            timeline_offset = self.converter_config[FEATURES_KEY][ACTION_KEY].get(TIMELINE_OFFSET_KEY, 0)
            max_frames = 10 + timeline_offset
            episode_data = self._get_episode_data_minimal(task_path, ep_idx, max_frames=max_frames)
            return episode_data["states"]
        episode_data = self._get_episode_data(task_path, ep_idx)
        return episode_data["states"]

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> Any:  # noqa: ANN401
        if is_test:
            # Test 模式：只解析前N帧（需要考虑 timeline_offset）
            from robocoin_dataset.format_converter.tolerobot.constant import (
                ACTION_KEY,
                FEATURES_KEY,
                TIMELINE_OFFSET_KEY,
            )
            
            timeline_offset = self.converter_config[FEATURES_KEY][ACTION_KEY].get(TIMELINE_OFFSET_KEY, 0)
            max_frames = 10 + timeline_offset
            episode_data = self._get_episode_data_minimal(task_path, ep_idx, max_frames=max_frames)
            return episode_data["actions"]
        episode_data = self._get_episode_data(task_path, ep_idx)
        return episode_data["actions"]

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """快速获取帧数，避免解析整个 MCAP 文件
        
        只统计主对齐 topic 的消息数量，不解码任何图像
        
        在 test 模式下，返回受限的帧数
        """
        # Test 模式：返回较小的帧数
        if self._is_test_mode:
            return self._test_mode_frames
        
        # 正常模式：统计完整帧数
        mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
        
        # 获取主对齐 topic（通常是关节状态）
        state_subs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][STATE_KEY][SUB_STATE_KEY]
        main_joint_topic = state_subs[0]['args']['mcap_topic']
        
        # 快速统计该 topic 的消息数量
        frame_count = 0
        with open(mcap_file, "rb") as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages(topics=[main_joint_topic]):
                frame_count += 1
        
        return frame_count

    def _get_task_episodes_num(self, task_path: Path) -> int:
        # 与_get_episode_mcap_file保持一致，使用统一的方法
        return len(self._get_all_mcap_files(task_path))
    
    def _gen_image_configs(self) -> None:
        """重写图像配置生成，使用快速样本获取避免解析整个MCAP文件"""
        # 获取第一个任务的第一个episode
        first_task_path = list(self.path_task_dict.keys())[0]
        mcap_file = self._get_episode_mcap_file(first_task_path, 0)
        
        # 快速获取图像样本
        sample_images = self._get_first_frame_sample(mcap_file)
        
        # 配置图像信息
        from robocoin_dataset.format_converter.tolerobot.constant import (
            DEFAULT_IMAGE_SHAPE_NAMES,
            DTYPE_KEY,
            IMAGE_DTYPE_VALUE,
            NAME_KEY,
            SHAPE_KEY,
        )
        
        for image_config in self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]:
            cam_name = image_config[CAM_NAME_KEY]
            image_config[LEROBOT_FEATURE_KEY] = f"{OBSERVATION_KEY}.{IMAGE_KEY}.{cam_name}"
            
            if cam_name in sample_images:
                image = sample_images[cam_name]
                image_config[DTYPE_KEY] = IMAGE_DTYPE_VALUE
                image_config[NAME_KEY] = DEFAULT_IMAGE_SHAPE_NAMES
                image_config[SHAPE_KEY] = image.shape
            else:
                available_cameras = sorted(sample_images.keys())
                raise ValueError(
                    f"❌ 相机配置错误：MCAP文件中未找到指定相机\n"
                    f"📹 请求的相机：{cam_name}\n"
                    f"📊 MCAP文件中可用的相机：\n" +
                    "\n".join(f"   - {cam}" for cam in available_cameras) +
                    (f"\n💡 相机数量：{len(available_cameras)}" if available_cameras else "\n⚠️ MCAP文件中没有任何相机数据") +
                    f"\n🔍 话题映射来源：converter_config[{FEATURES_KEY}][{OBSERVATION_KEY}][{IMAGE_KEY}]\n"
                    "📋 请检查：\n"
                    "   1. converter_config中的cam_name是否与MCAP话题匹配\n"
                    "   2. MCAP文件是否包含所有配置的相机话题\n"
                    "   3. 话题名称是否正确（mcap_topic字段）"
                )

    def _get_frame_image(self, task_path: Path, ep_idx: int, frame_idx: int, args_dict: dict, images_buffer: Any = None) -> np.ndarray:  # noqa: ANN401
        cam_name = args_dict.get("cam_name")
        if images_buffer is None:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)
        return images_buffer[cam_name][frame_idx]

    def _get_frame_sub_states(self, task_path: Path, ep_idx: int, frame_idx: int, args_dict: dict, sub_states_buffer: Any = None) -> np.ndarray:  # noqa: ANN401
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        return sub_states_buffer[frame_idx][from_idx:to_idx]

    def _get_frame_sub_actions(self, task_path: Path, ep_idx: int, frame_idx: int, args_dict: dict, sub_actions_buffer: Any = None) -> np.ndarray:  # noqa: ANN401
        if sub_actions_buffer is None:
            sub_actions_buffer = self._prepare_episode_actions_buffer(task_path, ep_idx)
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        return sub_actions_buffer[frame_idx][from_idx:to_idx]
    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 MCAP episode 的源文件信息"""
        try:
            mcap_files = self._get_all_mcap_files(task_path)
            if ep_idx < len(mcap_files):
                mcap_file = mcap_files[ep_idx]
                return {
                    "format": "MCAP",
                    "mcap_file": str(mcap_file.relative_to(self.dataset_path)),
                    "absolute_path": str(mcap_file.absolute()),
                }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        return {}

