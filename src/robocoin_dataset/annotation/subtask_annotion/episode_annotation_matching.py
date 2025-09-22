import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import tempfile
from pathlib import Path

import av
import cv2
import imagehash
import requests
from PIL import Image
from tqdm import tqdm

SUBTASK_ANNOTATION_DIR = "local_annotations/subtask_annotations"

SUBTASK_ANNOTATION_DOWNLOAD_VIDEO_DIR = f"{SUBTASK_ANNOTATION_DIR}/.download_videos"

SUBTASK_ANNOTATION_MATCH_FILE_PATH = ".subtask_annotation_match.json"

VIDEO_URL_DLPATH_MAP_FILE_PATH = "video_url_to_dlpath.json"


def download_video(video_url: str, downloaded_file: str) -> None:
    # 1. 创建输出目录
    if not Path(downloaded_file).exists():
        # 2. 创建输出目录
        Path(downloaded_file).parent.mkdir(parents=True, exist_ok=True)

        response = requests.get(video_url, stream=True, timeout=30)
        response.raise_for_status()

        try:
            with open(downloaded_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as e:
            raise RuntimeError(f"下载失败: {video_url}, 错误: {e}")


def compute_file_hash(filepath: str) -> str:
    """计算文件的 SHA-256 哈希值"""
    hasher = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"无法读取文件 {filepath}: {e}")
        return None


def match_videos_by_file_hash(set_a: set[str], set_b: set[str]) -> dict[str, str]:
    """
    根据文件内容的 SHA-256 哈希值，匹配两组视频文件中完全相同的文件。

    Args:
        seta (set[str]): 第一组视频文件路径的集合
        setb (set[str]): 第二组视频文件路径的集合

    Returns:
        dict[str, str]: 匹配结果，键为 seta 中的路径，值为 setb 中匹配的路径
    """

    # 步骤1: 构建 seta 中文件的 哈希 -> 路径 映射
    hash_to_a = {}
    for path in tqdm(set_a, desc="处理 A 组视频文件", unit="file"):
        if not os.path.isfile(path):
            print(f"跳过不存在的文件 (seta): {path}")
            continue
        file_hash = compute_file_hash(path)
        if file_hash:
            # 如果多个文件哈希相同，保留一个即可（集合本应无重复）
            hash_to_a[file_hash] = path

    # 步骤2: 遍历 setb，查找匹配项
    matches = {}  # path_in_seta -> path_in_setb
    for path in tqdm(set_b, desc="处理 A 组视频文件", unit="file"):
        if not os.path.isfile(path):
            print(f"跳过不存在的文件 (setb): {path}")
            continue
        file_hash = compute_file_hash(path)
        if file_hash in hash_to_a:
            path_a = hash_to_a[file_hash]
            matches[path_a] = path  # seta 中的路径作为键，setb 中的路径作为值

    print(f"哈希匹配完成: 找到 {len(matches)} 对完全相同的视频文件。")
    return matches


def get_frame_count(filepath: str) -> int:
    try:
        with av.open(filepath) as container:
            # 查找视频流
            video_stream = next((s for s in container.streams if s.type == "video"), None)
            if not video_stream:
                return -1
            return video_stream.frames if video_stream.frames > 0 else -1
    except Exception:
        return -1


def extract_phash_from_frame(
    cap: cv2.VideoCapture, frame_idx: int, hash_size: int = 16
) -> imagehash.ImageHash:
    """从指定帧提取 pHash"""
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        return None
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    return imagehash.phash(pil_img, hash_size=hash_size)


def gen_random_frame_indices(total_frames: int, n_samples: int) -> list[int]:
    """生成随机帧序号列表"""
    if n_samples > total_frames:
        return range(total_frames)
    return random.sample(range(total_frames), n_samples)


def extract_frame_phashes(
    filepath: str, frame_indices: list[int], hash_size: int = 16
) -> list[imagehash.ImageHash]:
    """从指定帧提取 pHash"""
    cap = cv2.VideoCapture(filepath)
    try:
        return [extract_phash_from_frame(cap, idx, hash_size) for idx in frame_indices]
    except Exception as e:
        raise (f"无法读取文件 {filepath}") from e


