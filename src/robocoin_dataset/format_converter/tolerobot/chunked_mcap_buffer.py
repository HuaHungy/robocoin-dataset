"""
Chunked MCAP Buffer - 分块加载MCAP数据，平衡内存和性能

核心思路：
- 将episode分成多个块（例如每块1000帧）
- 一次性解析一个块的所有数据（图像、state、action）
- 当访问下一个块时，清理旧块，加载新块
- 🚀 性能优化：初始化时建立消息索引，避免每次chunk都重新扫描文件

性能对比（27,000帧，chunk_size=1000）：
- 全部加载：扫描1次，内存80GB 💥
- 逐帧lazy：扫描27,000次，内存200MB，极慢 🐌
- 分块加载（旧）：扫描27次，内存3GB，慢 🐌
- 分块加载（新）：扫描1次+索引，内存3GB，快速 ⚡✅
"""

from pathlib import Path
from typing import Any, Callable

import numpy as np
from mcap.reader import make_reader


def find_nearest_msg(msgs, target_time):
    """查找最接近目标时间的消息（二分查找优化）"""
    if not msgs:
        return None
    
    import bisect
    times = [t for t, _ in msgs]
    pos = bisect.bisect_left(times, target_time)
    
    if pos == 0:
        return msgs[0][1]
    if pos == len(msgs):
        return msgs[-1][1]
    
    before = times[pos - 1]
    after = times[pos]
    
    if abs(target_time - before) <= abs(after - target_time):
        return msgs[pos - 1][1]
    return msgs[pos][1]


def parse_cdr_joint_state(data: bytes) -> dict | None:
    """手动解析CDR格式的JointState消息（从原MCAP转换器复制）"""
    import struct
    
    try:
        offset = 0
        offset += 4  # Skip CDR header
        offset += 4  # sec
        offset += 4  # nanosec
        
        # frame_id
        frame_id_len = struct.unpack_from('<I', data, offset)[0]
        offset += 4 + frame_id_len
        while offset % 4 != 0:
            offset += 1
        
        # name array (skip)
        name_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        for _ in range(name_count):
            name_len = struct.unpack_from('<I', data, offset)[0]
            offset += 4 + name_len
            while offset % 4 != 0:
                offset += 1
        
        # position array
        pos_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        positions = []
        for _ in range(pos_count):
            pos = struct.unpack_from('<d', data, offset)[0]
            positions.append(pos)
            offset += 8
        
        # velocity array
        vel_count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        velocities = []
        for _ in range(vel_count):
            vel = struct.unpack_from('<d', data, offset)[0]
            velocities.append(vel)
            offset += 8
        
        # effort array
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


def decode_image_bytes(img_bytes: bytes, typestore) -> np.ndarray | None:
    """解码CompressedImage消息（从原MCAP转换器复制）"""
    try:
        from PIL import Image
        import io
        
        compressed_img_msg = typestore.deserialize_cdr(img_bytes, 'sensor_msgs/msg/CompressedImage')
        img_data = bytes(compressed_img_msg.data)
        with Image.open(io.BytesIO(img_data)) as img:
            return np.array(img.convert("RGB"))
    except Exception:
        return None


