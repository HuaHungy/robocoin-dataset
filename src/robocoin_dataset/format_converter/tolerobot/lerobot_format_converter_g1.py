import json
import logging
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
from natsort import natsorted
from PIL import Image

from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter import (
    LerobotFormatConverter,
)


@dataclass
class G1Buffer:
    g1_data: dict | None = None
    task_path: Path | None = None
    ep_idx: int | None = None


class LerobotFormatConverterG1(LerobotFormatConverter):
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
        self.g1_buffer: G1Buffer = G1Buffer()

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

    def _prevalidate_files(self) -> None:
        """Validate G1 dataset files and structure."""
        validation_errors = []
        critical_errors = []
        
        for task_path in self.path_task_dict.keys():
            if not task_path.exists():
                critical_errors.append(f"Task path does not exist: {task_path}")
                continue
            if not task_path.is_dir():
                critical_errors.append(f"Task path is not a directory: {task_path}")
                continue
            
            # 获取该任务的JSON文件列表
            task_json_files = self.task_episode_jsonfile_paths.get(task_path, [])
            if not task_json_files:
                validation_errors.append(f"No JSON files found for task: {task_path}")
                continue
            
            # 验证每个JSON文件
            for ep_idx, json_file_path in enumerate(task_json_files):
                try:
                    # 1. 检查文件是否存在
                    if not json_file_path.exists():
                        critical_errors.append(f"JSON file does not exist: {json_file_path}")
                        continue
                    
                    # 2. 检查文件是否为空
                    if json_file_path.stat().st_size == 0:
                        critical_errors.append(f"JSON file is empty: {json_file_path}")
                        continue
                    
                    # 3. 检查JSON文件是否可以正常解析
                    try:
                        with open(json_file_path, encoding='utf-8') as f:
                            json_data = json.load(f)
                    except json.JSONDecodeError as e:
                        critical_errors.append(f"JSON file is corrupted or malformed: {json_file_path} - {str(e)}")
                        continue
                    except UnicodeDecodeError as e:
                        critical_errors.append(f"JSON file has encoding issues: {json_file_path} - {str(e)}")
                        continue
                    except Exception as e:
                        critical_errors.append(f"Cannot read JSON file: {json_file_path} - {str(e)}")
                        continue
                    
                    # 4. 检查JSON基础结构
                    if not isinstance(json_data, dict):
                        critical_errors.append(f"JSON file must contain a dictionary: {json_file_path}")
                        continue
                    
                    if "data" not in json_data:
                        critical_errors.append(f"JSON file missing 'data' field: {json_file_path}")
                        continue
                    
                    if not isinstance(json_data["data"], list):
                        critical_errors.append(f"JSON 'data' field must be a list: {json_file_path}")
                        continue
                    
                    if len(json_data["data"]) == 0:
                        validation_errors.append(f"JSON file has empty 'data' list: {json_file_path}")
                        continue
                    
                    # 5. 检查对应的图像文件
                    episode_dir = json_file_path.parent
                    image_files = (list(episode_dir.rglob("*.jpg")) + 
                                 list(episode_dir.rglob("*.JPG")) + 
                                 list(episode_dir.rglob("*.jpeg")) + 
                                 list(episode_dir.rglob("*.JPEG")) + 
                                 list(episode_dir.rglob("*.png")) + 
                                 list(episode_dir.rglob("*.PNG")))
                    
                    if not image_files:
                        validation_errors.append(f"No image files found for episode: {episode_dir}")
                        continue
                    
                    # 6. 检查数据帧数与图像数量的合理性
                    frame_count = len(json_data["data"])
                    image_count = len(image_files)
                    
                    # 分组图像以检查相机数量
                    camera_groups = self._group_images_by_camera_g1(image_files)
                    camera_count = len(camera_groups)
                    
                    if camera_count == 0:
                        validation_errors.append(f"No valid camera groups found in: {episode_dir}")
                        continue
                    
                    # 检查图像数量是否合理（考虑多相机情况）
                    expected_images_per_camera = frame_count
                    total_expected_images = expected_images_per_camera * camera_count
                    
                    # 允许一定的误差范围（±10%）
                    if abs(image_count - total_expected_images) > total_expected_images * 0.1:
                        validation_errors.append(
                            f"Image count mismatch in {episode_dir}: "
                            f"Found {image_count} images, expected ~{total_expected_images} "
                            f"({frame_count} frames × {camera_count} cameras)"
                        )
                    
                    # 7. 验证数据结构完整性（抽样检查第一帧）
                    if frame_count > 0:
                        first_frame = json_data["data"][0]
                        if not isinstance(first_frame, dict):
                            critical_errors.append(f"Frame data must be dictionaries: {json_file_path}")
                            continue
                        
                        # 检查关键字段是否存在（基于配置文件）
                        missing_fields = self._check_required_json_fields(first_frame, json_file_path)
                        if missing_fields:
                            critical_errors.extend(missing_fields)
                    
                    if self.logger:
                        self.logger.debug(f"Validated episode {ep_idx}: {json_file_path} "
                                        f"({frame_count} frames, {image_count} images, {camera_count} cameras)")
                
                except Exception as e:
                    critical_errors.append(f"Unexpected error validating {json_file_path}: {str(e)}")
        
        # 报告验证结果
        if critical_errors:
            error_count = len(critical_errors)
            error_list = "\n".join(f"      {i+1}. {err}" for i, err in enumerate(critical_errors[:10]))
            if error_count > 10:
                error_list += f"\n      ... and {error_count - 10} more errors"
            
            error_msg = (
                f"❌ G1 dataset validation failed with {error_count} critical error(s).\n"
                f"   📊 Total errors: {error_count}\n"
                f"   ❌ Critical errors (showing first 10):\n"
                f"{error_list}\n"
                f"   💡 Common issues:\n"
                f"      1. JSON files are corrupted or malformed\n"
                f"      2. Required fields are missing in JSON data\n"
                f"      3. Image files referenced in JSON don't exist\n"
                f"      4. Camera groupings are inconsistent"
            )
            if self.logger:
                self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        if validation_errors:
            warning_msg = "Validation warnings:\n" + "\n".join(validation_errors)
            if self.logger:
                self.logger.warning(warning_msg)
        
        if self.logger:
            total_episodes = sum(len(episodes) for episodes in self.task_episode_jsonfile_paths.values())
            self.logger.info(f"G1 dataset validation completed successfully: {total_episodes} episodes validated")
        
        # 验证JSON文件内部结构与配置匹配
        self._validate_g1_json_structure()

    def _check_required_json_fields(self, frame_data: dict, json_file_path: Path) -> list[str]:
        """检查JSON帧数据中是否包含配置文件要求的所有字段"""
        missing_fields = []
        
        # 获取配置中需要的JSON路径
        required_json_paths = set()
        
        # 从状态配置中收集JSON路径
        if "observation" in self.converter_config.get("features", {}):
            observation_config = self.converter_config["features"]["observation"]
            if "state" in observation_config and "sub_state" in observation_config["state"]:
                for state_config in observation_config["state"]["sub_state"]:
                    if "args" in state_config and "json_path" in state_config["args"]:
                        required_json_paths.add(state_config["args"]["json_path"])
        
        # 从动作配置中收集JSON路径
        if "action" in self.converter_config.get("features", {}):
            action_config = self.converter_config["features"]["action"]
            if "sub_action" in action_config:
                for action_config_item in action_config["sub_action"]:
                    if "args" in action_config_item and "json_path" in action_config_item["args"]:
                        required_json_paths.add(action_config_item["args"]["json_path"])
        
        # 验证每个必需的JSON路径
        for json_path in required_json_paths:
            try:
                # 导航到目标数据
                data = frame_data
                path_parts = json_path.split(".")
                for part in path_parts:
                    if isinstance(data, dict) and part in data:
                        data = data[part]
                    else:
                        missing_fields.append(f"Missing JSON path '{json_path}' in {json_file_path}")
                        break
                else:
                    # 检查数据是否为有效的列表/数组
                    if not isinstance(data, (list, tuple)):
                        missing_fields.append(
                            f"JSON path '{json_path}' should be a list/array but got {type(data).__name__} in {json_file_path}"
                        )
                    elif len(data) == 0:
                        missing_fields.append(f"JSON path '{json_path}' is an empty array in {json_file_path}")
            except Exception as e:
                missing_fields.append(f"Error accessing JSON path '{json_path}' in {json_file_path}: {e}")
        
        return missing_fields

    def _validate_g1_json_structure(self) -> None:
        """验证G1 JSON文件内部结构是否与YAML配置匹配"""
        if self.logger:
            self.logger.info("Validating G1 JSON structure...")
        
        # 收集所有需要验证的JSON路径
        required_json_paths = set()
        
        # 从状态配置中收集JSON路径
        if "observation" in self.converter_config.get("features", {}):
            observation_config = self.converter_config["features"]["observation"]
            if "state" in observation_config and "sub_state" in observation_config["state"]:
                for state_config in observation_config["state"]["sub_state"]:
                    if "args" in state_config and "json_path" in state_config["args"]:
                        required_json_paths.add(state_config["args"]["json_path"])
        
        # 从动作配置中收集JSON路径
        if "action" in self.converter_config.get("features", {}):
            action_config = self.converter_config["features"]["action"]
            if "sub_action" in action_config:
                for action_config_item in action_config["sub_action"]:
                    if "args" in action_config_item and "json_path" in action_config_item["args"]:
                        required_json_paths.add(action_config_item["args"]["json_path"])
        
        # 收集所有需要验证的图像键
        required_image_keys = set()
        if "observation" in self.converter_config.get("features", {}):
            observation_config = self.converter_config["features"]["observation"]
            if "images" in observation_config:
                for image_config in observation_config["images"]:
                    if "args" in image_config and "image_key" in image_config["args"]:
                        required_image_keys.add(image_config["args"]["image_key"])
        
        if not required_json_paths and not required_image_keys:
            if self.logger:
                self.logger.warning("No json_path or image_key found in configuration, skipping G1 structure validation")
            return
        
        # 验证每个任务路径下的JSON文件
        validation_errors = []
        for task_path in self.path_task_dict.keys():
            json_files = self.task_episode_jsonfile_paths.get(task_path, [])
            
            if not json_files:
                validation_errors.append(f"No JSON files found in task path: {task_path}")
                continue
            
            # 验证第一个JSON文件作为样本（假设同一任务下的JSON文件结构一致）
            sample_json_file = json_files[0]
            try:
                with open(sample_json_file, encoding='utf-8') as f:
                    json_data = json.load(f)
                
                # 验证JSON数据基本结构
                if "data" not in json_data:
                    validation_errors.append(f"Missing 'data' key in {sample_json_file}")
                    continue
                
                if not isinstance(json_data["data"], list) or len(json_data["data"]) == 0:
                    validation_errors.append(f"'data' should be a non-empty list in {sample_json_file}")
                    continue
                
                # 验证第一帧数据结构
                first_frame = json_data["data"][0]
                missing_paths = []
                invalid_paths = []
                
                # 验证JSON路径
                for required_path in required_json_paths:
                    try:
                        # 导航到目标数据
                        data = first_frame
                        path_parts = required_path.split(".")
                        for part in path_parts:
                            if isinstance(data, dict) and part in data:
                                data = data[part]
                            else:
                                missing_paths.append(required_path)
                                break
                        else:
                            # 检查数据是否为有效的列表/数组
                            if not isinstance(data, (list, tuple)):
                                invalid_paths.append(f"{required_path} (not a list/array, got {type(data).__name__})")
                            elif len(data) == 0:
                                invalid_paths.append(f"{required_path} (empty array)")
                    except Exception as e:
                        invalid_paths.append(f"{required_path} (error: {e})")
                
                # 验证图像文件匹配
                missing_image_keys = []
                if required_image_keys:
                    # 检查是否有对应的图像文件
                    episode_dir = sample_json_file.parent
                    image_files = list(episode_dir.rglob("*.jpg")) + list(episode_dir.rglob("*.jpeg")) + list(episode_dir.rglob("*.png"))
                    
                    # 使用现有的图像分组逻辑
                    camera_groups = self._group_images_by_camera_g1(image_files)
                    
                    for image_key in required_image_keys:
                        camera_idx = self._extract_camera_index_from_key(image_key)
                        if camera_idx not in camera_groups:
                            missing_image_keys.append(f"{image_key} (camera {camera_idx} not found)")
                        elif len(camera_groups[camera_idx]) == 0:
                            missing_image_keys.append(f"{image_key} (no images for camera {camera_idx})")
                
                if missing_paths:
                    validation_errors.append(
                        f"Missing required JSON paths in {sample_json_file}: {missing_paths}"
                    )
                
                if invalid_paths:
                    validation_errors.append(
                        f"Invalid JSON data structure in {sample_json_file}: {invalid_paths}"
                    )
                
                if missing_image_keys:
                    validation_errors.append(
                        f"Missing required image keys in {task_path}: {missing_image_keys}"
                    )
                
                if self.logger and not missing_paths and not invalid_paths and not missing_image_keys:
                    self.logger.info(f"G1 JSON structure validation passed for task: {task_path}")
                        
            except Exception as e:
                validation_errors.append(f"Error reading JSON file {sample_json_file}: {e}")
        
        if validation_errors:
            error_msg = "G1 JSON structure validation failed:\n" + "\n".join(validation_errors)
            raise ValueError(error_msg)
        
        if self.logger:
            self.logger.info("G1 JSON structure validation completed successfully")

    def _get_structure_summary(self, data: any, max_depth: int = 2, current_depth: int = 0) -> any:
        """获取数据结构的简要总结，用于调试"""
        if current_depth >= max_depth:
            return f"... (max depth {max_depth} reached)"
        
        if isinstance(data, dict):
            if not data:
                return "{}"
            keys = list(data.keys())[:5]  # 只显示前5个键
            summary = {key: self._get_structure_summary(data[key], max_depth, current_depth + 1) for key in keys}
            if len(data) > 5:
                summary["..."] = f"({len(data) - 5} more keys)"
            return summary
        
        if isinstance(data, list):
            if not data:
                return "[]"
            length = len(data)
            if length > 0:
                sample = self._get_structure_summary(data[0], max_depth, current_depth + 1)
                return f"[{sample}, ...] (length: {length})"
            return "[]"
        
        return f"{type(data).__name__}"

    # @override
    def _get_frame_image(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        images_buffer: any = None,
    ) -> np.ndarray:
        if not images_buffer:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)

        # 从缓存的图像列表中获取指定帧的图像
        image_key = args_dict.get("image_key", "color_0")  # 默认为color_0
        print("g1_override _get_frame_image")
        print(f"image_key: {image_key}, frame_idx: {frame_idx}")

        # G1多相机支持：从image_key解析相机索引
        camera_idx = self._extract_camera_index_from_key(image_key)

        # 获取对应相机的图像文件列表
        camera_groups = images_buffer.get("camera_groups", {})

        if camera_idx not in camera_groups:
            available_cameras = list(camera_groups.keys())
            error_msg = (
                f"❌ Camera not found in camera groups.\n"
                f"   📹 Requested camera: {camera_idx}\n"
                f"   🔑 Image key: {image_key}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   📋 Available cameras: {available_cameras if available_cameras else 'None'}\n"
            )
            
            if not available_cameras:
                error_msg += (
                    f"   💡 No camera data found. Check if:\n"
                    f"      1. Images exist and are properly formatted\n"
                    f"      2. Expected naming pattern: *0.jpg, *1.jpg (last digit = camera index)\n"
                    f"      3. JSON references valid image files"
                )
            else:
                error_msg += (
                    f"   💡 Camera mismatch. Check if:\n"
                    f"      1. Config uses correct camera index\n"
                    f"      2. image_key format is correct (e.g., 'color_0', 'color_1')\n"
                    f"      3. Dataset has images for requested camera"
                )
            
            if self.logger:
                self.logger.error(error_msg)
            
            raise ValueError(error_msg)

        camera_files = camera_groups[camera_idx]
        
        if not camera_files:
            raise ValueError(
                f"❌ No image files found for camera.\n"
                f"   📹 Camera index: {camera_idx}\n"
                f"   🔑 Image key: {image_key}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}, frame_idx={frame_idx}\n"
                f"   💡 Check if:\n"
                f"      1. Images exist for this camera in dataset\n"
                f"      2. Image naming matches expected pattern\n"
                f"      3. JSON references are correct"
            )

        # 查找与frame_idx匹配的图像文件，支持稀疏采样
        target_image_path = None
        for image_path in camera_files:
            # 从文件名提取帧号，例如：000379_color_0.jpg -> 379
            filename = image_path.stem  # 去掉扩展名
            frame_num_str = filename.split("_")[0]  # 取第一部分
            try:
                file_frame_idx = int(frame_num_str)
                if file_frame_idx == frame_idx:
                    target_image_path = image_path
                    break
            except ValueError:
                continue

        if target_image_path is None:
            # 如果找不到精确匹配的帧，使用最近的帧或最后一帧
            if camera_files:
                # 找到最接近的帧
                closest_file = None
                min_distance = float("inf")
                for image_path in camera_files:
                    filename = image_path.stem
                    frame_num_str = filename.split("_")[0]
                    try:
                        file_frame_idx = int(frame_num_str)
                        distance = abs(file_frame_idx - frame_idx)
                        if distance < min_distance:
                            min_distance = distance
                            closest_file = image_path
                    except ValueError:
                        continue
                target_image_path = closest_file

            if target_image_path is None:
                available_frames = []
                for img_path in camera_files[:10]:  # 只显示前10个
                    try:
                        frame_num = int(img_path.stem.split("_")[0])
                        available_frames.append(frame_num)
                    except (ValueError, IndexError, AttributeError):
                        pass
                
                raise ValueError(
                    f"❌ No suitable image found for frame.\n"
                    f"   🎯 Requested frame: {frame_idx}\n"
                    f"   📹 Camera index: {camera_idx}\n"
                    f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                    f"   📋 Available frames (first 10): {sorted(available_frames) if available_frames else 'None'}\n"
                    f"   📊 Total images for camera: {len(camera_files)}\n"
                    f"   💡 Check if:\n"
                    f"      1. Frame index matches actual recorded frames\n"
                    f"      2. Image naming follows pattern: NNNNNN_*_{camera_idx}.jpg\n"
                    f"      3. Dataset contains images for requested frame"
                )

        if not target_image_path.exists():
            raise FileNotFoundError(
                f"❌ Image file does not exist.\n"
                f"   🖼️  Image path: {target_image_path}\n"
                f"   📹 Camera index: {camera_idx}\n"
                f"   🎯 Frame index: {frame_idx}\n"
                f"   📁 Location: task={task_path.name}, ep_idx={ep_idx}\n"
                f"   💡 Check if:\n"
                f"      1. Image file was recorded\n"
                f"      2. File path in JSON is correct\n"
                f"      3. Dataset extraction was complete"
            )

        # 读取并返回图像
        img = Image.open(target_image_path)
        return np.array(img)

    # @override
    def _get_frame_sub_states(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_states_buffer: any = None,
    ) -> np.ndarray:
        if not sub_states_buffer:
            sub_states_buffer = self._prepare_episode_states_buffer(task_path, ep_idx)

        # 解析JSON路径，例如: "states.left_arm.qpos"
        json_path = args_dict["json_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]

        # 获取帧数据
        try:
            frame_data = sub_states_buffer["data"][frame_idx]
        except (KeyError, IndexError) as e:
            available_keys = list(sub_states_buffer.keys()) if isinstance(sub_states_buffer, dict) else "Not a dict"
            data_length = len(sub_states_buffer.get("data", [])) if isinstance(sub_states_buffer, dict) else "Unknown"
            raise ValueError(
                f"Failed to access frame {frame_idx} in states buffer for task {task_path}, episode {ep_idx}. "
                f"Available buffer keys: {available_keys}, data length: {data_length}. "
                f"Original error: {e}"
            )

        # 按路径导航到目标数据
        data = frame_data
        current_path = ""
        for i, path_part in enumerate(json_path.split(".")):
            current_path = ".".join(json_path.split(".")[:i+1])
            if isinstance(data, dict) and path_part in data:
                data = data[path_part]
            else:
                # 提供详细的调试信息
                available_keys = list(data.keys()) if isinstance(data, dict) else f"Not a dict, type: {type(data)}"
                total_frames = len(sub_states_buffer.get("data", []))
                
                # 尝试找到相似的键
                similar_keys = []
                if isinstance(data, dict):
                    similar_keys = [
                        key for key in data.keys()
                        if path_part.lower() in key.lower() or key.lower() in path_part.lower()
                    ]
                
                error_msg = (
                    f"Path '{json_path}' not found in frame {frame_idx} at step '{current_path}' "
                    f"for task {task_path}, episode {ep_idx}. "
                    f"Available keys at current level: {available_keys}. "
                    f"Total frames in episode: {total_frames}. "
                    f"Target path part: '{path_part}'. "
                )
                
                if similar_keys:
                    error_msg += f"Similar keys found: {similar_keys}. "
                
                # 记录第一个可用帧的结构作为参考
                if frame_idx > 0:
                    try:
                        first_frame = sub_states_buffer["data"][0]
                        error_msg += f"Structure of frame 0 for reference: {self._get_structure_summary(first_frame)}. "
                    except Exception:
                        pass
                
                if self.logger:
                    self.logger.error(f"G1 States Path Error: {error_msg}")
                
                # 确保错误信息包含足够的诊断信息
                simplified_error = f"Path '{json_path}' not found in frame {frame_idx}"
                if self.logger:
                    self.logger.error(f"WARNING: If you see only this simplified error '{simplified_error}', check the full error above!")
                
                raise ValueError(error_msg)

        # 提取指定范围的数据
        if isinstance(data, list):
            if to_idx > len(data):
                if self.logger:
                    self.logger.warning(
                        f"Requested range [{from_idx}:{to_idx}] exceeds data length {len(data)} "
                        f"for path '{json_path}' in frame {frame_idx}"
                    )
            return np.array(data[from_idx:to_idx], dtype=np.float32)
        
        raise ValueError(
            f"Expected list data for path '{json_path}', got {type(data)} with value: {data} "
            f"in frame {frame_idx} for task {task_path}, episode {ep_idx}"
        )

    # @override
    def _get_frame_sub_actions(
        self,
        task_path: Path,
        ep_idx: int,
        frame_idx: int,
        args_dict: dict,
        sub_actions_buffer: any = None,
    ) -> np.ndarray:
        if not sub_actions_buffer:
            sub_actions_buffer = self._prepare_episode_actions_buffer(task_path, ep_idx)

        # 解析JSON路径，例如: "actions.left_arm.qpos"
        json_path = args_dict["json_path"]
        from_idx = args_dict["range_from"]
        to_idx = args_dict["range_to"]

        # 获取帧数据
        try:
            frame_data = sub_actions_buffer["data"][frame_idx]
        except (KeyError, IndexError) as e:
            available_keys = list(sub_actions_buffer.keys()) if isinstance(sub_actions_buffer, dict) else "Not a dict"
            data_length = len(sub_actions_buffer.get("data", [])) if isinstance(sub_actions_buffer, dict) else "Unknown"
            raise ValueError(
                f"Failed to access frame {frame_idx} in actions buffer for task {task_path}, episode {ep_idx}. "
                f"Available buffer keys: {available_keys}, data length: {data_length}. "
                f"Original error: {e}"
            )

        # 按路径导航到目标数据
        data = frame_data
        current_path = ""
        for i, path_part in enumerate(json_path.split(".")):
            current_path = ".".join(json_path.split(".")[:i+1])
            if isinstance(data, dict) and path_part in data:
                data = data[path_part]
            else:
                # 提供详细的调试信息
                available_keys = list(data.keys()) if isinstance(data, dict) else f"Not a dict, type: {type(data)}"
                total_frames = len(sub_actions_buffer.get("data", []))
                
                # 尝试找到相似的键
                similar_keys = []
                if isinstance(data, dict):
                    similar_keys = [
                        key for key in data.keys()
                        if path_part.lower() in key.lower() or key.lower() in path_part.lower()
                    ]
                
                error_msg = (
                    f"Path '{json_path}' not found in frame {frame_idx} at step '{current_path}' "
                    f"for task {task_path}, episode {ep_idx}. "
                    f"Available keys at current level: {available_keys}. "
                    f"Total frames in episode: {total_frames}. "
                    f"Target path part: '{path_part}'. "
                )
                
                if similar_keys:
                    error_msg += f"Similar keys found: {similar_keys}. "
                
                # 记录第一个可用帧的结构作为参考
                if frame_idx > 0:
                    try:
                        first_frame = sub_actions_buffer["data"][0]
                        error_msg += f"Structure of frame 0 for reference: {self._get_structure_summary(first_frame)}. "
                    except Exception:
                        pass
                
                if self.logger:
                    self.logger.error(f"G1 Actions Path Error: {error_msg}")
                
                # 确保错误信息包含足够的诊断信息
                simplified_error = f"Path '{json_path}' not found in frame {frame_idx}"
                if self.logger:
                    self.logger.error(f"WARNING: If you see only this simplified error '{simplified_error}', check the full error above!")
                
                raise ValueError(error_msg)

        # 提取指定范围的数据
        if isinstance(data, list):
            if to_idx > len(data):
                if self.logger:
                    self.logger.warning(
                        f"Requested range [{from_idx}:{to_idx}] exceeds data length {len(data)} "
                        f"for path '{json_path}' in frame {frame_idx}"
                    )
            return np.array(data[from_idx:to_idx], dtype=np.float32)
        
        raise ValueError(
            f"Expected list data for path '{json_path}', got {type(data)} with value: {data} "
            f"in frame {frame_idx} for task {task_path}, episode {ep_idx}"
        )

    # @override
    def _get_episode_frames_num(self, task_path: Path, ep_idx: int) -> int:
        json_file_path = self.task_episode_jsonfile_paths[task_path][ep_idx]
        try:
            with open(json_file_path) as json_file:
                json_data = json.load(json_file)
                return len(json_data["data"])
        except Exception as e:
            raise ValueError(f"Error while reading json file {json_file_path}") from e

    # @override
    def _get_task_episodes_num(self, task_path: Path) -> int:
        return len(self.task_episode_jsonfile_paths[task_path])

    # @override
    def _prepare_episode_images_buffer(self, task_path: Path, ep_idx: int) -> any:
        """
        准备episode图像缓存
        支持G1多相机自动检索：
        - 单相机：*0.jpg
        - 多相机：*0.jpg, *1.jpg, *2.jpg, *3.jpg等
        """
        # 获取JSON文件路径
        json_file_path = self.task_episode_jsonfile_paths[task_path][ep_idx]
        json_dir = json_file_path.parent

        # 从JSON同级目录递归搜索JPG文件
        jpg_files = list(json_dir.rglob("*.jpg"))
        jpg_files.extend(list(json_dir.rglob("*.JPG")))  # 支持大写扩展名
        jpg_files.extend(list(json_dir.rglob("*.jpeg")))  # 支持jpeg格式
        jpg_files.extend(list(json_dir.rglob("*.JPEG")))

        # G1多相机自动分组：按文件名模式分组
        camera_groups = self._group_images_by_camera_g1(jpg_files)

        print(f"Found {len(jpg_files)} image files in {json_dir}")
        print(f"Detected {len(camera_groups)} cameras")

        for cam_idx, cam_files in camera_groups.items():
            print(f"  Camera {cam_idx}: {len(cam_files)} images")
            if cam_files:
                print(f"    First: {cam_files[0].name}")
                print(f"    Last: {cam_files[-1].name}")

        return {
            "camera_groups": camera_groups,
            "all_image_files": jpg_files,
            "json_data": self._get_episode_json_data(task_path, ep_idx),
        }

    # @override
    def _prepare_episode_states_buffer(self, task_path: Path, ep_idx: int) -> any:
        return self._get_episode_json_data(task_path, ep_idx)

    # @override
    def _prepare_episode_actions_buffer(self, task_path: Path, ep_idx: int) -> any:
        return self._get_episode_json_data(task_path, ep_idx)

    @cached_property
    def task_episode_jsonfile_paths(self) -> dict[Path, list[Path]]:
        task_episode_paths = {}
        for path in self.path_task_dict.keys():
            if path.exists():
                # 方法1: 尝试智能episode目录发现
                episode_dirs = self._find_episode_directories_g1(path)

                if episode_dirs:
                    # 找到了有规律的episode目录
                    json_files = []
                    for episode_dir in episode_dirs:
                        # 在每个episode目录中查找JSON文件
                        episode_json_files = list(episode_dir.rglob("*.json"))
                        if episode_json_files:
                            # 选择主要的数据文件
                            main_file = self._select_main_json_file(episode_json_files)
                            json_files.append(main_file)

                    if json_files:
                        task_episode_paths[path] = json_files
                        print(f"Found {len(json_files)} episodes using directory pattern in {path}")
                        continue

                # 方法2: 回退到递归搜索
                json_files = natsorted(list(path.rglob("*.json")))
                task_episode_paths[path] = json_files
                print(f"Found {len(json_files)} JSON files using recursive search in {path}")

        return task_episode_paths

    def _group_images_by_camera_g1(self, jpg_files: list[Path]) -> dict[int, list[Path]]:
        """
        G1多相机图像分组
        根据文件名模式将图像按相机分组：
        G1格式：*0.jpg, *1.jpg, *2.jpg, *3.jpg (文件名最后一位数字表示相机索引)
        """
        camera_groups = {}

        # G1相机文件名模式匹配：文件名最后一位数字表示相机索引
        camera_pattern = r".*(\d)\.jpe?g$"  # 匹配文件名最后一位数字

        for jpg_file in jpg_files:
            match = re.match(camera_pattern, jpg_file.name, re.IGNORECASE)
            if match:
                camera_idx = int(match.group(1))

                if camera_idx not in camera_groups:
                    camera_groups[camera_idx] = []

                camera_groups[camera_idx].append(jpg_file)

        # 对每个相机的图像按文件名排序
        for camera_idx in camera_groups:
            camera_groups[camera_idx] = natsorted(camera_groups[camera_idx], key=lambda x: x.name)

        # 按相机索引排序
        return dict(sorted(camera_groups.items()))

    def _extract_camera_index_from_key(self, image_key: str) -> int:
        """
        从image_key提取相机索引
        color_0 -> 0
        color_1 -> 1
        camera_2 -> 2
        """

        # 提取key中的数字
        match = re.search(r"(\d+)$", image_key)
        if match:
            return int(match.group(1))

        # 默认返回相机0
        return 0

    def _find_episode_directories_g1(self, task_path: Path) -> list[Path]:
        """
        在JPG+JSON转换器中实现智能episode目录发现
        支持多种episode目录命名模式：episode1, episode_1, ep1, ep_1, 001, 1等
        支持深度搜索，找到分散在不同子目录中的episode
        """

        # Episode目录匹配模式
        episode_patterns = [
            r"^episode(\d+)$",  # episode1, episode2, episode10
            r"^episode_(\d+)$",  # episode_1, episode_2, episode_10
            r"^ep(\d+)$",  # ep1, ep2, ep10
            r"^ep_(\d+)$",  # ep_1, ep_2, ep_10
            r"^(\d+)$",  # 1, 2, 10, 001, 002
        ]

        # 递归搜索所有子目录（限制深度避免过深搜索）
        def find_all_directories(root_path, max_depth=3, current_depth=0):  # noqa: ANN001, ANN202
            dirs = []
            if current_depth >= max_depth:
                return dirs

            try:
                for item in root_path.iterdir():
                    if item.is_dir():
                        dirs.append(item)
                        # 递归搜索子目录
                        dirs.extend(find_all_directories(item, max_depth, current_depth + 1))
            except (PermissionError, OSError):
                pass  # 忽略权限或其他访问错误

            return dirs

        all_dirs = find_all_directories(task_path)
        episode_dirs = []

        for directory in all_dirs:
            dir_name = directory.name

            # 检查是否匹配任何episode模式
            for pattern in episode_patterns:
                match = re.match(pattern, dir_name, re.IGNORECASE)
                if match:
                    episode_num = int(match.group(1))

                    # 检查目录中是否包含JSON文件（确保是有效的episode目录）
                    json_files = list(directory.rglob("*.json"))
                    if json_files:
                        episode_dirs.append((episode_num, directory))
                    break

        if episode_dirs:
            # 按episode编号排序，然后按目录名排序（处理相同编号的情况）
            episode_dirs.sort(key=lambda x: (x[0], x[1].name))
            sorted_dirs = [d[1] for d in episode_dirs]

            print(f"Found episode directories in {task_path}:")
            for i, dir_path in enumerate(sorted_dirs):
                relative_path = (
                    dir_path.relative_to(task_path)
                    if dir_path.is_relative_to(task_path)
                    else dir_path
                )
                print(f"  Episode {i}: {dir_path.name} at {relative_path}")

            return sorted_dirs

        return []

    def _select_main_json_file(self, json_files: list[Path]) -> Path:
        """
        从多个JSON文件中选择主要的数据文件
        优先选择包含episode数据的文件
        """
        if len(json_files) == 1:
            return json_files[0]

        # 优先级规则：
        # 1. 文件名包含"data"的文件
        # 2. 文件名包含"episode"的文件
        # 3. 文件名最短的文件（通常是主文件）
        # 4. 按字母顺序第一个文件

        priority_files = []

        # 检查包含"data"的文件
        for f in json_files:
            if "data" in f.name.lower():
                priority_files.append((1, f))  # noqa: PERF401
        
                priority_files.append((1, f))

        # 检查包含"episode"的文件
        if not priority_files:
            for f in json_files:
                if "episode" in f.name.lower():
                    priority_files.append((2, f))  # noqa: PERF401
        
                    priority_files.append((2, f))

        # 按文件名长度排序
        if not priority_files:
            for f in json_files:
                priority_files.append((len(f.name), f))  # noqa: PERF401
        
                priority_files.append((len(f.name), f))

        # 选择优先级最高的文件
        priority_files.sort(key=lambda x: x[0])
        selected_file = priority_files[0][1]

        print(f"Selected main JSON file: {selected_file.name}")
        return selected_file

    def _get_episode_json_data(self, task_path: Path, ep_idx: int) -> any:
        should_load = self.g1_buffer.task_path != task_path or self.g1_buffer.ep_idx != ep_idx
        if not should_load:
            print(f"buffer is ok, skipping Loading episode {ep_idx} from {task_path}")
            return self.g1_buffer.g1_data

        json_file_path = self.task_episode_jsonfile_paths[task_path][ep_idx]
        
        # 详细的错误诊断
        try:
            # 1. 检查文件是否存在
            if not json_file_path.exists():
                raise FileNotFoundError(f"JSON file does not exist: {json_file_path}")
            
            # 2. 检查文件大小
            file_size = json_file_path.stat().st_size
            if file_size == 0:
                raise ValueError(f"JSON file is empty (0 bytes): {json_file_path}")
            
            # 3. 尝试读取文件内容
            try:
                with open(json_file_path, encoding='utf-8') as json_file:
                    file_content = json_file.read()
                    
                    # 检查文件内容是否为空或只包含空白字符
                    if not file_content.strip():
                        raise ValueError(f"JSON file contains only whitespace: {json_file_path}")
                    
                    # 尝试解析JSON
                    json_data = json.loads(file_content)
                    
            except UnicodeDecodeError as e:
                raise ValueError(f"JSON file has encoding issues: {json_file_path} - {str(e)}")
            except json.JSONDecodeError as e:
                # 提供更详细的JSON错误信息
                error_msg = f"JSON file is malformed: {json_file_path}\n"
                error_msg += f"JSON Error: {str(e)}\n"
                error_msg += f"File size: {file_size} bytes\n"
                
                # 显示文件开头内容以帮助诊断
                try:
                    with open(json_file_path, encoding='utf-8') as f:
                        preview = f.read(200)  # 读取前200个字符
                        error_msg += f"File preview: {repr(preview)}"
                except Exception:
                    error_msg += "Cannot read file preview"
                
                raise ValueError(error_msg)
            
            # 4. 验证JSON结构
            if not isinstance(json_data, dict):
                raise ValueError(f"JSON file must contain a dictionary, got {type(json_data).__name__}: {json_file_path}")
            
            if "data" not in json_data:
                raise ValueError(f"JSON file missing required 'data' field: {json_file_path}")
            
            if not isinstance(json_data["data"], list):
                raise ValueError(f"JSON 'data' field must be a list, got {type(json_data['data']).__name__}: {json_file_path}")
            
            if len(json_data["data"]) == 0:
                raise ValueError(f"JSON 'data' field is empty: {json_file_path}")
            
            # 5. 缓存成功加载的数据
            self.g1_buffer.g1_data = json_data
            self.g1_buffer.task_path = task_path
            self.g1_buffer.ep_idx = ep_idx

            print("json_file loaded")
            print(f"Total frames: {len(json_data.get('data', []))}")
            return json_data
            
        except Exception as e:
            # 增强错误信息，包含更多上下文
            error_context = f"Failed to load episode {ep_idx} from task {task_path}\n"
            error_context += f"JSON file path: {json_file_path}\n"
            error_context += f"Episode index: {ep_idx}/{len(self.task_episode_jsonfile_paths.get(task_path, []))}\n"
            
            if json_file_path.exists():
                try:
                    stat = json_file_path.stat()
                    error_context += f"File size: {stat.st_size} bytes\n"
                    error_context += f"Last modified: {stat.st_mtime}\n"
                except Exception:
                    pass
            
            # 建议可能的解决方案
            if isinstance(e, FileNotFoundError):
                error_context += "Suggestion: Check if the file was moved, deleted, or if there are permission issues\n"
            elif "empty" in str(e).lower() or "whitespace" in str(e).lower():
                error_context += "Suggestion: The file appears to be empty or corrupted. It may need to be regenerated\n"
            elif "malformed" in str(e).lower() or "JSONDecodeError" in str(e):
                error_context += "Suggestion: The JSON file is corrupted. It may need to be regenerated or fixed manually\n"
            elif "encoding" in str(e).lower():
                error_context += "Suggestion: Try converting the file to UTF-8 encoding\n"
            
            raise ValueError(f"{error_context}Original error: {str(e)}") from e
    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 G1 episode 的源文件信息"""
        try:
            episode_dir = self._get_episode_directory(task_path, ep_idx)
            return {
                "format": "G1",
                "episode_directory": str(episode_dir.relative_to(self.dataset_path)),
                "absolute_path": str(episode_dir.absolute()),
            }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        return {}

