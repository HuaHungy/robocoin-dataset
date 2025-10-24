"""
JSON文件缓存工具
用于缓存已解析的JSON数据，避免重复读取和解析
"""

import json
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Any


class JsonFileCache:
    """JSON文件缓存
    
    使用LRU策略缓存JSON文件的解析结果，避免重复读取和解析相同的文件
    """
    
    def __init__(self, max_cache_size: int = 1000, logger: logging.Logger | None = None):
        """初始化缓存
        
        Args:
            max_cache_size: 最大缓存数量（默认1000个文件）
            logger: 日志记录器
        """
        self.max_cache_size = max_cache_size
        self.logger = logger
        self._cache: OrderedDict[Path, Any] = OrderedDict()
        self._hits = 0
        self._misses = 0
    
    def load(self, json_path: Path) -> Any:
        """加载JSON文件（带缓存）
        
        Args:
            json_path: JSON文件路径
            
        Returns:
            解析后的JSON数据
        """
        # 检查缓存
        if json_path in self._cache:
            # 缓存命中：移动到末尾（最近使用）
            self._cache.move_to_end(json_path)
            self._hits += 1
            return self._cache[json_path]
        
        # 缓存未命中：读取并解析
        self._misses += 1
        with open(json_path) as f:
            data = json.load(f)
        
        # 添加到缓存
        self._cache[json_path] = data
        self._cache.move_to_end(json_path)
        
        # 检查缓存大小限制
        if len(self._cache) > self.max_cache_size:
            # 移除最早的条目（LRU策略）
            removed_path = next(iter(self._cache))
            del self._cache[removed_path]
        
        return data
    
    def load_batch(self, json_paths: list[Path]) -> list[Any]:
        """批量加载JSON文件
        
        Args:
            json_paths: JSON文件路径列表
            
        Returns:
            解析后的JSON数据列表
        """
        return [self.load(path) for path in json_paths]
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    def get_stats(self) -> dict:
        """获取缓存统计信息
        
        Returns:
            包含缓存命中率等信息的字典
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'cache_size': len(self._cache),
            'max_cache_size': self.max_cache_size,
            'hits': self._hits,
            'misses': self._misses,
            'total_requests': total_requests,
            'hit_rate_percent': round(hit_rate, 2),
        }
    
    def log_stats(self):
        """输出缓存统计信息到日志"""
        if self.logger:
            stats = self.get_stats()
            self.logger.info(
                f"📊 JSON Cache Stats:\n"
                f"   - Cache size: {stats['cache_size']}/{stats['max_cache_size']}\n"
                f"   - Hits: {stats['hits']}\n"
                f"   - Misses: {stats['misses']}\n"
                f"   - Hit rate: {stats['hit_rate_percent']}%"
            )
    
    def __len__(self):
        """返回当前缓存的条目数"""
        return len(self._cache)
    
    def __contains__(self, json_path: Path):
        """检查文件是否在缓存中"""
        return json_path in self._cache

