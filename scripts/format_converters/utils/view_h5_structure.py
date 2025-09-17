from pathlib import Path

import h5py


def explore_hdf5_group(group, prefix="") -> None:  # noqa: ANN001
    for key in group.keys():
        item = group[key]
        if isinstance(item, h5py.Dataset):
            print(f"{prefix}Dataset: {key} -> Shape: {item.shape}, Dtype: {item.dtype}")
        elif isinstance(item, h5py.Group):
            print(f"{prefix}Group: {key}")
            # 递归进入子组
            explore_hdf5_group(item, prefix + "  ")


def view_hdf5_file(file_path: Path) -> None:
    """
    View the structure of an HDF5 file.
    """
    if not Path(file_path).exists():
        print(f"File {file_path} does not exist.")
        return

    with h5py.File(file_path, "r") as f:
        print(f"HDF5 File Structure for {file_path}:")
        explore_hdf5_group(f)


def main() -> None:
    import argparse

    argparser = argparse.ArgumentParser(description="View HDF5 file structure.")
    argparser.add_argument(
        "file_path",
        type=Path,
        help="Path to the HDF5 file to view",
    )
    args = argparser.parse_args()

    view_hdf5_file(args.file_path)


if __name__ == "__main__":
    main()
