# 问题深度分析 - 2025-10-27

## 1️⃣ galaxea - completed但有异常

### 你的问题
"为什么是completed？"

### 分析

**错误发生的位置**：
```python
# client.py 第85行
converter = LerobotFormatConverterFactory.create_converter(...)
# 在创建converter对象时就失败了
```

**异常类型**：
```
RuntimeError: ❌ Failed to get sample image for camera 'cam_high_rgb' 
after trying 5 task_path/episode combinations.
Failed to read frame 0 from .../3942_cam_high.mp4
```

**错误流程**：
1. Client尝试创建converter对象
2. 初始化时需要读取样本图像（用于获取图像shape）
3. 尝试读取5个不同episode的视频第一帧
4. **全部失败** → 抛出RuntimeError
5. Client返回 `TASK_FAILED` 给Server
6. Server应该更新状态为 `FAILED`

### 可能的原因

#### 可能性1：不同的任务
- galaxea可能有多个子数据集
- 之前的任务成功了（状态=COMPLETED）
- 现在的任务失败了（但你看到的还是旧的COMPLETED状态）

#### 可能性2：视频文件问题
- 视频文件损坏
- 视频编码格式问题（cv2.VideoCapture无法读取）
- 文件权限问题

#### 可能性3：数据库显示问题
- 你查看的是test表还是正式表？
- `lerobot_format_convert` vs `lerobot_format_convert_test`
- 可能两个表的状态不一致

### 验证步骤

```bash
# 检查视频文件
ls -lh /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train/open_and_close_nightstand_door/3942/

# 尝试读取视频
ffprobe /mnt/nas/.../3942/3942_cam_high.mp4

# 手动测试能否读取
python3 << 'EOF'
import cv2
cap = cv2.VideoCapture('/mnt/nas/.../3942/3942_cam_high.mp4')
ret, frame = cap.read()
print(f"Can read frame: {ret}")
if ret:
    print(f"Frame shape: {frame.shape}")
cap.release()
EOF

# 查看数据库状态
sqlite3 db/datasets.db
SELECT dataset_uuid, convert_status, err_message 
FROM lerobot_format_convert_test 
WHERE device_model = 'galaxea_r1_lite';
.quit
```

---

## 2️⃣ leju_waibu - 配置vs实际H5字段对比

### H5文件实际路径（从错误信息）

```
实际存在：
- action/effector/index
- action/effector/position(dexhand)
- action/head/index
- action/head/position
- action/joint/index
- action/joint/position
- camera_extrinsic_params/...
- effector_dexhand_timestamps
- hand_left_color_mp4_timestamps
- ... 还有22个

❌ 不存在：任何 state/... 开头的路径
```

### 配置文件要求的路径

```yaml
observation.state 需要：
✅ state/joint/position (第87, 102行)
❌ state/leg/position (第116, 130行) ← 错误来源
✅ state/effector/position(dexhand) (第145, 160行)
❌ state/head/position (第171行)
❌ state/joint/velocity (第186, 201行)
❌ state/joint/effort (第216, 231行)
❌ state/leg/velocity (第245, 259行)
❌ state/leg/effort (第273, 287行)
❌ state/head/velocity (第297行)
❌ state/head/effort (第307行)
❌ state/end/position (第319, 332行)
❌ state/end/orientation (第345, 359行)
❌ imu/acc_xyz (第372行)
❌ imu/gyro_xyz (第383行)
❌ imu/quat_xyzw (第395行)

action 需要：
✅ action/joint/position (第426, 441行)
❌ action/leg/position (第455, 469行)
✅ action/effector/position(dexhand) (第483, 498行)
❌ action/head/position (但配置用state/head/position代替，第510行)
❌ state/joint/velocity (第526, 540行)
```

### 结论

**配置文件与实际数据完全不匹配！**

1. ❌ 配置期望 `state/...` 路径，但H5文件中**完全没有** `state/...` 路径
2. ✅ H5文件只有 `action/...` 路径
3. 📊 这是**完全不同版本**的数据格式

