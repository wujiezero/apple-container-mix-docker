# apple-container-docker

[English](README.md) | 简体中文

Docker CLI 兼容层：把 `docker` 命令翻译并转发给 Apple 官方的
[container](https://github.com/apple/container) 工具执行。安装后可以照常敲
`docker pull redis`、`docker run -d -p 6379:6379 redis`、`docker exec -it ... sh`
这类命令，在没有 Docker 的 Mac 上由 `container` CLI 实际完成。

基于 apple/container **1.0.0**、Apple Silicon（macOS 26）实测。

## 前置条件

- Apple Silicon Mac，已安装 [container](https://github.com/apple/container/releases)
  CLI（`/usr/local/bin/container`）。
- Python 3（任意较新版本，脚本零第三方依赖）。

## 一键安装

```bash
git clone https://github.com/wujiezero/apple-container-mix-docker.git
cd apple-container-mix-docker
./install.sh
```

安装脚本一次做完所有事：

1. 把 `bin/docker` 软链到 `~/.local/bin`（可传目录参数覆盖，如
   `./install.sh /usr/local/bin`，必要时才会用 sudo）。
2. 检查目标目录是否在 `PATH` 中。
3. 检测 `~/.zshrc` 里会遮挡 shim 的 `alias docker=...`——如果别名指向的命令
   已不存在（死别名）会自动注释掉（备份到 `~/.zshrc.docker-shim.bak`），
   否则给出告警提示手动处理。
4. 启动 `container` 后台服务；首次使用自动安装默认 Linux 内核
   （`container system kernel set --recommended`）。
5. 跑冒烟测试（`docker version` / `docker ps`）。

一键卸载：`./uninstall.sh`——自动扫描并删除所有指向本项目的 `docker` 软链
（加 `--stop-services` 可顺带停掉 `container` 服务）。

## 工作原理

`bin/docker` 是一个无依赖的 Python 3 脚本，分三层处理：

1. **子命令改名**：`ps`→`list`、`rm`→`delete`、`pull`→`image pull`、
   `rmi`→`image delete`、`login`→`registry login`，以及
   `docker container/image/volume/network/system ...` 二级分组命令。
2. **flag 翻译**：绝大多数常用 flag（`-d -it -e -v -p --name --rm --platform`
   等）两边同名直接透传；个别改名（`--tail`→`-n`、`--net`→`--network`、
   `--network bridge`→`--network default`）。
3. **不支持项处理**：Apple container 没有的 docker flag（`--restart`、
   `--privileged`、`--gpus`、`--add-host` 等）默认**告警并丢弃**，命令继续执行；
   设 `DOCKER_SHIM_STRICT=1` 可改为直接报错退出。

单命令场景用 `execvp` 直接替换进程，TTY 交互（`docker run -it`）、退出码、
信号都原样透传。没有一一对应的命令走模拟：`restart` = stop + start，
`docker inspect` 先按容器查、查不到自动按镜像查，`login -p` 自动转成
`--password-stdin`，`system prune` 展开为 container/image/network(/volume)
prune 并先确认。

## 支持范围

| 类别 | 命令 |
| --- | --- |
| 容器 | run, create, exec, ps, start, stop, kill, rm, logs, cp, stats, inspect, export, restart（模拟） |
| 镜像 | pull, push, images, rmi, tag, save, load, build |
| 登录 | login, logout |
| 分组 | `docker container/image/volume/network/system ...` 二级子命令 |
| 清理 | `docker system prune`（及各分组 prune，无 `-f` 时先确认） |
| Compose | `docker compose` / `docker-compose`——见下方章节 |
| 其他 | version, info |

明确**不支持**（会给出明确报错和替代建议）：attach, commit, pause/unpause,
top, port, wait, events, history, swarm, context——这些在
apple/container 1.0.0 中没有对应能力。

## docker compose

`docker compose`（以及 v1 风格的 `docker-compose` 命令）由
`bin/docker-compose` 实现，把 compose 文件翻译成一组 `container` 调用：

```bash
docker compose up -d          # 支持 --build、--force-recreate、[SERVICE...]
docker compose ps / logs -f / exec SERVICE CMD / run --rm SERVICE CMD
docker compose stop / start / restart / down [-v]
docker compose pull / build / config
```

支持的 service 配置项：`image`、`build`（context/dockerfile/args/target）、
`container_name`、`command`、`entrypoint`、`environment`、`env_file`、
`ports`、`volumes`（bind 挂载、具名卷、tmpfs、`:ro`）、`networks`、
`depends_on`（启动顺序）、`labels`、`user`、`working_dir`、`platform`、
`tty`、`stdin_open`、`cap_add/drop`、`dns`、`tmpfs`、`shm_size`、`ulimits`、
`cpus`、`mem_limit`、`extra_hosts`、`read_only`、`init`。变量插值
（`${VAR:-default}`）和 `.env` 文件可用；YAML 解析优先用 PyYAML，没装则
自动退回 macOS 自带的 Ruby（零安装依赖）。

需要了解的实现细节：

- **服务发现**：Apple container 没有可用的裸名 DNS，shim 在 `up` 之后把每个
  服务的 IP 写进项目内所有容器的 `/etc/hosts`——服务间照常用服务名互访。
  要求镜像内有 `/bin/sh`；`up`/`start`/`restart` 时会重写 IP。
- 资源命名与 compose 一致：容器 `<项目>-<服务>-1`、网络 `<项目>_default`、
  卷 `<项目>_<卷名>`。
- 不支持（告警后忽略）：`restart:` 策略、`healthcheck`、
  `deploy.replicas`/scale > 1、端口区间、无宿主机端口的随机端口语法、
  单服务多网络（只挂第一个）、profiles、secrets、configs。

## 已知语义差异

- Apple container 的 `image pull` 默认会把 manifest 里**所有架构**都拉下来。
  shim 恢复了 Docker 的行为，只拉当前平台（如 `linux/arm64`，alpine 约 4 MB，
  而全部 8 个平台约 29 MB）。显式指定 `--platform` 或设置了
  `CONTAINER_DEFAULT_PLATFORM` 时以用户为准；设
  `DOCKER_SHIM_PULL_ALL_PLATFORMS=1` 可退回全架构拉取。
- 每个容器是独立轻量 VM，有自己的 IP（`docker ps` 可见），`-p` 端口映射可用，
  但没有 host 网络模式。
- `--restart` 策略、healthcheck、cgroup 细粒度资源限制不生效（被丢弃）。
- `ps --format` / `inspect --format` 只支持 `json`，不支持 Go template。
- 容器内对 bind mount 的**挂载点本身**做 `chmod`/`chown` 会被 virtiofs 拒绝
  （挂载点里面的子目录和文件完全正常）——数据库镜像会因此起不来，见下节。

### 数据库镜像与 bind mount（postgres、mysql 等）

官方数据库镜像的 entrypoint 启动时会对数据目录 `chown`。而 Apple container
的 bind mount 挂载点拒绝 `chmod`/`chown`（`Operation not permitted`，是
virtiofs 的限制，和目录归属无关），所以这样写会启动失败：

```bash
docker run -d -v ~/Documents/Docker/pg16:/var/lib/postgresql/data postgres:16-bookworm   # 失败
```

绕法一（推荐）：让真正的数据目录是**挂载点内的子目录**——挂载点里新建的
inode 可以随便 chown。以 postgres 为例，挂载父目录、用 `PGDATA` 指到里面：

```bash
docker run -d --name pg16 \
  -e PGDATA=/pg/data \
  -v ~/Documents/Docker/pg16:/pg \
  postgres:16-bookworm
```

```yaml
services:
  db:
    image: postgres:16-bookworm
    environment:
      PGDATA: /pg/data
    volumes:
      - ./pgdata:/pg
```

数据路径可配置的镜像同理（MySQL 的 `--datadir`、MongoDB 的 `--dbpath` 等）。

绕法二：用宿主机当前用户运行（`--user $(id -u):$(id -g)`，且挂载目录归属
该用户），跳过 entrypoint 的 chown 分支。

具名卷（`docker volume create` / compose 顶层 `volumes:`）不受此限制——
不需要在宿主机直接看文件时优先用具名卷。

## 调试

```bash
DOCKER_SHIM_DEBUG=1 docker run -d nginx   # 打印翻译后的实际命令
DOCKER_SHIM_STRICT=1 docker run ...       # 不支持的 flag 直接报错
DOCKER_SHIM_CONTAINER_BIN=echo docker ... # 干跑，只看翻译结果
DOCKER_SHIM_PULL_ALL_PLATFORMS=1 docker pull ... # 拉取全部架构（Apple 默认行为）
```

## 协议

[MIT](LICENSE)

