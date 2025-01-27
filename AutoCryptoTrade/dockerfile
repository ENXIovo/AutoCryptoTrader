# dockerfile

# 阶段 2：构建应用程序镜像
FROM auto-crypto-base AS app

# 复制应用程序代码到容器中
COPY . /app

# 暴露应用程序端口
EXPOSE 8080

# 启动应用程序
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]