# 各数据集验证器的Error文件夹位置说明

## 📋 Error文件夹位置规则

所有验证器都遵循一个统一的规则:
**error文件夹创建在episode所在的父目录下**

```
episode的父目录/
├── episode_1/          # 正常episode
├── episode_2/          # 正常episode
├── episode_3/          # 正常episode
└── error/              # ⭐ error文件夹
    ├── bad_episode_1/  # 移动到这里的有问题的episode
    └── bad_episode_2/  # 移动到这里的有问题的episode
```

---

## 1️⃣ 银河(Yinhe)数据集

### 数据集结构
```
/mnt/nas/synnas/docker/外部数据/银河通用/
├── fold_clothe/                    # 任务
│   ├── device_model_annotation.yaml
│   ├── bianlifeng-10/              # robot_id
│   │   ├── 20250328_record0/       # episode (正常)
│   │   ├── 20250328_record1/       # episode (正常)
│   │   └── error/                  # ⭐ error文件夹
│   │       ├── 20250328_record20/  # 有问题的episode
│   │       └── 20250328_record21/  # 有问题的episode
│   └── bianlifeng-11/              # 另一个robot_id
│       ├── 20250328_record0/
│       └── error/                  # ⭐ 每个robot_id下都有独立的error文件夹
├── steamer_storage_baozi/
│   ├── zhengbaozi-4/
│   │   ├── 20250903_103942_record0/
│   │   └── error/                  # ⭐
│   └── zhengbaozi-5/
│       └── error/                  # ⭐
└── take_snack/
    ├── robot1/
    │   └── error/                  # ⭐
    └── robot2/
        └── error/                  # ⭐
```

### Error文件夹路径
```bash
# 查找所有error文件夹
find /mnt/nas/synnas/docker/外部数据/银河通用 -type d -name "error"

# 示例路径:
/mnt/nas/synnas/docker/外部数据/银河通用/fold_clothe/bianlifeng-10/error/
/mnt/nas/synnas/docker/外部数据/银河通用/fold_clothe/bianlifeng-11/error/
/mnt/nas/synnas/docker/外部数据/银河通用/steamer_storage_baozi/zhengbaozi-4/error/
/mnt/nas/synnas/docker/外部数据/银河通用/take_snack/bianlifeng-10/error/
```

### 查看某个error文件夹内容
```bash
ls -la /mnt/nas/synnas/docker/外部数据/银河通用/steamer_storage_baozi/zhengbaozi-4/error/
```

---

## 2️⃣ 软通天擎(Ruantong)数据集

### 数据集结构
```
/mnt/nas/synnas/docker2/外部数据/软通天擎/
├── ruantong_dataset_1/             # 数据集目录
│   ├── episode_1/                  # episode (正常)
│   ├── episode_2/                  # episode (正常)
│   └── error/                      # ⭐ error文件夹
│       └── episode_3/              # 有问题的episode
└── ruantong_dataset_2/
    ├── episode_1/
    └── error/                      # ⭐
```

### Error文件夹路径
```bash
# 查找所有error文件夹
find /mnt/nas/synnas/docker2/外部数据/软通天擎 -type d -name "error"

# 示例路径:
/mnt/nas/synnas/docker2/外部数据/软通天擎/ruantong_dataset_1/error/
/mnt/nas/synnas/docker2/外部数据/软通天擎/ruantong_dataset_2/error/
```

---

## 3️⃣ 智平方(Zhipingfang)数据集

### 数据集结构
```
(数据集路径)/
├── dataset_1/
│   ├── episode_1.h5
│   ├── episode_2.h5
│   └── error/                      # ⭐
│       └── episode_3.h5
```

---

## 4️⃣ 睿尔曼(Realman)数据集

### 数据集结构
```
/mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条/
├── task_1/                         # 任务目录
│   ├── device_model_annotation.yaml
│   ├── episode_001/                # episode文件夹
│   ├── episode_002/
│   └── error/                      # ⭐ error文件夹
│       └── episode_003/            # 有问题的episode
└── task_2/
    ├── episode_001/
    └── error/                      # ⭐
```

### Error文件夹路径
```bash
# 查找所有error文件夹
find /mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条 -type d -name "error"

# 示例路径:
/mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条/task_1/error/
/mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条/task_2/error/
```

---

## 5️⃣ 星海图(Galaxea)数据集

### 数据集结构
```
/mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train/
├── boil_water/                     # 任务目录
│   ├── device_model_annotation.yaml
│   ├── episode_0000/               # episode
│   ├── episode_0001/
│   └── error/                      # ⭐
│       └── episode_0002/
└── clean_table/
    ├── episode_0000/
    └── error/                      # ⭐
```

### Error文件夹路径
```bash
# 查找所有error文件夹
find /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train -type d -name "error"

# 示例路径:
/mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train/boil_water/error/
/mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train/clean_table/error/
```

---

## 6️⃣ 乐聚(Leju)数据集

