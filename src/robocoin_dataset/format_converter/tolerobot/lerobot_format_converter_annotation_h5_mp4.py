"""
LeRobot格式转换器 - Annotation+H5+MP4格式
通过annotation JSON文件检索H5数据文件和MP4视频文件的数据集
用于robobrain等使用标注文件管理数据的数据集
"""

import json
import logging
from pathlib import Path

import cv2
import h5py
import numpy as np
import yaml

from robocoin_dataset.format_converter.tolerobot.constant import (
    ACTION_KEY,
    ARGS_KEY,
    CAM_NAME_KEY,
    FEATURES_KEY,
    IMAGE_KEY,
    OBSERVATION_KEY,
    STATE_KEY,
    SUB_ACTION_KEY,
    SUB_STATE_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)
from robocoin_dataset.format_converter.tolerobot.video_frame_validator import (
    validate_video_frame_count,
)


class LerobotFormatConverterAnnotationH5Mp4(LerobotFormatConverter):
    """
    处理通过annotation文件检索H5+MP4数据的转换器
    
    数据结构：
    - annotation/train.json: 标注文件，包含每个episode的元数据和文件路径
    - videos/train/{ep_id}/{ep_id}.hdf5: H5数据文件（qpos/action）
    - videos/train/{ep_id}/{ep_id}_cam_*.mp4: MP4视频文件
    """
    
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
        # 在调用super之前设置dataset_path和converter_config，以便_load_annotation可以使用它
        self.dataset_path = dataset_path
        self.converter_config = converter_config
        self._annotation_data = None
        self._video_readers = {}  # 缓存视频读取器
        
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

    def _load_annotation(self) -> list[dict]:
        """加载annotation文件"""
        if self._annotation_data is None:
            annotation_file = Path(self.dataset_path) / "annotation" / "train.json"
            if not annotation_file.exists():
                annotation_dir = annotation_file.parent
                available_files = []
                if annotation_dir.exists():
                    available_files = [f.name for f in annotation_dir.glob("*.json")]
                
                raise FileNotFoundError(
                    f"❌ Annotation file not found.\n"
                    f"   📄 Expected file: {annotation_file}\n"
                    f"   📂 Annotation directory: {annotation_dir} {'(exists)' if annotation_dir.exists() else '(NOT FOUND)'}\n"
                    f"   📋 JSON files in directory: {available_files if available_files else 'None'}\n"
                    f"   💡 Check if:\n"
                    f"      1. File name is 'train.json'\n"
                    f"      2. File is in 'annotation' directory\n"
                    f"      3. Dataset has been properly extracted"
                )
            
            try:
                with open(annotation_file) as f:
                    self._annotation_data = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"❌ Failed to parse annotation JSON file.\n"
                    f"   📄 File: {annotation_file}\n"
                    f"   ❌ Parse error: {e!s}\n"
                    f"   📐 Error at line {e.lineno}, column {e.colno}\n"
                    f"   💡 Check if:\n"
                    f"      1. File is valid JSON format\n"
                    f"      2. File is not corrupted\n"
                    f"      3. File encoding is correct (UTF-8)"
                ) from e
            except Exception as e:
                raise OSError(
                    f"❌ Failed to read annotation file.\n"
                    f"   📄 File: {annotation_file}\n"
                    f"   ❌ Error: {e!s}\n"
                    f"   💡 Check if:\n"
                    f"      1. File has read permissions\n"
                    f"      2. File is not locked by another process\n"
                    f"      3. Disk is not full or has I/O errors"
                ) from e
        
        return self._annotation_data

    def _gen_task_paths_dict(self) -> dict[Path, str]:
        """生成任务路径字典"""
        self._load_annotation()
        
        # robobrain将所有episodes作为一个大任务处理
        task_path = Path(self.dataset_path) / "videos" / "train"
        
        # 尝试从local_task_info.yaml获取任务名称
        local_task_info = Path(self.dataset_path) / "local_task_info.yaml"
        if local_task_info.exists():
            with open(local_task_info) as f:
                task_info = yaml.safe_load(f)
                tasks = task_info.get('tasks', {})
                if tasks:
                    task_name = list(tasks.keys())[0]
                else:
                    task_name = "default_task"
        else:
            task_name = "default_task"
        
        return {task_path: task_name}

    def _get_episode_entry(self, task_path: Path, ep_idx: int) -> dict:
        """获取指定episode的annotation条目"""
        annotation_data = self._load_annotation()
        
        # robobrain将所有episodes作为一个大任务，直接按索引访问
        if ep_idx >= len(annotation_data):
            raise IndexError(
                f"❌ Episode index out of range.\n"
                f"   🎯 Requested episode: {ep_idx}\n"
                f"   📊 Total episodes: {len(annotation_data)}\n"
                f"   📁 Task path: {task_path}\n"
                f"   📐 Valid range: 0 to {len(annotation_data) - 1}\n"
                f"   💡 Check if:\n"
                f"      1. Episode index is correct\n"
                f"      2. Annotation file has all expected episodes\n"
                f"      3. Dataset is complete"
            )
        
        return annotation_data[ep_idx]

    def _get_h5_file_path(self, entry: dict) -> Path:
        """从annotation条目获取H5文件路径"""
        # 检查 'data' 字段
        if 'data' not in entry:
            available_keys = list(entry.keys())[:10]
            raise KeyError(
                f"❌ Missing 'data' field in annotation entry.\n"
                f"   📋 Available fields (showing first 10): {available_keys}\n"
                f"   💡 Check if:\n"
                f"      1. Annotation format is correct\n"
                f"      2. Entry structure matches expected format\n"
                f"      3. Annotation file version is compatible"
            )
        
        state_path = entry['data'].get('state_path')
        if not state_path:
            available_keys = list(entry['data'].keys())
            raise ValueError(
                f"❌ Missing 'state_path' in annotation entry data.\n"
                f"   📋 Available keys in 'data': {available_keys}\n"
                f"   💡 Check if:\n"
                f"      1. Annotation entry has 'state_path' field\n"
                f"      2. H5 file path is properly specified\n"
                f"      3. Annotation format matches dataset type"
            )
        
        return Path(self.dataset_path) / state_path

    def _get_video_file_path(self, entry: dict, cam_name: str) -> Path:
        """从annotation条目获取视频文件路径
        
        cam_name可能带有_rgb后缀（如cam_high_rgb），需要尝试多种映射
        """
        video_paths = entry['data'].get('video_paths', {})
        
        # 尝试直接匹配
        if cam_name in video_paths:
            return Path(self.dataset_path) / video_paths[cam_name]
        
        # 尝试去掉_rgb后缀
        cam_name_without_rgb = cam_name.replace('_rgb', '')
        if cam_name_without_rgb in video_paths:
            return Path(self.dataset_path) / video_paths[cam_name_without_rgb]
        
        # 尝试添加_rgb后缀
        cam_name_with_rgb = f"{cam_name}_rgb" if not cam_name.endswith('_rgb') else cam_name
        if cam_name_with_rgb in video_paths and cam_name_with_rgb != cam_name:
            return Path(self.dataset_path) / video_paths[cam_name_with_rgb]
        
        # 提供详细的错误信息
        available_cameras = list(video_paths.keys())
        tried_names = [cam_name, cam_name_without_rgb]
        if cam_name_with_rgb not in tried_names:
            tried_names.append(cam_name_with_rgb)
        
        raise ValueError(
            f"❌ Camera not found in annotation video paths.\n"
            f"   📹 Requested camera: {cam_name}\n"
            f"   🔍 Tried names: {tried_names}\n"
            f"   📋 Available cameras: {available_cameras}\n"
            f"   💡 Check if:\n"
            f"      1. Camera name matches config\n"
            f"      2. Camera name format is correct (with/without _rgb suffix)\n"
            f"      3. Video paths are properly specified in annotation"
        )

    def _prevalidate_files(self) -> None:
        """验证数据集文件完整性"""
        dataset_path = Path(self.dataset_path)
        
        # 🆕 增加：检查dataset_path是否存在
        if not dataset_path.exists():
            parent_dir = dataset_path.parent
            siblings = []
            if parent_dir.exists():
                siblings = [d.name for d in parent_dir.iterdir()]
            
            raise FileNotFoundError(
                f"❌ Annotation+H5+MP4数据集路径不存在\n"
                f"📁 请求的路径：{dataset_path}\n"
                f"📂 父目录：{parent_dir} {'(存在)' if parent_dir.exists() else '(不存在)'}\n"
                f"🗂️ 父目录内容：\n" +
                "\n".join(f"   - {item}" for item in sorted(siblings)[:15]) +
                (f"\n   ... 还有 {len(siblings) - 15} 项" if len(siblings) > 15 else "") +
                "\n💡 请检查：\n"
                "   1. 数据集路径配置是否正确\n"
                "   2. 数据集是否已下载或挂载\n"
                "   3. 路径拼写是否有误"
            )
        
        # 🆕 增加：检查annotation目录是否存在
        annotation_dir = dataset_path / "annotation"
        if not annotation_dir.exists():
            all_dirs = [d.name for d in dataset_path.iterdir() if d.is_dir()]
            all_files = [f.name for f in dataset_path.iterdir() if f.is_file()]
            
            raise FileNotFoundError(
                f"❌ Annotation目录不存在\n"
                f"📂 数据集路径：{dataset_path}\n"
                f"📁 期望目录：annotation/\n"
                f"📋 现有目录：{all_dirs[:10] if all_dirs else '(无目录)'}\n"
                f"📄 现有文件：{all_files[:10] if all_files else '(无文件)'}\n"
                "💡 Annotation+H5+MP4格式要求：\n"
                "   - annotation/ (标注文件)\n"
                "   - data/ (H5数据文件)\n"
                "   - videos/ (视频文件，可选)\n"
                "📋 请检查数据集结构是否完整"
            )
        
        # 加载annotation文件
        annotation_data = self._load_annotation()
        
        if not annotation_data:
            annotation_file = Path(self.dataset_path) / "annotation" / "train.json"
            raise ValueError(
                f"❌ Annotation data is empty.\n"
                f"   📄 File: {annotation_file}\n"
                f"   📊 Episodes: 0\n"
                f"   💡 Check if:\n"
                f"      1. Annotation file has valid content\n"
                f"      2. JSON array is not empty\n"
                f"      3. Dataset has been properly generated"
            )
        
        # 检查至少有一个episode的数据
        sample = annotation_data[0]
        if 'data' not in sample:
            available_keys = list(sample.keys())
            raise ValueError(
                f"❌ Invalid annotation format.\n"
                f"   ❌ Missing required field: 'data'\n"
                f"   📋 Available fields in first entry: {available_keys}\n"
                f"   💡 Expected annotation format:\n"
                f"      [{{'data': {{'state_path': '...', 'video_paths': {{...}}}}, ...}}, ...]\n"
                f"   💡 Check if:\n"
                f"      1. Annotation format is correct\n"
                f"      2. Annotation version matches converter\n"
                f"      3. Dataset type is compatible"
            )
        
        # 🆕 增加：抽样检查第一个episode的H5文件（验证数据完整性）
        if len(annotation_data) > 0:
            try:
                first_entry = annotation_data[0]
                h5_path = self._get_h5_file_path(first_entry)
                
                if h5_path.exists():
                    # 验证H5文件可读性
                    try:
                        import h5py
                        with h5py.File(h5_path, 'r') as f:
                            datasets = list(f.keys())
                            if not datasets:
                                self.logger.warning(
                                    f"⚠️ 第一个episode的H5文件为空\n"
                                    f"📄 文件：{h5_path}\n"
                                    "💡 这可能导致后续转换失败"
                                )
                            else:
                                self.logger.info(
                                    f"✅ H5文件验证通过：{h5_path.name}\n"
                                    f"   - 数据集数量：{len(datasets)}\n"
                                    f"   - 数据集列表：{datasets[:5]}"
                                )
                    except Exception as e:
                        self.logger.warning(
                            f"⚠️ 第一个episode的H5文件无法读取\n"
                            f"📄 文件：{h5_path}\n"
                            f"⚠️ 错误：{str(e)}\n"
                            "💡 请检查H5文件是否损坏"
                        )
                else:
                    self.logger.warning(
                        f"⚠️ 第一个episode的H5文件不存在\n"
                        f"📄 期望路径：{h5_path}\n"
                        "💡 这可能表明数据文件未完全下载或路径配置错误"
                    )
            except Exception as e:
                self.logger.warning(f"⚠️ 无法验证H5文件：{e}")
            
            # 🆕 增加：验证视频帧数与H5数据帧数是否匹配
            try:
                # 获取视频路径
                video_paths = first_entry.get('data', {}).get('video_paths', {})
                if video_paths and h5_path and h5_path.exists():
                    # 从H5文件获取预期帧数
                    expected_frame_count = None
                    try:
                        with h5py.File(h5_path, 'r') as f:
                            if 'qpos' in f:
                                expected_frame_count = f['qpos'].shape[0]
                            elif 'action' in f:
                                expected_frame_count = f['action'].shape[0]
                    except Exception as e:
                        self.logger.warning(f"⚠️ 无法从H5文件读取帧数：{e}")
                    
                    if expected_frame_count is not None:
                        if self.logger:
                            self.logger.info(
                                f"🔍 Validating video frame counts for first episode\n"
                                f"   📊 H5 data frames: {expected_frame_count}"
                            )
                        
                        # 检查每个视频文件
                        for cam_name, video_rel_path in list(video_paths.items())[:3]:  # 只检查前3个相机
                            video_path = Path(self.dataset_path) / video_rel_path
                            if video_path.exists():
                                try:
                                    validate_video_frame_count(
                                        video_path=video_path,
                                        expected_frame_count=expected_frame_count,
                                        data_source="H5 file",
                                        logger=self.logger,
                                        tolerance=1  # 允许±1帧误差
                                    )
                                except ValueError as e:
                                    self.logger.warning(
                                        f"⚠️ 视频帧数不匹配（相机: {cam_name}）\n"
                                        f"{str(e)}\n"
                                        "💡 这可能导致数据对齐问题"
                                    )
                                except RuntimeError as e:
                                    self.logger.warning(
                                        f"⚠️ 无法验证视频帧数（相机: {cam_name}）\n"
                                        f"📄 Video: {video_path.name}\n"
                                        f"⚠️ 原因: {str(e)}"
                                    )
            except Exception as e:
                self.logger.warning(f"⚠️ 视频帧数验证过程出错：{e}")
        
        # 注意：由于videos文件夹可能为空（数据太大），我们不验证视频文件存在性
        self.logger.info(f"✅ Loaded {len(annotation_data)} episodes from annotation file")

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取episode的帧数"""
        entry = self._get_episode_entry(task_path, ep_idx)
        
        # 从annotation中直接获取帧数
        if 'frame' in entry:
            return entry['frame']
        
        # 如果annotation中没有帧数，尝试从H5文件读取
        h5_path = None
        h5_datasets_found = []
        try:
            h5_path = self._get_h5_file_path(entry)
            if h5_path.exists():
                with h5py.File(h5_path, 'r') as f:
                    # 收集可用的数据集
                    h5_datasets_found = list(f.keys())
                    
                    if 'qpos' in f:
                        return f['qpos'].shape[0]
                    if 'action' in f:
                        return f['action'].shape[0]
        except Exception as e:
            self.logger.warning(f"Cannot read H5 file for episode {ep_idx}: {e}")
        
        # 如果所有方法都失败，提供详细的错误信息
        available_keys = list(entry.keys())
        error_details = []
        
        if 'frame' not in entry:
            error_details.append(f"'frame' field not in annotation entry (available: {available_keys})")
        
        if h5_path:
            if not h5_path.exists():
                error_details.append(f"H5 file does not exist: {h5_path}")
            elif h5_datasets_found:
                error_details.append(f"H5 file exists but missing 'qpos'/'action' datasets (found: {h5_datasets_found})")
        
        raise ValueError(
            f"❌ Cannot determine frame count for episode.\n"
            f"   🎯 Episode index: {ep_idx}\n"
            f"   📁 Task path: {task_path}\n"
            f"   🗂️  H5 file: {h5_path if h5_path else 'Not determined'}\n"
            f"   ❌ Issues:\n"
            + "\n".join(f"      - {detail}" for detail in error_details) + "\n"
            f"   💡 Frame count can be obtained from:\n"
            f"      1. 'frame' field in annotation entry\n"
            f"      2. 'qpos' or 'action' dataset shape in H5 file\n"
            f"   💡 Check if annotation or H5 file has required data"
        )

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量"""
        annotation_data = self._load_annotation()
        
        # robobrain将所有episodes作为一个大任务
        return len(annotation_data)

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> dict[str, list[np.ndarray]]:
        """准备episode的图像缓冲区"""
        entry = self._get_episode_entry(task_path, ep_idx)
        
        images = {}
        image_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]
        
        for image_config in image_configs:
            cam_name = image_config.get(CAM_NAME_KEY)
            
            try:
                video_path = self._get_video_file_path(entry, cam_name)
                
                # 如果文件不存在，跳过（因为videos文件夹可能为空）
                if not video_path.exists():
                    self.logger.warning(f"Video file not found: {video_path}, skipping camera {cam_name}")
                    continue
                
                cap = cv2.VideoCapture(str(video_path))
                if not cap.isOpened():
                    file_size = video_path.stat().st_size if video_path.exists() else 0
                    raise OSError(
                        f"❌ Cannot open video file.\n"
                        f"   📹 Camera: {cam_name}\n"
                        f"   📄 Video file: {video_path}\n"
                        f"   📊 File size: {file_size} bytes\n"
                        f"   📁 Location: task={task_path}, ep_idx={ep_idx}\n"
                        f"   💡 Check if:\n"
                        f"      1. Video file is not corrupted\n"
                        f"      2. Video codec is supported by OpenCV\n"
                        f"      3. File has correct permissions"
                    )
                
                frames = []
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    # OpenCV读取的是BGR，转换为RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(frame_rgb)
                cap.release()
                
                images[cam_name] = frames
            except Exception as e:
                self.logger.warning(f"Error loading camera {cam_name}: {e}")
        
        return images

    def _infer_camera_name(self, filename: str) -> str | None:
        """从文件名推断相机名称"""
        # 定义常见的相机名称映射
        mappings = {
            'high': 'cam_high',
            'left_wrist': 'cam_left_wrist',
            'right_wrist': 'cam_right_wrist',
            'cam_high': 'cam_high',
            'cam_left_wrist': 'cam_left_wrist',
            'cam_right_wrist': 'cam_right_wrist',
        }
        
        filename_lower = filename.lower()
        for key, value in mappings.items():
            if key in filename_lower:
                return value
        
        return None

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> np.ndarray:
        """准备episode的状态缓冲区"""
        entry = self._get_episode_entry(task_path, ep_idx)
        h5_path = self._get_h5_file_path(entry)
        
        if not h5_path.exists():
            self.logger.warning(f"H5 file not found: {h5_path}")
            # 返回一个空数组，形状根据配置推断
            frame_num = entry.get('frame', 0)
            state_dim = self._get_state_dimension()
            return np.zeros((frame_num, state_dim), dtype=np.float32)
        
        try:
            with h5py.File(h5_path, 'r') as f:
                if 'qpos' in f:
                    return np.array(f['qpos'])
                
                # qpos 不存在，列出可用的数据集
                available_datasets = list(f.keys())
                raise ValueError(
                    f"❌ Missing 'qpos' dataset in H5 file.\n"
                    f"   🗂️  File: {h5_path}\n"
                    f"   📁 Location: task={task_path}, ep_idx={ep_idx}\n"
                    f"   📋 Available datasets: {available_datasets}\n"
                    f"   💡 Check if:\n"
                    f"      1. H5 file has 'qpos' dataset for states\n"
                    f"      2. Dataset name matches expected format\n"
                    f"      3. H5 file structure is correct"
                )
        except OSError as e:
            raise OSError(
                f"❌ Cannot read H5 file.\n"
                f"   🗂️  File: {h5_path}\n"
                f"   📁 Location: task={task_path}, ep_idx={ep_idx}\n"
                f"   ❌ Error: {e!s}\n"
                f"   💡 Check if:\n"
                f"      1. File is not corrupted\n"
                f"      2. File is not being written to\n"
                f"      3. File permissions are correct"
            ) from e

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> np.ndarray:
        """准备episode的动作缓冲区"""
        entry = self._get_episode_entry(task_path, ep_idx)
        h5_path = self._get_h5_file_path(entry)
        
        if not h5_path.exists():
            self.logger.warning(f"H5 file not found: {h5_path}")
            # 返回一个空数组
            frame_num = entry.get('frame', 0)
            action_dim = self._get_action_dimension()
            return np.zeros((frame_num, action_dim), dtype=np.float32)
        
        try:
            with h5py.File(h5_path, 'r') as f:
                if 'action' in f:
                    return np.array(f['action'])
                
                # action 不存在，列出可用的数据集
                available_datasets = list(f.keys())
                raise ValueError(
                    f"❌ Missing 'action' dataset in H5 file.\n"
                    f"   🗂️  File: {h5_path}\n"
                    f"   📁 Location: task={task_path}, ep_idx={ep_idx}\n"
                    f"   📋 Available datasets: {available_datasets}\n"
                    f"   💡 Check if:\n"
                    f"      1. H5 file has 'action' dataset\n"
                    f"      2. Dataset name matches expected format\n"
                    f"      3. H5 file structure is correct"
                )
        except OSError as e:
            raise OSError(
                f"❌ Cannot read H5 file.\n"
                f"   🗂️  File: {h5_path}\n"
                f"   📁 Location: task={task_path}, ep_idx={ep_idx}\n"
                f"   ❌ Error: {e!s}\n"
                f"   💡 Check if:\n"
                f"      1. File is not corrupted\n"
                f"      2. File is not being written to\n"
                f"      3. File permissions are correct"
            ) from e

    def _get_state_dimension(self) -> int:
        """从配置中获取状态维度"""
        state_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY].get(STATE_KEY, {}).get(SUB_STATE_KEY, [])
        total_dim = 0
        for state_config in state_configs:
            state_config.get(ARGS_KEY, {}).get('range_from', 0)
            to_idx = state_config.get(ARGS_KEY, {}).get('range_to', 0)
            total_dim = max(total_dim, to_idx)
        return total_dim

    def _get_action_dimension(self) -> int:
        """从配置中获取动作维度"""
        action_configs = self.converter_config[FEATURES_KEY].get(ACTION_KEY, {}).get(SUB_ACTION_KEY, [])
        total_dim = 0
        for action_config in action_configs:
            action_config.get(ARGS_KEY, {}).get('range_from', 0)
            to_idx = action_config.get(ARGS_KEY, {}).get('range_to', 0)
            total_dim = max(total_dim, to_idx)
        return total_dim

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
        if cam_name not in images_buffer:
            available_cameras = list(images_buffer.keys())
            raise KeyError(
                f"❌ Camera not found in images buffer.\n"
                f"   📹 Requested camera: {cam_name}\n"
                f"   📁 Location: task={task_path}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📋 Available cameras: {available_cameras}\n"
                f"   💡 Check if:\n"
                f"      1. Camera name matches config\n"
                f"      2. Video file was successfully loaded\n"
                f"      3. Camera exists in annotation video_paths"
            )
        
        if frame_idx >= len(images_buffer[cam_name]):
            max_frames = len(images_buffer[cam_name])
            raise IndexError(
                f"❌ Frame index out of range.\n"
                f"   🎯 Requested frame: {frame_idx}\n"
                f"   📹 Camera: {cam_name}\n"
                f"   📁 Location: task={task_path}, ep_idx={ep_idx}\n"
                f"   📐 Available frames: 0 to {max_frames - 1} (total: {max_frames})\n"
                f"   💡 Check if:\n"
                f"      1. Frame index is within valid range\n"
                f"      2. Video file has expected number of frames\n"
                f"      3. Frame count in annotation matches video"
            )
        
        return images_buffer[cam_name][frame_idx]

    def _get_frame_sub_states(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_states_buffer: np.ndarray | None = None
    ) -> np.ndarray:
        """获取指定帧的子状态"""
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        
        from_idx = args_dict.get('range_from', 0)
        to_idx = args_dict.get('range_to', sub_states_buffer.shape[1])
        
        return sub_states_buffer[frame_idx, from_idx:to_idx].astype(np.float32)

    def _get_frame_sub_actions(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_actions_buffer: np.ndarray | None = None
    ) -> np.ndarray:
        """获取指定帧的子动作"""
        if sub_actions_buffer is None:
            sub_actions_buffer = self._prepare_episode_actions_buffer(task_path, ep_idx)
        
        from_idx = args_dict.get('range_from', 0)
        to_idx = args_dict.get('range_to', sub_actions_buffer.shape[1])
        
        return sub_actions_buffer[frame_idx, from_idx:to_idx].astype(np.float32)

    def __del__(self) -> None:
        """清理视频读取器"""
        for cap in self._video_readers.values():
            if cap.isOpened():
                cap.release()
