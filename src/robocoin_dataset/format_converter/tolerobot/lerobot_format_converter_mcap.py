import logging
from pathlib import Path
from typing import Any
import numpy as np
import io
from mcap.reader import make_reader
from rosbags.typesys import Stores, get_typestore

from robocoin_dataset.format_converter.tolerobot.constant import (
    FEATURES_KEY, OBSERVATION_KEY, IMAGE_KEY, STATE_KEY, SUB_STATE_KEY,
    ACTION_KEY, SUB_ACTION_KEY, ARGS_KEY, CAM_NAME_KEY, NAME_KEY, LEROBOT_FEATURE_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import LerobotFormatConverter

try:
    from PIL import Image
except ImportError:
    Image = None

def decode_image_bytes(img_bytes: bytes) -> np.ndarray:
    if Image is None:
        raise ImportError("PIL is required for image decoding.")
    with Image.open(io.BytesIO(img_bytes)) as img:
        return np.array(img.convert("RGB"))

def find_nearest_msg(msgs, target_time):
    # msgs: list of (log_time, data)
    # 返回最近时间的消息
    if not msgs:
        return None
    times = [t for t, _ in msgs]
    idx = np.argmin(np.abs(np.array(times) - target_time))
    return msgs[idx][1]

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
        self.typestore = get_typestore(Stores.ROS2_FOXY)

    def _prevalidate_files(self) -> None:
        for path in self.path_task_dict.keys():
            mcap_files = list(path.rglob("*.mcap"))
            if not mcap_files:
                raise FileNotFoundError(f"No .mcap files found in {path}")

    def _get_episode_mcap_file(self, task_path: Path, ep_idx: int) -> Path:
        mcap_files = sorted(list(task_path.glob("*.mcap")))
        if ep_idx >= len(mcap_files):
            raise IndexError(f"Episode index {ep_idx} out of range for {task_path}")
        return mcap_files[ep_idx]

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

        with open(mcap_file, "rb") as f:
            reader = make_reader(f)
            for log_time, channel, msg in reader.iter_messages():
                topic = channel.topic
                if topic in topic_msgs:
                    topic_msgs[topic].append((log_time, msg.data))

        # 主对齐topic（如右臂关节）
        main_joint_topic = state_subs[0]['args']['mcap_topic']
        main_joint_msgs = topic_msgs[main_joint_topic]
        frames = len(main_joint_msgs)
        main_times = [t for t, _ in main_joint_msgs]

        # 解析图片（对齐主topic时间戳）
        images = {cam: [] for cam in image_topics.values()}
        for i, t in enumerate(main_times):
            for topic, cam_name in image_topics.items():
                img_bytes = find_nearest_msg(topic_msgs[topic], t)
                if img_bytes is not None:
                    try:
                        img_arr = decode_image_bytes(img_bytes)
                    except Exception:
                        img_arr = None
                    images[cam_name].append(img_arr)
                else:
                    images[cam_name].append(None)

        # 解析状态
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
                        state_vec.extend(js.position[from_idx:to_idx])
                    elif 'udp_arm_position' in topic:
                        pose = self.typestore.deserialize_cdr(data, 'rm_ros_interfaces/msg/Jointposeorientation')
                        pos = [pose.pose.position.x, pose.pose.position.y, pose.pose.position.z]
                        rot = [pose.pose.orientation.x, pose.pose.orientation.y, pose.pose.orientation.z]
                        # 判断是否取位置还是旋转
                        if to_idx <= 3:
                            state_vec.extend(pos[from_idx:to_idx])
                        else:
                            state_vec.extend(rot[from_idx-3:to_idx-3])
                    else:
                        state_vec.extend([np.nan] * (to_idx - from_idx))
                else:
                    state_vec.extend([np.nan] * (to_idx - from_idx))
            states.append(np.array(state_vec, dtype=np.float32))

        # 解析动作（同状态）
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
                        action_vec.extend(js.position[from_idx:to_idx])
                    elif 'udp_arm_position' in topic:
                        pose = self.typestore.deserialize_cdr(data, 'rm_ros_interfaces/msg/Jointposeorientation')
                        pos = [pose.pose.position.x, pose.pose.position.y, pose.pose.position.z]
                        rot = [pose.pose.orientation.x, pose.pose.orientation.y, pose.pose.orientation.z]
                        if to_idx <= 3:
                            action_vec.extend(pos[from_idx:to_idx])
                        else:
                            action_vec.extend(rot[from_idx-3:to_idx-3])
                    else:
                        action_vec.extend([np.nan] * (to_idx - from_idx))
                else:
                    action_vec.extend([np.nan] * (to_idx - from_idx))
            actions.append(np.array(action_vec, dtype=np.float32))

        return {
            "images": images,
            "states": states,
            "actions": actions,
            "frames": frames,
        }

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> Any:
        mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
        episode_data = self._parse_mcap_episode(mcap_file)
        return episode_data["images"]

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> Any:
        mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
        episode_data = self._parse_mcap_episode(mcap_file)
        return episode_data["states"]

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> Any:
        mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
        episode_data = self._parse_mcap_episode(mcap_file)
        return episode_data["actions"]

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        mcap_file = self._get_episode_mcap_file(task_path, ep_idx)
        episode_data = self._parse_mcap_episode(mcap_file)
        return episode_data["frames"]

    def _get_task_episodes_num(self, task_path: Path) -> int:
        return len(list(task_path.glob("*.mcap")))

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