def extract_frame_phashes_ffmpeg(
    filepath: str, frame_indices: list[int], hash_size: int = 16
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
    # 检查文件是否存在
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"视频文件不存在: {filepath}")

    # 如果没有要抽的帧，直接返回
    if not frame_indices:
        return []

    # 创建临时目录保存中间图像
    with tempfile.TemporaryDirectory() as tmpdir:
        output_pattern = os.path.join(tmpdir, "frame_%08d.png")
        print(output_pattern)

        # 构建 ffmpeg 的 select 滤镜表达式：eq(n,0)+eq(n,100)+eq(n,200)
        select_expr = "+".join(f"eq(n,{idx})" for idx in frame_indices)
        filter_complex = f"select='{select_expr}'"

        # 构造 ffmpeg 命令
        cmd = [
            "ffmpeg",
            "-i",
            filepath,  # 输入文件
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
            print(f"❌ ffmpeg 抽帧失败 (退出码 {result.returncode}): {filepath}")
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
                print(f"视频文件路径: {filepath} ")
                input("press enter to continue")
                phash_list.append(None)

        return phash_list


def group_videos_by_frame_count(
    set_a: set[str], set_b: set[str]
) -> dict[int, tuple[set[str], set[str]]]:
    """
    根据视频帧数对 A 组和 B 组的视频进行分组。

    Args:
        set_a (set[str]): 第一组视频文件路径集合
        set_b (set[str]): 第二组视频文件路径集合

    Returns:
        dict[int, tuple[set[str], set[str]]]:
            键: 视频帧数（int）
            值: (A组中该帧数的视频集合, B组中该帧数的视频集合)
            如果某组中没有对应帧数的视频，则集合为空 set()
    """

    # 存储分组结果：帧数 -> (set_a_paths, set_b_paths)
    grouped: dict[int, tuple[set[str], set[str]]] = {}

    # 处理 set_a 中的视频
    for path in set_a:
        if not os.path.isfile(path):
            print(f"跳过不存在的文件 (A): {path}")
            continue
        frame_num = get_frame_count(path)
        if frame_num <= 0:
            continue
        if frame_num not in grouped:
            grouped[frame_num] = (set(), set())
        a_set, b_set = grouped[frame_num]
        a_set.add(path)
        grouped[frame_num] = (a_set, b_set)

    # 处理 set_b 中的视频
    for path in set_b:
        if not os.path.isfile(path):
            print(f"跳过不存在的文件 (B): {path}")
            continue
        frame_num = get_frame_count(path)
        if frame_num < 0:
            continue
        if frame_num not in grouped:
            grouped[frame_num] = (set(), set())
        a_set, b_set = grouped[frame_num]
        b_set.add(path)
        grouped[frame_num] = (a_set, b_set)

    print(f"帧数分组完成：共发现 {len(grouped)} 个不同的帧数组。")
    if -1 in grouped:
        print(f"帧数分组结果中包含 -1 帧数，请检查视频文件: {grouped[-1]}")
    return grouped


def match_videos_by_image_phash(
    grouped_videos: dict[int, tuple[set[str], set[str]]],
    n_samples: int = 10,
    hash_size: int = 16,
    min_similarity: float = 0.95,  # 至少95%相似
) -> dict[str, str]:
    """
    使用pHash相似度进行视频内容匹配
    """
    matches = {}
    matched_b_paths = set()
    items = grouped_videos.items()

    for frame_count, (set_a, set_b) in tqdm(items, desc="匹配视频组", unit="group"):
        if not set_a or not set_b:
            continue

        print(f"处理 {frame_count} 帧组: A组{len(set_a)}个, B组{len(set_b)}个")
        sample_indices = gen_random_frame_indices(frame_count, n_samples)
        # print(f"sample_frames_num is {len(sample_indices)}")

        # 提取哈希
        # a_hashes = {p: extract_frame_phashes(p, sample_indices, hash_size) for p in set_a}
        # b_hashes = {p: extract_frame_phashes(p, sample_indices, hash_size) for p in set_b}

        a_hashes = {p: extract_frame_phashes_ffmpeg(p, sample_indices, hash_size) for p in set_a}
        b_hashes = {p: extract_frame_phashes_ffmpeg(p, sample_indices, hash_size) for p in set_b}

        # 匹配
        for path_a, hashes_a in a_hashes.items():
            best_match = None
            best_avg_sim = 0.0

            for path_b, hashes_b in b_hashes.items():
                if path_b in matched_b_paths:
                    continue

                similarities = []
                for h_a, h_b in zip(hashes_a, hashes_b):
                    dist = h_a - h_b
                    max_dist = h_a.hash.size  # = hash_size ** 2
                    sim = 1.0 - (dist / max_dist)
                    similarities.append(sim)

                avg_sim = sum(similarities) / len(similarities)

                if avg_sim > best_avg_sim and avg_sim >= min_similarity:
                    best_avg_sim = avg_sim
                    best_match = path_b

            if best_match:
                matches[path_a] = best_match
                matched_b_paths.add(best_match)
                print(
                    f"  匹配: {os.path.basename(path_a)} -> {os.path.basename(best_match)} "
                    f"(平均相似度: {best_avg_sim:.3f})"
                )

    print(f"pHash匹配完成: 找到 {len(matches)} 对")
    return matches


def read_episodes_jsonl(file_path: str) -> list[dict]:
    """读取 JSONL 文件，返回字典列表"""
    data = []
    try:
        with open(file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:  # 跳过空行
                    continue
                try:
                    record = json.loads(line)
                    data.append(record)
                except json.JSONDecodeError as e:
                    print(f"第 {line_num} 行 JSON 解析错误: {e}")
        print(f"成功读取 {len(data)} 条记录")
        return data
    except Exception as e:
        raise (f"无法读取文件 {file_path}") from e


def load_episode_annotations(root_dir: str) -> list[dict]:
    subtask_annotation_dir = Path(root_dir) / SUBTASK_ANNOTATION_DIR

    episode_annotations = []
    for file in subtask_annotation_dir.glob("*.json"):
        with open(file) as f:
            annotations = json.load(f)
            episode_annotations.extend(annotations)

    return episode_annotations


def gen_videourl_annotation_idx_dict(episode_annotations: list[dict]) -> dict[str, int]:
    res = {}

    for annotation_idx in range(len(episode_annotations)):
        if "video" not in episode_annotations[annotation_idx]:
            raise ValueError(f"{episode_annotations[annotation_idx]} 中没有 video 字段")
        http_video_url = episode_annotations[annotation_idx]["video"]
        # download_video_file_name = url_to_filename_ascii_letters_and_dot(http_video_url)
        res[http_video_url] = annotation_idx
    return res


def gen_dlpath_videourl_dict(episode_annotations: list[dict], dl_root_dir: Path) -> dict[Path, str]:
    url_dlpath_dict = {}
    map_file_path = Path(dl_root_dir) / VIDEO_URL_DLPATH_MAP_FILE_PATH
    try:
        with open(map_file_path) as f:
            url_dlpath_dict = json.load(f)
    except Exception:
        url_dlpath_dict = {}

    mapped_num = len(url_dlpath_dict)

    for annotation_idx in range(len(episode_annotations)):
        if "video" not in episode_annotations[annotation_idx]:
            raise ValueError(f"{episode_annotations[annotation_idx]} 中没有 video 字段")
        http_video_url = episode_annotations[annotation_idx]["video"]
        if http_video_url not in url_dlpath_dict.values():
            dlfile_name = f"{mapped_num}.mp4"
            dlpath = dl_root_dir / dlfile_name
            url_dlpath_dict[str(dlpath)] = str(http_video_url)
            mapped_num += 1

    map_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(map_file_path, "w") as f:
        json.dump(url_dlpath_dict, f)
    return url_dlpath_dict


def load_episodes(root_dir: str) -> list[dict]:
    episodes_jsonl_path = Path(root_dir) / "meta" / "episodes.jsonl"
    return read_episodes_jsonl(episodes_jsonl_path)


def find_episode_videos(root_dir: str, accepted_labels: list[str] = ["high", "head"]) -> list[Path]:
    videos_dir = Path(root_dir) / "videos"
    sub_dirs = list(videos_dir.iterdir())
    chunk_dir_patter = re.compile(r"^chunk-\d{3}$")

    matched_videos = []
    video_file_pattern = re.compile(r"^episode_\d{6}\.mp4$")
    for sub_dir in sub_dirs:
        if chunk_dir_patter.match(sub_dir.name):
            for image_dir in sub_dir.iterdir():
                if image_dir.is_dir():
                    if any(label in image_dir.name for label in accepted_labels):
                        for file in image_dir.rglob("*.mp4"):
                            if video_file_pattern.match(file.name):
                                matched_videos.append(file)
    for videos_path_for_label in videos_dir.iterdir():
        if videos_path_for_label.is_file():
            continue
        if any(label in videos_path_for_label.name for label in accepted_labels):
            matched_videos.extend(
                file
                for file in videos_path_for_label.rglob("*.mp4")
                if video_file_pattern.match(file.name)
            )

    if not matched_videos:
        raise ValueError(f"{videos_dir} 中没有符合要求的文件")

    return sorted(matched_videos)


def gen_video_episode_idx_dict(video_list: list[Path]) -> dict[Path, int]:
    res = {}
    for idx in range(len(video_list)):
        video_file_path = video_list[idx]
        res[video_file_path] = idx
    return res


def download_annotation_videos(dlpath_vidoe_url_dict: dict[str, str]) -> None:
    """下载视频"""
    download_failed_videos = []
    items = list(dlpath_vidoe_url_dict.items())
    for dl_path, url in tqdm(items, desc="下载视频", unit="video"):
        try:
            # 确保目录存在
            Path(dl_path).parent.mkdir(parents=True, exist_ok=True)
            download_video(url, dl_path)
        except Exception as e:  # noqa: PERF203
            # 捕获具体异常信息（可选）
            print(f"下载失败: {dl_path} -> {e}")
            tqdm.write(f"下载失败: {url} -> {e}")  # 使用 tqdm.write 避免打乱进度条
            download_failed_videos.append(url)

    if download_failed_videos:
        raise ValueError(f"下载视频失败: {download_failed_videos}")


def match_epivideo_and_annotation(
    ep_video_paths: list[Path], annotation_list: list[dict], video_download_dir: Path
) -> dict[int, dict]:
    video_epidx_dict = gen_video_episode_idx_dict(ep_video_paths)
    httpvideo_annoidx_dict = gen_videourl_annotation_idx_dict(annotation_list)
    anno_dlpath_videourl_dict: dict = gen_dlpath_videourl_dict(
        annotation_list, dl_root_dir=Path(video_download_dir)
    )

    download_annotation_videos(anno_dlpath_videourl_dict)

    ep_videos = video_epidx_dict.keys()
    anno_dl_videos = anno_dlpath_videourl_dict.keys()

    # file_hash_matches = match_videos_by_file_hash(ep_videos, anno_dl_videos)
    file_hash_matches = {}

    av.logging.set_level(av.logging.ERROR)
    groupped_res = group_videos_by_frame_count(set(ep_videos), set(anno_dl_videos))
    # input(f"Found {len(groupped_res)} groups, press enter to continue")
    image_phash_matches = match_videos_by_image_phash(grouped_videos=groupped_res)
    input("image_phash_matches, press enter to continue")

    matches = file_hash_matches | image_phash_matches
    unmatched_videos = []
    unmatched_msg = "\n"
    for video in ep_video_paths:
        if video not in matches:
            unmatched_videos.append(video)
            unmatched_msg += f"视频 {video} 未匹配到任何视频\n"

    if unmatched_videos:
        raise ValueError(unmatched_msg)

    res = {}
    for ep_idx in range(len(ep_video_paths)):
        anno_dlvideo_path = matches[ep_video_paths[ep_idx]]
        anno_httpvideo_url = anno_dlpath_videourl_dict[anno_dlvideo_path]
        anno_idx = httpvideo_annoidx_dict[anno_httpvideo_url]
        annotation = annotation_list[anno_idx]
        res[ep_idx] = annotation

    return res


def try_match_epidx_and_videoidx(rootdir: str) -> dict[int, dict]:
    match_file_path = Path(rootdir) / SUBTASK_ANNOTATION_MATCH_FILE_PATH
    annotation_videos_download_dir = Path(rootdir) / SUBTASK_ANNOTATION_DOWNLOAD_VIDEO_DIR
    try:
        with open(match_file_path) as f:
            return json.load(f)
    except Exception:
        episode_videos = find_episode_videos(rootdir)
        episode_annotations = load_episode_annotations(rootdir)
        match_res = match_epivideo_and_annotation(
            episode_videos, episode_annotations, annotation_videos_download_dir
        )

        with open(match_file_path, "w") as f:
            json.dump(match_res, f)
            return match_res


# --- 使用示例 ---

if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument("root_dir", help="数据集根目录")
    args = argparser.parse_args()

    import traceback

    try:
        matched_pairs = try_match_epidx_and_videoidx(args.root_dir)
    except Exception as e:
        print(f"匹配失败: {traceback(e)}")
        exit(1)

    print(f"Found {len(matched_pairs)} matched pairs")