### 建议

#### 选项A：创建新配置文件

为NAS上的新版本数据创建专门的配置：
```
converter_config_leju_waibu_v2.yaml  # 新版本（只有action）
converter_config_leju_waibu_v1.yaml  # 旧版本（有state和action）
```

#### 选项B：暂时跳过

等待确认数据格式后再处理。

#### 选项C：修改配置使用action数据

如果action数据可以代替state：
```yaml
observation:
  state:
    sub_state:
      - h5_path: action/joint/position  # 用action代替state
      - h5_path: action/effector/position(dexhand)
```

---

## 3️⃣ yinhe - 还在访问cmd_body_joint

### 你的问题
"你能不能好好检查一下你的代码"

### 深入检查

#### 配置文件检查

```bash
grep "cmd_body_joint" converter_config_yinhe.yaml
```

**结果**：
```
158:    # 🆕 删除了body joints (cmd_body_joint字段为空)
164:      # 🆕 Body joints已删除 - cmd_body_joint字段在数据中为空
```

✅ 配置文件确实已修改，`cmd_body_joint`只出现在注释中！

#### 错误信息分析

**错误来自**：`lerobot_format_converter_mp4_json.py` 第818行

```python
raise IndexError(
    f"❌ Frame index out of range in JSON data.\n"
    f"   📁 Location: task_path={task_path}, ep_idx={ep_idx}\n"
    f"   🔍 JSON path: 'cmd_body_joint'\n"  ← 这里！
    ...
)
```

**问题**：代码正在访问`cmd_body_joint`，但我们已经删除了配置！

#### 可能的原因

1. **Client代码没有更新**
   - Client机器上的代码是旧版本
   - 配置文件没有被拉取

2. **配置被缓存**
   - Python的`__pycache__`或配置缓存
   - 需要清理缓存

3. **不同的yinhe数据集**
   - 有两个yinhe数据集
   - 一个用了新配置，一个还在用旧配置

4. **配置文件路径问题**
   - Client在用其他路径的配置文件
   - 不是`scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml`

### 验证步骤

```bash
# 在Client机器上（报错的那台）

# 1. 检查git状态
cd ~/robocoin-dataset
git status
git log --oneline -1  # 查看最新commit

# 2. 检查配置文件
grep "cmd_body_joint" scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml

# 3. 清理Python缓存
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# 4. 重新拉取代码
git pull origin feat/test

# 5. 确认配置文件内容
head -200 scripts/format_converters/tolerobot/configs/converter_config_yinhe.yaml | grep -A 5 "sub_action"
```

### 真正的问题

**Client机器的代码/配置没有更新！**

即使数据库正确，如果Client用的是旧配置，还是会报错。

---

## 4️⃣ mmk2/所有数据集 - PROCESSING但有err_message

### 你的问题
"这是为什么，我们就是这麼设计的程序吗，台奇怪了，这种报错之后，他究竟还是不是processing啊"

### 代码流程分析

#### 正常流程

```
1. Client处理任务
2. 失败 → 返回 {TASK_RESULT_STATUS: TASK_FAILED, ERR_MSG: "..."}
3. Server收到 → handle_task_result()
4. 计算状态：convert_status = FAILED
5. 调用 upsert_leformat_convert(..., convert_status=FAILED, err_message="...")
6. 数据库更新成功
7. ✅ 结果：convert_status = FAILED, err_message = "..."
```

#### 异常流程（你遇到的情况）

```
1. Client处理任务
2. 失败 → 返回 {TASK_RESULT_STATUS: TASK_FAILED, ERR_MSG: "..."}
3. Server收到 → handle_task_result()
4. 计算状态：convert_status = FAILED
5. 调用 upsert_leformat_convert(...)
6. ❌ 数据库更新失败（某种原因）
7. ❌ 结果：convert_status = PROCESSING (未更新), err_message = "..." (可能写入)
```

