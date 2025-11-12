"""
Mixin class for batch file uploading functionality.

This module provides file-level batching for uploading large datasets
by splitting files into smaller groups and uploading them incrementally.
"""

import logging
from pathlib import Path


class BatchUploadMixin:
    """
    Mixin class that adds file-level batch upload capability.

    This allows uploading large folders by splitting files into smaller batches,
    improving reliability and allowing progress tracking/resumption.
    """

    @staticmethod
    def get_files_to_upload(
        folder_path: Path,
        allow_patterns: list[str],
        ignore_patterns: list[str]
    ) -> list[Path]:
        """
        Get list of files to upload based on allow/ignore patterns.

        Args:
            folder_path: Root folder to scan
            allow_patterns: Glob patterns for files to include
            ignore_patterns: Glob patterns for files to exclude

        Returns:
            List of file paths to upload
        """
        files_to_upload = []

        # Get all files in folder
        all_files = [f for f in folder_path.rglob("*") if f.is_file()]

        # Apply patterns
        for file_path in all_files:
            relative_path = file_path.relative_to(folder_path)
            relative_path_str = str(relative_path)

            # Check ignore patterns first
            should_ignore = False
            if ignore_patterns:
                for pattern in ignore_patterns:
                    if Path(relative_path_str).match(pattern):
                        should_ignore = True
                        break

            if should_ignore:
                continue

            # Check allow patterns
            should_allow = not allow_patterns  # If no allow patterns, allow all
            if allow_patterns:
                for pattern in allow_patterns:
                    if Path(relative_path_str).match(pattern):
                        should_allow = True
                        break

            if should_allow:
                files_to_upload.append(file_path)

        return files_to_upload

    @staticmethod
    def split_into_batches(
        files: list[Path],
        max_batch_size_mb: int = 500,
        max_files_per_batch: int = 1000
    ) -> list[list[Path]]:
        """
        Split files into batches based on size and count limits.

        Args:
            files: List of file paths to batch
            max_batch_size_mb: Maximum size per batch in MB
            max_files_per_batch: Maximum number of files per batch

        Returns:
            List of batches, where each batch is a list of file paths
        """
        batches = []
        current_batch = []
        current_batch_size = 0
        max_batch_size_bytes = max_batch_size_mb * 1024 * 1024

        for file_path in sorted(files):  # Sort for consistent ordering
            try:
                file_size = file_path.stat().st_size
            except Exception:
                # If we can't get size, assume small file
                file_size = 0

            # Check if adding this file would exceed limits
            would_exceed_size = (current_batch_size + file_size) > max_batch_size_bytes
            would_exceed_count = len(current_batch) >= max_files_per_batch

            if current_batch and (would_exceed_size or would_exceed_count):
                # Start new batch
                batches.append(current_batch)
                current_batch = [file_path]
                current_batch_size = file_size
            else:
                # Add to current batch
                current_batch.append(file_path)
                current_batch_size += file_size

        # Add final batch if not empty
        if current_batch:
            batches.append(current_batch)

        return batches

    def upload_repo_batched(
        self,
        folder_path: Path,
        repo_id: str,
        commit_msg: str,
        max_batch_size_mb: int = 500,
        max_files_per_batch: int = 1000,
        allow_patterns: list[str] = None,
        ignore_patterns: list[str] = None,
        logger: logging.Logger = None
    ) -> str:
        """
        Upload a folder in batches for better reliability with large datasets.

        This method:
        1. Scans all files in the folder
        2. Splits them into manageable batches based on size/count
        3. Uploads each batch as a separate commit
        4. Returns the final commit URL

        Args:
            folder_path: Path to folder to upload
            repo_id: Repository identifier (namespace/repo-name)
            commit_msg: Base commit message (batch number will be appended)
            max_batch_size_mb: Maximum size per batch in MB (default: 500)
            max_files_per_batch: Maximum files per batch (default: 1000)
            allow_patterns: Glob patterns for files to include
            ignore_patterns: Glob patterns for files to exclude
            logger: Logger for progress messages

        Returns:
            URL of the final commit

        Raises:
            NotImplementedError: Subclasses must implement this with hub-specific logic
        """
        raise NotImplementedError(
            "Subclasses must implement upload_repo_batched() with hub-specific batch upload logic"
        )

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes as human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"

    @staticmethod
    def calculate_batch_stats(batch: list[Path]) -> tuple[int, int]:
        """
        Calculate statistics for a batch of files.

        Args:
            batch: List of file paths

        Returns:
            Tuple of (file_count, total_size_bytes)
        """
        def get_file_size(file_path: Path) -> int:
            try:
                return file_path.stat().st_size
            except Exception:
                return 0

        total_size = sum(get_file_size(file_path) for file_path in batch)
        return len(batch), total_size
