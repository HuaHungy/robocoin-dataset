# Agilex H5+MP4 Converter 分析与优化

## 📦 数据集信息

**Device**: `agilex_cobot_decoupled_magic:h5_mp4_new`  
**格式**: H5 + MP4 (HDF5数据文件 + MP4视频文件)  
**示例路径**: `data/agilex_cobot_decoupled_magic:h5_mp4_new/5539/`

### 数据结构
```
data/agilex_cobot_decoupled_magic:h5_mp4_new/
└── 5539/  # episode目录
    ├── 5539.hdf5  # 包含qpos和action数据
    ├── 5539_cam_high.mp4
    ├── 5539_cam_left_wrist.mp4
    └── 5539_cam_right_wrist.mp4
```

### H5文件内容
```
qpos: (598, 14) - 598帧，14维状态
  - [0:7]  左臂6关节 + 左夹爪
  - [7:14] 右臂6关节 + 右夹爪

action: (598, 14) - 598帧，14维动作
  - [0:7]  左臂6关节 + 左夹爪
  - [7:14] 右臂6关节 + 右夹爪
```

---

## 🏗️ 当前架构分析

### 1. 基类架构

#### 基类抽象方法
```python
# LerobotFormatConverter基类定义
@abstractmethod
def _get_episode_frames_num(task_path, ep_idx) -> int:
    """获取episode的帧数"""
    
@abstractmethod
def _get_task_episodes_num(task_path) -> int:
    """获取task的episode数量"""
    
@abstractmethod
def _get_frame_image(task_path, ep_idx, frame_idx, args_dict, images_buffer) -> np.ndarray:
    """获取指定帧的图像"""
    
@abstractmethod
def _get_frame_sub_states(task_path, ep_idx, frame_idx, args_dict, sub_states_buffer) -> np.ndarray:
    """获取指定帧的状态"""
    
@abstractmethod
def _get_frame_sub_actions(task_path, ep_idx, frame_idx, args_dict, sub_actions_buffer) -> np.ndarray:
    """获取指定帧的动作"""
    
@abstractmethod
def _prevalidate_files() -> None:
    """验证文件完整性"""
```

### 2. H5+MP4 Converter 实现

#### 特有的方法（不在基类接口中）
```python
def _get_all_episode_dirs(task_path) -> list[Path]:
    """递归查找包含.hdf5/.h5文件的目录
    
    支持多层嵌套结构（最多5层）：
    - 扁平: task_path/episode_0/
    - 2层: task_path/color/episode_0/
    - 3层: task_path/color/batch/episode_0/
    - 4层: task_path/variant/color/batch/episode_0/
    """
```

#### 当前实现的问题

1. **Episode定位逻辑冗余**
   - ❌ 每个子类都要实现自己的episode定位逻辑
   - ❌ 代码重复：H5+MP4、MP4+JSON、MCAP等都有类似逻辑
   - ❌ 不一致：不同子类的查找深度、策略不同

2. **性能问题**
   ```python
   def _get_all_episode_dirs(path, max_depth=5, current_depth=0):
       # 递归遍历所有子目录
       for sub_dir in path.iterdir():  # ❌ 遍历所有目录
           episode_dirs.extend(find_episode_dirs(sub_dir, ...))  # ❌ 递归调用
   ```
   - ❌ **递归遍历整个目录树**，对于大数据集很慢
   - ❌ 每次调用都要重新扫描
   - ❌ 没有缓存机制

3. **视频加载效率问题**
   ```python
   def _prepare_episode_images_buffer(task_path, ep_idx, is_test=False):
       # 使用 PyAV 读取整个视频
       for frame_idx, frame in enumerate(container.decode(video=0)):
           img = frame.to_ndarray(format='rgb24')
           frames.append(img)  # ❌ 全部加载到内存
   ```
   - ❌ **一次性加载所有帧到内存**
   - ❌ 对于长视频（598帧）内存占用大
   - ❌ 没有使用`LazyVideoReader`