class ChunkedMcapBuffer:
    """分块MCAP缓冲区
    
    表现得像一个dict[str, list]，支持：
    - buffer["camera_front"][frame_idx] -> image
    - buffer.get_state(frame_idx) -> state array
    - buffer.get_action(frame_idx) -> action array
    
    但内部只保留当前chunk的数据，自动管理内存。
    """
    
    def __init__(
        self,
        mcap_file: Path,
        main_times: list[int],
        image_topics: dict[str, str],  # {topic: cam_name}
        state_subs: list[dict],
        action_subs: list[dict],
        typestore,
        chunk_size: int = 1000,
        logger=None,
    ):
        self.mcap_file = mcap_file
        self.main_times = main_times
        self.image_topics = image_topics
        self.state_subs = state_subs
        self.action_subs = action_subs
        self.typestore = typestore
        self.chunk_size = chunk_size
        self.logger = logger
        
        self.total_frames = len(main_times)
        self.num_chunks = (self.total_frames + chunk_size - 1) // chunk_size
        
        # 🚀 性能优化：在初始化时建立消息索引，避免每次chunk都重新扫描文件
        # 只存储消息的字节数据（不解码），内存占用相对较小
        self._topic_msgs_index = None  # {topic: [(log_time, data_bytes), ...]}
        self._index_built = False
        
        # 当前加载的chunk
        self._current_chunk_idx = -1
        self._current_chunk_data = None  # {images: {...}, states: [...], actions: [...]}
        self._current_chunk_start = 0
        self._current_chunk_end = 0
        
        # 统计信息
        self._stats = {
            'total_accesses': 0,
            'chunk_loads': 0,
            'chunk_hits': 0,
            'index_build_time': 0,
        }
        
        # 🚀 立即建立消息索引（只扫描一次）
        self._build_message_index()
    
    def __len__(self) -> int:
        return self.total_frames
    
    def _build_message_index(self):
        """🚀 建立消息索引（只扫描一次MCAP文件）
        
        将所有topic的消息加载到内存，但只存储字节数据（不解码图像）
        这样可以避免每次chunk都重新扫描文件
        """
        if self._index_built:
            return
        
        import time
        start_time = time.time()
        
        if self.logger:
            self.logger.info(
                f"🔍 Building MCAP message index (one-time scan)...\n"
                f"   File: {self.mcap_file.name}\n"
                f"   This will take ~60 seconds but will speed up all chunk loads"
            )
        
        # 收集所有需要的topics
        required_topics = set(self.image_topics.keys())
        for sub in self.state_subs + self.action_subs:
            required_topics.add(sub['args']['mcap_topic'])
        
        # 初始化索引
        self._topic_msgs_index = {topic: [] for topic in required_topics}
        
        # 🚀 阶段4优化：使用更大的文件缓冲区加速I/O
        # 默认缓冲区是8KB，对于大文件使用更大的缓冲区可以减少系统调用
        import io
        buffer_size = 1024 * 1024  # 1MB缓冲区
        
        with open(self.mcap_file, "rb", buffering=buffer_size) as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages():
                topic = channel.topic
                if topic in self._topic_msgs_index:
                    # 只存储时间戳和字节数据（不解码）
                    self._topic_msgs_index[topic].append((message.log_time, message.data))
        
        self._index_built = True
        build_time = time.time() - start_time
        self._stats['index_build_time'] = build_time
        
        total_messages = sum(len(msgs) for msgs in self._topic_msgs_index.values())
        if self.logger:
            self.logger.info(
                f"✅ Message index built successfully:\n"
                f"   Topics: {len(self._topic_msgs_index)}\n"
                f"   Total messages: {total_messages}\n"
                f"   Build time: {build_time:.2f} seconds\n"
                f"   💡 All future chunk loads will use this index (no file re-scanning)"
            )
    
    def _load_chunk(self, chunk_idx: int):
        """加载指定的chunk"""
        if chunk_idx == self._current_chunk_idx and self._current_chunk_data is not None:
            self._stats['chunk_hits'] += 1
            return  # Already loaded
        
        self._stats['chunk_loads'] += 1
        
        # 计算chunk范围
        start_frame = chunk_idx * self.chunk_size
        end_frame = min(start_frame + self.chunk_size, self.total_frames)
        
        if self.logger:
            self.logger.info(
                f"📦 Loading chunk {chunk_idx + 1}/{self.num_chunks} "
                f"(frames {start_frame}-{end_frame-1}, {end_frame - start_frame} frames)"
            )
        
        # 清理旧chunk
        if self._current_chunk_data is not None:
            if self.logger:
                self.logger.debug(f"🧹 Clearing previous chunk {self._current_chunk_idx}")
            # 显式清理
            if 'images' in self._current_chunk_data:
                for cam_images in self._current_chunk_data['images'].values():
                    cam_images.clear()
                self._current_chunk_data['images'].clear()
            if 'states' in self._current_chunk_data:
                self._current_chunk_data['states'].clear()
            if 'actions' in self._current_chunk_data:
                self._current_chunk_data['actions'].clear()
            self._current_chunk_data = None
            
            # 强制垃圾回收
            import gc
            gc.collect()
        
        # 解析这个chunk（类似原来的_parse_mcap_episode，但只解析chunk范围）
        chunk_times = self.main_times[start_frame:end_frame]
        
        # 🚀 性能优化：直接从索引中获取消息，而不是重新扫描文件
        # 使用TopicMessageCache优化find_nearest_msg性能
        from robocoin_dataset.format_converter.tolerobot.lerobot_format_converter_mcap import TopicMessageCache
        
        topic_caches = {}
        for topic, msgs in self._topic_msgs_index.items():
            topic_caches[topic] = TopicMessageCache(msgs)
        
        # 🚀 阶段3优化：并行图像解码
        # 先收集所有需要解码的图像字节数据
        image_decode_tasks = []  # [(frame_idx, cam_name, img_bytes), ...]
        for i, t in enumerate(chunk_times):
            for topic, cam_name in self.image_topics.items():
                img_bytes = topic_caches[topic].find_nearest(t)
                image_decode_tasks.append((i, cam_name, img_bytes))
        
        # 并行解码图像
        num_workers = min(4, len(self.image_topics) * 2)  # 根据相机数量调整
        if self.logger:
            self.logger.debug(f"🚀 Using parallel image decoding with {num_workers} workers for chunk {chunk_idx}")
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        images = {cam: [None] * len(chunk_times) for cam in self.image_topics.values()}  # 预分配列表
        
        def decode_single_image(args):
            """解码单张图像（用于并行处理）"""
            frame_idx, cam_name, img_bytes = args
            if img_bytes is not None:
                try:
                    return (frame_idx, cam_name, decode_image_bytes(img_bytes, self.typestore))
                except Exception:
                    return (frame_idx, cam_name, None)
            return (frame_idx, cam_name, None)
        
        # 并行解码
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # 提交所有任务
            future_to_task = {executor.submit(decode_single_image, task): task for task in image_decode_tasks}
            
            # 收集结果（保持顺序）
            for future in as_completed(future_to_task):
                try:
                    frame_idx, cam_name, img_arr = future.result()
                    images[cam_name][frame_idx] = img_arr
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Failed to decode image in chunk {chunk_idx}: {e}")
                    frame_idx, cam_name, _ = future_to_task[future]
                    images[cam_name][frame_idx] = None
        
        # 解析states
        states = []
        for i, t in enumerate(chunk_times):
            state_vec = []
            for sub in self.state_subs:
                topic = sub['args']['mcap_topic']
                from_idx = sub['args']['range_from']
                to_idx = sub['args']['range_to']
                
                # 🚀 使用缓存的topic消息，避免重复提取时间戳
                data = topic_caches[topic].find_nearest(t)
                if data is not None:
                    sub_data = self._parse_state_action_data(data, topic, from_idx, to_idx)
                    state_vec.extend(sub_data.tolist() if isinstance(sub_data, np.ndarray) else sub_data)
                else:
                    state_vec.extend([np.nan] * (to_idx - from_idx))
            states.append(np.array(state_vec, dtype=np.float32))
        
        # 解析actions
        actions = []
        for i, t in enumerate(chunk_times):
            action_vec = []
            for sub in self.action_subs:
                topic = sub['args']['mcap_topic']
                from_idx = sub['args']['range_from']
                to_idx = sub['args']['range_to']
                
                # 🚀 使用缓存的topic消息，避免重复提取时间戳
                data = topic_caches[topic].find_nearest(t)
                if data is not None:
                    sub_data = self._parse_state_action_data(data, topic, from_idx, to_idx)
                    action_vec.extend(sub_data.tolist() if isinstance(sub_data, np.ndarray) else sub_data)
                else:
                    action_vec.extend([np.nan] * (to_idx - from_idx))
            actions.append(np.array(action_vec, dtype=np.float32))
        
        # 保存chunk数据
        self._current_chunk_data = {
            'images': images,
            'states': states,
            'actions': actions,
        }
        self._current_chunk_idx = chunk_idx
        self._current_chunk_start = start_frame
        self._current_chunk_end = end_frame
        
        if self.logger:
            self.logger.debug(f"✅ Chunk {chunk_idx} loaded successfully")
    
    def _parse_state_action_data(self, data_bytes, topic, from_idx, to_idx):
        """解析state/action数据（复用原有逻辑）"""
        try:
            if 'joint_states' in topic or 'gripper_pos' in topic:
                js_dict = parse_cdr_joint_state(data_bytes)
                if js_dict and js_dict['position']:
                    return np.array(js_dict['position'][from_idx:to_idx], dtype=np.float32)
            elif 'udp_arm_position' in topic:
                pose = self.typestore.deserialize_cdr(data_bytes, 'rm_ros_interfaces/msg/Jointposeorientation')
                pos = np.array([pose.pose.position.x, pose.pose.position.y, pose.pose.position.z], dtype=np.float32)
                quat = np.array([pose.pose.orientation.x, pose.pose.orientation.y,
                               pose.pose.orientation.z, pose.pose.orientation.w], dtype=np.float32)
                if from_idx < 3:
                    return pos[from_idx:min(to_idx, 3)]
                else:
                    return quat[from_idx-3:to_idx-3]
            elif 'udp_six_force' in topic:
                six_force = self.typestore.deserialize_cdr(data_bytes, 'rm_ros_interfaces/msg/Sixforce')
                force_data = np.array([
                    six_force.force_fx, six_force.force_fy, six_force.force_fz,
                    six_force.force_mx, six_force.force_my, six_force.force_mz
                ], dtype=np.float32)
                return force_data[from_idx:to_idx]
        except Exception:
            pass
        return np.array([np.nan] * (to_idx - from_idx), dtype=np.float32)
    
    def __getitem__(self, key):
        """支持 buffer[cam_name] 返回该相机的所有帧的伪list"""
        if isinstance(key, str):
            # buffer["camera_front"] -> CameraFrameAccessor
            return CameraFrameAccessor(self, key)
        else:
            raise TypeError(f"Expected string key (camera name), got {type(key)}")
    
    def get_image(self, cam_name: str, frame_idx: int) -> np.ndarray | None:
        """获取指定相机的指定帧"""
        self._stats['total_accesses'] += 1
        
        # 确定需要哪个chunk
        chunk_idx = frame_idx // self.chunk_size
        
        # 加载chunk（如果需要）
        self._load_chunk(chunk_idx)
        
        # 从chunk中获取数据
        local_idx = frame_idx - self._current_chunk_start
        if 0 <= local_idx < len(self._current_chunk_data['images'][cam_name]):
            return self._current_chunk_data['images'][cam_name][local_idx]
        return None
    
    def get_state(self, frame_idx: int) -> np.ndarray:
        """获取指定帧的state"""
        chunk_idx = frame_idx // self.chunk_size
        self._load_chunk(chunk_idx)
        local_idx = frame_idx - self._current_chunk_start
        if 0 <= local_idx < len(self._current_chunk_data['states']):
            return self._current_chunk_data['states'][local_idx]
        return np.array([], dtype=np.float32)
    
    def get_action(self, frame_idx: int) -> np.ndarray:
        """获取指定帧的action"""
        chunk_idx = frame_idx // self.chunk_size
        self._load_chunk(chunk_idx)
        local_idx = frame_idx - self._current_chunk_start
        if 0 <= local_idx < len(self._current_chunk_data['actions']):
            return self._current_chunk_data['actions'][local_idx]
        return np.array([], dtype=np.float32)
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        hit_rate = self._stats['chunk_hits'] / self._stats['total_accesses'] if self._stats['total_accesses'] > 0 else 0
        return {
            'total_accesses': self._stats['total_accesses'],
            'chunk_loads': self._stats['chunk_loads'],
            'chunk_hits': self._stats['chunk_hits'],
            'hit_rate': f"{hit_rate:.1%}",
            'current_chunk': self._current_chunk_idx + 1 if self._current_chunk_idx >= 0 else None,
            'total_chunks': self.num_chunks,
            'index_build_time': f"{self._stats['index_build_time']:.2f}s",  # 🆕 索引构建时间
            'index_built': self._index_built,  # 🆕 索引是否已构建
        }


