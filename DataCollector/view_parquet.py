#!/usr/bin/env python3
"""
Parquet文件查看工具
用于查看M2 DataStore中的Parquet文件，不影响写入操作
"""
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def view_parquet_file(file_path: str, limit: Optional[int] = None):
    """
    查看单个Parquet文件
    
    Args:
        file_path: Parquet文件路径
        limit: 限制显示的记录数（None表示显示所有）
    """
    try:
        print(f"\n{'='*80}")
        print(f"文件: {file_path}")
        print(f"{'='*80}")
        
        # 读取Parquet文件（只读，不影响写入）
        df = pd.read_parquet(file_path)
        
        # 基本信息
        print(f"\n📊 基本信息:")
        print(f"  总记录数: {len(df)}")
        print(f"  列数: {len(df.columns)}")
        print(f"  列名: {', '.join(df.columns.tolist())}")
        
        # 文件大小
        file_size = Path(file_path).stat().st_size
        print(f"  文件大小: {file_size / 1024:.2f} KB ({file_size / 1024 / 1024:.2f} MB)")
        
        # 时间范围（如果有timestamp列）
        if 'timestamp' in df.columns:
            # 确保时间戳解析为UTC时区
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            print(f"\n⏰ 时间范围 (UTC):")
            print(f"  开始: {df['datetime'].min()}")
            print(f"  结束: {df['datetime'].max()}")
            print(f"  跨度: {(df['datetime'].max() - df['datetime'].min()).total_seconds() / 3600:.2f} 小时")
        
        # 数据预览
        print(f"\n📋 数据预览 (前{min(10, len(df))}条):")
        display_df = df.head(limit) if limit else df.head(10)
        print(display_df.to_string())
        
        # 数据统计（如果有数值列）
        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
        if len(numeric_cols) > 0:
            print(f"\n📈 数据统计:")
            print(df[numeric_cols].describe())
        
        # 检查是否有缺失值
        missing = df.isnull().sum()
        if missing.sum() > 0:
            print(f"\n⚠️  缺失值:")
            for col, count in missing[missing > 0].items():
                print(f"  {col}: {count} ({count/len(df)*100:.1f}%)")
        else:
            print(f"\n✅ 无缺失值")
        
        return df
        
    except FileNotFoundError:
        print(f"❌ 错误: 文件不存在 - {file_path}")
        return None
    except Exception as e:
        print(f"❌ 错误: {e}")
        return None


def list_parquet_files(base_path: str = "/app/data/candles"):
    """
    列出所有Parquet文件
    
    Args:
        base_path: 数据存储根路径
    """
    base = Path(base_path)
    if not base.exists():
        print(f"❌ 路径不存在: {base_path}")
        return
    
    print(f"\n{'='*80}")
    print(f"Parquet文件列表: {base_path}")
    print(f"{'='*80}\n")
    
    files = list(base.rglob("*.parquet"))
    
    if not files:
        print("  未找到Parquet文件")
        return
    
    # 按symbol和timeframe分组
    by_symbol_timeframe = {}
    for file in sorted(files):
        # 路径格式: base_path/SYMBOL_TIMEFRAME/YYYY-MM-DD.parquet
        parts = file.parts
        if len(parts) >= 2:
            symbol_timeframe = parts[-2]  # SYMBOL_TIMEFRAME
            date_file = parts[-1]  # YYYY-MM-DD.parquet
            
            if symbol_timeframe not in by_symbol_timeframe:
                by_symbol_timeframe[symbol_timeframe] = []
            by_symbol_timeframe[symbol_timeframe].append((file, date_file))
    
    # 显示分组列表
    for symbol_timeframe, file_list in sorted(by_symbol_timeframe.items()):
        print(f"\n📁 {symbol_timeframe}:")
        total_size = 0
        for file, date_file in sorted(file_list):
            size = file.stat().st_size
            total_size += size
            print(f"  - {date_file:20s}  {size / 1024:8.2f} KB")
        print(f"  总计: {len(file_list)} 个文件, {total_size / 1024 / 1024:.2f} MB")


def view_summary(base_path: str = "/app/data/candles"):
    """
    查看数据摘要
    
    Args:
        base_path: 数据存储根路径
    """
    base = Path(base_path)
    if not base.exists():
        print(f"❌ 路径不存在: {base_path}")
        return
    
    print(f"\n{'='*80}")
    print(f"数据摘要: {base_path}")
    print(f"{'='*80}\n")
    
    files = list(base.rglob("*.parquet"))
    
    if not files:
        print("  未找到Parquet文件")
        return
    
    summary = {}
    total_records = 0
    total_size = 0
    
    for file in files:
        try:
            df = pd.read_parquet(file)
            parts = file.parts
            if len(parts) >= 2:
                symbol_timeframe = parts[-2]
                date_str = parts[-1].replace('.parquet', '')
                
                if symbol_timeframe not in summary:
                    summary[symbol_timeframe] = {
                        'files': 0,
                        'records': 0,
                        'size': 0,
                        'dates': []
                    }
                
                summary[symbol_timeframe]['files'] += 1
                summary[symbol_timeframe]['records'] += len(df)
                summary[symbol_timeframe]['size'] += file.stat().st_size
                summary[symbol_timeframe]['dates'].append(date_str)
                
                total_records += len(df)
                total_size += file.stat().st_size
        except Exception as e:
            print(f"⚠️  读取文件失败 {file}: {e}")
    
    # 显示摘要
    for symbol_timeframe, stats in sorted(summary.items()):
        dates = sorted(stats['dates'])
        print(f"\n📊 {symbol_timeframe}:")
        print(f"  文件数: {stats['files']}")
        print(f"  总记录数: {stats['records']:,}")
        print(f"  总大小: {stats['size'] / 1024 / 1024:.2f} MB")
        print(f"  日期范围: {dates[0]} ~ {dates[-1]}")
        print(f"  覆盖天数: {len(set(dates))}")
    
    print(f"\n{'='*80}")
    print(f"总计:")
    print(f"  文件数: {len(files)}")
    print(f"  总记录数: {total_records:,}")
    print(f"  总大小: {total_size / 1024 / 1024:.2f} MB")
    print(f"{'='*80}")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python view_parquet.py list                    # 列出所有文件")
        print("  python view_parquet.py summary                # 查看摘要")
        print("  python view_parquet.py <file_path>            # 查看单个文件")
        print("  python view_parquet.py <file_path> <limit>    # 查看文件（限制记录数）")
        print("\n示例:")
        print("  python view_parquet.py list")
        print("  python view_parquet.py summary")
        print("  python view_parquet.py /app/data/candles/BTCUSD_1m/2025-11-22.parquet")
        print("  python view_parquet.py /app/data/candles/BTCUSD_1m/2025-11-22.parquet 20")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list":
        base_path = sys.argv[2] if len(sys.argv) > 2 else "/app/data/candles"
        list_parquet_files(base_path)
    elif command == "summary":
        base_path = sys.argv[2] if len(sys.argv) > 2 else "/app/data/candles"
        view_summary(base_path)
    else:
        # 查看单个文件
        file_path = command
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        view_parquet_file(file_path, limit)


if __name__ == "__main__":
    main()