4. **H5文件读取效率问题**
   ```python
   def _prepare_episode_states_buffer(task_path, ep_idx):
       h5_file = self._get_episode_h5_file(task_path, ep_idx)
       with h5py.File(h5_file, 'r') as f:  # ❌ 每次都打开关闭
           return np.array(f['qpos'])  # ❌ 全部加载到内存
   ```
   - ❌ 每次都打开关闭H5文件
   - ❌ 没有使用`H5FileCache`
   - ❌ 全部加载到内存

---

## 🎯 优化方案

### 方案1: Episode定位优化（高优先级）

#### 问题
- 用户提到"部分数据集比较深"
- 递归遍历整个目录树慢
- 每个子类都要重复实现

#### 解决方案A: 统一的Episode定位器（推荐）

**在基类中提供通用的episode定位逻辑**：

```python
# 在 LerobotFormatConverter 基类中添加
class LerobotFormatConverter(ABC):
    
    def _find_episode_dirs(
        self, 
        task_path: Path, 
        episode_marker_files: list[str] = None,  # e.g., ['*.hdf5', '*.h5']
        max_depth: int = 5,
        cache: bool = True
    ) -> list[Path]:
        """通用的episode目录查找器
        
        Args:
            task_path: 任务路径
            episode_marker_files: 用于标识episode目录的文件pattern
            max_depth: 最大搜索深度
            cache: 是否缓存结果
            
        Returns:
            按顺序排序的episode目录列表
        """
        # 检查缓存
        cache_key = (task_path, tuple(episode_marker_files), max_depth)
        if cache and hasattr(self, '_episode_dirs_cache'):
            if cache_key in self._episode_dirs_cache:
                return self._episode_dirs_cache[cache_key]
        
        if not hasattr(self, '_episode_dirs_cache'):
            self._episode_dirs_cache = {}
        
        # 快速查找策略
        episode_dirs = []
        
        # 策略1: 先检查是否是扁平结构（最常见）
        if self._is_flat_structure(task_path, episode_marker_files):
            episode_dirs = list(task_path.iterdir())
            episode_dirs = [d for d in episode_dirs if d.is_dir() and self._has_marker_files(d, episode_marker_files)]
        else:
            # 策略2: 递归查找（但限制深度）
            episode_dirs = self._recursive_find_episodes(
                task_path, episode_marker_files, max_depth, 0
            )
        
        # 排序
        episode_dirs = sorted(episode_dirs)
        
        # 缓存
        if cache:
            self._episode_dirs_cache[cache_key] = episode_dirs
        
        return episode_dirs
    
    def _is_flat_structure(self, path: Path, marker_files: list[str]) -> bool:
        """快速检查是否是扁平结构"""
        # 检查前几个子目录是否都包含marker文件
        subdirs = [d for d in path.iterdir() if d.is_dir()][:3]
        if not subdirs:
            return False
        return all(self._has_marker_files(d, marker_files) for d in subdirs)
    
    def _has_marker_files(self, path: Path, marker_files: list[str]) -> bool:
        """检查目录是否包含标记文件"""
        for pattern in marker_files:
            if list(path.glob(pattern)):
                return True
        return False
```

**子类使用**：
```python
class LerobotFormatConverterH5Mp4(LerobotFormatConverter):
    
    def _get_all_episode_dirs(self, task_path: Path) -> list[Path]:
        """使用基类的通用定位器"""
        return self._find_episode_dirs(
            task_path,
            episode_marker_files=['*.hdf5', '*.h5'],
            max_depth=5,
            cache=True
        )
```

#### 解决方案B: 预扫描 + 缓存（更快）

```python
# 在初始化时一次性扫描所有episode
def __init__(self, ...):
    super().__init__(...)
    # 预扫描所有episode
    self._episode_cache = {}
    for task_path in self.path_task_dict.keys():
        self._episode_cache[task_path] = self._scan_episodes_fast(task_path)
        
def _scan_episodes_fast(self, task_path: Path) -> list[Path]:
    """快速扫描episode（使用os.walk更快）"""
    import os
    
    episodes = []
    for root, dirs, files in os.walk(task_path):
        # 检查当前目录是否包含h5文件
        if any(f.endswith('.hdf5') or f.endswith('.h5') for f in files):
            episodes.append(Path(root))
            dirs.clear()  # 不再向下搜索
    
    return sorted(episodes)
```

