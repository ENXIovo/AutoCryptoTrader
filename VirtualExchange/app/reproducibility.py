"""
Reproducibility Info - 单职责：收集复现信息
data_hash, strategy_config, engine_version
统一使用UTC时区
"""
import logging
import json
import hashlib
import subprocess
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ReproducibilityInfo:
    """
    复现信息收集器
    """
    
    @staticmethod
    def collect(
        data_files: List[Path],  # 本次使用的parquet文件列表
        strategy_config: Dict[str, Any],  # run()的参数
        fee_rate: float,
        repo_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        收集复现信息
        
        Args:
            data_files: 数据文件列表
            strategy_config: 策略配置参数
            fee_rate: 手续费率
            repo_path: 仓库路径（默认从当前文件推断）
            
        Returns:
            复现信息字典
        """
        # Data hash
        data_hash = ReproducibilityInfo._hash_data_files(data_files)
        
        # Strategy config（直接dump参数）
        strategy_config_snapshot = json.dumps(strategy_config, sort_keys=True, default=str)
        
        # Engine version
        if repo_path is None:
            # 从当前文件推断repo路径（向上3级到项目根）
            repo_path = Path(__file__).parent.parent.parent
        
        engine_version = ReproducibilityInfo._get_git_version(repo_path)
        
        return {
            "data_hash": data_hash,
            "strategy_config": strategy_config_snapshot,
            "engine_version": engine_version,
            "fee_rate": fee_rate,
            "slippage_model": "market: fill_price - bar_close, limit: 0",
            "data_file_count": len(data_files)
        }
    
    @staticmethod
    def _hash_data_files(files: List[Path]) -> str:
        """
        计算数据文件hash（路径+mtime+size）
        
        Args:
            files: 文件路径列表
            
        Returns:
            hash字符串（16位）
        """
        h = hashlib.sha256()
        for f in sorted(files):
            try:
                stat = f.stat()
                h.update(f"{f}:{stat.st_mtime}:{stat.st_size}".encode())
            except Exception as e:
                logger.warning(f"[ReproducibilityInfo] Failed to stat {f}: {e}")
                h.update(str(f).encode())
        return h.hexdigest()[:16]
    
    @staticmethod
    def _get_git_version(repo_path: Path) -> Optional[str]:
        """
        获取git commit hash
        
        Args:
            repo_path: 仓库路径
            
        Returns:
            commit hash（带-dirty标记）或None
        """
        try:
            # 获取commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
                
                # 检查是否有未提交的改动
                status_result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                is_dirty = bool(status_result.stdout.strip())
                return f"{commit}{'-dirty' if is_dirty else ''}"
        except Exception as e:
            logger.warning(f"[ReproducibilityInfo] Failed to get git version: {e}")
        
        return None

