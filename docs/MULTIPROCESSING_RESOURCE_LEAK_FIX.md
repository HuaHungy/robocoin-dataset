# 多进程资源泄漏修复说明

## 问题现象

在使用 MCAP/其他格式转换器时，程序结束后出现资源泄漏警告：

```
/usr/lib/python3.10/multiprocessing/resource_tracker.py:224: UserWarning: 
resource_tracker: There appear to be 8 leaked semaphore objects to clean up at shutdown
```

## 问题原因

`LeRobotDataset` 内部使用多进程进行图像写入（通过 `image_writer_processes` 参数）。这些进程池创建了信号量（semaphore）等系统资源，但在转换完成后没有被正确释放。

具体来说：
1. `LeRobotDataset.create()` 创建了一个包含 `AsyncImageWriter` 的 dataset 对象
2. `AsyncImageWriter` 使用 `multiprocessing.JoinableQueue` 和多个进程/线程
3. 转换器在所有 episode 处理完后直接退出，没有调用 `stop_image_writer()` 清理方法
4. Python 垃圾回收器无法自动清理这些系统级资源（JoinableQueue、Process、Semaphore）
5. 导致信号量对象泄漏

## 解决方案

### 修改内容

修改了 `lerobot_format_converter.py` 中的 `convert()` 方法，添加完整的资源清理逻辑：

**修改前**：
```python
def convert(self, is_test: bool = False) -> Iterable[tuple[str, int, int]]:
    if not is_test:
        dataset = self._create_lerobot_dataset()
    ep_idx = 0
    # ... 处理所有episode ...
    # 函数结束，dataset对象没有被清理
```

**修改后**：
```python
def convert(self, is_test: bool = False) -> Iterable[tuple[str, int, int]]:
    dataset = None
    try:
        if not is_test:
            dataset = self._create_lerobot_dataset()
        ep_idx = 0
        # ... 处理所有episode ...
    finally:
        # 清理资源：确保 LeRobotDataset 内部的异步 image writer 和其他多进程资源被释放
        if dataset is not None:
            try:
                if self.logger:
                    self.logger.info("Cleaning up dataset resources...")

                # 1) Stop image writer (关闭所有异步写入进程/线程)
                if hasattr(dataset, "stop_image_writer"):
                    dataset.stop_image_writer()
                    if self.logger:
                        self.logger.info("✅ Dataset image writer stopped")

                # 2) Wait for image writer (等待所有任务完成)
                if hasattr(dataset, "_wait_image_writer"):
                    dataset._wait_image_writer()
                    if self.logger:
                        self.logger.info("✅ Image writer joined successfully")

                # 3) Call consolidate() if available (兼容某些分支)
                if hasattr(dataset, "consolidate"):
                    dataset.consolidate()
                    if self.logger:
                        self.logger.info("✅ Dataset consolidated successfully")

            except Exception as e:
                if self.logger:
                    self.logger.warning(f"⚠️ Error during dataset cleanup: {e}")
```

### 关键改进

1. **使用 try-finally 结构**：确保即使转换出错，资源也会被清理
2. **调用 dataset.stop_image_writer()**：这个方法会：
   - 向所有工作进程发送停止信号（None）
   - 调用 `process.join()` 等待进程结束
   - 调用 `process.terminate()` 强制终止未响应的进程
   - 关闭 `JoinableQueue` 并释放信号量
3. **调用 dataset._wait_image_writer()**：确保所有待写入任务完成
4. **异常处理**：即使 cleanup 失败也不影响主流程

## 影响范围

此修改影响所有继承 `LerobotFormatConverter` 的转换器：
- ✅ MCAP 格式（realman_rmc_aidal）
- ✅ H5 格式（zhipingfang, ruantong等）
- ✅ MP4+JSON 格式（yinhe）
- ✅ H5+MP4 格式（galaxea - 使用 PyAV）
- ✅ 其他所有格式转换器

## 验证方法

转换完成后检查日志，应该看到：
```
INFO | Cleaning up dataset resources...
INFO | ✅ Dataset image writer stopped
INFO | ✅ Image writer joined successfully
```

并且不再出现资源泄漏警告。

## 技术说明

### AsyncImageWriter 的资源使用

```python
# 创建时分配资源（在 LeRobotDataset.__init__ 或 start_image_writer 中）
image_writer = AsyncImageWriter(
    num_processes=4,  # 创建4个图像写入进程
    num_threads=4,    # 每个进程4个线程
)

# 每个进程都使用：
#  - multiprocessing.Process
#  - multiprocessing.JoinableQueue (内部使用 Semaphore)
#  - threading.Thread (工作线程)

# 必须显式清理
image_writer.stop()  # 关闭所有进程和队列
```

### AsyncImageWriter.stop() 的清理步骤

```python
def stop(self):
    if self.num_processes == 0:
        # 线程模式：发送停止信号
        for _ in self.threads:
            self.queue.put(None)
        for t in self.threads:
            t.join()
    else:
        # 多进程模式：发送停止信号
        num_nones = self.num_processes * self.num_threads
        for _ in range(num_nones):
            self.queue.put(None)  # 每个线程一个停止信号
        
        # 等待所有进程结束
        for p in self.processes:
            p.join()
            if p.is_alive():
                p.terminate()  # 强制终止
        
        # 关闭队列并释放资源
        self.queue.close()
        self.queue.join_thread()  # 释放 feeder 线程和信号量
```

### 什么是信号量（Semaphore）？

信号量是多进程/多线程编程中的同步原语，用于：
- 限制同时访问资源的进程数
- 进程间通信和同步
- 在 `multiprocessing.Queue` 内部用于跟踪队列状态

### 为什么会泄漏？

1. **系统级资源**：信号量是系统级对象（POSIX semaphore），不是 Python 对象
2. **需要显式清理**：必须调用 `queue.close()` 和 `queue.join_thread()` 才能释放
3. **GC 不够**：Python 垃圾回收器无法自动清理系统资源
4. **进程未join**：未 join 的进程会保留打开的资源句柄

## 相关问题

如果仍然出现资源泄漏，检查：
1. 是否有其他地方创建了多进程资源没有清理？
2. 是否有临时文件没有关闭？
3. 是否有 H5 文件没有 close？
4. 是否有 PyAV 容器没有 close？

可以使用以下工具检查：
```python
import multiprocessing
import gc

# 查看所有活跃的进程
for p in multiprocessing.active_children():
    print(f"Active process: {p.name} (pid={p.pid})")

# 强制垃圾回收
gc.collect()
```

### 查看系统信号量

```bash
# Linux: 查看当前进程的信号量
ls -l /dev/shm/sem.*

# 或使用 ipcs 命令
ipcs -s
```

## 参考

- Python multiprocessing资源追踪：https://docs.python.org/3/library/multiprocessing.html#multiprocessing.resource_tracker
- LeRobot Dataset API：`lerobot.datasets.lerobot_dataset.LeRobotDataset`
- AsyncImageWriter 实现：`lerobot.datasets.image_writer.AsyncImageWriter`
- JoinableQueue 文档：https://docs.python.org/3/library/multiprocessing.html#multiprocessing.JoinableQueue
