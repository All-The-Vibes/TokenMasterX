"""Trusted Linux-only bootstrap, sent by sandbox.py, never read by a model.

No installation, shell, host execution of model text, recursive host cleanup or
background service. Linux x86_64 / CPython 3.12 only; other runtimes fail closed.
The kernel boundary is namespaces + read-only chroot + zero caps + seccomp.
"""
import ast
import builtins
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import socket
import subprocess
import sys
import tempfile
import time
import types
# Preload useful calculator extensions; no dynamic-loader host paths in the jail.
import csv  # noqa: F401
import datetime  # noqa: F401
import decimal  # noqa: F401
import fractions  # noqa: F401
import math  # noqa: F401
import random  # noqa: F401
import statistics  # noqa: F401


ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
LIMIT = 65536
REPLY_LIMIT = 16 * LIMIT  # ASCII-escaped JSON, including both streams and receipt.
LIBC = ctypes.CDLL(None, use_errno=True)
MS_RDONLY, MS_NOSUID, MS_NODEV = 1, 2, 4
MS_REMOUNT, MS_BIND, MS_REC, MS_PRIVATE = 32, 4096, 16384, 1 << 18


PURE_BUILTINS = {
    "ValueError", "sum", "len", "min", "max", "abs", "round", "sorted",
    "list", "tuple", "bool", "int", "float", "range", "all", "any",
    "enumerate", "zip",
}
_NODES = {
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If,
    ast.Raise, ast.Assign, ast.Expr, ast.Pass, ast.Name, ast.Load, ast.Store,
    ast.Constant, ast.Call, ast.keyword, ast.BinOp, ast.UnaryOp, ast.BoolOp,
    ast.Compare, ast.IfExp, ast.Subscript, ast.Slice, ast.List, ast.Tuple,
    ast.ListComp, ast.GeneratorExp, ast.comprehension,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
}


def validate_sources(sources):
    """Canonical oracle policy. Call ONLY inside the resource-limited child.

    Return compiled modules so validation and execution use the same AST.
    """
    compiled = {}
    for path, source in sources.items():
        if not path.endswith(".py"):
            continue
        if "/" in path or path[:-3].startswith("_"):
            raise ValueError("only flat public Python modules are supported")
        tree = ast.parse(source, filename=path)
        functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        if len(functions) != len(tree.body) or functions & PURE_BUILTINS:
            raise ValueError("only uniquely named function definitions at module level")
        permitted = functions | PURE_BUILTINS
        for index, node in enumerate(ast.walk(tree)):
            if index >= 10000:
                raise ValueError("AST node budget exceeded")
            if type(node) not in _NODES:
                raise ValueError("unsupported generated AST: " + type(node).__name__)
            if isinstance(node, ast.FunctionDef):
                if (node not in tree.body or node.decorator_list or node.returns
                        or node.type_comment or getattr(node, "type_params", None)):
                    raise ValueError("decorators, nested definitions and annotations unsupported")
                if node.name.startswith("_"):
                    raise ValueError("private/reflection names unsupported")
            if isinstance(node, ast.arguments) and (
                node.defaults or any(x is not None for x in node.kw_defaults)
                or node.vararg or node.kwarg
            ):
                raise ValueError("defaults and variadic arguments unsupported")
            if isinstance(node, ast.arg) and (
                node.annotation or node.arg.startswith("_") or node.arg in permitted
            ):
                raise ValueError("unsafe parameter")
            if isinstance(node, ast.Name) and (
                node.id.startswith("_") or
                (isinstance(node.ctx, ast.Store) and node.id in permitted)
            ):
                raise ValueError("unsafe name or builtin/function rebinding")
            if isinstance(node, ast.Assign) and any(
                not isinstance(target, ast.Name) for target in node.targets
            ):
                raise ValueError("only local name assignment supported")
            if isinstance(node, ast.Call) and (
                not isinstance(node.func, ast.Name) or node.func.id not in permitted
                or any(k.arg is None for k in node.keywords)
            ):
                raise ValueError("only named pure builtin/intra-module calls supported")
            if isinstance(node, ast.Raise) and (
                node.cause is not None or not isinstance(node.exc, ast.Call)
                or not isinstance(node.exc.func, ast.Name) or node.exc.func.id != "ValueError"
            ):
                raise ValueError("only ValueError raising supported")
            if isinstance(node, ast.comprehension) and (
                node.is_async or not isinstance(node.target, ast.Name)
            ):
                raise ValueError("unsupported comprehension")
        compiled[path] = compile(tree, path, "exec")
    return compiled


