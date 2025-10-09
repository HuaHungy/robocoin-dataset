import logging
from pathlib import Path
from typing import Any
import numpy as np
import io
from mcap.reader import make_reader
from rosbags.typesys import Stores, get_typestore, get_types_from_msg

from robocoin_dataset.format_converter.tolerobot.constant import (
    FEATURES_KEY, OBSERVATION_KEY, IMAGE_KEY, STATE_KEY, SUB_STATE_KEY,
    ACTION_KEY, SUB_ACTION_KEY, ARGS_KEY, CAM_NAME_KEY, NAME_KEY, LEROBOT_FEATURE_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import LerobotFormatConverter

try:
    from PIL import Image
except ImportError:
    Image = None

def decode_image_bytes(img_bytes: bytes, typestore) -> np.ndarray:
    """解码压缩的ROS图像消息
    
    Args:
        img_bytes: sensor_msgs/msg/CompressedImage消息的CDR字节
        typestore: ROS typestore用于反序列化
    
    Returns:
        np.ndarray: RGB图像数组
    """
    if Image is None:
        raise ImportError("PIL is required for image decoding.")
    
    # 反序列化CompressedImage消息
    try:
        compressed_img_msg = typestore.deserialize_cdr(img_bytes, 'sensor_msgs/msg/CompressedImage')
        # compressed_img_msg.data包含JPEG/PNG压缩的图像字节
        img_data = bytes(compressed_img_msg.data)
        with Image.open(io.BytesIO(img_data)) as img:
            return np.array(img.convert("RGB"))
    except Exception as e:
        # 如果解码失败，返回None
        return None

def find_nearest_msg(msgs, target_time):
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
    else:
        return msgs[pos][1]

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
        self._episode_data_cache = {}
        
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

    def _get_dataset_task_paths(self) -> dict[Path, str]:
        """重写基类方法：扫描dataset_path下包含.mcap文件的子目录作为task"""
        from pathlib import Path
        import yaml
        
        task_paths_dict = {}
        
        # 读取dataset根目录的local_task_info.yaml获取task_index
        local_task_info_path = self.dataset_path / "local_task_info.yaml"
        if not local_task_info_path.exists():
            raise FileNotFoundError(f"local_task_info.yaml not found in {self.dataset_path}")
        
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
            raise FileNotFoundError(f"No directories with .mcap files found in {self.dataset_path}")
        
        return task_paths_dict

    def _prevalidate_files(self) -> None:
        for path in self.path_task_dict.keys():
            mcap_files = list(path.rglob("*.mcap"))
            if not mcap_files:
                raise FileNotFoundError(f"No .mcap files found in {path}")

    def _get_episode_mcap_file(self, task_path: Path, ep_idx: int) -> Path:
        # 先在任务路径下查找mcap文件
        mcap_files = sorted(list(task_path.glob("*.mcap")))
        # 如果没找到，在子目录中递归查找
        if not mcap_files:
            mcap_files = sorted(list(task_path.rglob("*.mcap")))
        if ep_idx >= len(mcap_files):
            raise IndexError(f"Episode index {ep_idx} out of range for {task_path}")
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

    def _parse_mcap_episode(self, mcap_file: Path) -> dict[str, Any]:
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

        self.logger.info(f"Parsing MCAP file: {mcap_file.name}")
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
        frames = len(main_joint_msgs)
        main_times = [t for t, _ in main_joint_msgs]

        self.logger.info(f"Starting to decode {frames} frames with {len(image_topics)} cameras")
        
        # 解析图片（对齐主topic时间戳）
        images = {cam: [] for cam in image_topics.values()}
        decode_progress_step = max(1, frames // 10)  # 每10%记录一次
        
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
        
        self.logger.info(f"Finished decoding all images")

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
                    # JointState类型
                    if 'joint_states' in topic or 'gripper_pos' in topic:
                        js = self.typestore.deserialize_cdr(data, 'sensor_msgs/msg/JointState')
                        sub_data = np.array(js.position[from_idx:to_idx], dtype=np.float32)
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
                    if 'joint_states' in topic or 'gripper_pos' in topic:
                        js = self.typestore.deserialize_cdr(data, 'sensor_msgs/msg/JointState')
                        sub_data = np.array(js.position[from_idx:to_idx], dtype=np.float32)
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
        """获取episode数据，使用缓存避免重复解析"""
        cache_key = (str(task_path), ep_idx)
        if cache_key not in self._episode_data_cache:
            mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
            self._episode_data_cache[cache_key] = self._parse_mcap_episode(mcap_file)
        return self._episode_data_cache[cache_key]

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> Any:
        episode_data = self._get_episode_data(task_path, ep_idx)
        return episode_data["images"]

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> Any:
        episode_data = self._get_episode_data(task_path, ep_idx)
        return episode_data["states"]

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> Any:
        episode_data = self._get_episode_data(task_path, ep_idx)
        return episode_data["actions"]

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        episode_data = self._get_episode_data(task_path, ep_idx)
        return episode_data["frames"]

    def _get_task_episodes_num(self, task_path: Path) -> int:
        return len(list(task_path.glob("*.mcap")))
    
    def _gen_image_configs(self) -> None:
        """重写图像配置生成，使用快速样本获取避免解析整个MCAP文件"""
        # 获取第一个任务的第一个episode
        first_task_path = list(self.path_task_dict.keys())[0]
        mcap_file = self._get_episode_mcap_file(first_task_path, 0)
        
        # 快速获取图像样本
        sample_images = self._get_first_frame_sample(mcap_file)
        
        # 配置图像信息
        from robocoin_dataset.format_converter.tolerobot.constant import (
            DTYPE_KEY, IMAGE_DTYPE_VALUE, NAME_KEY, SHAPE_KEY,
            DEFAULT_IMAGE_SHAPE_NAMES
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
                raise ValueError(f"Camera {cam_name} not found in MCAP file sample")

    def _get_frame_image(self, task_path: Path, ep_idx: int, frame_idx: int, args_dict: dict, images_buffer: Any = None) -> np.ndarray:
        cam_name = args_dict.get("cam_name")
        if images_buffer is None:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)
        return images_buffer[cam_name][frame_idx]

    def _get_frame_sub_states(self, task_path: Path, ep_idx: int, frame_idx: int, args_dict: dict, sub_states_buffer: Any = None) -> np.ndarray:
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        return sub_states_buffer[frame_idx][from_idx:to_idx]

    def _get_frame_sub_actions(self, task_path: Path, ep_idx: int, frame_idx: int, args_dict: dict, sub_actions_buffer: Any = None) -> np.ndarray:
        if sub_actions_buffer is None:
            sub_actions_buffer = self._prepare_episode_actions_buffer(task_path, ep_idx)
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        return sub_actions_buffer[frame_idx][from_idx:to_idx]