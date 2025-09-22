import av
import imagehash


def get_video_phash_list(
    video_path: str, frame_indices: list[int], hash_size: int = 16
) -> list[imagehash.ImageHash]:
    """
    获取视频中指定帧序号的感知哈希（pHash）值列表

    :param video_path: 视频文件路径
    :param frame_indices: 要提取的帧序号列表（如 [0, 100, 200]）
    :param hash_size: 感知哈希的尺寸（默认 16）
    :return: pHash 对象列表，每个元素可直接用于比较（如 h1 - h2）
    """
    if not frame_indices:
        return []

    # 排序以顺序读取，提高效率
    sorted_indices = sorted(frame_indices)
    target_set = set(frame_indices)

    # 打开视频
    try:
        container = av.open(video_path)
        container.streams.video[0]
    except Exception as e:
        raise RuntimeError(f"无法打开视频文件: {video_path}, 错误: {e}")

    phash_list = []
    current_idx = 0

    try:
        for frame in container.decode(video=0):
            if current_idx in target_set:
                # 转为 PIL 图像并灰度化
                img_rgb = frame.to_image()  # PIL.Image, RGB

                # 计算感知哈希
                phash = imagehash.phash(img_rgb, hash_size=hash_size)
                phash_list.append(phash)

                # 提前退出优化
                if current_idx >= max(frame_indices):
                    break

            current_idx += 1

        container.close()
    except Exception as e:
        container.close()
        raise RuntimeError(f"解码或处理帧时出错: {e}")

    # 保持原始输入顺序
    index_to_phash = {idx: phash for idx, phash in zip(sorted_indices, phash_list)}
    return [index_to_phash[idx] for idx in frame_indices]


def calculate_phash_similarity(
    phash_list1: list[imagehash.ImageHash], phash_list2: list[imagehash.ImageHash]
) -> float:
    """
    计算两个 pHash 列表之间的平均相似度

    :param phash_list1: 第一个视频的 pHash 列表
    :param phash_list2: 第二个视频的 pHash 列表
    :return: 平均相似度 (0.0 ~ 1.0)，1 表示完全相同
    """
    if not phash_list1 or not phash_list2:
        return 0.0

    if len(phash_list1) != len(phash_list2):
        raise ValueError("两个 pHash 列表长度必须相同")

    n = len(phash_list1)
    total_similarity = 0.0

    for h1, h2 in zip(phash_list1, phash_list2):
        # 计算汉明距离（bit 不同的数量）
        distance = h1 - h2
        # 转为相似度：1.0 表示完全相同，0 表示完全不同
        max_distance = h1.hash.size  # hash 是二维布尔数组，size = hash_size ** 2
        similarity = 1.0 - (distance / max_distance)
        total_similarity += similarity

    return total_similarity / n