---

### 方案2: 视频加载优化（高优先级）

#### 使用 LazyVideoReader

```python
from robocoin_dataset.format_converter.video.lazy_video_reader import LazyVideoReader

class LerobotFormatConverterH5Mp4(LerobotFormatConverter):
    
    def __init__(self, ...):
        super().__init__(...)
        # ✅ 使用LazyVideoReader代替_video_readers
        self._lazy_video_readers = {}
    
    def _prepare_episode_images_buffer(self, task_path, ep_idx, is_test=False):
        """准备图像buffer - 使用LazyVideoReader"""
        episodes = self._get_all_episode_dirs(task_path)
        ep_dir = episodes[ep_idx]
        
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
            
            # ✅ 使用LazyVideoReader（延迟加载）
            lazy_reader = LazyVideoReader(
                str(mp4_file),
                backend='pyav',  # 支持更多格式
                logger=self.logger
            )
            
            # 返回lazy reader而不是所有帧
            images[cam_name] = lazy_reader
        
        return images
    
    def _get_frame_image(self, task_path, ep_idx, frame_idx, args_dict, images_buffer=None):
        """获取单帧图像 - 支持LazyVideoReader"""
        if images_buffer is None:
            images_buffer = self._prepare_episode_images_buffer(task_path, ep_idx)
        
        cam_name = args_dict.get(CAM_NAME_KEY)
        if cam_name not in images_buffer:
            raise KeyError(f"Camera {cam_name} not found")
        
        video_source = images_buffer[cam_name]
        
        # ✅ 支持两种模式
        if isinstance(video_source, LazyVideoReader):
            # 延迟加载模式：只读取需要的帧
            return video_source[frame_idx]
        elif isinstance(video_source, list):
            # 预加载模式（test mode）：从列表读取
            return video_source[frame_idx]
        else:
            raise TypeError(f"Unexpected video source type: {type(video_source)}")
```

**优点**：
- ✅ **大幅减少内存占用**（不再一次性加载所有帧）
- ✅ **加快启动速度**（不需要等待全部视频加载）
- ✅ **支持长视频**（598帧不会占用大量内存）
- ✅ **向后兼容**（test mode仍可以预加载）

---

### 方案3: H5文件缓存优化（高优先级）

#### 使用 H5FileCache

```python
from robocoin_dataset.format_converter.utils.h5_cache import H5FileCache

class LerobotFormatConverterH5Mp4(LerobotFormatConverter):
    
    def __init__(self, ...):
        super().__init__(...)
        # ✅ 使用H5FileCache
        self._h5_cache = H5FileCache(
            max_open_files=10,  # 最多同时打开10个H5文件
            logger=self.logger
        )
    
    def _prepare_episode_states_buffer(self, task_path, ep_idx):
        """准备状态buffer - 使用H5缓存"""
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        
        # ✅ 使用缓存的H5文件句柄
        with self._h5_cache.get_file(h5_file) as f:
            # 只读取需要的数据
            if 'qpos' in f:
                return np.array(f['qpos'])
            raise ValueError(f"No qpos data in {h5_file}")
    
    def _prepare_episode_actions_buffer(self, task_path, ep_idx):
        """准备动作buffer - 使用H5缓存"""
        h5_file = self._get_episode_h5_file(task_path, ep_idx)
        
        # ✅ 使用缓存的H5文件句柄（不需要重新打开）
        with self._h5_cache.get_file(h5_file) as f:
            if 'action' in f:
                return np.array(f['action'])
            raise ValueError(f"No action data in {h5_file}")
    
    def __del__(self):
        """清理资源"""
        if hasattr(self, '_h5_cache'):
            self._h5_cache.close_all()
```

