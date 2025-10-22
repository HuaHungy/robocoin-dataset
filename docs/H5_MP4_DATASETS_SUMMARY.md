# H5+MP4 数据集结构总结

## 📦 使用H5+MP4 Converter的数据集

共4个device/version使用此converter：

### 1. Agilex Cobot - h5_mp4_new ✅

**Device**: `agilex_cobot_decoupled_magic:h5_mp4_new`  
**配置**: `converter_config_agilex_cobot_decoupled_magic_h5_mp4_new.yaml`

**目录结构**:
```
dataset/
└── 5539/  # episode目录
    ├── 5539.hdf5
    ├── 5539_cam_high.mp4
    ├── 5539_cam_left_wrist.mp4
    └── 5539_cam_right_wrist.mp4
```

**H5结构**:
```python
qpos: (598, 14)  # 598帧
  - [0:6]   左臂6关节
  - [6]     左夹爪
  - [7:13]  右臂6关节
  - [13]    右夹爪

action: (598, 14)  # 同上
```

**特点**:
- ✅ 扁平episode结构（1层）
- ✅ 使用range_from/range_to取数据
- ✅ 简单的H5结构（qpos, action）
- ✅ 所有数据为弧度（rad）
- ✅ 配置已修正（gripper添加_rad）

---

### 2. Agilex Cobot - h5_mp4 (旧版) ✅

**Device**: `agilex_cobot_decoupled_magic:h5_mp4`  
**配置**: `converter_config_agilex_cobot_decoupled_magic_h5_mp4.yaml`

**目录结构**: （基于注释）
```
任务/颜色/episode/
├── data.hdf5
├── front.mp4
├── left.mp4
└── right.mp4
```

**H5结构**:
```python
qpos: (T, 14)  # 14维
  - [0:6]   左臂6关节
  - [6]     左夹爪
  - [7:13]  右臂6关节
  - [13]    右夹爪

action: (T, 14)  # 同上
```

**特点**:
- ✅ 扁平H5结构（qpos, action）
- ✅ 14维（6关节+夹爪 × 2）
- ✅ 视频pattern: `*front.mp4`, `*left.mp4`, `*right.mp4`
- ✅ 所有数据为弧度（rad）
- ✅ 配置已修正（gripper添加_rad）
- 📍 数据集路径: `/mnt/nas/synnas/docker/外部数据/aloha15000条`

**与h5_mp4_new的区别**:
- 视频文件命名不同（front/left/right vs cam_high/cam_left_wrist/cam_right_wrist）
- 可能是同一套数据的不同采集批次

---

### 3. Galaxea R1 Lite (h5_mp4_version)

**配置**: `converter_config_galaxea_r1_lite_h5_mp4.yaml`

**目录结构**: （待确认）
```
dataset/
└── episode_dir/
    ├── *.hdf5
    ├── *cam_high.mp4
    ├── *cam_left_wrist.mp4
    └── *cam_right_wrist.mp4
```

**H5结构**:
```python
qpos: (N, 14)  # 14维
  - 左臂7个 + 右臂7个

action: (N, 14)  # 14维
```

**特点**:
- 使用`h5_path`参数
- 14维qpos和action
- 字段命名：left_arm_qpos_0...6, right_arm_qpos_0...6

---

### 3. RoboBrain (h5_mp4)

**配置**: `converter_config_robobrain_h5_mp4.yaml`

**目录结构**: （待确认）
```
dataset/
└── episode_dir/
    ├── *.hdf5
    ├── *cam_high.mp4
    ├── *cam_left_wrist.mp4
    └── *cam_right_wrist.mp4
```

**H5结构**:
```python
observations/qpos: (N, >=89)  # 复杂结构
  - [0:6]    左臂6关节
  - [10]     左夹爪
  - [30:33]  左臂末端位置 (x,y,z)
  - [33:39]  左臂末端旋转 (6D)
  - [50:56]  右臂6关节
  - [60]     右夹爪
  - [80:83]  右臂末端位置 (x,y,z)
  - [83:89]  右臂末端旋转 (6D)

action: (N, >=89)  # 同上结构
```

**特点**:
- 复杂的H5结构（嵌套：observations/qpos）
- 包含末端执行器位姿
- 使用convert_func进行数据转换（rot6d_to_euler_xyz）
- 非连续的索引（0:6, 10, 30:33, ...）

---

## 🔍 共同特征

### Episode定位策略