### 数据集结构
```
/mnt/nas/synnas/docker2/外部数据/乐聚2/
├── fast_moving/                    # 任务类别
│   └── fast_moving_consumer_goods/ # 具体任务
│       └── FMCG_loading/           # 子任务
│           ├── device_model_annotation.yaml
│           ├── single_FMCG_loading/
│           │   ├── 000e9786-afb8-4f67-b749-ef87f7de0fde/  # episode (UUID)
│           │   ├── 0037ea9c-56ae-4696-a95f-fea312f8d05/   # episode
│           │   └── error/          # ⭐ error文件夹
│           │       └── 0052723d-b732-4991-80bd-fa585af87aa3/  # 有问题的episode
│           └── more_FMCG_loading/
│               ├── 00df9f1a-4607-4d00-8250-b56536323ace/
│               └── error/          # ⭐
```

### Error文件夹路径
```bash
# 查找所有error文件夹
find /mnt/nas/synnas/docker2/外部数据/乐聚2 -type d -name "error"

# 示例路径:
/mnt/nas/synnas/docker2/外部数据/乐聚2/fast_moving/.../FMCG_loading/single_FMCG_loading/error/
/mnt/nas/synnas/docker2/外部数据/乐聚2/fast_moving/.../FMCG_loading/more_FMCG_loading/error/
```

---

## 📝 快速查找命令

### 统计每个数据集的error文件夹数量

```bash
# 1. 银河
echo "银河:" && find /mnt/nas/synnas/docker/外部数据/银河通用 -type d -name "error" | wc -l

# 2. 软通天擎
echo "软通天擎:" && find /mnt/nas/synnas/docker2/外部数据/软通天擎 -type d -name "error" | wc -l

# 3. 睿尔曼
echo "睿尔曼:" && find /mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条 -type d -name "error" | wc -l

# 4. 星海图
echo "星海图:" && find /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train -type d -name "error" | wc -l

# 5. 乐聚
echo "乐聚:" && find /mnt/nas/synnas/docker2/外部数据/乐聚2 -type d -name "error" | wc -l
```

### 统计error文件夹中的episode总数

```bash
# 银河数据集
find /mnt/nas/synnas/docker/外部数据/银河通用 -type d -name "error" -exec sh -c 'echo -n "{}: "; ls -1 "{}" | wc -l' \;

# 或者统计总数
find /mnt/nas/synnas/docker/外部数据/银河通用 -path "*/error/*" -type d -maxdepth 5 | wc -l
```

### 查看特定error文件夹的内容

```bash
# 银河 - 查看steamer_storage_baozi任务的某个robot下的error
ls -la /mnt/nas/synnas/docker/外部数据/银河通用/steamer_storage_baozi/*/error/

# 睿尔曼 - 查看第一个任务的error
ls -la /mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条/*/error/ | head -20

# 星海图 - 查看boil_water任务的error
ls -la /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train/boil_water/error/
```

---

## ⚠️ 重要说明

1. **Error文件夹位置**: 
   - 始终在episode的父目录下
   - 与正常的episodes处于同一层级
   - 便于管理和恢复

2. **配置问题 vs 数据问题**:
   - 如果某个错误在 ≥90% 的episodes中出现 → **配置问题** → 不会移动到error
   - 如果某个错误只在少数episodes中出现 → **数据问题** → 移动到error

3. **查找不到error文件夹的可能原因**:
   - 验证器没有使用 `--move-errors` 参数
   - 所有错误都是配置问题(≥90%错误率),被过滤了
   - 验证器还没有发现任何错误

4. **银河数据集的特殊情况**:
   - 由于之前的10MB限制bug,大量episodes被错误移动到error
   - 需要使用 `restore_yinhe_episodes.py` 脚本恢复

---

## 🔧 如何查看移动了多少episodes

```bash
# 创建统计脚本
cat > count_error_episodes.sh << 'EOF'
#!/bin/bash
echo "统计各数据集error文件夹中的episode数量"
echo "========================================"

# 银河
yinhe_count=$(find /mnt/nas/synnas/docker/外部数据/银河通用 -path "*/error/*" -type d -mindepth 4 2>/dev/null | wc -l)
echo "银河数据集: $yinhe_count episodes"

# 软通天擎
ruantong_count=$(find /mnt/nas/synnas/docker2/外部数据/软通天擎 -path "*/error/*" -type d 2>/dev/null | wc -l)
echo "软通天擎: $ruantong_count episodes"

# 睿尔曼
realman_count=$(find /mnt/nas/synnas/docker2/外部数据/外来睿尔曼2000条 -path "*/error/*" -type d 2>/dev/null | wc -l)
echo "睿尔曼: $realman_count episodes"

# 星海图
galaxea_count=$(find /mnt/nas/synnas/docker/外部数据/星海图外部1.5w/videos/train -path "*/error/*" -type d 2>/dev/null | wc -l)
echo "星海图: $galaxea_count episodes"

# 乐聚
leju_count=$(find /mnt/nas/synnas/docker2/外部数据/乐聚2 -path "*/error/*" -type d 2>/dev/null | wc -l)
echo "乐聚: $leju_count episodes"

echo "========================================"
total=$((yinhe_count + ruantong_count + realman_count + galaxea_count + leju_count))
echo "总计: $total episodes"
EOF

chmod +x count_error_episodes.sh
bash count_error_episodes.sh
```

---

**最后更新**: 2025年1月20日