def checked(value):
    if value < 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
    return value


def mount(source, target, kind=None, flags=0, data=None):
    def encode(value):
        return value.encode() if isinstance(value, str) else value
    checked(LIBC.mount(encode(source), encode(target), encode(kind),
                       ctypes.c_ulong(flags), encode(data)))


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def namespaces():
    return {name: os.readlink("/proc/self/ns/" + name)
            for name in ("user", "mnt", "net", "pid")}


def drop_caps():
    # Drop the complete supported capability bounding set while still privileged.
    for cap in range(64):
        present = LIBC.prctl(23, cap, 0, 0, 0)  # PR_CAPBSET_READ
        if present == -1 and ctypes.get_errno() == errno.EINVAL:
            break
        checked(present)
        checked(LIBC.prctl(24, cap, 0, 0, 0))  # PR_CAPBSET_DROP
    checked(LIBC.prctl(47, 4, 0, 0, 0))  # PR_CAP_AMBIENT_CLEAR_ALL
    class Header(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]
    class Data(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint32) for name in
                    ("effective", "permitted", "inheritable")]
    header, data = Header(0x20080522, 0), (Data * 2)()
    checked(LIBC.capset(ctypes.byref(header), data))
    checked(LIBC.capget(ctypes.byref(header), data))
    if any(getattr(d, name) for d in data for name, _ in Data._fields_):
        raise RuntimeError("capabilities remain")
    if any(checked(LIBC.prctl(23, c, 0, 0, 0)) for c in range(cap)):
        raise RuntimeError("bounding capabilities remain")
    checked(LIBC.prctl(38, 1, 0, 0, 0))  # PR_SET_NO_NEW_PRIVS
    if checked(LIBC.prctl(39, 0, 0, 0, 0)) != 1:
        raise RuntimeError("no_new_privs not set")


def seccomp():
    """x86_64 syscall allowlist; every omitted syscall returns EPERM.

    No socket/connect, fork/vfork/clone/clone3, exec, ptrace, process_vm_*,
    mount, namespace, keyring, bpf, io_uring, signals to other processes, or
    capability/prctl/resource-limit mutation. In particular prlimit64 (302)
    cannot inspect or change the trusted PID 1 supervisor after limit setup.
    No alternate ABI (including x32) is accepted.
    """
    if os.uname().machine != "x86_64":
        raise RuntimeError("seccomp architecture unsupported")
    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                    ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]
    class Program(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]
    # read/write/close/stat/lseek/memory/signals/self identity/read-only filesystem,
    # clocks/sleep/futex/getrandom. Filesystem itself is entirely read-only.
    allowed = {
        0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
        19, 20, 21, 24, 25, 28, 32, 33, 35, 39, 60, 63, 72, 73,
        79, 80, 89, 96, 97, 98, 99, 102, 104, 107, 108, 110,
        131, 158, 186, 202, 217, 218, 228, 230, 231, 257, 262,
        267, 269, 273, 318, 332, 334,
    }
    instructions = [(0x20, 0, 0, 4), (0x15, 1, 0, 0xC000003E),
                    (0x06, 0, 0, 0x80000000), (0x20, 0, 0, 0)]
    for number in sorted(allowed):
        instructions += [(0x15, 0, 1, number), (0x06, 0, 0, 0x7FFF0000)]
    instructions += [(0x06, 0, 0, 0x00050000 | errno.EPERM)]
    filters = (Filter * len(instructions))(*(Filter(*i) for i in instructions))
    program = Program(len(filters), filters)
    checked(LIBC.syscall(317, 1, 0, ctypes.byref(program)))  # seccomp SET_MODE_FILTER


