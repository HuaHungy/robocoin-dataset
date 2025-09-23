from pathlib import Path
from typing import Iterator
import h5py


def explore_hdf5_group(group, prefix="") -> None:  # noqa: ANN001
    for key in group.keys():
        item = group[key]
        if isinstance(item, h5py.Dataset):
            pass
        elif isinstance(item, h5py.Group):
            explore_hdf5_group(item, prefix + "  ")


def iter_h5_files(root_path:Path) ->  Iterator[Path]:
    yield from root_path.rglob("*.h5")
    yield from root_path.rglob("*.hdf5")

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
    if path.is_dir():
        h5_files = list(iter_h5_files(path))
        if not h5_files:
            print(f" No .h5 or .hdf5 files found in {path} (including subdirectories).")
            exit(0)

        print(f" Checking {len(h5_files)} HDF5 file(s)...")
        error_h5files = []

        for file in h5_files:
            try:
                with h5py.File(file, "r") as f:
                    explore_hdf5_group(f)  
            except Exception as e:
                print(f" Failed to read {file}: {e}")
                error_h5files.append(file)

        if error_h5files:
            print(f"\n Found {len(error_h5files)} invalid HDF5 file(s):")
            for file in error_h5files:
                print(f"  - {file}")
            exit(1)
        else:
            print(f"\n  All {len(h5_files)} HDF5 files are valid.")
    else:
        print(f"{path} is neither a file nor a directory.")
        exit(1)


if __name__ == "__main__":
    main()

"""usage:
# check a single h5file
python scripts/format_converters/utils/check_h5file.py /mnt/nas/synnas/docker/11realman_rmc_aidal/storage_bin_storage/episode_234.hdf5

# check all h5files in a dir (do NOT recursively)
python scripts/format_converters/utils/check_h5file.py /mnt/nas/synnas/docker/11realman_rmc_aidal/storage_bin_storage/

"""
