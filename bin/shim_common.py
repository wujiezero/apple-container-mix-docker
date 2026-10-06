"""Shared argv translation for the dependency-free Docker and Compose shims."""


# All boolean run/create flags emitted by either shim. Other emitted flags take
# one value, which must not be mistaken for another option during this scan.
_RUN_BOOLEAN_FLAGS = {
    "--detach", "--interactive", "--tty", "--rm", "--init", "--read-only",
    "--help", "--debug",
}


def prepare_run_args(flags, image, command):
    """Return native run/create args, honoring the final entrypoint override.

    Apple container 1.5 ignores an explicit empty entrypoint and falls back to
    the image entrypoint. Use the explicit command's executable as the native
    entrypoint instead, preserving argv without requiring a shell in the image.
    """
    output = []
    entrypoint = None
    help_requested = False
    i = 0
    while i < len(flags):
        option = flags[i]
        if option == "--entrypoint":
            entrypoint = flags[i + 1]
            i += 2
        else:
            help_requested = help_requested or option == "--help"
            count = 1 if option in _RUN_BOOLEAN_FLAGS else 2
            output.extend(flags[i:i + count])
            i += count

    command = list(command)
    if entrypoint == "" and not help_requested:
        if not command or not command[0]:
            raise ValueError("clearing --entrypoint requires an explicit command")
        entrypoint = command.pop(0)
    if entrypoint is not None:
        output.extend(["--entrypoint", entrypoint])
    return [*output, image, *command]
