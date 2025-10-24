"""
LeRobot格式转换器 - H5+JPG格式
处理 aligned_joints.h5 (state/action) + camera/{frame_idx}/*.jpg (images) 的数据集
专门用于 Ruantong A2D 人形机器人数据集
"""

import json
import logging
from pathlib import Path

import h5py
import numpy as np
from PIL import Image

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)
from robocoin_dataset.format_converter.utils.h5_file_cache import H5FileCache


class LerobotFormatConverterH5Jpg(LerobotFormatConverter):
    """H5+JPG格式转换器
    
    数据结构：
    - episode_dir/aligned_joints.h5: 包含 state 和 action 数据
    - episode_dir/camera/{frame_idx}/{cam_name}.jpg: 图像文件
    - episode_dir/meta_info.json: 元数据信息
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
        # 🆕 软通容错机制：定义必需相机（缺失则跳过整个episode）
        # ⚠️ 必须在super().__init__之前定义，因为父类初始化会调用_get_frame_image
        self.required_cameras = ['cam_high_rgb', 'cam_left_wrist_rgb', 'cam_right_wrist_rgb']
        
        # 🆕 图像缓存：用于可选相机缺失时复制上一帧
        # 格式: {(task_path, ep_idx, cam_name): (frame_idx, numpy_array)}
        # ⚠️ 必须在super().__init__之前定义
        self._previous_frame_cache = {}
        
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
        # 使用专业的 H5FileCache，支持 LRU 缓存和性能统计
        self._h5_file_cache = H5FileCache(max_cache_size=50, logger=self.logger)
        self._meta_info_cache = {}  # 缓存元数据
        
        # 🆕 动态移除不可用的可选相机
        self._remove_unavailable_optional_cameras()
    
    def _remove_unavailable_optional_cameras(self) -> None:
        """🆕 软通容错：移除第0帧就不存在的可选相机
        
        策略：
        - 检查第一个task的第一个episode的第0帧
        - 如果可选相机在第0帧就不存在，从配置中移除
        - 必需相机在预验证阶段检查
        """
        if not self.path_task_dict:
            return
        
        # 获取第一个task
        first_task_path = list(self.path_task_dict.keys())[0]
        
        try:
            # 获取第一个episode
            episodes = self._get_all_episode_dirs(first_task_path)
            if not episodes:
                return
            
            first_episode = episodes[0]
            frame_0_dir = first_episode / "camera" / "0"
            
            if not frame_0_dir.exists():
                if self.logger:
                    self.logger.warning(
                        f"⚠️  无法检查可选相机：第0帧目录不存在 {frame_0_dir}"
                    )
                return
            
            # 检查每个相机
            images_config = self.converter_config.get('features', {}).get('observation', {}).get('images', [])
            available_cameras = []
            removed_cameras = []
            
            for cam_config in images_config:
                if not isinstance(cam_config, dict):
                    continue
                
                cam_name = cam_config.get('cam_name', '')
                if not cam_name:
                    continue
                
                # 构造第0帧的图像路径
                h5_path = cam_config.get('args', {}).get('h5_path', '')
                if not h5_path:
                    # 如果没有h5_path，尝试默认路径
                    img_path = frame_0_dir / f"{cam_name}.jpg"
                else:
                    # 替换{frame_idx}占位符
                    img_relative_path = h5_path.replace('{frame_idx}', '0')
                    img_path = first_episode / img_relative_path
                
                # 检查图像是否存在
                if img_path.exists():
                    available_cameras.append(cam_config)
                elif cam_name in self.required_cameras:
                    # 必需相机缺失，保留配置，稍后在预验证阶段会报错
                    available_cameras.append(cam_config)
                else:
                    # 可选相机缺失，移除
                    removed_cameras.append(cam_name)
                    if self.logger:
                        self.logger.info(
                            f"ℹ️  可选相机 '{cam_name}' 在第0帧不存在，已从配置中移除"
                        )
            
            # 更新配置
            if removed_cameras:
                self.converter_config['features']['observation']['images'] = available_cameras
                if self.logger:
                    self.logger.info(
                        f"📋 软通容错：移除了 {len(removed_cameras)} 个不可用的可选相机: "
                        f"{', '.join(removed_cameras)}"
                    )
        
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"⚠️  检查可选相机时出错: {e}，将在预验证阶段检查"
                )

    def _prevalidate_files(self) -> None:
        """验证数据集文件完整性
        
        使用 _get_all_episode_dirs() 进行递归搜索，支持任意深度的嵌套结构（最多5层）
        
        🆕 软通容错：检查必需相机是否存在
        """
        for task_path in self.path_task_dict.keys():
            # 使用现有的递归搜索方法查找所有 episode 目录
            try:
                episodes = self._get_all_episode_dirs(task_path)
            except FileNotFoundError:
                # _get_all_episode_dirs() 已经会抛出详细的错误信息
                raise
            
            for ep_dir in episodes:
                h5_file = ep_dir / "aligned_joints.h5"
                camera_dir = ep_dir / "camera"
                meta_file = ep_dir / "meta_info.json"
                
                if not h5_file.exists():
                    raise FileNotFoundError(
                        f"❌ H5 file not found.\n"
                        f"   📁 Episode directory: {ep_dir}\n"
                        f"   🗂️  Expected file: aligned_joints.h5\n"
                        f"   💡 This file should contain state and action data"
                    )
                
                if not camera_dir.exists():
                    available_items = [item.name for item in ep_dir.iterdir()]
                    raise FileNotFoundError(
                        f"❌ Camera directory not found.\n"
                        f"   📁 Episode directory: {ep_dir}\n"
                        f"   📂 Expected directory: camera/\n"
                        f"   📋 Available items: {available_items}\n"
                        f"   💡 Camera directory should contain frame subdirectories with images"
                    )
                
                # 🆕 软通容错：检查必需相机（在第0帧）
                frame_0_dir = camera_dir / "0"
                if frame_0_dir.exists():
                    missing_required_cameras = []
                    
                    for required_cam in self.required_cameras:
                        # 查找该相机的配置
                        cam_config = None
                        for img_config in self.converter_config.get('features', {}).get('observation', {}).get('images', []):
                            if isinstance(img_config, dict) and img_config.get('cam_name') == required_cam:
                                cam_config = img_config
                                break
                        
                        if not cam_config:
                            # 配置中没有这个相机，跳过检查
                            continue
                        
                        # 构造图像路径
                        h5_path = cam_config.get('args', {}).get('h5_path', '')
                        if not h5_path:
                            img_path = frame_0_dir / f"{required_cam}.jpg"
                        else:
                            img_relative_path = h5_path.replace('{frame_idx}', '0')
                            img_path = ep_dir / img_relative_path
                        
                        # 检查图像是否存在
                        if not img_path.exists():
                            missing_required_cameras.append(required_cam)
                    
                    if missing_required_cameras:
                        available_cameras = []
                        if frame_0_dir.exists():
                            available_cameras = [f.name for f in frame_0_dir.iterdir() if f.is_file() and f.suffix == '.jpg']
                        
                        raise FileNotFoundError(
                            f"❌ 必需相机缺失，跳过整个episode\n"
                            f"   📁 Episode directory: {ep_dir}\n"
                            f"   📂 Frame 0 directory: {frame_0_dir}\n"
                            f"   ❌ 缺失的必需相机: {', '.join(missing_required_cameras)}\n"
                            f"   📋 第0帧可用图像: {available_cameras if available_cameras else '无'}\n"
                            f"   💡 必需相机: {', '.join(self.required_cameras)}\n"
                            f"      这些相机缺失将导致整个episode被跳过"
                        )
                
                if not meta_file.exists():
                    if self.logger:
                        self.logger.warning(
                            f"⚠️  meta_info.json not found in {ep_dir.name} (optional file)"
                        )

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的 episode 数量"""
        episodes = self._get_all_episode_dirs(task_path)
        return len(episodes)

    def _get_all_episode_dirs(self, task_path: Path) -> list[Path]:
        """获取所有 episode 目录（支持嵌套结构）
        
        该方法支持多种结构：
        1. 扁平结构：task_path/episode_0/aligned_joints.h5
        2. 嵌套结构：task_path/sub_dir1/sub_dir2/episode_0/aligned_joints.h5
        
        判断标准：包含 aligned_joints.h5 文件的目录即为 episode 目录
        """
        def find_episode_dirs(path: Path, max_depth: int = 5, current_depth: int = 0) -> list[Path]:
            """递归查找episode目录（最多支持5层嵌套）"""
            if current_depth > max_depth:
                return []
            
            episode_dirs = []
            
            # 检查当前目录是否是episode目录（包含 aligned_joints.h5）
            h5_file = path / "aligned_joints.h5"
            if h5_file.exists():
                episode_dirs.append(path)
                return episode_dirs  # 找到episode目录后不再向下搜索
            
            # 否则继续向下搜索子目录
            try:
                for sub_dir in path.iterdir():
                    # 跳过隐藏目录和特殊目录（以 . 或 @ 开头）
                    if sub_dir.is_dir() and not sub_dir.name.startswith('.') and not sub_dir.name.startswith('@'):
                        episode_dirs.extend(find_episode_dirs(sub_dir, max_depth, current_depth + 1))
            except PermissionError:
                if self.logger:
                    self.logger.warning(f"Permission denied when accessing {path}")
            
            return episode_dirs
        
        episodes = find_episode_dirs(task_path)
        
        if not episodes:
            # 收集目录结构用于错误诊断（显示前3层）
            def collect_dir_structure(path: Path, max_depth: int = 3, current_depth: int = 0, prefix: str = "") -> list[str]:
                """收集目录结构用于诊断"""
                if current_depth >= max_depth:
                    return []
                
                structure = []
                try:
                    items = sorted([item for item in path.iterdir() if item.is_dir() and not item.name.startswith('.')],
                                   key=lambda x: x.name)
                    for item in items[:10]:  # 每层最多显示10个目录
                        indent = "  " * current_depth
                        structure.append(f"{indent}{prefix}{item.name}/")
                        if current_depth < max_depth - 1:
                            structure.extend(collect_dir_structure(item, max_depth, current_depth + 1, ""))
                    if len(items) > 10:
                        indent = "  " * current_depth
                        structure.append(f"{indent}... and {len(items) - 10} more directories")
                except (PermissionError, OSError):
                    pass
                return structure
            
            dir_structure = collect_dir_structure(task_path)
            structure_str = "\n".join(dir_structure) if dir_structure else "Empty or inaccessible"
            
            raise FileNotFoundError(
                f"❌ No episode directories found.\n"
                f"   📁 Task path: {task_path}\n"
                f"   🔍 Searched up to 5 levels deep\n"
                f"   📂 Directory structure (first 3 levels):\n{structure_str}\n"
                f"   🗂️  Expected: Directories containing 'aligned_joints.h5' file\n"
                f"   💡 Check if:\n"
                f"      1. Episode directories exist under task path\n"
                f"      2. Each episode directory contains 'aligned_joints.h5' file\n"
                f"      3. File permissions are correct\n"
                f"      4. Directory names don't start with '.' or '@' (these are skipped)"
            )
        
        return sorted(episodes)

    def _get_episode_dir(self, task_path: Path, ep_idx: int) -> Path:
        """获取指定的 episode 目录"""
        episodes = self._get_all_episode_dirs(task_path)
        if ep_idx >= len(episodes):
            episode_names = [ep.name for ep in episodes]
            raise IndexError(
                f"❌ Episode index out of range.\n"
                f"   📁 Task path: {task_path}\n"
                f"   🎯 Requested ep_idx: {ep_idx}\n"
                f"   📊 Available episodes: {len(episodes)} (valid range: 0-{len(episodes)-1})\n"
                f"   📋 Episode names: {episode_names}\n"
                f"   💡 Check if ep_idx is within valid range"
            )
        return episodes[ep_idx]

    def _get_h5_file(self, task_path: Path, ep_idx: int) -> h5py.File:
        """获取 H5 文件（使用专业缓存）"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        h5_path = ep_dir / "aligned_joints.h5"
        
        # 使用 H5FileCache.get() 直接返回h5py.File对象（不是上下文管理器）
        return self._h5_file_cache.get(h5_path)

    def _get_meta_info(self, task_path: Path, ep_idx: int) -> dict:
        """获取元数据（带缓存）"""
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        meta_file = ep_dir / "meta_info.json"
        
        cache_key = str(meta_file)
        if cache_key not in self._meta_info_cache:
            if meta_file.exists():
                with open(meta_file) as f:
                    self._meta_info_cache[cache_key] = json.load(f)
            else:
                self._meta_info_cache[cache_key] = {}
        
        return self._meta_info_cache[cache_key]

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取 episode 的帧数
        
        注意：
        1. H5 文件中可能有 490 帧，但 camera 目录可能只有部分帧
        2. 帧编号可能不连续（例如：0, 1, 10, 11, 12...）
        需要使用实际存在的帧列表
        """
        h5_file = self._get_h5_file(task_path, ep_idx)
        
        # 从 timestamp 或任一 dataset 获取帧数
        if 'timestamp' in h5_file:
            h5_frames = len(h5_file['timestamp'])
        elif 'state/joint/position' in h5_file:
            h5_frames = h5_file['state/joint/position'].shape[0]
        else:
            available_keys = list(h5_file.keys())
            raise ValueError(
                f"❌ Cannot determine frame count from H5 file.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   🗂️  H5 file: aligned_joints.h5\n"
                f"   📋 Available top-level keys: {available_keys}\n"
                f"   💡 Expected 'timestamp' or 'state/joint/position' key\n"
                f"      Check if H5 file structure matches expected format"
            )
        
        # 获取 camera 目录中实际存在的帧
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        camera_dir = ep_dir / "camera"
        frame_dirs = [d for d in camera_dir.glob("[0-9]*") if d.is_dir()]
        
        if not frame_dirs:
            available_items = [item.name for item in camera_dir.iterdir() if item.is_dir()]
            raise FileNotFoundError(
                f"❌ No frame directories found.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   📂 Camera directory: {camera_dir}\n"
                f"   📋 Subdirectories: {available_items if available_items else 'None'}\n"
                f"   💡 Expected numeric frame directories (e.g., 0/, 1/, 2/...)\n"
                f"      Each should contain camera image files"
            )
        
        # 获取帧编号列表并排序
        frame_indices = sorted([int(d.name) for d in frame_dirs])
        
        # 保存帧索引映射供后续使用
        cache_key = str(ep_dir)
        if not hasattr(self, '_frame_indices_cache'):
            self._frame_indices_cache = {}
        self._frame_indices_cache[cache_key] = frame_indices
        
        # 返回实际可用的帧数（取 H5 帧数和最大帧索引+1 的最小值）
        max_frame_idx = frame_indices[-1]
        return min(h5_frames, max_frame_idx + 1, len(frame_indices))

    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 episode 的源文件信息（override）
        
        Returns:
            dict: 包含源文件详细信息
        """
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        
        # 相对路径（相对于 dataset_path）
        relative_ep_dir = ep_dir.relative_to(self.dataset_path)
        
        # 收集所有源文件
        h5_file = ep_dir / "aligned_joints.h5"
        meta_file = ep_dir / "meta_info.json"
        camera_dir = ep_dir / "camera"
        
        source_info = {
            "format": "H5+JPG",  # 🆕 添加格式标识
            "episode_directory": str(relative_ep_dir),
            "absolute_path": str(ep_dir.absolute()),  # 🆕 添加主绝对路径
            "h5_file": str(h5_file.relative_to(self.dataset_path)) if h5_file.exists() else None,
            "h5_absolute_path": str(h5_file.absolute()) if h5_file.exists() else None,  # 🆕 H5绝对路径
            "meta_file": str(meta_file.relative_to(self.dataset_path)) if meta_file.exists() else None,
            "camera_directory": str(camera_dir.relative_to(self.dataset_path)) if camera_dir.exists() else None,
        }
        
        # 统计图像文件数量（不列出所有文件，只统计数量以节省空间）
        if camera_dir.exists():
            frame_dirs = [d for d in camera_dir.glob("[0-9]*") if d.is_dir()]
            image_count = 0
            for frame_dir in frame_dirs:
                image_count += len(list(frame_dir.glob("*.jpg")))
                image_count += len(list(frame_dir.glob("*.png")))
            
            source_info["image_frames_count"] = len(frame_dirs)
            source_info["total_images_count"] = image_count
        
        return source_info


    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> dict:
        """准备 episode 的图像缓冲区
        
        返回包含 episode_dir 路径的字典，实际图像按需加载
        """
        ep_dir = self._get_episode_dir(task_path, ep_idx)
        return {"episode_dir": ep_dir}

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> h5py.File:
        """准备 episode 的状态缓冲区"""
        return self._get_h5_file(task_path, ep_idx)

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> h5py.File:
        """准备 episode 的动作缓冲区"""
        return self._get_h5_file(task_path, ep_idx)

    def _get_frame_image(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        images_buffer: dict | None = None,
    ) -> np.ndarray:
        """获取指定帧的图像
        
        注意：帧编号可能不连续，需要使用映射表
        
        🆕 软通容错：
        - 可选相机缺失时，复制上一帧
        - 必需相机缺失时，抛出错误
        """
        if images_buffer is None:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)
        
        ep_dir = images_buffer["episode_dir"]
        
        # 获取实际的帧索引（处理不连续的帧编号）
        cache_key = str(ep_dir)
        if hasattr(self, '_frame_indices_cache') and cache_key in self._frame_indices_cache:
            frame_indices = self._frame_indices_cache[cache_key]
            if frame_idx >= len(frame_indices):
                raise IndexError(
                    f"❌ Frame index out of range.\n"
                    f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                    f"   🎯 Requested frame_idx: {frame_idx}\n"
                    f"   📊 Available frames: {len(frame_indices)} (valid range: 0-{len(frame_indices)-1})\n"
                    f"   🔢 Frame indices: {frame_indices[:10]}{'...' if len(frame_indices) > 10 else ''}\n"
                    f"   💡 Note: Frame indices may not be continuous (e.g., 0,1,10,11...)\n"
                    f"      Check if frame_idx exceeds available frame count"
                )
            actual_frame_idx = frame_indices[frame_idx]
        else:
            # 如果没有缓存，直接使用 frame_idx
            actual_frame_idx = frame_idx
        
        # 从 args_dict 获取图像路径模板和相机名称
        h5_path = args_dict.get("h5_path", "")
        cam_name = args_dict.get("cam_name", "unknown")
        
        # 替换 {frame_idx} 占位符为实际的帧索引
        image_path = h5_path.replace("{frame_idx}", str(actual_frame_idx))
        full_path = ep_dir / image_path
        
        # 🆕 尝试读取图像，实现容错逻辑
        try:
            if not full_path.exists():
                raise FileNotFoundError(f"Image not found: {full_path}")
            
            # 读取图像
            img = Image.open(full_path)
            img_array = np.array(img)
            
            # 确保 RGB 格式
            if len(img_array.shape) == 2:
                # Grayscale image, add channel dimension
                img_array = np.expand_dims(img_array, axis=-1)
            elif img_array.shape[2] == 4:
                # RGBA image, convert to RGB
                img_array = img_array[:, :, :3]
            
            # 🆕 成功读取，更新缓存
            cache_key_frame = (str(task_path), ep_idx, cam_name)
            self._previous_frame_cache[cache_key_frame] = (frame_idx, img_array.copy())
            
            return img_array
        
        except (FileNotFoundError, IOError) as e:
            # 🆕 图像读取失败，判断是必需相机还是可选相机
            is_required = cam_name in self.required_cameras
            
            if is_required:
                # ❌ 必需相机缺失，抛出错误
                frame_dir = full_path.parent
                available_files = []
                if frame_dir.exists():
                    available_files = [f.name for f in frame_dir.iterdir() if f.is_file()]
                
                raise FileNotFoundError(
                    f"❌ 必需相机图像缺失\n"
                    f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                    f"   🎯 Logical frame_idx: {frame_idx}, Actual frame_idx: {actual_frame_idx}\n"
                    f"   📷 Camera: {cam_name} (必需相机)\n"
                    f"   🖼️  Expected file: {full_path}\n"
                    f"   📂 Frame directory: {frame_dir}\n"
                    f"   📋 Available files: {available_files if available_files else 'Directory not found'}\n"
                    f"   💡 必需相机: {', '.join(self.required_cameras)}\n"
                    f"      必需相机缺失将导致整个episode被跳过"
                ) from e
            else:
                # 🔶 可选相机缺失，尝试复制上一帧
                cache_key_frame = (str(task_path), ep_idx, cam_name)
                
                if frame_idx > 0 and cache_key_frame in self._previous_frame_cache:
                    # 📋 复制上一帧
                    prev_frame_idx, prev_img_array = self._previous_frame_cache[cache_key_frame]
                    if self.logger:
                        self.logger.warning(
                            f"⚠️  可选相机图像缺失，已复制上一帧\n"
                            f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                            f"   🎯 Frame: {frame_idx} (actual: {actual_frame_idx})\n"
                            f"   📷 Camera: {cam_name} (可选相机)\n"
                            f"   📋 Copied from frame: {prev_frame_idx}"
                        )
                    return prev_img_array.copy()
                else:
                    # ❌ 第0帧或上一帧也不存在，抛出错误
                    frame_dir = full_path.parent
                    available_files = []
                    if frame_dir.exists():
                        available_files = [f.name for f in frame_dir.iterdir() if f.is_file()]
                    
                    raise FileNotFoundError(
                        f"❌ 可选相机图像缺失且无法复制上一帧\n"
                        f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                        f"   🎯 Logical frame_idx: {frame_idx}, Actual frame_idx: {actual_frame_idx}\n"
                        f"   📷 Camera: {cam_name} (可选相机)\n"
                        f"   🖼️  Expected file: {full_path}\n"
                        f"   📂 Frame directory: {frame_dir}\n"
                        f"   📋 Available files: {available_files if available_files else 'Directory not found'}\n"
                        f"   💡 该相机在第0帧就不存在，应该已在初始化时被移除\n"
                        f"      这可能是配置问题，请检查配置文件"
                    ) from e

    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: h5py.File | None = None,
    ) -> np.ndarray:
        """获取指定帧的子状态数据"""
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        
        h5_path = args_dict["h5_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        
        # 检查路径是否存在
        if h5_path not in sub_states_buffer:
            available_paths = list(sub_states_buffer.keys())
            # 提供部分匹配建议
            similar_paths = [p for p in available_paths if any(part in p for part in h5_path.split('/'))]
            raise KeyError(
                f"❌ H5 state path not found.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   🗂️  Requested h5_path: '{h5_path}'\n"
                f"   📋 Available paths: {available_paths[:10]}{'...' if len(available_paths) > 10 else ''}\n"
                f"   🔍 Similar paths: {similar_paths if similar_paths else 'None'}\n"
                f"   💡 Check if:\n"
                f"      1. h5_path in config matches H5 file structure\n"
                f"      2. State data is under 'state/' prefix\n"
                f"      3. Path syntax is correct (use '/' separator)"
            )
        
        dataset = sub_states_buffer[h5_path]
        
        # 检查是否需要处理额外的数组索引（例如 end/position 是 (N, 2, 3)）
        array_index = args_dict.get("array_index")
        
        if array_index is not None:
            # 有额外的维度，需要先索引
            if frame_idx >= dataset.shape[0]:
                raise IndexError(
                    f"❌ Frame index out of range in H5 dataset.\n"
                    f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                    f"   🗂️  H5 path: '{h5_path}'\n"
                    f"   🎯 Requested frame_idx: {frame_idx}\n"
                    f"   📐 Dataset shape: {dataset.shape}\n"
                    f"   🔢 Valid frame range: 0-{dataset.shape[0]-1}\n"
                    f"   🔢 Array index: {array_index}, Range: [{from_idx}:{to_idx}]\n"
                    f"   💡 Frame index exceeds first dimension of dataset"
                )
            return dataset[frame_idx, array_index, from_idx:to_idx]
        
        # 标准的 2D 数组
        if frame_idx >= dataset.shape[0]:
            raise IndexError(
                f"❌ Frame index out of range in H5 dataset.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   🗂️  H5 path: '{h5_path}'\n"
                f"   🎯 Requested frame_idx: {frame_idx}\n"
                f"   📐 Dataset shape: {dataset.shape}\n"
                f"   🔢 Valid frame range: 0-{dataset.shape[0]-1}\n"
                f"   🔢 Extracting range: [{from_idx}:{to_idx}]\n"
                f"   💡 Frame index exceeds dataset first dimension"
            )
        return dataset[frame_idx, from_idx:to_idx]

    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: h5py.File | None = None,
    ) -> np.ndarray:
        """获取指定帧的子动作数据"""
        if sub_actions_buffer is None:
            sub_actions_buffer = self._prepare_episode_actions_buffer(task_path, ep_idx)
        
        h5_path = args_dict["h5_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]
        
        # 检查路径是否存在
        if h5_path not in sub_actions_buffer:
            available_paths = list(sub_actions_buffer.keys())
            # 提供部分匹配建议
            similar_paths = [p for p in available_paths if any(part in p for part in h5_path.split('/'))]
            raise KeyError(
                f"❌ H5 action path not found.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   🗂️  Requested h5_path: '{h5_path}'\n"
                f"   📋 Available paths: {available_paths[:10]}{'...' if len(available_paths) > 10 else ''}\n"
                f"   🔍 Similar paths: {similar_paths if similar_paths else 'None'}\n"
                f"   💡 Check if:\n"
                f"      1. h5_path in config matches H5 file structure\n"
                f"      2. Action data is under 'action/' prefix (not 'state/')\n"
                f"      3. Path syntax is correct (use '/' separator)"
            )
        
        dataset = sub_actions_buffer[h5_path]
        
        # 检查是否需要处理额外的数组索引
        array_index = args_dict.get("array_index")
        
        if array_index is not None:
            if frame_idx >= dataset.shape[0]:
                raise IndexError(
                    f"❌ Frame index out of range in H5 dataset.\n"
                    f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                    f"   🗂️  H5 path: '{h5_path}'\n"
                    f"   🎯 Requested frame_idx: {frame_idx}\n"
                    f"   📐 Dataset shape: {dataset.shape}\n"
                    f"   🔢 Valid frame range: 0-{dataset.shape[0]-1}\n"
                    f"   🔢 Array index: {array_index}, Range: [{from_idx}:{to_idx}]\n"
                    f"   💡 Frame index exceeds first dimension of action dataset"
                )
            return dataset[frame_idx, array_index, from_idx:to_idx]
        
        if frame_idx >= dataset.shape[0]:
            raise IndexError(
                f"❌ Frame index out of range in H5 dataset.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   🗂️  H5 path: '{h5_path}'\n"
                f"   🎯 Requested frame_idx: {frame_idx}\n"
                f"   📐 Dataset shape: {dataset.shape}\n"
                f"   🔢 Valid frame range: 0-{dataset.shape[0]-1}\n"
                f"   🔢 Extracting range: [{from_idx}:{to_idx}]\n"
                f"   💡 Frame index exceeds action dataset first dimension"
            )
        return dataset[frame_idx, from_idx:to_idx]

    def convert(self, is_test: bool = False):
        """执行转换并记录缓存统计
        
        Yields:
            (task, task_ep_idx, global_ep_idx): 成功转换的episode信息
        """
        # 调用父类的 convert 方法并 yield 结果
        yield from super().convert(is_test=is_test)
        
        # 记录 H5 缓存统计
        stats = self._h5_file_cache.get_stats()
        if self.logger and stats:
            self.logger.info(f"H5 File Cache Stats: {stats}")
