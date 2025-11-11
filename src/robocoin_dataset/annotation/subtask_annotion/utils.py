import base64
import os
import pickle
import re
import subprocess
import tempfile
from pathlib import Path

import av
import imagehash
from PIL import Image

FRAME_SAMPLE_NUM = 10
MAX_SUBTASK_NUM = 5


def get_frame_num(video_path: str) -> int:
    try:
        with av.open(video_path) as container:
            # 查找视频流
            video_stream = next((s for s in container.streams if s.type == "video"), None)
            if not video_stream:
                raise Exception(f"No video stream found in {video_path}")
            return video_stream.frames if video_stream.frames > 0 else -1
    except Exception as e:
        raise Exception("Failed to get frame num") from e


def compute_sha256(filepath: str | Path) -> str:
    """计算文件的 SHA-256 哈希值"""
    import hashlib

    hasher = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        raise e


def gen_frame_indices_from_framenum(frame_num: int) -> list[int]:
    """
    根据视频总帧数和目标采样帧数，生成准均匀分布的帧索引列表。
    保证：对于相同的 (frame_num, sample_num)，返回结果始终一致。

    采用等距采样（首帧固定为 0，末帧包含），并向下取整索引。

    :param frame_num: 视频总帧数（>= 1）
    :param sample_num: 要采样的帧数量（>= 1）
    :return: 准均匀分布的帧索引列表，长度为 min(sample_num, frame_num)
    """
    if frame_num <= 0:
        raise ValueError("frame_num 必须大于 0")
    if FRAME_SAMPLE_NUM <= 0:
        raise ValueError("sample_num 必须大于 0")

    # 实际采样数不能超过总帧数
    actual_sample_num = min(FRAME_SAMPLE_NUM, frame_num)

    if actual_sample_num == 1:
        return [0]  # 单帧时返回第一帧

    if actual_sample_num == frame_num:
        return list(range(frame_num))  # 全部采样

    # 等间距采样：从 0 到 frame_num-1，均匀取 actual_sample_num 个点
    indices = []
    for i in range(actual_sample_num):
        # 线性映射：i / (sample_num - 1) * (frame_num - 1)
        index = int(round(i * (frame_num - 1) / (actual_sample_num - 1)))
        indices.append(index)

    # 去重并保持顺序（理论上不会重复，但 round 可能导致边界重复）
    seen = set()
    unique_indices = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            unique_indices.append(idx)

    # 如果去重后数量不足，补充缺失的帧（比如中间插值或从中间取）
    while len(unique_indices) < actual_sample_num:
        # 简单策略：从中间开始逐个添加未使用的帧
        mid = frame_num // 2
        for offset in range(0, frame_num // 2 + 1):
            candidates = [mid + offset, mid - offset] if offset > 0 else [mid]
            for cand in candidates:
                if 0 <= cand < frame_num and cand not in seen:
                    unique_indices.append(cand)
                    seen.add(cand)
                    break
            if len(unique_indices) >= actual_sample_num:
                break

    # 排序并截断到目标数量
    unique_indices.sort()
    return unique_indices[:actual_sample_num]


def extract_frame_phashes_ffmpeg(
    video_path: str, frame_indices: list[int], hash_size: int = 16
) -> list[imagehash.ImageHash]:
    """
    使用 ffmpeg 从视频中提取指定帧的 pHash（批量抽取，高效稳定）

    Args:
        filepath (str): 视频文件路径
        frame_indices (list[int]): 要提取的帧索引列表（如 [0, 100, 200]）
        hash_size (int): pHash 的尺寸（默认 16，表示 16x16=256 bit）

    Returns:
        List[imagehash.ImageHash]: pHash 列表，对应每个帧，失败为 None
    """
    video_path = Path(video_path)

    # 检查文件是否存在
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    # 如果没有要抽的帧，直接返回
    if not frame_indices:
        return []

    # 创建临时目录保存中间图像
    with tempfile.TemporaryDirectory() as tmpdir:
        output_pattern = os.path.join(tmpdir, "frame_%08d.png")

        # 构建 ffmpeg 的 select 滤镜表达式：eq(n,0)+eq(n,100)+eq(n,200)
        select_expr = "+".join(f"eq(n,{idx})" for idx in frame_indices)
        filter_complex = f"select='{select_expr}'"

        # 构造 ffmpeg 命令
        cmd = [
            "ffmpeg",
            "-i",
            video_path,  # 输入文件
            "-vf",
            filter_complex,  # 只保留指定帧
            "-vsync",  # 最高质量
            "0",  # 覆盖输出
            output_pattern,  # 输出文件命名
        ]

        # 执行命令
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,  # 5 分钟超时
        )

        if result.returncode != 0:
            print(f"❌ ffmpeg 抽帧失败 (退出码 {result.returncode}): {video_path}")
            print(f"错误信息:\n{result.stderr}")
            return [None] * len(frame_indices)

        # 按 frame_indices 顺序加载图像并计算 pHash
        phash_list = []
        # 获取生成的图像文件，按序号排序
        generated_files = sorted(
            [f for f in os.listdir(tmpdir) if f.startswith("frame_")],
            key=lambda x: int(x.split("_")[1].split(".")[0]),
        )

        # 映射：文件名 -> 是否存在
        file_map = {f: True for f in generated_files}

        for idx in range(len(frame_indices)):
            # filename = f"frame_{idx:08d}.png"
            filename = f"frame_{idx + 1:08d}.png"
            img_path = os.path.join(tmpdir, filename)
            if filename in file_map and os.path.exists(img_path):
                try:
                    img = Image.open(img_path)
                    phash = imagehash.phash(img, hash_size=hash_size)
                    phash_list.append(phash)
                except Exception as e:
                    print(f"❌ 处理图像 {filename} 失败: {e}")
                    phash_list.append(None)
            else:
                print(f"⚠️ 未找到帧 {idx} 的图像")
                print(f"视频文件路径: {video_path} ")
                phash_list.append(None)

        return phash_list


