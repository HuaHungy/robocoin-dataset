"""
RoboCoin Repository Name Utility
================================

This module provides utilities for sanitizing and normalizing dataset repository names
to comply with Hugging Face Hub requirements. It includes logic for:
- Removing duplicate robot names from repository strings.
- Mapping invalid characters to underscores (while preserving dashes).
- Collapsing multiple consecutive separators.
- Stripping common upload suffixes (_hardlink, _qced_hardlink).
- Renaming local folders to match sanitized names.
"""

import re
from pathlib import Path

import yaml

ROBOT_NAME_SEPARATORS = frozenset({"_", "-", "."})

_ROBOT_NAMES_CONFIG_PATH = (
    Path(__file__).resolve().parent
    / "config"
    / "to_detect_duplication.yml"
)
_ROBOT_NAMES_CACHE: list[str] | None = None


def load_robot_names_from_config() -> list[str]:
    """
    Load the list of robot name identifiers from the shared configuration file.
    """
    global _ROBOT_NAMES_CACHE

    if _ROBOT_NAMES_CACHE is not None:
        return _ROBOT_NAMES_CACHE

    try:
        with open(_ROBOT_NAMES_CONFIG_PATH, encoding="utf-8") as config_file:
            raw_names = yaml.safe_load(config_file)
    except (FileNotFoundError, yaml.YAMLError):
        _ROBOT_NAMES_CACHE = []
        return _ROBOT_NAMES_CACHE

    if isinstance(raw_names, list):
        cleaned_names: list[str] = []
        for entry in raw_names:
            name = str(entry).strip()
            if name:
                cleaned_names.append(name)
        _ROBOT_NAMES_CACHE = cleaned_names
    else:
        _ROBOT_NAMES_CACHE = []

    return _ROBOT_NAMES_CACHE


def sanitize_repo_name(repo_name: str) -> str:
    """
    Sanitize repository name to comply with Hugging Face validation rules:
    - Only alphanumeric chars, '-', '_', or '.' are allowed
    - Cannot start or end with '-' or '.'
    - Maximum length is 96 characters

    Args:
        repo_name: Original repository name

    Returns:
        Sanitized repository name that meets Hugging Face requirements
    """
    if not repo_name:
        return repo_name

    # Replace invalid characters with underscore
    # Keep only alphanumeric, '-', '_', and '.'
    sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', repo_name)

    # Remove leading/trailing '-' and '.'
    sanitized = sanitized.strip('-.')

    # Collapse multiple consecutive separators
    # Note: User requested NOT to map '-' to '_' automatically.
    # We collapse consecutive dots, underscores, and dashes individually.
    sanitized = re.sub(r'\.+', '.', sanitized)
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = re.sub(r'-+', '-', sanitized)

    # Remove leading/trailing separators again after collapsing
    sanitized = sanitized.strip('-.')

    # Truncate to maximum length of 96 characters
    if len(sanitized) > 96:
        sanitized = sanitized[:96].rstrip('-.')

    # Ensure we don't end up with an empty string
    if not sanitized:
        sanitized = "dataset"

    return sanitized


def locate_duplicate_start(repo_name: str, duplicate_start: int) -> int:
    """
    Walk backwards to remove surrounding separators before the duplicate entry.
    """
    start = duplicate_start
    while start > 0 and repo_name[start - 1] in ROBOT_NAME_SEPARATORS:
        start -= 1
    return start


def remove_duplicate_robot_names(
    repo_name: str,
    robot_names: list[str],
) -> str:
    """
    Ensure each robot name appears at most once in the repository name.
    """
    if not robot_names:
        return repo_name

    sanitized = repo_name
    for robot_name in robot_names:
        if not robot_name:
            continue

        first_index = sanitized.find(robot_name)
        if first_index == -1:
            continue

        search_start = first_index + len(robot_name)
        while True:
            duplicate_index = sanitized.find(robot_name, search_start)
            if duplicate_index == -1:
                break

            remove_start = locate_duplicate_start(sanitized, duplicate_index)
            sanitized = (
                sanitized[:remove_start]
                + sanitized[duplicate_index + len(robot_name) :]
            )
            search_start = remove_start

    return sanitized


def process_repo_name(folder_name: str) -> str:
    """
    Normalize a folder name into a valid repository name by stripping upload suffixes,
    removing duplicate robot names, and sanitizing invalid characters.

    Args:
        folder_name: Original folder name (may contain suffixes and invalid chars)

    Returns:
        Sanitized repository name that meets Hugging Face requirements
    """
    # Remove common suffixes
    dataset_name = folder_name.removesuffix("_qced_hardlink").removesuffix("_hardlink")

    # Remove duplicate robot names
    robot_names = load_robot_names_from_config()
    normalized_name = remove_duplicate_robot_names(dataset_name, robot_names)

    # Sanitize invalid characters
    return sanitize_repo_name(normalized_name)


def process_folder_name(folder_name: str) -> str:
    """
    Sanitize a folder name while preserving its suffix (_hardlink or _qced_hardlink).
    """
    suffix = ""
    if folder_name.endswith("_qced_hardlink"):
        suffix = "_qced_hardlink"
    elif folder_name.endswith("_hardlink"):
        suffix = "_hardlink"

    # process_repo_name already removes these suffixes, so we can just call it
    # and then add the suffix back.
    processed_base = process_repo_name(folder_name)
    return processed_base + suffix


def rename_folder(folder_path: str | Path) -> str:
    """
    Rename a folder at the given path to its sanitized version.
    Returns the new name of the folder.

    Args:
        folder_path: Path to the folder to rename.

    Returns:
        The new name of the folder (sanitized).
    """
    path = Path(folder_path).resolve()
    if not path.is_dir():
        return path.name

    old_name = path.name
    new_name = process_folder_name(old_name)

    if old_name != new_name:
        new_path = path.parent / new_name
        if new_path.exists():
            raise FileExistsError(f"Cannot rename {path} to {new_path}: destination already exists.")
        path.rename(new_path)
        return new_name

    return old_name
