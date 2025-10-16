"""
LeRobot格式转换器 - JPG+JSON格式
处理多传感器文件夹结构的数据集（alohaold, pika, mayi）
"""

import json
import logging
from pathlib import Path

import numpy as np
from PIL import Image

from robocoin_dataset.format_converter.tolerobot.constant import (
    ARGS_KEY,
    CAM_NAME_KEY,
    FEATURES_KEY,
    IMAGE_KEY,
    OBSERVATION_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)


class LerobotFormatConverterJpgJson(LerobotFormatConverter):
    """JPG+JSON格式转换器 - 用于多传感器文件夹结构的数据集"""
    
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
        self._json_data_cache = {}  # 缓存JSON数据

    def _prevalidate_files(self) -> None:
        """验证数据集文件完整性"""
        # 🆕 增加：验证所有task_path存在性
        for task_path in self.path_task_dict.keys():
            if not task_path.exists():
                # 显示父目录内容
                parent_dir = task_path.parent
                siblings = []
                if parent_dir.exists():
                    siblings = [d.name for d in parent_dir.iterdir() if d.is_dir()]
                    if len(siblings) > 15:
                        siblings = siblings[:15] + [f"... ({len(siblings) - 15} more)"]
                
                raise FileNotFoundError(
                    f"❌ Task path does not exist\n"
                    f"   📂 Task path: {task_path}\n"
                    f"   📂 Parent directory: {parent_dir}\n"
                    f"   📋 Available directories in parent:\n"
                    f"      {', '.join(siblings) if siblings else 'Parent directory not found'}\n"
                    f"   💡 Please check:\n"
                    f"      1. Path is correct in configuration\n"
                    f"      2. Dataset has been downloaded/extracted\n"
                    f"      3. No typos in directory names"
                )
            
            if not task_path.is_dir():
                raise NotADirectoryError(
                    f"❌ Task path exists but is not a directory\n"
                    f"   📂 Path: {task_path}\n"
                    f"   📋 Type: {('file' if task_path.is_file() else 'unknown')}\n"
                    f"   💡 Task path must be a directory containing episode folders"
                )
        
        for task_path in self.path_task_dict.keys():
            episodes = list(task_path.glob("episode*"))
            episodes = [ep for ep in episodes if ep.is_dir()]
            
            if not episodes:
                # 列出task_path下的所有目录，帮助用户诊断
                all_dirs = [d.name for d in task_path.iterdir() if d.is_dir()]
                raise FileNotFoundError(
                    f"❌ No episode directories found.\n"
                    f"   📂 Task path: {task_path}\n"
                    f"   📋 Directories found: {all_dirs if all_dirs else 'None'}\n"
                    f"   💡 Expected directory pattern: episode0, episode1, ...\n"
                    f"   💡 Check if:\n"
                    f"      1. Dataset has been extracted correctly\n"
                    f"      2. Episode directories are named correctly\n"
                    f"      3. Task path points to correct location"
                )
            
            for ep_dir in episodes:
                # 检查是否有嵌套的episode目录
                nested_ep = ep_dir / ep_dir.name
                if nested_ep.exists() and nested_ep.is_dir() and (nested_ep / "camera").exists():
                    ep_dir = nested_ep
                
                # 🆕 增加：抽样检查第一个episode的图像文件
                if ep_dir == episodes[0]:
                    camera_dir = ep_dir / "camera" / "color"
                    if camera_dir.exists():
                        # 查找第一个相机文件夹
                        camera_folders = [d for d in camera_dir.iterdir() if d.is_dir()]
                        if camera_folders:
                            first_cam = camera_folders[0]
                            image_files = list(first_cam.glob("*.jpg")) + list(first_cam.glob("*.png"))
                            
                            if image_files:
                                # 尝试读取第一张图片
                                try:
                                    from PIL import Image
                                    test_img = Image.open(image_files[0])
                                    width, height = test_img.size
                                    self.logger.info(
                                        f"✅ 图像文件验证通过：{first_cam.name}\n"
                                        f"   - 图像数量：{len(image_files)}\n"
                                        f"   - 分辨率：{width}x{height}\n"
                                        f"   - 格式：{test_img.format}"
                                    )
                                except Exception as e:
                                    self.logger.warning(
                                        f"⚠️ 无法读取图像文件\n"
                                        f"📄 文件：{image_files[0]}\n"
                                        f"⚠️ 错误：{str(e)}\n"
                                        "💡 请检查图像文件是否损坏"
                                    )
                            else:
                                self.logger.warning(
                                    f"⚠️ 相机文件夹中没有图像文件\n"
                                    f"📂 文件夹：{first_cam}\n"
                                    "💡 期望找到 .jpg 或 .png 文件"
                                )
                
                # 检查相机文件夹
                camera_dir = ep_dir / "camera" / "color"
                if not camera_dir.exists():
                    # 提供详细的目录结构信息
                    camera_base = ep_dir / "camera"
                    ep_subdirs = [d.name for d in ep_dir.iterdir() if d.is_dir()] if ep_dir.exists() else []
                    camera_subdirs = [d.name for d in camera_base.iterdir() if d.is_dir()] if camera_base.exists() else []
                    
                    raise FileNotFoundError(
                        f"❌ Camera color directory not found.\n"
                        f"   📂 Expected path: {camera_dir}\n"
                        f"   📂 Episode directory: {ep_dir}\n"
                        f"   📋 Episode subdirectories: {ep_subdirs}\n"
                        f"   📋 Camera subdirectories: {camera_subdirs if camera_base.exists() else 'camera/ not found'}\n"
                        f"   💡 Expected structure: episode/camera/color/[camera_name]/\n"
                        f"   💡 Check if:\n"
                        f"      1. Directory structure matches expected format\n"
                        f"      2. 'camera' and 'color' directories exist\n"
                        f"      3. Dataset extraction was complete"
                    )

    def _get_episode_dir(self, task_path: Path, ep_idx: int) -> Path:
        """获取episode目录"""
        episodes = sorted([ep for ep in task_path.glob("episode*") if ep.is_dir()])
        if ep_idx >= len(episodes):
            episode_names = [ep.name for ep in episodes[:10]]  # 只显示前10个
            raise IndexError(
                f"❌ Episode index out of range.\n"
                f"   🎯 Requested episode: {ep_idx}\n"
                f"   📂 Task path: {task_path}\n"
                f"   📊 Total episodes: {len(episodes)}\n"
                f"   📋 Episode directories (showing first 10): {episode_names}\n"
                f"   📐 Valid range: 0 to {len(episodes) - 1}\n"
                f"   💡 Check if:\n"
                f"      1. Episode index is correct\n"
                f"      2. All episodes have been recorded\n"
                f"      3. Dataset is complete"
            )
        
        ep_dir = episodes[ep_idx]
        
        # 检查是否有嵌套的episode目录（如pika数据集：episode0/episode0/...）
        nested_ep = ep_dir / ep_dir.name
        if nested_ep.exists() and nested_ep.is_dir():
            # 检查嵌套目录是否包含camera数据
            if (nested_ep / "camera").exists():
                return nested_ep
        
        return ep_dir

    def _get_camera_images(self, ep_dir: Path, camera_name: str) -> list[Path]:
        """获取指定相机的所有图像文件"""
        camera_dir = ep_dir / "camera" / "color" / camera_name
        if not camera_dir.exists():
            return []
        
        return sorted(camera_dir.glob("*.jpg")) + sorted(camera_dir.glob("*.png"))

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取episode的帧数"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        
        # 从第一个可用的相机获取帧数
        camera_dir = ep_dir / "camera" / "color"
        if not camera_dir.exists():
            ep_subdirs = [d.name for d in ep_dir.iterdir() if d.is_dir()] if ep_dir.exists() else []
            
            raise FileNotFoundError(
                f"❌ Camera color directory not found.\n"
                f"   📂 Expected path: {camera_dir}\n"
                f"   📂 Episode directory: {ep_dir}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   📋 Episode subdirectories: {ep_subdirs}\n"
                f"   💡 Expected path: episode/camera/color/\n"
                f"   💡 Check if:\n"
                f"      1. Episode structure is correct\n"
                f"      2. 'camera/color' directories exist\n"
                f"      3. Dataset was extracted properly"
            )
        
        # 尝试从每个相机文件夹获取图像
        camera_folders = [d for d in camera_dir.iterdir() if d.is_dir()]
        camera_info = {}
        
        for cam_folder in camera_folders:
            images = list(cam_folder.glob("*.jpg")) + list(cam_folder.glob("*.png"))
            camera_info[cam_folder.name] = len(images)
            if images:
                return len(images)
        
        # 如果没有找到任何图像，提供详细的诊断信息
        raise ValueError(
            f"❌ No images found in episode.\n"
            f"   📂 Episode directory: {ep_dir}\n"
            f"   📂 Camera color path: {camera_dir}\n"
            f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
            f"   📋 Camera folders found: {list(camera_info.keys()) if camera_info else 'None'}\n"
            f"   📊 Images per camera: {camera_info if camera_info else 'No cameras with images'}\n"
            f"   💡 Check if:\n"
            f"      1. Image files exist (.jpg or .png)\n"
            f"      2. Camera directories contain images\n"
            f"      3. Episode was recorded successfully"
        )

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量"""
        episodes = [ep for ep in task_path.glob("episode*") if ep.is_dir()]
        return len(episodes)

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> dict[str, list[np.ndarray]]:
        """准备episode的图像缓冲区"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        
        images = {}
        
        # 遍历配置中的所有相机
        image_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]
        for image_config in image_configs:
            cam_name = image_config.get(CAM_NAME_KEY)
            args = image_config.get(ARGS_KEY, {})
            camera_folder = args.get('camera_folder')
            is_depth = args.get('is_depth', False)
            
            # 确定相机目录类型（color 或 depth）
            if is_depth:
                camera_base_dir = ep_dir / "camera" / "depth"
            else:
                camera_base_dir = ep_dir / "camera" / "color"
            
            if not camera_folder:
                # 如果没有指定camera_folder，尝试使用cam_name的前缀匹配
                if camera_base_dir.exists():
                    for cam_folder in camera_base_dir.iterdir():
                        if cam_folder.is_dir() and cam_name and (cam_name in cam_folder.name or cam_folder.name in cam_name):
                            camera_folder = cam_folder.name
                            break
            
            if camera_folder:
                cam_folder_path = camera_base_dir / camera_folder
                if cam_folder_path.exists():
                    image_files = sorted(cam_folder_path.glob("*.jpg")) + sorted(cam_folder_path.glob("*.png"))
                    
                    frames = []
                    for img_file in image_files:
                        img = Image.open(img_file)
                        if is_depth:
                            # 深度图保持单通道或转换为适当格式
                            img_array = np.array(img)
                            # 如果是单通道，扩展为3通道以兼容LeRobot格式
                            if img_array.ndim == 2:
                                img_array = np.stack([img_array] * 3, axis=-1)
                        else:
                            # RGB图像
                            img_array = np.array(img.convert("RGB"))
                        frames.append(img_array)
                    
                    if frames:
                        images[cam_name] = frames
        
        return images

    def _load_joint_state_data(self, ep_dir: Path, joint_type: str) -> list[dict]:
        """加载关节状态数据"""
        joint_dir = ep_dir / "arm" / "jointState" / joint_type
        if not joint_dir.exists():
            return []
        
        json_files = sorted(joint_dir.glob("*.json"))
        data = []
        for json_file in json_files:
            with open(json_file) as f:
                data.append(json.load(f))
        
        return data

    def _load_gripper_data(self, ep_dir: Path, gripper_side: str) -> list[dict]:
        """加载夹爪数据"""
        gripper_dir = ep_dir / "gripper" / "encoder" / gripper_side
        if not gripper_dir.exists():
            return []
        
        json_files = sorted(gripper_dir.glob("*.json"))
        data = []
        for json_file in json_files:
            with open(json_file) as f:
                data.append(json.load(f))
        
        return data

    def _load_imu_data(self, ep_dir: Path, imu_side: str) -> list[dict]:
        """加载IMU数据"""
        imu_dir = ep_dir / "imu" / "9axis" / imu_side
        if not imu_dir.exists():
            return []
        
        json_files = sorted(imu_dir.glob("*.json"))
        data = []
        for json_file in json_files:
            with open(json_file) as f:
                data.append(json.load(f))
        
        return data

    def _load_localization_data(self, ep_dir: Path, localization_side: str) -> list[dict]:
        """加载定位/位姿数据"""
        localization_dir = ep_dir / "localization" / "pose" / localization_side
        if not localization_dir.exists():
            return []
        
        json_files = sorted(localization_dir.glob("*.json"))
        data = []
        for json_file in json_files:
            with open(json_file) as f:
                data.append(json.load(f))
        
        return data

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> dict:
        """准备episode的状态缓冲区"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        
        # 加载各种数据
        buffer = {
            # 关节数据（pika, aloha等）
            'puppet_left': self._load_joint_state_data(ep_dir, 'puppetLeft'),
            'puppet_right': self._load_joint_state_data(ep_dir, 'puppetRight'),
            'master_left': self._load_joint_state_data(ep_dir, 'masterLeft'),
            'master_right': self._load_joint_state_data(ep_dir, 'masterRight'),
            
            # 夹爪数据
            'gripper_pika_l': self._load_gripper_data(ep_dir, 'pika_l'),
            'gripper_pika_r': self._load_gripper_data(ep_dir, 'pika_r'),
            
            # IMU数据（mayi）
            'imu_pika_l': self._load_imu_data(ep_dir, 'pika_l'),
            'imu_pika_r': self._load_imu_data(ep_dir, 'pika_r'),
            
            # 定位数据（mayi）
            'localization_pika_l': self._load_localization_data(ep_dir, 'pika_l'),
            'localization_pika_r': self._load_localization_data(ep_dir, 'pika_r'),
        }
        
        return buffer
        

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> dict:
        """准备episode的动作缓冲区"""
        # 对于这类数据集，action通常与observation相同
        return self._prepare_episode_states_buffer(task_path, ep_idx)

    def _get_frame_image(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict, 
        images_buffer: dict[str, list[np.ndarray]] | None = None
    ) -> np.ndarray:
        """获取指定帧的图像"""
        if images_buffer is None:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)
        
        cam_name = args_dict.get(CAM_NAME_KEY)
        
        # 尝试匹配相机名称
        matched_cam = None
        for key in images_buffer.keys():
            if cam_name in key or key in cam_name:
                matched_cam = key
                break
        
        if matched_cam is None:
            available_cameras = list(images_buffer.keys())
            raise KeyError(
                f"❌ Camera not found in images buffer.\n"
                f"   📹 Requested camera: {cam_name}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📋 Available cameras: {available_cameras}\n"
                f"   💡 Camera matching uses partial string match\n"
                f"   💡 Check if:\n"
                f"      1. Camera name matches config\n"
                f"      2. Camera folder exists in episode/camera/color/\n"
                f"      3. Images were loaded successfully for this camera"
            )
        
        if frame_idx >= len(images_buffer[matched_cam]):
            max_frames = len(images_buffer[matched_cam])
            raise IndexError(
                f"❌ Frame index out of range.\n"
                f"   🎯 Requested frame: {frame_idx}\n"
                f"   📹 Camera: {matched_cam} (matched from: {cam_name})\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   📐 Available frames: 0 to {max_frames - 1} (total: {max_frames})\n"
                f"   💡 Check if:\n"
                f"      1. Frame index is within valid range\n"
                f"      2. All images were loaded correctly\n"
                f"      3. Episode has expected number of frames"
            )
        
        return images_buffer[matched_cam][frame_idx]

    def _get_frame_sub_states(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_states_buffer: dict | None = None
    ) -> np.ndarray:
        """获取指定帧的子状态"""
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        
        data_type = args_dict.get('data_type', 'joint')
        
        # 处理不同的数据类型
        if data_type == 'gripper':
            # 夹爪数据: {"angle": 1.72, "distance": 0}
            gripper_side = args_dict.get('gripper_side', 'pika_l')
            field_name = args_dict.get('field_name', 'angle')
            
            buffer_key = f'gripper_{gripper_side}'
            if buffer_key not in sub_states_buffer or not sub_states_buffer[buffer_key]:
                return np.zeros(1, dtype=np.float32)
            
            data = sub_states_buffer[buffer_key]
            if frame_idx >= len(data):
                return np.zeros(1, dtype=np.float32)
            
            frame_data = data[frame_idx]
            if field_name in frame_data:
                return np.array([frame_data[field_name]], dtype=np.float32)
            return np.zeros(1, dtype=np.float32)
        
        elif data_type == 'imu':
            # IMU数据: {"angular_velocity": {"x": -0.313, "y": -0.076, "z": -0.313}, ...}
            imu_side = args_dict.get('imu_side', 'pika_l')
            field_name = args_dict.get('field_name', 'angular_velocity')
            subfields = args_dict.get('subfields', ['x', 'y', 'z'])
            
            buffer_key = f'imu_{imu_side}'
            if buffer_key not in sub_states_buffer or not sub_states_buffer[buffer_key]:
                return np.zeros(len(subfields), dtype=np.float32)
            
            data = sub_states_buffer[buffer_key]
            if frame_idx >= len(data):
                return np.zeros(len(subfields), dtype=np.float32)
            
            frame_data = data[frame_idx]
            if field_name in frame_data and isinstance(frame_data[field_name], dict):
                values = [frame_data[field_name].get(sf, 0.0) for sf in subfields]
                return np.array(values, dtype=np.float32)
            return np.zeros(len(subfields), dtype=np.float32)
        
        elif data_type == 'localization':
            # 定位数据: {"x": -0.043, "y": 0.087, "z": -0.176, "roll": 0.049, "pitch": 0.913, "yaw": 0.080}
            localization_side = args_dict.get('localization_side', 'pika_l')
            field_names = args_dict.get('field_names', ['x', 'y', 'z', 'roll', 'pitch', 'yaw'])
            
            buffer_key = f'localization_{localization_side}'
            if buffer_key not in sub_states_buffer or not sub_states_buffer[buffer_key]:
                return np.zeros(len(field_names), dtype=np.float32)
            
            data = sub_states_buffer[buffer_key]
            if frame_idx >= len(data):
                return np.zeros(len(field_names), dtype=np.float32)
            
            frame_data = data[frame_idx]
            values = [frame_data.get(fn, 0.0) for fn in field_names]
            return np.array(values, dtype=np.float32)
        
        else:
            # 默认：关节数据 (joint_type, field_name, range)
            joint_type = args_dict.get('joint_type', 'puppet_left')
            field_name = args_dict.get('field_name', 'position')
            
            if joint_type not in sub_states_buffer:
                # 返回零值
                range_from = args_dict.get('range_from', 0)
                range_to = args_dict.get('range_to', 7)
                return np.zeros(range_to - range_from, dtype=np.float32)
            
            data = sub_states_buffer[joint_type]
            if frame_idx >= len(data):
                range_from = args_dict.get('range_from', 0)
                range_to = args_dict.get('range_to', 7)
                return np.zeros(range_to - range_from, dtype=np.float32)
            
            frame_data = data[frame_idx]
            if field_name in frame_data:
                values = frame_data[field_name]
                if isinstance(values, list):
                    range_from = args_dict.get('range_from', 0)
                    range_to = args_dict.get('range_to', len(values))
                    return np.array(values[range_from:range_to], dtype=np.float32)
                return np.array([values], dtype=np.float32)
            
            # 默认返回零值
            range_from = args_dict.get('range_from', 0)
            range_to = args_dict.get('range_to', 7)
            return np.zeros(range_to - range_from, dtype=np.float32)

    def _get_frame_sub_actions(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_actions_buffer: dict | None = None
    ) -> np.ndarray:
        """获取指定帧的子动作"""
        # 对于新数据类型（gripper, imu, localization），直接使用相同的逻辑
        data_type = args_dict.get('data_type', 'joint')
        
        if data_type in ['gripper', 'imu', 'localization']:
            # 新数据类型：直接调用 _get_frame_sub_states
            return self._get_frame_sub_states(task_path, ep_idx, frame_idx, args_dict, sub_actions_buffer)
        else:
            # 传统关节数据：使用master数据作为action
            if args_dict.get('joint_type', '').startswith('puppet'):
                args_dict = args_dict.copy()
                args_dict['joint_type'] = args_dict['joint_type'].replace('puppet', 'master')
            
            return self._get_frame_sub_states(task_path, ep_idx, frame_idx, args_dict, sub_actions_buffer)