def compute_video_hash(video_path: str | Path) -> tuple[str, int, str]:
    video_path = Path(video_path).expanduser().absolute()
    if not video_path.exists():
        raise FileNotFoundError(f"文件不存在: {video_path}")

    file_hash = compute_sha256(video_path)
    frame_num = get_frame_num(video_path=video_path)

    # image_frame_indices = gen_frame_indices_from_framenum(frame_num=frame_num)
    image_frame_indices = [0]
    phashes: list[imagehash.ImageHash] = extract_frame_phashes_ffmpeg(
        video_path=video_path, frame_indices=image_frame_indices
    )
    phash = phashes[0]
    serialized_phash = pickle.dumps(phash)
    serialized_phash = base64.b64encode(serialized_phash).decode("ascii")

    return file_hash, frame_num, serialized_phash


# def sort_video_imagehashes_from_frame_num(
#     video_imagehashes: dict[int, list[imagehash.ImageHash]],
#     frame_num_dict: dict[int, int],
# ) -> dict[int, list[tuple[int, list[imagehash.ImageHash]]]]:
#     result = defaultdict(list)
#     for idx, frame_num in frame_num_dict.items():
#         if idx in video_imagehashes:
#             result[frame_num].append((idx, video_imagehashes[idx]))

#     return dict(result)


def match_video_file_hash(hash: str, file_hash_lib: dict[str, int]) -> int | None:
    if hash in file_hash_lib:
        return file_hash_lib[hash]
    return None


def match_video_image_hash(
    frame_num: int,
    image_phash: imagehash.ImageHash,
    video_image_phashes_lib: dict[int, dict[int, imagehash.ImageHash]],
    win_size: int = 1,
    threashold: float = 0.95,
) -> int | None:
    if frame_num not in video_image_phashes_lib:
        return None

    frame_num_scope = range(frame_num - win_size, frame_num + win_size + 1)

    phashes: dict[int, imagehash.ImageHash] = {}
    for frame_num_in_scope in frame_num_scope:
        if frame_num_in_scope not in video_image_phashes_lib:
            continue
        phashes = phashes | video_image_phashes_lib[frame_num_in_scope]

    min_dist = float("inf")
    matched_id = None
    for url_idx, phash in phashes.items():
        dist = (image_phash - phash) / len(phash)
        if dist < min_dist:
            min_dist = dist
            matched_id = url_idx

    if min_dist > threashold:
        return None

    return matched_id


def get_video_paths(
    repo_path: str | Path,
) -> dict[str, int]:
    repo_path = Path(repo_path).expanduser().absolute()
    if not repo_path.exists():
        raise FileNotFoundError(f"目录不存在: {repo_path}")

    results = {}

    pattern = re.compile(r"^episode_\d{6}\.mp4$")
    for video_path in (repo_path / "videos").rglob("*.mp4"):
        if not pattern.match(video_path.name):
            continue
        ep_idx = int(video_path.with_suffix("").name.split("_")[-1])
        results[video_path] = ep_idx

    return results