def resource_limits(seconds):
    limits = {
        resource.RLIMIT_CPU: (int(seconds), int(seconds) + 1),
        resource.RLIMIT_AS: (256 * 1024 * 1024,) * 2,
        resource.RLIMIT_FSIZE: (LIMIT,) * 2,
        resource.RLIMIT_NOFILE: (32,) * 2,
        resource.RLIMIT_NPROC: (1,) * 2,  # seccomp enforces this even for mapped UID 0
        resource.RLIMIT_CORE: (0, 0),
        resource.RLIMIT_STACK: (8 * 1024 * 1024,) * 2,
    }
    for which, values in limits.items():
        resource.setrlimit(which, values)
        if resource.getrlimit(which) != values:
            raise RuntimeError("resource limit verification failed")


def jail(request):
    root = request["root"]
    if (os.path.dirname(root) != request["owned"] or os.path.basename(root) != "root"
            or os.path.islink(root) or not os.path.isdir(root)):
        raise RuntimeError("invalid owned root")
    changed = namespaces()
    if any(changed[n] == request["host_namespaces"][n] for n in changed):
        raise RuntimeError("namespace separation failed")
    if os.getpid() != 1:
        raise RuntimeError("not private PID namespace init")
    mount(None, "/", flags=MS_REC | MS_PRIVATE)
    mount("tmpfs", root, "tmpfs", MS_NOSUID | MS_NODEV, "size=16m,nr_inodes=1024,mode=0755")
    runtime = "/usr/lib/python3.12"
    target = root + runtime
    os.makedirs(target)
    mount(runtime, target, flags=MS_BIND)
    mount(None, target, flags=MS_BIND | MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV)
    os.mkdir(root + "/workspace")
    for relative, source in request["sources"].items():
        # Defense in depth, independent of Windows validation.
        if (relative.startswith("/") or "\\" in relative
                or any(p in ("", ".", "..") for p in relative.split("/"))):
            raise RuntimeError("unsafe source path")
        target = Path(root, "workspace", relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    mount(None, root, flags=MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV)
    return changed


def child(request, control, stdout, stderr):
    ready_sent = False
    receipt = dict(ready=False, executed=False, stage="setup")
    # Reserved before untrusted parsing, released to report allocation exhaustion.
    emergency = bytearray(131072)
    try:
        os.dup2(stdout, 1)
        os.dup2(stderr, 2)
        os.close(0)  # no inherited JSON input or host handles
        os.chroot(request["root"])
        os.chdir("/workspace")  # never retain host cwd
        os.environ.clear()
        os.environ.update(ENV)
        sys.path[:] = ["/workspace", "/usr/lib/python3.12", "/usr/lib/python3.12/lib-dynload"]
        sys.dont_write_bytecode = True
        resource_limits(request["seconds"])
        drop_caps()
        # Negative probes are trusted and run BEFORE model code.
        try:
            with open(request["canary"], "rb"):
                raise RuntimeError("host canary visible in jail")
        except FileNotFoundError:
            pass
        for forbidden in ("/proc", "/home", "/mnt", "/run", "/dev", "/tmp"):
            if os.path.exists(forbidden):
                raise RuntimeError("forbidden host surface present: " + forbidden)
        with socket.socket() as probe:
            probe.settimeout(0.2)
            try:
                probe.connect(("127.0.0.1", request["port"]))
                raise RuntimeError("host listener reachable")
            except OSError:
                pass
        try:
            with open("/workspace/.write-probe", "w"):
                raise RuntimeError("workspace writable")
        except OSError as exc:
            if exc.errno != errno.EROFS:
                raise
        seccomp()
        # Actual forbidden syscall probes after installing the filter.
        for number in (41, 57, 272, 302):  # socket, fork, unshare, prlimit64
            if LIBC.syscall(number, 0, 0, 0, 0, 0, 0) != -1 or ctypes.get_errno() != errno.EPERM:
                raise RuntimeError("syscall filter verification failed")
        receipt = dict(ready=False, executed=False, stage="preflight", preflight_status="running",
                       no_new_privs=True, capabilities="zero",
                       seccomp="x86_64_allowlist", host_canary_hidden=True,
                       host_listener_unreachable=True, readonly_root=True,
                       no_host_proc=True, max_candidate_processes=1,
                       memory_bytes=256 * 1024 * 1024, output_bytes=LIMIT,
                       output_raw_bytes_per_stream=LIMIT,
                       output_utf8_bytes_per_stream=3 * LIMIT, serialized_reply_bytes=REPLY_LIMIT,
                       cpu_seconds=int(request["seconds"]), wall_seconds=request["seconds"])
        # Newline-delimited trusted stage records; channel closes before exec.
        os.write(control, json.dumps(receipt).encode() + b"\n")
        compiled = validate_sources(request["sources"]) if request["mode"] == "oracle" else {}
        test_or_program = compile(request["code"], "<held-out-tests>" if compiled else "<calculator>", "exec")
        receipt.update(ready=True, executed=True, stage="candidate", preflight_status="passed")
        os.write(control, json.dumps(receipt).encode() + b"\n")
        ready_sent = True
        os.closerange(3, 1024)  # close attestation channel BEFORE any model code
        if request["mode"] == "oracle":
            pure = {name: getattr(builtins, name) for name in PURE_BUILTINS}
            for path, code in compiled.items():
                module = types.ModuleType(path[:-3])
                module.__dict__["__builtins__"] = pure.copy()
                exec(code, module.__dict__)
                sys.modules[path[:-3]] = module
            exec(test_or_program, {"__builtins__": builtins.__dict__})
        else:
            exec(test_or_program, {"__name__": "__main__", "__builtins__": builtins.__dict__})
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    except BaseException as exc:
        # Error text is bounded; no host traceback/source disclosure.
        del emergency
        try:
            if not ready_sent:
                receipt["error"] = type(exc).__name__
                if receipt["stage"] == "preflight":
                    receipt["preflight_status"] = (
                        "memory_limit" if isinstance(exc, MemoryError) else
                        "rejected" if isinstance(exc, (ValueError, SyntaxError, RecursionError)) else "error"
                    )
                os.write(control, json.dumps(receipt).encode() + b"\n")
            os.write(2, (type(exc).__name__ + ": " + str(exc)[:1024] + "\n").encode())
        finally:
            os._exit(1)


def namespace_main(request):
    try:
        changed = jail(request)
    except Exception as exc:
        return dict(exit_code=None, stdout="", stderr="", timed_out=False,
                    boundary={"executed": False, "error": type(exc).__name__ + ": " + str(exc)})
    channels = [os.pipe() for _ in range(3)]
    pid = os.fork()
    if pid == 0:
        child(request, channels[0][1], channels[1][1], channels[2][1])
    selector, outputs = selectors.DefaultSelector(), [bytearray(), bytearray(), bytearray()]
    for index, (read, write) in enumerate(channels):
        os.close(write)
        os.set_blocking(read, False)
        selector.register(read, selectors.EVENT_READ, index)
    deadline, timed_out, overflow = time.monotonic() + request["seconds"], False, False
    status = None
    try:
        while selector.get_map() or status is None:
            if time.monotonic() >= deadline or overflow:
                timed_out = not overflow
                if status is None:
                    os.kill(pid, signal.SIGKILL)
                    _, status = os.waitpid(pid, 0)
                break
            for key, _ in selector.select(0.02):
                data = os.read(key.fd, 8192)
                if not data:
                    selector.unregister(key.fd)
                    os.close(key.fd)
                else:
                    outputs[key.data].extend(data)
                    if len(outputs[key.data]) > LIMIT:
                        overflow = True
            if status is None:
                waited, result = os.waitpid(pid, os.WNOHANG)
                if waited:
                    status = result
    finally:
        for key in list(selector.get_map().values()):
            # After reaping, drain pending trusted stage records even on timeout.
            # This distinguishes preflight exhaustion from candidate execution.
            try:
                while data := os.read(key.fd, 8192):
                    outputs[key.data].extend(data[:max(0, LIMIT + 1 - len(outputs[key.data]))])
            except BlockingIOError:
                pass
            os.close(key.fd)
        selector.close()
    try:
        receipt = json.loads(outputs[0].splitlines()[-1])
    except (ValueError, UnicodeDecodeError, IndexError):
        receipt = {"ready": False}
    ready = receipt.get("ready") is True
    process_exit = os.waitstatus_to_exitcode(status)
    timed_out = timed_out or process_exit == -signal.SIGXCPU
    if not ready and receipt.get("preflight_status") == "running":
        receipt["preflight_status"] = "timeout" if timed_out else "terminated"
    return dict(exit_code=(1 if overflow else process_exit) if ready else None,
                process_exit_code=process_exit,
                stdout=outputs[1][:LIMIT].decode("utf-8", "replace"),
                stderr=outputs[2][:LIMIT].decode("utf-8", "replace"),
                timed_out=timed_out, output_limit_exceeded=overflow,
                boundary=dict(receipt, executed=True if ready else receipt.get("executed"), namespaces=changed,
                              process_reaped=True, completion="waitpid"))


def emit_result(result):
    # Each 64 KiB RAW stream can become 192 KiB UTF-8 (replacement characters)
    # or 384 KiB ASCII-escaped JSON. Guard the entire serialized receipt as well.
    encoded = json.dumps(result, ensure_ascii=True)
    if len(encoded) > REPLY_LIMIT:
        raise RuntimeError("supervisor serialization budget exceeded")
    print(encoded)


def main():
    request = json.load(sys.stdin)
    if sys.version_info[:2] != (3, 12) or os.uname().machine != "x86_64":
        raise RuntimeError("only Linux x86_64 CPython 3.12 supported")
    if request.pop("namespace_child", False):
        emit_result(namespace_main(request))
        return
    helper = request.pop("helper")
    request_identity = identity(request)
    owned = tempfile.mkdtemp(prefix="tokenmaster-quality-", dir="/tmp")
    stat = os.stat(owned, follow_symlinks=False)
    root, canary = owned + "/root", owned + "/HOST_CANARY"
    process = None
    try:
        os.mkdir(root)
        Path(canary).write_text("synthetic tokenmaster host canary", encoding="ascii")
        if Path(canary).read_text() != "synthetic tokenmaster host canary":
            raise RuntimeError("host canary unavailable")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                connection, _ = listener.accept()
                connection.close()
            namespace_request = dict(request, namespace_child=True, root=root, owned=owned,
                                     canary=canary, port=port, host_namespaces=namespaces())
            command = ["/usr/bin/timeout", "--signal=KILL", "12s",
                       "/usr/bin/unshare", "--user", "--map-root-user", "--mount",
                       "--net", "--pid", "--fork", "--kill-child", "--",
                       "/usr/bin/python3", "-I", "-S", "-c", helper]
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, env=ENV, close_fds=True,
                                       start_new_session=True)
            try:
                stdout, stderr = process.communicate(json.dumps(namespace_request).encode(), timeout=14)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=1)
            if process.returncode != 0:
                result = dict(exit_code=None, stdout="", stderr=stderr.decode("utf-8", "replace")[:4096],
                              timed_out=process.returncode in (124, 137, -9),
                              boundary={"executed": None, "error": "namespace setup/supervisor failed"})
            else:
                result = json.loads(stdout)
            result["boundary"].update(host_canary_present=True, host_listener_present=True,
                                      environment="allowlisted", linux_deadline_seconds=18)
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=1)
        # Never recursively delete. Namespace-owned tmpfs vanishes with its PID 1.
        now = os.stat(owned, follow_symlinks=False)
        if (os.path.dirname(owned) != "/tmp" or not os.path.basename(owned).startswith("tokenmaster-quality-")
                or (now.st_dev, now.st_ino) != (stat.st_dev, stat.st_ino) or os.path.islink(owned)):
            raise RuntimeError("cleanup identity mismatch")
        os.rmdir(root)
        os.unlink(canary)
        os.rmdir(owned)
    result["boundary"]["scoped_cleanup"] = True
    result["request_identity"] = request_identity
    emit_result(result)


if __name__ == "__main__":
    main()