class CameraFrameAccessor:
    """相机帧访问器，支持 buffer["camera"][frame_idx] 语法"""
    
    def __init__(self, parent_buffer: ChunkedMcapBuffer, cam_name: str):
        self.parent = parent_buffer
        self.cam_name = cam_name
    
    def __len__(self) -> int:
        return self.parent.total_frames
    
    def __getitem__(self, frame_idx: int) -> np.ndarray | None:
        return self.parent.get_image(self.cam_name, frame_idx)


class ChunkedImagesBuffer:
    """图像buffer wrapper - 表现为 dict[str, list]"""
    
    def __init__(self, parent: ChunkedMcapBuffer):
        self.parent = parent
    
    def __getitem__(self, cam_name: str):
        """返回特定相机的帧访问器"""
        return CameraFrameAccessor(self.parent, cam_name)
    
    def keys(self):
        """返回所有相机名称"""
        return self.parent.image_topics.values()


class ChunkedStatesBuffer:
    """States buffer wrapper - 表现为 list[np.ndarray]"""
    
    def __init__(self, parent: ChunkedMcapBuffer):
        self.parent = parent
    
    def __len__(self) -> int:
        return self.parent.total_frames
    
    def __getitem__(self, frame_idx: int) -> np.ndarray:
        return self.parent.get_state(frame_idx)


class ChunkedActionsBuffer:
    """Actions buffer wrapper - 表现为 list[np.ndarray]"""
    
    def __init__(self, parent: ChunkedMcapBuffer):
        self.parent = parent
    
    def __len__(self) -> int:
        return self.parent.total_frames
    
    def __getitem__(self, frame_idx: int) -> np.ndarray:
        return self.parent.get_action(frame_idx)