**优点**：
- ✅ **减少文件I/O**（不需要反复打开关闭）
- ✅ **提高读取速度**（文件句柄缓存）
- ✅ **自动管理资源**（LRU缓存，自动关闭旧文件）

---

## 📊 性能对比估算

### 当前实现
| 操作 | 时间 | 内存 |
|------|------|------|
| Episode定位 | ~1-5秒（递归遍历） | 低 |
| 视频加载（598帧x3） | ~2-5秒 | ~500MB |
| H5文件读取 | ~0.1秒/次 | 低 |
| **总计（单episode）** | **~3-10秒** | **~500MB** |

### 优化后
| 操作 | 时间 | 内存 |
|------|------|------|
| Episode定位（缓存） | ~0.1秒（首次），<0.01秒（缓存） | 低 |
| 视频加载（Lazy） | <0.1秒 | ~10MB |
| H5文件读取（缓存） | ~0.05秒/次 | 低 |
| **总计（单episode）** | **~0.2秒** | **~20MB** |

**预期提升**：
- ⚡ **速度提升 15-50倍**
- 💾 **内存减少 25倍**

---

## 🚀 实施计划

### 阶段1: Episode定位优化（1-2小时）
1. ✅ 分析当前目录结构
2. 在基类添加`_find_episode_dirs()`通用方法
3. 修改H5+MP4 converter使用新方法
4. 测试多种目录结构

### 阶段2: 视频加载优化（1-2小时）
1. 集成`LazyVideoReader`
2. 修改`_prepare_episode_images_buffer()`
3. 修改`_get_frame_image()`支持lazy loading
4. 保留test mode的预加载逻辑

### 阶段3: H5缓存优化（30分钟）
1. 集成`H5FileCache`
2. 修改state/action buffer方法
3. 添加资源清理

### 阶段4: 测试验证（1小时）
1. 测试单episode转换
2. 测试批量转换
3. 验证内存占用
4. 验证速度提升

---

## ⚠️ 当前紧急问题

### 配置文件问题
```yaml
# converter_config_agilex_cobot_decoupled_magic_h5_mp4_new.yaml
state:
  sub_state:
    - names:
        - left_gripper_open  # ❌ 缺少单位后缀
```

**需要修正**：
```yaml
- names:
    - left_arm_joint_1_rad
    - left_arm_joint_2_rad
    - left_arm_joint_3_rad
    - left_arm_joint_4_rad
    - left_arm_joint_5_rad
    - left_arm_joint_6_rad
    - left_gripper_open  # ⚠️ 需要确认单位（rad? mm? pct?）
```

---

## 📝 建议的优先级

1. **🔴 Critical - 立即处理**:
   - 确认gripper单位（同galaxea问题）
   - 测试当前converter是否能正常工作

2. **🟡 High - 本周完成**:
   - Episode定位优化（解决速度问题）
   - 视频Lazy加载（解决内存问题）

3. **🟢 Medium - 下周完成**:
   - H5文件缓存
   - 性能监控工具

---

## 🤔 需要确认的问题

1. **Gripper单位**：数据中gripper的值是什么单位？
2. **目录结构**：你说"比较深"的数据集具体有多深？能给个例子吗？
3. **内存限制**：转换时内存限制是多少？（决定是否使用lazy loading）
4. **转换速度要求**：期望的转换速度是多少？（影响优化优先级）

---

## 🎯 下一步

**选项A - 先优化性能（推荐）**：
1. 实现LazyVideoReader集成
2. 实现H5FileCache集成
3. 测试验证速度和内存提升

**选项B - 先验证配置**：
1. 运行配置验证工具
2. 确认gripper单位
3. 检查数据质量

**选项C - 两者并行**：
1. 我优化converter代码
2. 你提供gripper单位信息和更多数据集样本

**你希望：**
- A. 先优化性能（立即实施LazyVideoReader + H5Cache）
- B. 先验证配置（读取实际数据确认单位）
- C. 你直接告诉我gripper单位，我两者一起做

