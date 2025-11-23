# dockerfile

# 阶段 2：构建应用程序镜像
FROM auto-crypto-base AS app

# 复制应用程序代码到容器中
COPY . /app

# 启动应用程序
CMD ["python", "-m", "app.main"]