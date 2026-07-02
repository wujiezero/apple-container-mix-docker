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
| 其他 | version, info |

明确**不支持**（会给出明确报错和替代建议）：attach, commit, pause/unpause,
top, port, wait, events, history, swarm, context, compose——这些在
apple/container 1.0.0 中没有对应能力。

## 已知语义差异

- 每个容器是独立轻量 VM，有自己的 IP（`docker ps` 可见），`-p` 端口映射可用，
  但没有 host 网络模式。
- `--restart` 策略、healthcheck、cgroup 细粒度资源限制不生效（被丢弃）。
- `ps --format` / `inspect --format` 只支持 `json`，不支持 Go template。

## 调试

```bash
DOCKER_SHIM_DEBUG=1 docker run -d nginx   # 打印翻译后的实际命令
DOCKER_SHIM_STRICT=1 docker run ...       # 不支持的 flag 直接报错
DOCKER_SHIM_CONTAINER_BIN=echo docker ... # 干跑，只看翻译结果
```

## 协议

[MIT](LICENSE)