**当前实现**（`_get_all_episode_dirs`）:
```python
# 递归查找包含.hdf5/.h5文件的目录作为episode目录
def _get_all_episode_dirs(task_path) -> list[Path]:
    # 返回包含.h5文件的目录列表
    return [dir_with_h5_files]
```

**问题**:
- ❌ 对于嵌套结构很慢
- ❌ 需要递归遍历整个目录树
- ❌ 对于扁平结构（agilex）也要递归

**建议改进**（以.h5文件为单位）:
```python
def _get_all_episode_h5_files(task_path) -> list[Path]:
    """直接返回.h5文件列表，而不是包含它们的目录"""
    # 方案1: glob查找（更快）
    h5_files = list(task_path.glob("**/*.hdf5")) + list(task_path.glob("**/*.h5"))
    
    # 方案2: 限制搜索深度（避免过深）
    h5_files = []
    for depth in range(5):  # 最多5层
        pattern = "/".join(["*"] * depth) + "/*.hdf5"
        h5_files.extend(task_path.glob(pattern))
    
    return sorted(h5_files)
```

**优点**:
- ✅ 更快（glob比递归快）
- ✅ 更直接（直接定位文件而不是目录）
- ✅ 更灵活（可以处理各种结构）

### 视频文件定位

**当前实现**:
```python
# 在episode目录中用glob查找视频
mp4_files = list(ep_dir.glob(video_pattern))
```

**改进后**:
```python
# 如果ep_path是.h5文件
ep_dir = ep_path.parent  # 获取h5文件所在目录
mp4_files = list(ep_dir.glob(video_pattern))
```

---

## 🎯 优化方案

### 方案1: 修改Episode定位（推荐）

**修改`_get_all_episode_dirs`为`_get_all_episode_h5_files`**:

```python
class LerobotFormatConverterH5Mp4(LerobotFormatConverter):
    
    def _get_all_episode_h5_files(self, task_path: Path) -> list[Path]:
        """直接获取所有H5文件路径（更快）"""
        # 缓存检查
        cache_key = ('h5_files', task_path)
        if hasattr(self, '_ep_cache') and cache_key in self._ep_cache:
            return self._ep_cache[cache_key]
        
        if not hasattr(self, '_ep_cache'):
            self._ep_cache = {}
        
        # 快速查找：先尝试扁平结构
        h5_files = list(task_path.glob("*.hdf5")) + list(task_path.glob("*.h5"))
        
        if not h5_files:
            # 如果没找到，尝试1层嵌套
            for subdir in task_path.iterdir():
                if subdir.is_dir():
                    h5_files.extend(subdir.glob("*.hdf5"))
                    h5_files.extend(subdir.glob("*.h5"))
        
        if not h5_files:
            # 如果还是没找到，使用递归（最多5层）
            h5_files = list(task_path.glob("**/*.hdf5")) + list(task_path.glob("**/*.h5"))
        
        h5_files = sorted(h5_files)
        
        if not h5_files:
            raise FileNotFoundError(f"No .h5/.hdf5 files found in {task_path}")
        
        # 缓存
        self._ep_cache[cache_key] = h5_files
        
        return h5_files
    
    def _get_episode_h5_file(self, task_path: Path, ep_idx: int) -> Path:
        """获取episode的H5文件（直接返回，无需额外查找）"""
        h5_files = self._get_all_episode_h5_files(task_path)
        if ep_idx >= len(h5_files):
            raise IndexError(f"Episode index {ep_idx} out of range")
        return h5_files[ep_idx]
    
    def _get_episode_dir(self, h5_file: Path) -> Path:
        """从H5文件路径获取episode目录（用于查找视频）"""
        return h5_file.parent
```

### 方案2: 集成LazyVideoReader

