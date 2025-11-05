import argparse

from robocoin_dataset.dataloader.mk_hard_link import (
    RepoHardLinkCorresp,
    create_hardlinks_from_correspondence,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("src_root", type=str, help="源目录路径")
    parser.add_argument("dst_root", type=str, help="目标目录路径")
    args = parser.parse_args()
    create_hardlinks_from_correspondence(
        args.src_root,
        args.dst_root,
        RepoHardLinkCorresp(),
    )
