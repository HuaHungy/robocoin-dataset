"""Validation utilities for hardlink structures.

Simplified validation: checks if hardlink structure exists with expected files.
"""

# from pathlib import Path

# from robocoin_dataset..make_hardlink import HardLinkCorresp


# def validate_hardlink(
#     src_root: str | Path,
#     dst_root: str | Path,
#     hard_link_corresp: HardLinkCorresp,
# ) -> bool:
#     """Validate hardlink structure exists with expected files.

#     Returns:
#         True if hardlink structure exists with expected files, False otherwise
#     """
#     src_root = Path(src_root)
#     dst_root = Path(dst_root)

#     # Check if directories exist
#     if not src_root.exists() or not dst_root.exists():
#         return False

#     # Validate file correspondence - just check if destination files exist
#     for dst_rel in hard_link_corresp.file_corresp.values():
#         dst_file = dst_root / dst_rel

#         if not dst_file.exists() or not dst_file.is_file():
#             return False

#     # Validate directory correspondence (sampling approach)
#     if hard_link_corresp.dir_corresp:
#         for src_prefix, dst_prefix in hard_link_corresp.dir_corresp.items():
#             # Ensure directory format
#             src_prefix = src_prefix.rstrip("/") + "/"
#             dst_prefix = dst_prefix.rstrip("/") + "/"

#             # Check if any files exist in source directory
#             src_dir = src_root / src_prefix.rstrip("/")
#             if not src_dir.exists():
#                 continue

#             # Validate at least one file exists in destination directory
#             dst_dir = dst_root / dst_prefix.rstrip("/")
#             if not dst_dir.exists():
#                 return False

#             # Check if at least one corresponding file exists
#             found_files = False
#             for src_file in src_dir.rglob("*"):
#                 if not src_file.is_file() or src_file.is_symlink():
#                     continue

#                 found_files = True
#                 rel_str = src_file.relative_to(src_root).as_posix()
#                 if rel_str.startswith(src_prefix):
#                     dst_rel = dst_prefix + rel_str[len(src_prefix):]
#                     dst_file = dst_root / dst_rel

#                     if not dst_file.exists() or not dst_file.is_file():
#                         return False
#                     # Only check first file from each directory for efficiency
#                     break

#             if found_files and not dst_dir.exists():
#                 return False

#     return True
