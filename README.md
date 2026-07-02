# apple-container-docker

English | [简体中文](README.zh-CN.md)

A Docker CLI compatibility layer for [Apple container](https://github.com/apple/container):
it translates `docker` commands into the corresponding `container` CLI calls, so
`docker pull redis`, `docker run -d -p 6379:6379 redis`, `docker exec -it ... sh`
and friends keep working on a Mac with no Docker installed.

Tested against apple/container **1.0.0** on Apple Silicon (macOS 26).

## Requirements

- Apple Silicon Mac with the [container](https://github.com/apple/container/releases)
  CLI installed (`/usr/local/bin/container`).
- Python 3 (any recent version; the shim has no third-party dependencies).

## Quick start

```bash
git clone https://github.com/wujiezero/apple-container-mix-docker.git
cd apple-container-mix-docker
./install.sh
```

The installer does everything needed in one shot:

1. Symlinks `bin/docker` into `~/.local/bin` (pass a directory argument to
   override, e.g. `./install.sh /usr/local/bin`; sudo is used only if needed).
2. Verifies the target directory is on your `PATH`.
3. Detects a shell `alias docker=...` in `~/.zshrc` that would shadow the shim —
   if the alias points to a binary that no longer exists it is commented out
   automatically (with a `~/.zshrc.docker-shim.bak` backup), otherwise you get
   a warning.
4. Starts the `container` system services and installs the default Linux kernel
   on first use (`container system kernel set --recommended`).
5. Runs a smoke test (`docker version` / `docker ps`).

Uninstall with `./uninstall.sh` — it removes every `docker` symlink pointing at
this project (add `--stop-services` to also stop the `container` services).

## How it works

`bin/docker` is a single dependency-free Python 3 script with three layers:

1. **Subcommand renaming** — `ps`→`list`, `rm`→`delete`, `pull`→`image pull`,
   `rmi`→`image delete`, `login`→`registry login`, and the two-level
   `docker container/image/volume/network/system ...` groups.
2. **Flag translation** — most common flags (`-d -it -e -v -p --name --rm
   --platform ...`) are identical on both CLIs and pass straight through; a few
   are renamed (`--tail`→`-n`, `--net`→`--network`,
   `--network bridge`→`--network default`).
3. **Unsupported-flag policy** — Docker flags with no Apple container
   equivalent (`--restart`, `--privileged`, `--gpus`, `--add-host`, ...) are
   dropped with a warning and the command still runs; set
   `DOCKER_SHIM_STRICT=1` to fail instead.

Single-command invocations are `execvp`'d, so TTY interaction
(`docker run -it`), exit codes and signals behave natively. Commands with no
1:1 mapping are emulated: `restart` = stop + start, `docker inspect` tries the
container first and falls back to the image, `login -p` is converted to
`--password-stdin`, `system prune` fans out to
container/image/network(/volume) prune with a confirmation prompt.

## Supported commands

| Area | Commands |
| --- | --- |
| Containers | run, create, exec, ps, start, stop, kill, rm, logs, cp, stats, inspect, export, restart (emulated) |
| Images | pull, push, images, rmi, tag, save, load, build |
| Auth | login, logout |
| Groups | `docker container/image/volume/network/system ...` subcommands |
| Cleanup | `docker system prune` (+ per-group prune, with confirmation unless `-f`) |
| Misc | version, info |

Explicitly **unsupported** (clear error + suggested alternative): attach,
commit, pause/unpause, top, port, wait, events, history, swarm, context,
compose — apple/container 1.0.0 has no equivalent capability.

## Known semantic differences

- Apple container's `image pull` downloads **every** architecture in the
  manifest by default. The shim restores Docker's behavior and pulls only the
  host platform (e.g. `linux/arm64`, ~4 MB for alpine instead of ~29 MB for
  all 8 platforms). An explicit `--platform` or `CONTAINER_DEFAULT_PLATFORM`
  is respected; set `DOCKER_SHIM_PULL_ALL_PLATFORMS=1` to opt out.
- Every container is a lightweight VM with its own IP (visible in `docker ps`).
  `-p` port publishing works, but there is no host network mode.
- `--restart` policies, healthchecks and fine-grained cgroup limits are dropped.
- `ps --format` / `inspect --format` only accept `json`, not Go templates.

## Debugging

```bash
DOCKER_SHIM_DEBUG=1 docker run -d nginx   # print the translated command
DOCKER_SHIM_STRICT=1 docker run ...       # fail on unsupported flags
DOCKER_SHIM_CONTAINER_BIN=echo docker ... # dry run: only show the translation
DOCKER_SHIM_PULL_ALL_PLATFORMS=1 docker pull ... # pull all architectures (Apple default)
```

## License

[MIT](LICENSE)

