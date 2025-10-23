"""
LeRobot格式转换器 - MP4+JSON格式
处理MP4视频文件配合JSON数据文件的数据集
"""

import json
import logging
from pathlib import Path

import cv2
import numpy as np

from robocoin_dataset.format_converter.tolerobot.constant import (
    CAM_NAME_KEY,
)
from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)
from robocoin_dataset.format_converter.tolerobot.video_frame_validator import (
    validate_video_frame_count,
)
from robocoin_dataset.format_converter.tolerobot.lazy_video_reader import (
    LazyVideoReader,
    LazyVideoReaderPool,
)
from robocoin_dataset.format_converter.utils.unified_episode_locator import (
    UnifiedEpisodeLocator,
    is_mp4_json_episode,
)


class LerobotFormatConverterMp4Json(LerobotFormatConverter):
    """MP4+JSON格式转换器 - 用于yinhe等数据集"""
    
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
        strict_episodes: int = 3,
        failure_threshold: float = 0.8,
    ) -> None:
        # 🚀 在super().__init__之前初始化，因为父类会调用_get_all_episode_dirs
        self._episode_locator = UnifiedEpisodeLocator(logger=logger)
        
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
            strict_episodes=strict_episodes,
            failure_threshold=failure_threshold,
        )
        self._json_data_cache = {}  # 缓存JSON数据
        self._is_test_mode = False  # Test模式标志（限制加载帧数）
        self._video_caps = {}  # 延迟加载的VideoCapture对象缓存 {(task_path, ep_idx, cam_name): cv2.VideoCapture}

    def convert(self, is_test: bool = False) -> None:
        """重写父类方法以设置test模式标志
        
        Args:
            is_test: 是否为测试模式。测试模式只处理少量帧以快速验证
        """
        self._is_test_mode = is_test
        if is_test and self.logger:
            self.logger.info("🧪 Mp4Json Converter running in TEST mode - will only load first 11 frames per video")
        
        # 调用父类的转换逻辑
        super().convert(is_test=is_test)

    def _prevalidate_files(self) -> None:
        """验证数据集文件完整性"""
        for task_path in self.path_task_dict.keys():
            # 🆕 增加：检查task_path本身是否存在
            if not task_path.exists():
                parent_dir = task_path.parent
                siblings = []
                if parent_dir.exists():
                    siblings = [d.name for d in parent_dir.iterdir() if d.is_dir()]
                
                raise FileNotFoundError(
                    f"❌ MP4+JSON任务路径不存在\n"
                    f"📁 请求的路径：{task_path}\n"
                    f"📂 父目录：{parent_dir} {'(存在)' if parent_dir.exists() else '(不存在)'}\n"
                    f"🗂️ 父目录中的子目录：\n" +
                    "\n".join(f"   - {d}" for d in sorted(siblings)[:10]) +
                    (f"\n   ... 还有 {len(siblings) - 10} 个目录" if len(siblings) > 10 else "") +
                    "\n💡 请检查：\n"
                    "   1. 路径配置是否正确\n"
                    "   2. 数据集是否已下载或挂载\n"
                    "   3. 路径拼写是否有误"
                )
            
            if not task_path.is_dir():
                raise ValueError(
                    f"❌ MP4+JSON任务路径不是目录\n"
                    f"📄 路径：{task_path}\n"
                    f"🔍 实际类型：{'文件' if task_path.is_file() else '符号链接' if task_path.is_symlink() else '未知'}\n"
                    "💡 任务路径必须是包含episode子目录的目录"
                )
            
            try:
                episodes = self._get_all_episode_dirs(task_path)
            except FileNotFoundError as e:
                all_items = [item.name for item in task_path.iterdir()] if task_path.exists() else []
                raise FileNotFoundError(
                    f"❌ MP4+JSON无法找到episode目录\n"
                    f"📁 任务路径：{task_path}\n"
                    f"📋 目录内容：{all_items[:10] if all_items else '(空目录)'}\n"
                    f"⚠️ 原始错误：{str(e)}\n"
                    "💡 请检查：\n"
                    "   1. Episode目录是否存在\n"
                    "   2. 目录命名是否符合规范\n"
                    "   3. 数据集是否完整提取"
                ) from e
            
            if not episodes:
                all_items = [item.name for item in task_path.iterdir()]
                raise FileNotFoundError(
                    f"❌ MP4+JSON未找到episode目录\n"
                    f"📁 任务路径：{task_path}\n"
                    f"📋 目录内容：{all_items[:15]}\n"
                    "💡 期望找到包含data.json和MP4文件的episode子目录\n"
                    "📋 请检查数据集结构是否正确"
                )
            
            for ep_dir in episodes:
                json_file = ep_dir / "data.json"
                if not json_file.exists():
                    ep_files = [f.name for f in ep_dir.iterdir() if f.is_file()]
                    raise FileNotFoundError(
                        f"❌ MP4+JSON数据文件缺失\n"
                        f"📂 Episode目录：{ep_dir}\n"
                        f"📄 期望文件：data.json\n"
                        f"📋 目录中的文件：{ep_files[:10] if ep_files else '(无文件)'}\n"
                        "💡 每个episode必须包含data.json文件"
                    )
                
                # 🆕 增加：验证JSON文件内容
                try:
                    import json
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    
                    # 检查JSON基本结构
                    if not isinstance(json_data, dict):
                        raise ValueError(
                            f"❌ MP4+JSON数据格式错误\n"
                            f"📄 文件：{json_file}\n"
                            f"❌ 期望类型：dict (字典)\n"
                            f"❌ 实际类型：{type(json_data).__name__}\n"
                            "💡 data.json应该是一个JSON对象（字典）"
                        )
                    
                    # 检查是否有相机数据
                    if not json_data:
                        self.logger.warning(
                            f"⚠️ JSON文件为空对象：{json_file}\n"
                            "💡 这可能导致后续处理失败"
                        )
                
                except json.JSONDecodeError as e:
                    file_size = json_file.stat().st_size if json_file.exists() else 0
                    raise ValueError(
                        f"❌ MP4+JSON文件解析失败\n"
                        f"📄 文件：{json_file}\n"
                        f"📊 文件大小：{file_size} bytes\n"
                        f"⚠️ 错误位置：行{e.lineno}, 列{e.colno}\n"
                        f"⚠️ 错误信息：{e.msg}\n"
                        "💡 可能原因：\n"
                        "   1. JSON语法错误（缺少引号、逗号等）\n"
                        "   2. 文件编码问题\n"
                        "   3. 文件损坏或不完整\n"
                        "📋 建议使用JSON验证工具检查文件格式"
                    ) from e
                
                except UnicodeDecodeError as e:
                    raise ValueError(
                        f"❌ MP4+JSON文件编码错误\n"
                        f"📄 文件：{json_file}\n"
                        f"⚠️ 错误：{str(e)}\n"
                        "💡 文件可能使用了非UTF-8编码\n"
                        "📋 请确保JSON文件使用UTF-8编码"
                    ) from e
                
                except Exception as e:
                    raise ValueError(
                        f"❌ MP4+JSON文件读取失败\n"
                        f"📄 文件：{json_file}\n"
                        f"⚠️ 错误类型：{type(e).__name__}\n"
                        f"⚠️ 错误详情：{str(e)}\n"
                        "💡 请检查文件权限和完整性"
                    ) from e
                
                # 检查是否有对应的MP4文件
                mp4_files = list(ep_dir.glob("*.mp4"))
                if not mp4_files:
                    all_files = [f.name for f in ep_dir.iterdir() if f.is_file()]
                    video_files = [f for f in all_files if any(f.endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv'])]
                    
                    raise FileNotFoundError(
                        f"❌ MP4+JSON视频文件缺失\n"
                        f"📂 Episode目录：{ep_dir}\n"
                        f"📹 期望格式：*.mp4\n"
                        f"📋 目录中的文件：{all_files[:10] if all_files else '(无文件)'}\n"
                        f"🎥 其他视频格式：{video_files if video_files else '(无)'}\n"
                        "💡 请检查：\n"
                        "   1. 视频文件是否已录制\n"
                        "   2. 文件扩展名是否为.mp4\n"
                        "   3. 文件是否在正确的episode目录中"
                    )
                
                # 🆕 增加：验证视频帧数与JSON数据帧数是否匹配
                expected_frame_count = None
                
                if 'data' in json_data:
                    # 处理两种JSON格式：
                    # 1. 简单格式: {"data": [frame1, frame2, ...]}
                    # 2. yinhe格式: {"data": {"camera_front": [...], "camera_left": [...], ...}}
                    if isinstance(json_data['data'], list):
                        # 简单格式：data是一个列表
                        expected_frame_count = len(json_data['data'])
                    elif isinstance(json_data['data'], dict):
                        # yinhe格式：data是一个字典，包含多个数据流
                        # 使用_get_episode_frames_num的逻辑来计算最小帧数
                        json_frame_counts = {}
                        for key, value in json_data['data'].items():
                            if isinstance(value, list) and len(value) > 0:
                                json_frame_counts[key] = len(value)
                        
                        if json_frame_counts:
                            expected_frame_count = min(json_frame_counts.values())
                            if self.logger:
                                self.logger.info(
                                    f"🔍 Detected yinhe-style JSON format with {len(json_frame_counts)} data streams\n"
                                    f"   📊 Frame counts: {json_frame_counts}\n"
                                    f"   📊 Using minimum: {expected_frame_count}"
                                )
                
                if expected_frame_count is not None:
                    if self.logger:
                        self.logger.info(
                            f"🔍 Validating video frame counts for episode: {ep_dir.name}\n"
                            f"   📊 JSON data frames: {expected_frame_count}"
                        )
                    
                    # 验证每个MP4文件的帧数
                    for mp4_file in mp4_files:
                        try:
                            validate_video_frame_count(
                                video_path=mp4_file,
                                expected_frame_count=expected_frame_count,
                                data_source="JSON data",
                                logger=self.logger,
                                tolerance=0  # 要求完全匹配
                            )
                        except ValueError as e:  # noqa: PERF203
                            # 帧数不匹配，抛出详细错误
                            raise ValueError(
                                f"❌ MP4+JSON帧数不匹配\n"
                                f"📂 Episode: {ep_dir.name}\n"
                                f"📄 Video: {mp4_file.name}\n"
                                f"📄 JSON: {json_file.name}\n"
                                f"{str(e)}"
                            ) from e
                        except RuntimeError as e:
                            # ffprobe执行失败
                            if self.logger:
                                self.logger.warning(
                                    f"⚠️ 无法验证视频帧数（跳过）\n"
                                    f"📄 Video: {mp4_file.name}\n"
                                    f"⚠️ 原因: {str(e)}\n"
                                    "💡 请确保已安装ffprobe (ffmpeg的一部分)"
                                )
                else:
                    if self.logger:
                        self.logger.warning(
                            f"⚠️ 无法从JSON获取帧数信息：{json_file.name}\n"
                            "💡 JSON结构不包含有效的数据列表或字典，跳过帧数验证"
                        )

    def _load_json_data(self, task_path: Path, ep_idx: int) -> dict:
        """加载JSON数据（带缓存）"""
        episodes = self._get_all_episode_dirs(task_path)
        if ep_idx >= len(episodes):
            raise IndexError(
                f"❌ Episode index out of range.\n"
                f"   📁 Location: task_path={task_path}\n"
                f"   🎯 Requested ep_idx: {ep_idx}\n"
                f"   📊 Found episodes: {len(episodes)}\n"
                f"   💡 Valid episode indices: 0-{len(episodes)-1}"
            )
        
        ep_dir = episodes[ep_idx]
        json_file = ep_dir / "data.json"
        
        if not json_file.exists():
            raise FileNotFoundError(
                f"❌ JSON file not found.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   📂 Episode directory: {ep_dir}\n"
                f"   📄 Expected file: {json_file}\n"
                f"   💡 Check if data.json exists in the episode directory."
            )
        
        cache_key = str(json_file)
        if cache_key not in self._json_data_cache:
            try:
                with open(json_file) as f:
                    data = json.load(f)
                
                # 验证JSON结构
                if not isinstance(data, dict):
                    raise ValueError(
                        f"❌ Invalid JSON structure.\n"
                        f"   📄 File: {json_file}\n"
                        f"   ❌ Expected dict at root, but got {type(data).__name__}\n"
                        f"   💡 JSON file should contain a dictionary at the root level."
                    )
                
                self._json_data_cache[cache_key] = data
                
                if self.logger:
                    self.logger.debug(
                        f"✓ Loaded JSON data from {json_file.name} "
                        f"(keys: {list(data.keys())})"
                    )
                    
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"❌ Failed to parse JSON file.\n"
                    f"   📄 File: {json_file}\n"
                    f"   ❌ JSON error at line {e.lineno}, column {e.colno}: {e.msg}\n"
                    f"   💡 Check if JSON file is corrupted or has syntax errors."
                ) from e
            except Exception as e:
                raise RuntimeError(
                    f"❌ Failed to load JSON file.\n"
                    f"   📄 File: {json_file}\n"
                    f"   ❌ Error: {e!s}\n"
                    f"   💡 Check file permissions and disk space."
                ) from e
        
        return self._json_data_cache[cache_key]

    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        """获取episode的帧数
        
        需要返回所有数据源（JSON数据和视频文件）中的最小帧数，
        以确保所有帧都有完整的数据（observation、state、action）
        """
        # 1. 从JSON获取帧数（记录每个字段的详细信息）
        json_data = self._load_json_data(task_path, ep_idx)
        json_frame_counts = {}  # key -> frame_count
        
        if 'data' in json_data:
            for key, value in json_data['data'].items():
                if isinstance(value, list) and len(value) > 0:
                    json_frame_counts[key] = len(value)
        
        if not json_frame_counts:
            raise ValueError(
                f"❌ Cannot determine frame count from JSON data.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   📋 Available keys: {list(json_data.get('data', {}).keys())}\n"
                f"   💡 No valid list data found in JSON file."
            )
        
        min_json_frames = min(json_frame_counts.values())
        max_json_frames = max(json_frame_counts.values())
        
        # 2. 从视频文件获取帧数（记录每个相机的详细信息）
        episodes = self._get_all_episode_dirs(task_path)
        if ep_idx >= len(episodes):
            if self.logger:
                self.logger.warning(
                    f"Episode index {ep_idx} out of range, using JSON frame count: {min_json_frames}"
                )
            # 🧪 Test模式：限制帧数
            if self._is_test_mode:
                min_json_frames = min(10, min_json_frames)
            return min_json_frames
        
        ep_dir = episodes[ep_idx]
        mp4_files = sorted(ep_dir.glob("*.mp4"))
        
        video_frame_counts = {}  # camera_name -> frame_count
        for mp4_file in mp4_files:
            cam_name = self._infer_camera_name(mp4_file.stem)
            if cam_name:
                cap = cv2.VideoCapture(str(mp4_file))
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
                if frame_count > 0:
                    video_frame_counts[cam_name] = frame_count
                else:
                    if self.logger:
                        self.logger.warning(
                            f"⚠️  Camera '{cam_name}' has 0 frames in file: {mp4_file.name}"
                        )
        
        if not video_frame_counts:
            raise ValueError(
                f"❌ No valid video frames found.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}, ep_dir={ep_dir}\n"
                f"   📹 MP4 files: {[f.name for f in mp4_files]}\n"
                f"   💡 Either no MP4 files found or all videos have 0 frames."
            )
        
        min_video_frames = min(video_frame_counts.values())
        max_video_frames = max(video_frame_counts.values())
        
        # 3. 返回所有数据源中的最小帧数
        min_frames = min(min_json_frames, min_video_frames)
        
        # 🧪 Test模式：限制帧数
        if self._is_test_mode:
            min_frames = min(10, min_frames)
            if self.logger:
                self.logger.debug(f"🧪 Test mode: limiting episode {ep_idx} to {min_frames} frames")
        
        # 4. 详细的帧数不一致警告
        if min_json_frames != max_json_frames or min_video_frames != max_video_frames or min_json_frames != min_video_frames:
            # 找出帧数最少的数据源
            all_sources = {}
            all_sources.update({f"JSON:{k}": v for k, v in json_frame_counts.items()})
            all_sources.update({f"Video:{k}": v for k, v in video_frame_counts.items()})
            
            min_source = min(all_sources, key=all_sources.get)
            min_source_count = all_sources[min_source]
            
            # 找出所有帧数不同的数据源
            mismatched_sources = {k: v for k, v in all_sources.items() if v != min_source_count}
            
            warning_msg = (
                f"⚠️  Frame count mismatch detected!\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   📊 Summary:\n"
                f"      - JSON frames: min={min_json_frames}, max={max_json_frames}\n"
                f"      - Video frames: min={min_video_frames}, max={max_video_frames}\n"
                f"      - Will use minimum: {min_frames} frames\n"
                f"   🔍 Bottleneck (minimum): {min_source} = {min_source_count} frames\n"
            )
            
            if mismatched_sources:
                warning_msg += f"   📋 All frame counts:\n"
                for source, count in sorted(all_sources.items(), key=lambda x: x[1]):
                    status = "✓" if count == min_source_count else f"⚠️ ({count - min_source_count:+d})"
                    warning_msg += f"      {status} {source}: {count} frames\n"
            
            if self.logger:
                self.logger.warning(warning_msg)
        
        # 5. 检查帧数是否为0（这会导致后续的ValueError）
        if min_frames == 0:
            raise ValueError(
                f"❌ Episode has 0 frames after applying minimum!\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   📊 Frame counts:\n"
                f"      - JSON: {dict(list(json_frame_counts.items())[:5])}{'...' if len(json_frame_counts) > 5 else ''}\n"
                f"      - Video: {video_frame_counts}\n"
                f"   💡 This will cause 'You must add one or several frames' error."
            )
        
        return min_frames

    def _get_task_episodes_num(self, task_path: Path) -> int:
        """获取任务的episode数量"""
        episodes = self._get_all_episode_dirs(task_path)
        return len(episodes)
    
    def _is_episode(self, path: Path) -> bool:
        """判断路径是否是一个episode
        
        MP4+JSON格式的episode标志：目录中包含data.json文件
        """
        return is_mp4_json_episode(path)
    
    def _get_all_episode_dirs(self, task_path: Path) -> list[Path]:
        """获取所有episode目录（使用BFS搜索，支持任意层级结构）
        
        🚀 改进：使用UnifiedEpisodeLocator进行BFS搜索
        - 不再限制固定层级（扁平/嵌套2层）
        - 支持任意深度的目录结构
        - 支持task_path本身就是episode的情况
        
        支持的结构：
        1. task_path本身就是episode: task_path/data.json
        2. 扁平结构: task_path/episode_0/data.json
        3. 嵌套结构: task_path/subdir1/subdir2/episode_0/data.json
        """
        episodes = self._episode_locator.locate_episodes_bfs(
            dataset_path=task_path,
            is_episode_func=self._is_episode,
            max_depth=10  # 最多搜索10层
        )
        
        if not episodes:
            # 收集目录信息用于诊断
            try:
                all_items = [item.name for item in task_path.iterdir()][:20]
            except Exception:
                all_items = []
            
            raise FileNotFoundError(
                f"❌ No episode directories with data.json found in '{task_path}'.\n"
                f"   🔍 Searched up to 10 levels deep using BFS.\n"
                f"   📋 Items in task_path (first 20): {all_items if all_items else '(empty or inaccessible)'}\n"
                f"   💡 Episode detection criteria: directory containing 'data.json' file.\n"
                f"   💡 Ensure your dataset contains at least one directory with data.json."
            )
        
        return episodes

    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int, is_test: bool = False) -> dict[str, LazyVideoReader]:
        """准备episode的图像缓冲区（使用延迟加载）
        
        🚀 性能优化：使用LazyVideoReader替代加载所有帧到内存
        - 优化前：100帧 × 3相机 × 1MB = 300MB内存/episode
        - 优化后：仅缓存当前帧，约3MB内存/episode
        - 内存优化：100x
        
        Args:
            task_path: 任务路径
            ep_idx: Episode索引
            is_test: 是否为测试模式（LazyVideoReader下此参数无影响，按需加载）
            
        Returns:
            字典，键为相机名称，值为LazyVideoReader对象
            LazyVideoReader支持索引访问，可直接替代list[np.ndarray]
        """
        episodes = self._get_all_episode_dirs(task_path)
        if ep_idx >= len(episodes):
            raise IndexError(
                f"❌ Episode index out of range.\n"
                f"   📁 Location: task_path={task_path}\n"
                f"   📊 Requested ep_idx={ep_idx}, but only found {len(episodes)} episodes.\n"
                f"   💡 Check if episode directory structure is correct."
            )
        
        ep_dir = episodes[ep_idx]
        
        # 获取所有MP4文件
        mp4_files = sorted(ep_dir.glob("*.mp4"))
        
        if not mp4_files:
            raise FileNotFoundError(
                f"❌ No MP4 files found.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   📂 Episode directory: {ep_dir}\n"
                f"   💡 Expected *.mp4 files but found none."
            )
        
        images = {}
        failed_cameras = []
        
        for mp4_file in mp4_files:
            # 从文件名推断相机名称
            cam_name = self._infer_camera_name(mp4_file.stem)
            if not cam_name:
                if self.logger:
                    self.logger.warning(
                        f"⚠️  Cannot infer camera name from file: {mp4_file.name}, skipping..."
                    )
                continue
            
            try:
                # 🚀 使用LazyVideoReader替代加载所有帧
                reader = LazyVideoReader(mp4_file, logger=self.logger)
                
                # 验证视频可以打开且有帧
                if len(reader) == 0:
                    failed_cameras.append(f"{cam_name} ({mp4_file.name}): 0 frames")
                    reader.close()
                    continue
                
                images[cam_name] = reader
                
                if self.logger:
                    self.logger.debug(
                        f"✓ LazyVideoReader ready for {cam_name}: "
                        f"{len(reader)} frames ({mp4_file.name})"
                    )
                    
            except FileNotFoundError as e:
                failed_cameras.append(f"{cam_name} ({mp4_file.name}): File not found")
                if self.logger:
                    self.logger.error(f"❌ Video file not found: {mp4_file.name}")
                    
            except RuntimeError as e:
                failed_cameras.append(f"{cam_name} ({mp4_file.name}): {e!s}")
                if self.logger:
                    self.logger.error(
                        f"❌ Failed to open video {mp4_file.name}: {e}"
                    )
                    
            except Exception as e:
                failed_cameras.append(f"{cam_name} ({mp4_file.name}): {e!s}")
                if self.logger:
                    self.logger.error(
                        f"❌ Unexpected error loading video {mp4_file.name}: {e}"
                    )
        
        if not images:
            raise RuntimeError(
                f"❌ No valid camera images loaded.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   📂 Episode directory: {ep_dir}\n"
                f"   📹 MP4 files found: {[f.name for f in mp4_files]}\n"
                f"   ❌ Failed cameras:\n" + 
                "\n".join(f"      - {fc}" for fc in failed_cameras) + "\n"
                f"   💡 Check if video files are corrupted or in unsupported format."
            )
        
        # 检查所有相机的帧数是否一致
        frame_counts = {cam: len(reader) for cam, reader in images.items()}
        if len(set(frame_counts.values())) > 1:
            if self.logger:
                self.logger.warning(
                    f"⚠️  Camera frame counts are inconsistent at ep_idx={ep_idx}:\n"
                    + "\n".join(f"      {cam}: {count} frames" for cam, count in frame_counts.items())
                )
        
        return images

    def _infer_camera_name(self, filename: str) -> str | None:
        """从文件名推断相机名称"""
        mappings = {
            'front_head': 'camera_front_head_rgb',
            'left_wrist': 'camera_left_wrist',
            'right_wrist': 'camera_right_wrist',
            'camera_front_head_rgb': 'camera_front_head_rgb',
            'camera_left_wrist': 'camera_left_wrist',
            'camera_right_wrist': 'camera_right_wrist',
        }
        
        filename_lower = filename.lower()
        for key, value in mappings.items():
            if key in filename_lower:
                return value
        
        return None

    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> list[dict]:
        """准备episode的状态缓冲区"""
        json_data = self._load_json_data(task_path, ep_idx)
        
        if 'data' not in json_data:
            raise ValueError("No 'data' key in JSON file")
        
        return json_data['data']

    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> list[dict]:
        """准备episode的动作缓冲区"""
        # 对于yinhe数据集，action和state使用相同的数据
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
        if cam_name not in images_buffer:
            available_cameras = list(images_buffer.keys())
            # 提供详细的相机帧数信息
            cam_frame_info = {cam: len(frames) for cam, frames in images_buffer.items()}
            raise KeyError(
                f"❌ Camera not found in images buffer.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📹 Requested camera: '{cam_name}'\n"
                f"   📋 Available cameras: {available_cameras}\n"
                f"   📊 Camera frame counts: {cam_frame_info}\n"
                f"   💡 Check if camera name in config matches the video file names."
            )
        
        if frame_idx >= len(images_buffer[cam_name]):
            # 显示所有相机的帧数，帮助快速定位问题
            cam_frame_info = {cam: len(frames) for cam, frames in images_buffer.items()}
            raise IndexError(
                f"❌ Frame index out of range for camera.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   📹 Camera: '{cam_name}'\n"
                f"   🎯 Requested frame_idx: {frame_idx}\n"
                f"   📊 This camera has: {len(images_buffer[cam_name])} frames (valid range: 0-{len(images_buffer[cam_name])-1})\n"
                f"   📋 All camera frame counts:\n" +
                "\n".join(f"      - {cam}: {count} frames" for cam, count in sorted(cam_frame_info.items())) + "\n"
                f"   💡 This camera has fewer frames than expected. Check if:\n"
                f"      1. Video file is incomplete or corrupted\n"
                f"      2. timeline_offset in config is causing out-of-bounds access\n"
                f"      3. Frame count detection (_get_episode_frames_num) needs adjustment"
            )
        
        return images_buffer[cam_name][frame_idx]

    def _get_frame_sub_states(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_states_buffer: list[dict] | None = None
    ) -> np.ndarray:
        """获取指定帧的子状态"""
        if sub_states_buffer is None:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)
        
        json_path = args_dict.get('json_path', '')
        
        # 从JSON数据中提取指定路径的值
        frame_data = sub_states_buffer
        original_buffer_type = type(frame_data).__name__
        
        if isinstance(frame_data, dict):
            # 处理嵌套字典
            for key in json_path.split('/'):
                if key:
                    if not isinstance(frame_data, dict):
                        raise ValueError(
                            f"❌ Invalid JSON path traversal.\n"
                            f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                            f"   🔍 JSON path: '{json_path}'\n"
                            f"   ❌ Expected dict at key '{key}', but got {type(frame_data).__name__}\n"
                            f"   💡 Check if json_path in config matches the actual JSON structure."
                        )
                    frame_data = frame_data.get(key, {})
        
        # 检查是否成功获取到列表数据
        if not isinstance(frame_data, list):
            raise ValueError(
                f"❌ Expected list data from JSON path.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   🔍 JSON path: '{json_path}'\n"
                f"   ❌ Got {type(frame_data).__name__} instead of list\n"
                f"   📊 Buffer type: {original_buffer_type}\n"
                f"   💡 Check if json_path correctly points to a list in JSON data."
            )
        
        if frame_idx >= len(frame_data):
            raise IndexError(
                f"❌ Frame index out of range in JSON data.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   🔍 JSON path: '{json_path}'\n"
                f"   🎯 Requested frame_idx: {frame_idx}\n"
                f"   📊 JSON data length: {len(frame_data)} (valid range: 0-{len(frame_data)-1})\n"
                f"   💡 This JSON field has fewer entries than expected.\n"
                f"      Check if this field is the bottleneck in _get_episode_frames_num."
            )
        
        if frame_idx < 0:
            raise IndexError(
                f"❌ Negative frame index.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
                f"   🎯 frame_idx: {frame_idx}\n"
                f"   💡 Frame index cannot be negative."
            )
        
        value = frame_data[frame_idx]
        
        # 如果 value 是字典（例如 {'position': [...], 'velocity': [...], ...}）
        # 需要提取指定的字段（默认为 'position'）
        if isinstance(value, dict):
            # 尝试从 args_dict 获取字段名，默认使用 'position'
            field_name = args_dict.get('field_name', 'position')
            if field_name not in value:
                available_fields = list(value.keys())
                raise KeyError(
                    f"❌ Field not found in JSON dict value.\n"
                    f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                    f"   🔍 JSON path: '{json_path}'\n"
                    f"   🎯 Requested field: '{field_name}'\n"
                    f"   📋 Available fields: {available_fields}\n"
                    f"   💡 Specify correct field_name in config args, or ensure JSON has this field."
                )
            value = value.get(field_name, [])
        
        if isinstance(value, (list, tuple)):
            # 提取指定范围的值
            range_from = args_dict.get('range_from', 0)
            range_to = args_dict.get('range_to', len(value))
            
            if range_from < 0 or range_to > len(value) or range_from >= range_to:
                raise ValueError(
                    f"❌ Invalid range for data extraction.\n"
                    f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                    f"   🔍 JSON path: '{json_path}'\n"
                    f"   🎯 Requested range: [{range_from}:{range_to}]\n"
                    f"   📊 Value length: {len(value)}\n"
                    f"   💡 Check range_from and range_to in config args."
                )
            
            return np.array(value[range_from:range_to], dtype=np.float32)
        
        # 单个数值
        try:
            return np.array([float(value)], dtype=np.float32)
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"❌ Cannot convert value to float.\n"
                f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   🔍 JSON path: '{json_path}'\n"
                f"   ❌ Value: {value!r} (type: {type(value).__name__})\n"
                f"   💡 Error: {e!s}"
            ) from e

    def _get_frame_sub_actions(
        self, 
        task_path: Path, 
        ep_idx: int, 
        frame_idx: int, 
        args_dict: dict,
        sub_actions_buffer: list[dict] | None = None
    ) -> np.ndarray:
        """获取指定帧的子动作"""
        # 使用与状态相同的逻辑
        return self._get_frame_sub_states(task_path, ep_idx, frame_idx, args_dict, sub_actions_buffer)
    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 MP4+JSON episode 的源文件信息
        
        Args:
            task_path: 任务路径
            ep_idx: episode 索引
        
        Returns:
            dict: 包含源文件信息的字典，包括 episode_dir, json_file, video_files
        """
        try:
            episode_dirs = self._get_all_episode_dirs(task_path)
            if ep_idx < len(episode_dirs):
                episode_dir = episode_dirs[ep_idx]
                
                # 收集JSON和视频文件
                json_file = episode_dir / "metadata.json"
                video_files = []
                
                for cam_config in self.image_configs:
                    video_path_template = cam_config.get("args", {}).get("video_path", "")
                    if video_path_template:
                        video_path = video_path_template.format(ep_dir=episode_dir.name)
                        full_video_path = episode_dir / video_path
                        if full_video_path.exists():
                            video_files.append({
                                "camera": cam_config["cam_name"],
                                "relative_path": str(full_video_path.relative_to(self.dataset_path)),
                                "absolute_path": str(full_video_path.absolute()),
                            })
                
                return {
                    "format": "MP4+JSON",
                    "episode_directory": str(episode_dir.relative_to(self.dataset_path)),
                    "json_file": str(json_file.relative_to(self.dataset_path)) if json_file.exists() else None,
                    "video_files": video_files,
                    "absolute_path": str(episode_dir.absolute()),
                }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        
        return {}