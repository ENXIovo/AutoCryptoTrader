# dockerfile

# 应用镜像：依赖已预构建的基础镜像标签 exchange-base
FROM exchange-base AS app

# 复制应用程序代码到容器中
COPY . /app

# 暴露应用程序端口
EXPOSE 8100

# 启动应用程序
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]