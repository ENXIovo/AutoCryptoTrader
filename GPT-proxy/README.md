# Aosom GPT Backend docker操作指南

## Makefile说明
- version.mk
  - 版本信息
  - 强烈建议，通过版本信息文件（version.mk）来管理版本
- make build_base
  - build base镜像
  - 手动指定版本 make VERSION_BASE=v1.1 build_base
- make build_backend
  - build backend镜像
  - 手动指定版本 make VERSION_BACKEND=v1.1 build_backend
  - 手动指定版本 make VERSION_BASE=v1.1 VERSION_BACKEND=v1.1 build_backend
- make push_base
  - push base镜像
- make push_backend
  - push backend镜像


## 本地环境 - docker-compose分段构造

### 构建基础镜像

构建基础镜像 aosom_gpt_web-base，使用 Dockerfile.base 文件，禁用构建缓存以确保从最新源代码构建。

#### 更改 Dockerfile.base 后需重新运行
```bash
docker build --no-cache -f Dockerfile.base -t aosom_gpt_web-base .
```

### 构建应用镜像 - 可省略

构建应用镜像 aosom_gpt_web-app，使用 Dockerfile.app 文件，同样禁用构建缓存。

```bash
docker build --no-cache -f Dockerfile.app -t aosom_gpt_web-app .
```

### 启动服务

使用 docker-compose 启动服务，根据 docker-compose.yml 文件配置，构建应用镜像 aosom_gpt_web-app。
#### 此命令自动检测状态，aosom_gpt_web-app如有任何变化将自动重新构建app

```bash
docker-compose up
```

### 强制重新构建

重新构建服务，确保使用最新的镜像。

```bash
docker-compose up --build
```

## 测试环境 - jenkins(CI/CD)

也可在本地构建，即是不分段构建

### 构建测试镜像

构建测试环境的 Docker 镜像 aosom-gpt:dev，使用 Dockerfile 文件。

```bash
docker build --no-cache -f Dockerfile -t aosom-gpt:dev .
```

### 运行测试服务

以守护进程模式运行测试服务，端口映射为 8200:8000，并使用 .env.dev 环境配置文件。

```bash
docker run -d --name aosom-gpt-dev -p 8200:8000 --env-file .env.dev aosom-gpt:dev
```

## 正式环境 - jenkins(CI/CD)
### 构建生产镜像

构建生产环境的 Docker 镜像 aosom-gpt:prod，通过构建参数指定运行环境为生产环境。

```bash
docker build --no-cache -f Dockerfile --build-arg ENV=prod -t aosom-gpt:prod .
```

### 运行生产服务

以守护进程模式运行生产服务，端口映射为 8200:8000，并使用 .env.prod 环境配置文件。

```bash
docker run -d --name aosom-gpt-prod -p 8200:8000 --env-file .env.prod aosom-gpt:prod
```

# 清理镜像

删除不再需要的镜像，释放空间。

```bash
docker rmi aosom_gpt_web-base
docker rmi aosom_gpt_web-app
docker rmi new_backend-aosom_gpt_web-app
```

# 清理 Docker 系统

移除 Docker 中不再使用的资源，包括悬挂的镜像、未使用的容器、网络以及构建缓存，释放空间。
```bash
docker system prune
```

# 清理未使用的 Docker 镜像

移除 Docker 中未被容器使用的镜像，帮助管理镜像存储并释放空间。

```bash
docker image prune
```