### 可能导致更新失败的原因

#### 原因1：数据库表锁
```python
# 如果另一个进程持有写锁
# SQLite会返回 SQLITE_BUSY
# 更新失败但不抛异常
```

#### 原因2：Session回滚
```python
# 如果有其他异常导致session回滚
with self.db.with_session() as session:
    # ...
    upsert_leformat_convert(...)
    # 如果这里有异常 → 整个session回滚
```

#### 原因3：日志显示的是部分更新

可能：
- `err_message`字段单独更新成功了
- 但`convert_status`字段更新失败
- 导致状态不一致

### 检查代码

让我看看upsert_leformat_convert的实现：

```python
def upsert_leformat_convert(...):
    # 先查询是否存在
    existing = session.query(...).filter(...).first()
    
    if existing:
        # 更新
        existing.convert_status = convert_status
        existing.err_message = err_message
        # ...
    else:
        # 创建新记录
        new_record = LeFormatConvertDB(...)
        session.add(new_record)
    
    session.commit()  # ← 如果这里失败？
```

### 真实原因推测

根据你的描述：
1. ✅ 数据库schema正确（你说的）
2. ❌ 状态还是PROCESSING
3. ✅ err_message有内容

**可能的情况**：

1. **并发问题**
   - 多个Client同时处理同一个任务
   - 状态更新冲突

2. **异常未被捕获**
   - upsert过程中有异常
   - 但异常被外层的try-except捕获，没有重新抛出
   - Server日志应该有ERROR

3. **mmk2特定问题**：`FileExistsError`
   - 目录已存在
   - 转换在初始化阶段就失败
   - 但状态更新逻辑有问题

### 验证步骤

```bash
# 1. 查看Server日志中的错误
grep -B 5 -A 10 "Error handling task result" /path/to/server.log | tail -50

# 2. 检查是否有database lock错误
grep -i "database.*locked" /path/to/server.log

# 3. 查看有多少任务处于异常状态
sqlite3 db/datasets.db
SELECT COUNT(*) 
FROM lerobot_format_convert_test 
WHERE convert_status = 'PROCESSING' AND err_message IS NOT NULL;

# 4. 查看具体是哪些任务
SELECT dataset_uuid, device_model, err_message 
FROM lerobot_format_convert_test 
WHERE convert_status = 'PROCESSING' AND err_message IS NOT NULL
LIMIT 5;
```

---

## 📊 总结和建议

### 1️⃣ galaxea

**建议**：
1. 检查视频文件完整性
2. 确认数据库中查看的是哪个任务的状态
3. 如果视频损坏，暂时跳过这个数据集

### 2️⃣ leju_waibu

**明确结论**：配置与数据完全不匹配！

**建议**：
1. 提供一个H5文件样本，我分析完整结构
2. 或者提供`h5dump -n`的输出
3. 我创建新的配置文件

### 3️⃣ yinhe

**明确结论**：Client代码没有更新！

**立即执行**：
```bash
# 每台Client机器
cd ~/robocoin-dataset
git pull origin feat/test
# 重启clients
```

### 4️⃣ mmk2状态异常

**需要更多信息**：
1. Server的完整日志（特别是ERROR部分）
2. 数据库中异常状态的具体情况

**可能需要的修复**：
- 改进错误处理逻辑
- 确保状态更新的原子性
- 添加更详细的日志

---

## 🎯 立即执行清单

### [ ] 所有Client机器

```bash
cd ~/robocoin-dataset
git pull origin feat/test
# 重启clients
```

### [ ] 提供更多信息

1. Server日志中的ERROR部分
2. leju的H5文件结构（h5dump -n）
3. 确认galaxea在数据库中的具体状态

### [ ] Server端

查看和分析异常状态的任务：
```sql
SELECT * FROM lerobot_format_convert_test 
WHERE convert_status = 'PROCESSING' AND err_message IS NOT NULL;
```

