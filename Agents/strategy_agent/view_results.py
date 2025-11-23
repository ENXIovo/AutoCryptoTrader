"""
查看会议结果的工具脚本
从Redis Stream中读取最新的会议结果
"""
import json
import redis
import sys
from datetime import datetime, timezone

# 默认配置
REDIS_URL = "redis://redis-server:6379/0"
STREAM_KEY = "results"
MAX_ENTRIES = 10  # 默认显示最近10条

def view_results(redis_url: str = REDIS_URL, stream_key: str = STREAM_KEY, count: int = MAX_ENTRIES):
    """
    从Redis Stream读取会议结果
    
    Args:
        redis_url: Redis连接URL
        stream_key: Stream键名（默认"results"）
        count: 读取的条目数量
    """
    try:
        r = redis.Redis.from_url(redis_url, decode_responses=True)
        
        # 检查Stream是否存在
        stream_info = r.xinfo_stream(stream_key)
        if not stream_info:
            print(f"❌ Stream '{stream_key}' 不存在或为空")
            return
        
        length = stream_info.get("length", 0)
        print(f"📊 Stream '{stream_key}' 包含 {length} 条记录")
        print(f"📖 显示最近 {min(count, length)} 条记录\n")
        print("=" * 80)
        
        # 读取最新的条目（从最新到最旧）
        entries = r.xrevrange(stream_key, count=count)
        
        if not entries:
            print("❌ 没有找到任何记录")
            return
        
        for i, (entry_id, fields) in enumerate(entries, 1):
            print(f"\n{'=' * 80}")
            print(f"📝 记录 #{i} (ID: {entry_id})")
            print(f"{'=' * 80}")
            
            # 解析时间戳
            ts = fields.get("ts", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    print(f"⏰ 时间: {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                except:
                    print(f"⏰ 时间: {ts}")
            
            # 解析payload
            payload_str = fields.get("payload", "{}")
            try:
                payload = json.loads(payload_str)
                
                # 显示元数据
                if "_meta" in payload:
                    meta = payload["_meta"]
                    print(f"📋 元数据: {json.dumps(meta, indent=2, ensure_ascii=False)}")
                
                # 显示各个角色的报告
                roles = ["Market Analyst", "Lead Technical Analyst", "Position Manager", 
                        "Risk Manager", "Chief Trading Officer"]
                
                for role in roles:
                    if role in payload:
                        role_data = payload[role]
                        if isinstance(role_data, dict):
                            content = role_data.get("content", "")
                            if content:
                                print(f"\n👤 {role}:")
                                print(f"{'-' * 80}")
                                # 只显示前500个字符，避免输出过长
                                if len(content) > 500:
                                    print(content[:500] + "...")
                                    print(f"\n... (内容已截断，完整内容请查看Redis)")
                                else:
                                    print(content)
                        elif isinstance(role_data, dict) and "BTC" in role_data:
                            # TA可能有多个symbol
                            print(f"\n👤 {role}:")
                            for sym, sym_data in role_data.items():
                                if isinstance(sym_data, dict):
                                    content = sym_data.get("content", "")
                                    if content:
                                        print(f"\n  📈 {sym}:")
                                        if len(content) > 300:
                                            print(content[:300] + "...")
                                        else:
                                            print(content)
                
            except json.JSONDecodeError as e:
                print(f"❌ 解析JSON失败: {e}")
                print(f"原始payload: {payload_str[:200]}...")
            
            print()
        
        print("=" * 80)
        print(f"\n✅ 共显示 {len(entries)} 条记录")
        print(f"💡 提示: 使用 Redis CLI 查看完整数据: XREVRANGE {stream_key} COUNT {count}")
        
    except redis.exceptions.ConnectionError:
        print(f"❌ 无法连接到Redis: {redis_url}")
        print("💡 请检查Redis服务是否运行，以及URL是否正确")
    except redis.exceptions.ResponseError as e:
        if "no such key" in str(e).lower():
            print(f"❌ Stream '{stream_key}' 不存在")
        else:
            print(f"❌ Redis错误: {e}")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 支持命令行参数
    count = MAX_ENTRIES
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            print(f"⚠️  无效的参数: {sys.argv[1]}，使用默认值 {MAX_ENTRIES}")
    
    view_results(count=count)

