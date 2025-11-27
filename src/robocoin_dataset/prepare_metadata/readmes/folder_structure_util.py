from pathlib import Path


def generate_folder_structure(root_path: Path, max_files_per_dir: int = 5) -> str:
    """
    Generate a folder structure tree showing only leaf directories with limited files.

    This function traverses the directory tree and creates a visual representation where:
    - Only the deepest leaf directories are expanded
    - Each leaf directory shows at most max_files_per_dir files
    - Remaining files are represented as "(...)"

    Args:
        root_path: Root directory path to generate structure from.
        max_files_per_dir: Maximum number of files to show per leaf directory. Defaults to 5.

    Returns:
        str: Formatted folder structure tree as a string.
    """

    def is_leaf_directory(path: Path) -> bool:
        """Check if a directory is a leaf (contains no subdirectories)."""
        try:
            return not any(item.is_dir() for item in path.iterdir())
        except (PermissionError, OSError):
            return True

    def get_sorted_items(path: Path) -> tuple[list[Path], list[Path]]:
        """Get sorted directories and files from a path."""
        try:
            items = list(path.iterdir())
            dirs = sorted([item for item in items if item.is_dir()], key=lambda x: x.name)
            files = sorted([item for item in items if item.is_file()], key=lambda x: x.name)
            return dirs, files
        except (PermissionError, OSError):
            return [], []

    def build_tree(path: Path, prefix: str = "", is_last: bool = True) -> list[str]:
        """Recursively build the tree structure."""
        lines: list[str] = []

        if not path.exists():
            return lines

        # Add current directory
        connector = "└── " if is_last else "├── "
        if path == root_path:
            lines.append(f"{path.name}/")
        else:
            lines.append(f"{prefix}{connector}{path.name}/")

        # Get subdirectories and files
        dirs, files = get_sorted_items(path)

        # Determine the new prefix for children
        if path == root_path:
            new_prefix = ""
        else:
            new_prefix = prefix + ("    " if is_last else "│   ")

        # Check if this is a leaf directory
        if is_leaf_directory(path) and files:
            # Show only first max_files_per_dir files
            files_to_show = files[:max_files_per_dir]
            has_more = len(files) > max_files_per_dir

            for i, file in enumerate(files_to_show):
                is_last_file = (i == len(files_to_show) - 1) and not has_more
                file_connector = "└── " if is_last_file else "├── "
                lines.append(f"{new_prefix}{file_connector}{file.name}")

            if has_more:
                lines.append(f"{new_prefix}└── (...)")

        # Process subdirectories (but don't show their files unless they're leaf directories)
        for i, subdir in enumerate(dirs):
            is_last_dir = i == len(dirs) - 1
            lines.extend(build_tree(subdir, new_prefix, is_last_dir))

        return lines

    try:
        tree_lines = build_tree(root_path)
        return "\n".join(tree_lines)
    except Exception as e:  # pragma: no cover - defensive
        return f"Error generating folder structure: {e}"
