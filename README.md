# apple-container-docker

English | [简体中文](README.zh-CN.md)

A Docker CLI compatibility layer for [Apple container](https://github.com/apple/container):
it translates `docker` commands into the corresponding `container` CLI calls, so
`docker pull redis`, `docker run -d -p 6379:6379 redis`, `docker exec -it ... sh`
and friends keep working on a Mac with no Docker installed.

Tested against apple/container **1.5.0** on Apple Silicon; previously validated
against 1.3.1.

## Requirements

- Apple Silicon Mac with the [container](https://github.com/apple/container/releases)
  CLI installed and on `PATH` (Homebrew typically uses `/opt/homebrew/bin/container`).
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

`bin/docker` is a Python 3 script with no third-party dependencies. It shares
entrypoint argument translation with Compose through `bin/shim_common.py` and
has three layers:

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

`docker start A B` starts each container separately, continues after failures,
and returns a nonzero exit code if any start fails. `start -a/-i` accepts only
one container to preserve interactive terminal behavior.

`docker run/create --entrypoint "" IMAGE COMMAND [ARGS...]` executes the explicit
command directly, bypassing the image entrypoint; omitting the command is an
error. No shell is introduced, so spaces and special characters remain literal
arguments. Compose `entrypoint: []` / `entrypoint: ""` has the same behavior and
requires an explicit `command` or `compose run SERVICE COMMAND`.

## Supported commands

| Area | Commands |
| --- | --- |
| Containers | run, create, exec, ps, start, stop, kill, rm, logs, cp, stats, inspect, export, restart (emulated) |
| Images | pull, push, images, rmi, tag, save, load, build |
| Auth | login, logout |
| Groups | `docker container/image/volume/network/system ...` subcommands |
| Cleanup | `docker system prune` (+ per-group prune, with confirmation unless `-f`) |
| Compose | `docker compose` / `docker-compose` — see the section below |
| Misc | version, info |

Explicitly **unsupported** (clear error + suggested alternative): attach,
commit, pause/unpause, top, port, wait, events, history, swarm, context —
apple/container has no equivalent capability.

## docker compose

`docker compose` (and the v1-style `docker-compose` binary) is implemented by
`bin/docker-compose`, which translates a compose file into individual
`container` calls:

```bash
docker compose up -d          # also: --build, --force-recreate, [SERVICE...]
docker compose ps / logs -f / exec SERVICE CMD / run --rm SERVICE CMD
docker compose stop / start / restart / down [-v]
docker compose pull / build / config
```

Supported service keys: `image`, `build` (context/dockerfile/args/target),
`container_name`, `command`, `entrypoint`, `environment`, `env_file`, `ports`,
`volumes` (bind mounts, named volumes, tmpfs, `:ro`), `networks`, `depends_on`
(start ordering), `labels`, `user`, `working_dir`, `platform`, `tty`,
`stdin_open`, `cap_add/drop`, `dns`, `tmpfs`, `shm_size`, `ulimits`, `cpus`,
`mem_limit`, `extra_hosts`, `read_only`, `init`. Variable interpolation
(`${VAR:-default}`) and `.env` files work; YAML parsing uses PyYAML when
available and falls back to macOS's bundled Ruby (zero install).

Details worth knowing:

- **Service discovery**: Apple container has no usable DNS for bare names, so
  after `up` the shim writes every service's IP into `/etc/hosts` of all
  project containers — services reach each other by service name as usual.
  This requires `/bin/sh` in the image; IPs are re-written by
  `up`/`start`/`restart`.
- Project resources are namespaced like compose: containers
  `<project>-<service>-1`, network `<project>_default`, volumes
  `<project>_<name>`.
- Not supported (warned and ignored): `restart:` policies, `healthcheck`,
  `deploy.replicas`/scale > 1, port ranges, host/container-only port syntax,
  multiple networks per service (first one is used), profiles, secrets,
  configs.

## Known semantic differences

- Apple container's `image pull` downloads **every** architecture in the
  manifest by default. The shim restores Docker's behavior and pulls only the
  host platform (e.g. `linux/arm64`, ~4 MB for alpine instead of ~29 MB for
  all 8 platforms). An explicit `--platform` or `CONTAINER_DEFAULT_PLATFORM`
  is respected; set `DOCKER_SHIM_PULL_ALL_PLATFORMS=1` to opt out.
- Every container is a lightweight VM with its own IP (visible in `docker ps`).
  `-p` port publishing works, but there is no host network mode.
- `--restart` policies, healthchecks and fine-grained cgroup limits are dropped.
- `ps --format` / `images --format` accept `json`, `table`, `yaml` and `toml`
  (container 1.3), but not Go templates; `inspect --format` is not supported.
- Registries on `localhost` / `127.0.0.1` are contacted over **http**. Apple
  container 1.3.0 removed `--scheme auto` and now defaults to https, which
  breaks local plain-HTTP registries; the shim restores Docker's behavior.
  `DOCKER_SHIM_REGISTRY_SCHEME=http|https` forces one scheme everywhere.
- `chmod`/`chown` on a bind mount's **mount point itself** is denied by
  virtiofs (subdirectories and files inside it work normally) — this breaks
  database images at startup, see below.

### Database images and bind mounts (postgres, mysql, ...)

Official database images `chown` their data directory in the entrypoint. With
Apple container, a bind mount's mount point rejects `chmod`/`chown`
(`Operation not permitted` — a virtiofs restriction, regardless of ownership),
so this fails at startup:

```bash
docker run -d -v ~/Documents/Docker/pg16:/var/lib/postgresql/data postgres:16-bookworm   # FAILS
```

Workaround 1 (preferred): make the real data directory a **subdirectory of
the mount** — new inodes created inside the mount can be chown'd freely. For
postgres, mount the parent and point `PGDATA` inside it:

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

The same idea works for any image whose data path is configurable
(MySQL `--datadir`, MongoDB `--dbpath`, ...).

Workaround 2: skip the entrypoint's chown branch by running as your host user
(`--user $(id -u):$(id -g)`), with the host directory owned by that user.

Named volumes (`docker volume create` / compose top-level `volumes:`) are not
affected — prefer them when you don't need the files visible on the host.

## Debugging

```bash
DOCKER_SHIM_DEBUG=1 docker run -d nginx   # print the translated command
DOCKER_SHIM_STRICT=1 docker run ...       # fail on unsupported flags
DOCKER_SHIM_CONTAINER_BIN=echo docker ... # dry run: only show the translation
DOCKER_SHIM_PULL_ALL_PLATFORMS=1 docker pull ... # pull all architectures (Apple default)
DOCKER_SHIM_REGISTRY_SCHEME=http docker pull ... # force the registry scheme
```

## Validation

Run the dependency-free regression suite (no local containers are contacted or
modified):

```bash
python3 -m unittest discover -s tests -v
```

Validated on 1.5.0: multi-container start, continuation after a failed start,
empty entrypoints with run/create, Compose up/ps, and command overrides with
attached/detached Compose run. Temporary resources were cleaned up afterward.
Image builds, remote registries, and interactive TTY behavior were not retested
in this update.

## License

[MIT](LICENSE)
