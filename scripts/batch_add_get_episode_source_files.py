#!/usr/bin/env python3
"""批量为converters添加_get_episode_source_files()方法"""

from pathlib import Path

# 定义每个converter的实现
IMPLEMENTATIONS = {
    "lerobot_format_converter_mcap.py": '''    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 MCAP episode 的源文件信息"""
        try:
            mcap_files = self._get_all_mcap_files(task_path)
            if ep_idx < len(mcap_files):
                mcap_file = mcap_files[ep_idx]
                return {
                    "format": "MCAP",
                    "mcap_file": str(mcap_file.relative_to(self.dataset_path)),
                    "absolute_path": str(mcap_file.absolute()),
                }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        return {}
''',
    
    "lerobot_format_converter_rosbag.py": '''    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 ROS bag episode 的源文件信息"""
        try:
            episode_dir = self._get_episode_directory(task_path, ep_idx)
            return {
                "format": "ROSBAG",
                "episode_directory": str(episode_dir.relative_to(self.dataset_path)),
                "absolute_path": str(episode_dir.absolute()),
            }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        return {}
''',
    
    "lerobot_format_converter_mmk2.py": '''    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 MMK2 episode 的源文件信息"""
        try:
            episode_dir = self._get_episode_directory(task_path, ep_idx)
            return {
                "format": "MMK2",
                "episode_directory": str(episode_dir.relative_to(self.dataset_path)),
                "absolute_path": str(episode_dir.absolute()),
            }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        return {}
''',
    
    "lerobot_format_converter_leju_waibu.py": '''    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 Leju Waibu episode 的源文件信息"""
        # task_path在Leju Waibu中直接是episode目录
        return {
            "format": "LEJU_WAIBU",
            "episode_directory": str(task_path.relative_to(self.dataset_path)),
            "absolute_path": str(task_path.absolute()),
            "metadata_file": "metadata.json",
            "h5_file": "proprio_stats/proprio_stats.hdf5",
        }
''',
    
    "lerobot_format_converter_lerobot.py": '''    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 LeRobot episode 的源文件信息"""
        return {
            "format": "LEROBOT",
            "note": "Already in LeRobot format, no source conversion needed",
            "dataset_path": str(self.dataset_path.absolute()),
        }
''',
    
    "lerobot_format_converter_g1.py": '''    
    def _get_episode_source_files(self, task_path: Path, ep_idx: int) -> dict:
        """获取 G1 episode 的源文件信息"""
        try:
            episode_dir = self._get_episode_directory(task_path, ep_idx)
            return {
                "format": "G1",
                "episode_directory": str(episode_dir.relative_to(self.dataset_path)),
                "absolute_path": str(episode_dir.absolute()),
            }
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to get source files for episode {ep_idx}: {e}")
        return {}
''',
}

def main():
    converter_dir = Path(__file__).parent.parent / "src" / "robocoin_dataset" / "format_converter" / "tolerobot"
    
    for filename, implementation in IMPLEMENTATIONS.items():
        converter_file = converter_dir / filename
        if not converter_file.exists():
            print(f"⚠️ File not found: {converter_file}")
            continue
        
        # 读取文件内容
        content = converter_file.read_text(encoding='utf-8')
        
        # 检查是否已经有此方法
        if "_get_episode_source_files" in content:
            print(f"✓ {filename} already has _get_episode_source_files()")
            continue
        
        # 在文件末尾添加方法
        new_content = content.rstrip() + "\n" + implementation + "\n"
        
        # 写回文件
        converter_file.write_text(new_content, encoding='utf-8')
        print(f"✅ Added _get_episode_source_files() to {filename}")

if __name__ == "__main__":
    main()