```python
from robocoin_dataset.format_converter.video.lazy_video_reader import LazyVideoReader

class LerobotFormatConverterH5Mp4(LerobotFormatConverter):
    
    def __init__(self, ...):
        super().__init__(...)
        # 移除旧的_video_readers
        # self._video_readers = {}
        self._lazy_readers_cache = {}  # 缓存LazyVideoReader实例
    
    def _prepare_episode_images_buffer(self, task_path, ep_idx, is_test=False):
        """准备图像buffer - 使用LazyVideoReader"""
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        ep_dir = self._get_episode_dir(h5_file)
        
        images = {}
        image_configs = self.converter_config[FEATURES_KEY][OBSERVATION_KEY][IMAGE_KEY]
        
        for image_config in image_configs:
            args = image_config.get(ARGS_KEY, {})
            cam_name = args.get(CAM_NAME_KEY)
            video_pattern = args.get('video_file_pattern', '*')
            
            mp4_files = list(ep_dir.glob(video_pattern))
            if not mp4_files:
                continue
            
            mp4_file = mp4_files[0]
            video_key = str(mp4_file)
            
            # ✅ 使用LazyVideoReader（延迟加载）
            if is_test or self._is_test_mode:
                # Test模式：预加载前11帧
                lazy_reader = LazyVideoReader(video_key, backend='pyav', logger=self.logger)
                frames = [lazy_reader[i] for i in range(min(11, len(lazy_reader)))]
                images[cam_name] = frames
                lazy_reader.close()
            else:
                # 正常模式：返回lazy reader
                if video_key not in self._lazy_readers_cache:
                    self._lazy_readers_cache[video_key] = LazyVideoReader(
                        video_key, backend='pyav', logger=self.logger
                    )
                images[cam_name] = self._lazy_readers_cache[video_key]
        
        return images
```

### 方案3: 集成H5FileCache

```python
from robocoin_dataset.format_converter.utils.h5_cache import H5FileCache

class LerobotFormatConverterH5Mp4(LerobotFormatConverter):
    
    def __init__(self, ...):
        super().__init__(...)
        self._h5_cache = H5FileCache(max_open_files=10, logger=self.logger)
    
    def _prepare_episode_states_buffer(self, task_path, ep_idx):
        """准备状态buffer - 使用H5缓存"""
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        
        # ✅ 使用缓存的H5文件
        with self._h5_cache.get_file(h5_file) as f:
            if 'qpos' in f:
                return np.array(f['qpos'])
            elif 'observations/qpos' in f:
                return np.array(f['observations/qpos'])
            raise ValueError(f"No qpos data in {h5_file}")
    
    def _prepare_episode_actions_buffer(self, task_path, ep_idx):
        """准备动作buffer - 使用H5缓存"""
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        
        # ✅ 复用缓存的H5文件（不需要重新打开）
        with self._h5_cache.get_file(h5_file) as f:
            if 'action' in f:
                return np.array(f['action'])
            raise ValueError(f"No action data in {h5_file}")
```

---

## 📊 预期性能提升

| 操作 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| **Episode定位** | 1-5秒（递归） | <0.1秒（glob） | **10-50倍** |
| **视频加载** | 2-5秒（全加载） | <0.1秒（lazy） | **20-50倍** |
| **H5读取** | 0.1秒/次（重复打开） | 0.01秒/次（缓存） | **10倍** |
| **内存占用** | ~500MB/episode | ~20MB/episode | **25倍减少** |
| **总体转换速度** | 3-10秒/ep | 0.2-0.5秒/ep | **15-50倍** |

---

## ⚠️ Galaxea rosbag验证问题

**报错信息**:
```
13:27:07 - INFO - 检测到格式: rosbag
13:27:07 - ERROR - 分析Episode 9 失败: 不支持的格式: rosbag
```

**原因**: 配置验证工具还不支持rosbag格式

**解决方案**:
1. **短期**: 使用手动分析（我们已经完成）
2. **长期**: 在schema_analyzer.py中添加rosbag支持

---

## 🚀 实施计划

### 阶段1: Episode定位优化（30分钟）
1. 修改`_get_all_episode_dirs`为`_get_all_episode_h5_files`
2. 修改所有引用此方法的地方
3. 添加缓存机制
4. 测试

### 阶段2: LazyVideoReader集成（1小时）
1. 修改`_prepare_episode_images_buffer`
2. 修改`_get_frame_image`支持lazy reader
3. 保留test mode预加载逻辑
4. 测试

### 阶段3: H5FileCache集成（30分钟）
1. 修改state/action buffer方法
2. 添加资源清理
3. 测试

### 阶段4: 测试验证（1小时）
1. 测试agilex数据集
2. 如有其他H5+MP4数据，测试它们
3. 验证性能提升
4. 验证内存减少

---

## 📝 需要确认

1. **其他H5+MP4数据集的路径**？（galaxea h5_mp4, robobrain）
2. **是否有测试数据可以用来验证优化效果**？
3. **优先优化哪些converter**？
   - H5+MP4（当前）✅
   - Leju Waibu（也使用视频）
   - 其他？

