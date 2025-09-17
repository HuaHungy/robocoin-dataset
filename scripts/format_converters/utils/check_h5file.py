from pathlib import Path

import h5py


def explore_hdf5_group(group, prefix="") -> None:  # noqa: ANN001
    for key in group.keys():
        item = group[key]
        if isinstance(item, h5py.Dataset):
            pass
        elif isinstance(item, h5py.Group):
            explore_hdf5_group(item, prefix + "  ")


def main() -> None:
    import argparse

    argparser = argparse.ArgumentParser(
        description="Check h5file, if input is a h5file, only check the h5file, if input is a dir, check all h5files in the dir."
    )
    argparser.add_argument(
        "path",
        type=Path,
        help="Path to dir or file to check",
    )
    args = argparser.parse_args()
    path = Path(args.path)
    if not path.exists():
        print(f"{path} does not exist.")
        exit(1)
    if path.is_file():
        try:
            explore_hdf5_group(h5py.File(path, "r"))
            print(f"{path} is a valid h5file.")
        except Exception:
            print(f"{path} is NOT a valid h5file.")
            exit(1)
        exit(0)
    error_h5files = []
    h5_files = list(path.glob("*.h5"))
    h5_files = h5_files + list(path.glob("*.hdf5"))
    print(f"Checking {len(h5_files)} h5files...")
    for file in h5_files:
        try:
            explore_hdf5_group(h5py.File(file, "r"))
        except Exception:  # noqa: PERF203
            error_h5files.append(file)

    if error_h5files:
        print(f"Found {len(error_h5files)} error h5files:")
        for file in error_h5files:
            print(file)
    else:
        print("No error h5files found.")


if __name__ == "__main__":
    main()

"""usage:
# check a single h5file
python scripts/format_converters/utils/check_h5file.py /mnt/nas/synnas/docker/11realman_rmc_aidal/storage_bin_storage/episode_234.hdf5

# check all h5files in a dir (do NOT recursively)
python scripts/format_converters/utils/check_h5file.py /mnt/nas/synnas/docker/11realman_rmc_aidal/storage_bin_storage/

"""
