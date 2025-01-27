# app/db.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings
from tenacity import retry, wait_fixed, stop_after_attempt

@retry(wait=wait_fixed(2), stop=stop_after_attempt(10))
def connect_to_database():
    engine = create_engine(settings.DATABASE_URL)
    # 测试连接是否可用
    with engine.connect() as connection:
        connection.execute("SELECT 1")
    return engine

# 创建 MySQL 数据库引擎
engine = create_engine(
    settings.DATABASE_URL  # 直接从配置加载 MySQL 的连接字符串
)

# 配置 SessionLocal
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基础模型类
Base = declarative_base()
