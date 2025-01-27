FROM python:3.8-slim

# 创建并激活虚拟环境
RUN python3 -m venv /venv
ENV PATH=/venv/bin:$PATH

# 设置工作目录
WORKDIR /app

# 复制requirements.txt并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码到容器中
COPY . .

# 暴露端口8000
EXPOSE 8000

# 设置默认启动命令
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
