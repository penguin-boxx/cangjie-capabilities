#!/usr/bin/env python3
"""Orchestrator for building and testing the CangJie toolchain inside docker.

All heavy work happens in the `cangjie-dev` container (Ubuntu 22.04 with the
official build deps, see docker/Dockerfile); this project directory is
bind-mounted at /work, so all sources and build artifacts live here.

Build steps follow the official guide: cangjie_build/doc_en/linux.md.

Usage examples:
    ./cj.py image                 # build the docker image
    ./cj.py sh                    # interactive shell in the container
    ./cj.py sh -- cjc -v          # run a command in the container
    ./cj.py build all             # compiler -> runtime -> std -> stdx
    ./cj.py build compiler        # one component
    ./cj.py test compiler         # compiler unittests (ctest)
    ./cj.py clean std
"""

import argparse
import errno
import fcntl
import glob
import os
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGE = "cangjie-dev"
WORK = "/work"  # mount point of ROOT inside the container
# Cores this script may use IN TOTAL, across every container it has running at once -- one short
# of the host's eight, so the desktop stays responsive. '--cpus' is a per-container cap, so two
# concurrent runs at the full budget would ask for twice the machine; the registry below divides
# this number among the live runs instead and rebalances as they come and go.
CPU_BUDGET = 7
JOBS = CPU_BUDGET  # default '-j' when a run has the budget to itself
CPU_STATE_DIR = os.path.join(tempfile.gettempdir(), f"cj-cpu-{os.getuid()}")

_docker_ok = None


def _docker_accessible():
    """True if the docker socket is reachable directly from this process."""
    global _docker_ok
    if _docker_ok is None:
        _docker_ok = subprocess.call(
            ["docker", "info"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    return _docker_ok

# Component name -> repo directory, for `fmt` (which takes a repo, not a component).
FMT_REPO_ALIASES = {
    "compiler": "cangjie_compiler",
    "runtime": "cangjie_runtime",
    "std": "cangjie_runtime",
    "stdx": "cangjie_stdx",
    "test": "cangjie_test",
    "tools": "cangjie_tools",
}

# Component -> directory with its build.py (container paths)
COMPONENT_DIRS = {
    "compiler": f"{WORK}/cangjie_compiler",
    "runtime": f"{WORK}/cangjie_runtime/runtime",
    "std": f"{WORK}/cangjie_runtime/stdlib",
    "stdx": f"{WORK}/cangjie_stdx",
}
BUILD_ORDER = ["compiler", "runtime", "std", "stdx"]


def run(cmd, **kwargs):
    # If this process lacks the docker group (no re-login since usermod),
    # route docker calls through `sg docker` which consults /etc/group directly.
    if cmd[0] == "docker" and not _docker_accessible():
        cmd = ["sg", "docker", "-c", shlex.join(cmd)]
    print(f"+ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, **kwargs)


class _CpuRegistry:
    """CPU_BUDGET shared across every concurrent cj.py container.

    Each live container owns a slot file naming it and the pid that launched it. Joining and
    leaving recompute an equal share and push it onto the containers already running with
    'docker update', so a build started beside a long test run halves both rather than
    oversubscribing the host. Slots whose launcher died are pruned on the next join.
    """

    def __init__(self, name):
        self.name = name
        self.slot = os.path.join(CPU_STATE_DIR, f"{name}.slot")

    def _locked(self):
        os.makedirs(CPU_STATE_DIR, exist_ok=True)
        fd = os.open(os.path.join(CPU_STATE_DIR, "lock"), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    @staticmethod
    def _unlock(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    @staticmethod
    def _alive(pid):
        try:
            os.kill(pid, 0)
        except OSError as e:
            return e.errno == errno.EPERM
        return True

    def _live_slots(self):
        """Slot paths whose launching process still exists; the rest are removed."""
        live = []
        for path in sorted(glob.glob(os.path.join(CPU_STATE_DIR, "*.slot"))):
            try:
                with open(path) as f:
                    pid = int(f.read().strip() or "0")
            except (OSError, ValueError):
                pid = 0
            if pid and self._alive(pid):
                live.append(path)
            else:
                _quiet_unlink(path)
        return live

    def _rebalance(self, slots):
        """Give every live container an equal share, skipping the one that is not up yet."""
        share = max(0.5, round(CPU_BUDGET / max(1, len(slots)), 2))
        for path in slots:
            other = os.path.basename(path)[: -len(".slot")]
            if other == self.name:
                continue
            # A container that has already exited is not an error: its slot goes on the next pass.
            subprocess.call(["docker", "update", f"--cpus={share}", other],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return share

    def join(self):
        fd = self._locked()
        try:
            slots = self._live_slots()
            with open(self.slot, "w") as f:
                f.write(str(os.getpid()))
            slots.append(self.slot)
            return self._rebalance(slots)
        finally:
            self._unlock(fd)

    def leave(self):
        fd = self._locked()
        try:
            _quiet_unlink(self.slot)
            self._rebalance(self._live_slots())
        finally:
            self._unlock(fd)


def _quiet_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


_run_seq = 0


def docker_run(script, cwd=WORK, interactive=False):
    """Run a bash script string inside the build container, on this run's share of CPU_BUDGET."""
    global _run_seq
    _run_seq += 1
    name = f"cj-{os.getpid()}-{_run_seq}"
    registry = _CpuRegistry(name)
    share = registry.join()
    flags = ["-it"] if interactive else ["-i"]
    cmd = [
        "docker", "run", "--rm", *flags,
        "--name", name,
        # Hard cap: whatever a build tool decides internally, this container cannot exceed its
        # share -- which the registry raises again as the other runs finish.
        f"--cpus={share}",
        "-v", f"{ROOT}:{WORK}",
        "-w", cwd,
        IMAGE,
        "bash", "-c", script,
    ]
    try:
        return run(cmd)
    finally:
        registry.leave()


def sh_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------- subcommands

def cmd_image(args):
    return run(["docker", "build", "-t", IMAGE,
                "--build-arg", f"UID={os.getuid()}",
                "--build-arg", f"GID={os.getgid()}",
                os.path.join(ROOT, "docker")])


def cmd_sh(args):
    if args.cmd:
        script = " ".join(args.cmd)
        return docker_run(script, interactive=False)
    return docker_run("bash", interactive=True)


def build_compiler(args):
    jobs = f" -j {args.jobs or JOBS}"
    link_jobs = f" --link-jobs {args.link_jobs}" if args.link_jobs else ""
    tests = " --no-tests" if args.no_tests else ""
    script = f"""set -ex
python3 build.py build -t {args.build_type} -v $CANGJIE_VERSION{jobs}{link_jobs}{tests}
python3 build.py install
"""
    return docker_run(script, cwd=COMPONENT_DIRS["compiler"])


def build_runtime(args):
    script = f"""set -ex
python3 build.py build -t {args.build_type} -v $CANGJIE_VERSION
python3 build.py install
cp -R output/common/linux_{args.build_type}_$ARCH/lib     {WORK}/cangjie_compiler/output/
cp -R output/common/linux_{args.build_type}_$ARCH/runtime {WORK}/cangjie_compiler/output/
"""
    return docker_run(script, cwd=COMPONENT_DIRS["runtime"])


def build_std(args):
    # The stdlib sources carry `throws` clauses (migration phase 2), which only parse with the
    # feature enabled; warn severity keeps not-yet-annotated flows building. Permanent since the
    # first clause landed -- building without these flags fails at parse.
    script = f"""set -ex
source {WORK}/cangjie_compiler/output/envsetup.sh
python3 build.py build -t {args.build_type} \\
    --build-args=--experimental --build-args=--enable-checked-exceptions=warn \\
    --target-lib={WORK}/cangjie_runtime/runtime/output \\
    --target-lib=$OPENSSL_PATH
python3 build.py install
# Stream the tree instead of copying: `cp -R`/`cp -RL` across this bind mount has been
# observed to die with SIGSEGV part-way, leaving the SDK half-updated.
(cd output && tar cf - .) | (cd {WORK}/cangjie_compiler/output && tar xf -)
"""
    return docker_run(script, cwd=COMPONENT_DIRS["std"])


def build_stdx(args):
    # Same flags as std: stdx is the next migration ring, so it builds with checking on at `warn`
    # severity -- every capability a public stdx API needs is reported, nothing blocks the build.
    script = f"""set -ex
source {WORK}/cangjie_compiler/output/envsetup.sh
python3 build.py build -t {args.build_type} \\
    --build-args=--experimental --build-args=--enable-checked-exceptions=warn \\
    --include={WORK}/cangjie_compiler/include \\
    --target-lib=$OPENSSL_PATH
python3 build.py install
"""
    return docker_run(script, cwd=COMPONENT_DIRS["stdx"])


BUILDERS = {
    "compiler": build_compiler,
    "runtime": build_runtime,
    "std": build_std,
    "stdx": build_stdx,
}


def cmd_build(args):
    components = BUILD_ORDER if args.component == "all" else [args.component]
    for c in components:
        print(f"\n=== building {c} ===", flush=True)
        rc = BUILDERS[c](args)
        if rc != 0:
            print(f"error: build of {c} failed (exit {rc})", file=sys.stderr)
            return rc
    return 0


def cmd_test(args):
    if args.component == "llt":
        # cangjie_test LLT suite via the maple test framework, against the built SDK.
        # A custom testlist (e.g. one produced with --filter) narrows the run.
        testlist = f"{WORK}/cangjie_test/testsuites/LLT/cjnative_testlist"
        if args.filter:
            os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
            # Inherit the stock exclude section so known-broken cases stay skipped.
            stock = os.path.join(ROOT, "cangjie_test/testsuites/LLT/cjnative_testlist")
            with open(stock) as f:
                stock_lines = f.read().splitlines()
            exclude_start = stock_lines.index("[EXCLUDE-TEST-CASE]")
            with open(os.path.join(ROOT, "logs", "llt_filtered_testlist"), "w") as f:
                f.write("[ALL-TEST-CASE]\n")
                for entry in args.filter:
                    f.write(entry + "\n")
                f.write("\n".join(stock_lines[exclude_start:]) + "\n")
            testlist = f"{WORK}/logs/llt_filtered_testlist"
        jobs = args.jobs or JOBS
        # Unique temp dir per run: permission-test cases leave chmod-000 dirs behind,
        # which crash the framework's end-of-run rmtree on a reused dir.
        run_id = time.strftime("%Y%m%d-%H%M%S")
        temp_dir = f"{WORK}/logs/llt_temp/{run_id}"
        return docker_run(
            f"source {WORK}/cangjie_compiler/output/envsetup.sh && "
            f"export LD_LIBRARY_PATH={WORK}/cangjie_compiler/output/third_party/llvm/lib:$LD_LIBRARY_PATH && "
            # stdx tests import stdx and load its AOP plugins from $CANGJIE_STDX_PATH
            # (official guide §4.4); dynamic/ is the dir with the plugin .so files.
            f"export CANGJIE_STDX_PATH={WORK}/cangjie_stdx/target/linux_x86_64_cjnative/dynamic/stdx && "
            f"export LD_LIBRARY_PATH=$CANGJIE_STDX_PATH:$LD_LIBRARY_PATH && "
            f"mkdir -p {temp_dir} && "
            f"python3 {WORK}/cangjie_test_framework/main.py "
            f"--test_cfg={WORK}/cangjie_test/testsuites/LLT/configs/cjnative/cjnative_test.cfg "
            f"{WORK}/cangjie_test/testsuites/LLT "
            f"--test_list={testlist} "
            f"--fail-verbose -pFAIL -j{jobs} "
            f"--temp_dir={temp_dir}",
            cwd=WORK)
    if args.component == "compiler":
        # Requires a build without --no-tests. envsetup puts cjc on PATH and the
        # patched LLVM on LD_LIBRARY_PATH (macro tests shell out to cjc; codegen
        # tests dlopen the installed frontend lib).
        # Also prefer the SDK's patched LLVM over the system one: envsetup does not
        # add it, and unittest binaries (unlike cjc) carry no rpath to it.
        return docker_run(
            f"source {WORK}/cangjie_compiler/output/envsetup.sh && "
            f"export LD_LIBRARY_PATH={WORK}/cangjie_compiler/output/third_party/llvm/lib:$LD_LIBRARY_PATH && "
            # Half the jobs, not JOBS: every MacroTest case shells out to cjc, which parallelises
            # internally, so ctest -j{JOBS} on a {JOBS}-CPU container oversubscribes and
            # MacroTest.NoErrorInLSPMacro fails spuriously (it passes alone and at -j4).
            f"CTEST_PARALLEL_LEVEL={max(1, JOBS // 2)} python3 build.py test",
            cwd=COMPONENT_DIRS["compiler"])
    print(f"error: no direct test runner wired for '{args.component}' yet; "
          "runtime/std/stdx are tested via the cangjie_test suites",
          file=sys.stderr)
    return 2


def cmd_fmt(args):
    """clang-format only the LINES changed vs the base (not whole files).

    Whole-file formatting reformats pre-existing upstream code and floods every commit
    with unrelated hunks (see notes/format-history-rewrite-map.md for the cleanup this
    forced). Ranges come from `git diff -U0`; a freshly added file is one big range, so
    new code is still formatted in full.
    """
    # Component names are what every other subcommand takes, and passing one here used to
    # format nothing at all: the script would cd into a nonexistent '/work/compiler', land in
    # the workdir repo, and report "no C/C++ changes".
    repo = FMT_REPO_ALIASES.get(args.repo, args.repo)
    base = args.base
    check = " --dry-run --Werror" if args.check else " -i"
    # Raw: the awk program contains '\+', which is a regex escape, not a Python one.
    script = rf"""set -e
if [ ! -d {WORK}/{repo}/.git ]; then
  echo "error: {repo} is not a repo under the workdir" >&2
  exit 2
fi
cd {WORK}/{repo}
files=$(git diff --name-only {base} -- '*.cpp' '*.h' '*.inc' | grep -vE '^third_party/' || true)
if [ -z "$files" ]; then echo "no C/C++ changes vs {base}"; exit 0; fi
for f in $files; do
  ranges=$(git diff -U0 {base} -- "$f" | awk '
    /^@@/ {{
      plus = $3; sub(/^\+/, "", plus);
      n = split(plus, a, ",");
      start = a[1]; count = (n > 1 ? a[2] : 1);
      if (count > 0) printf " --lines=%d:%d", start, start + count - 1;
    }}')
  if [ -n "$ranges" ]; then
    echo "$f$ranges"
    clang-format{check} $ranges "$f"
  fi
done
echo FORMAT_OK
"""
    return docker_run(script, cwd=f"{WORK}/{repo}")


def cmd_clean(args):
    components = BUILD_ORDER if args.component == "all" else [args.component]
    rc = 0
    for c in components:
        rc = docker_run("python3 build.py clean", cwd=COMPONENT_DIRS[c]) or rc
    return rc


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="subcommand", required=True)

    sp = sub.add_parser("image", help="build the docker image")
    sp.set_defaults(func=cmd_image)

    sp = sub.add_parser("sh", help="shell or command inside the container")
    sp.add_argument("cmd", nargs="*", help="command to run (interactive shell if omitted)")
    sp.set_defaults(func=cmd_sh)

    sp = sub.add_parser("build", help="build a component (official build order for 'all')")
    sp.add_argument("component", choices=[*BUILD_ORDER, "all"])
    sp.add_argument("-t", "--build-type", default="release",
                    choices=["release", "debug", "relwithdebinfo"])
    sp.add_argument("-j", "--jobs", type=int, default=0,
                    help="parallel jobs (0 = {JOBS}, leaving a core free)".replace("{JOBS}", str(JOBS)))
    sp.add_argument("--link-jobs", type=int, default=2,
                    help="parallel link jobs for the compiler build (default 2, "
                         "linking LLVM is memory-hungry)")
    sp.add_argument("--no-tests", action="store_true",
                    help="compiler only: skip building unittests")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("test", help="run tests for a component")
    sp.add_argument("component", choices=[*BUILD_ORDER, "llt"])
    sp.add_argument("--filter", nargs="+", default=None,
                    help="llt only: testlist entries (dirs or .cj paths relative to "
                         "cangjie_test/testsuites/LLT) to run instead of the full list")
    sp.add_argument("-j", "--jobs", type=int, default=0,
                    help="llt only: parallel jobs (default {JOBS})".replace("{JOBS}", str(JOBS)))
    sp.set_defaults(func=cmd_test)

    sp = sub.add_parser("clean", help="clean build artifacts")
    sp.add_argument("component", choices=[*BUILD_ORDER, "all"])
    sp.set_defaults(func=cmd_clean)

    sp = sub.add_parser("fmt", help="clang-format files changed on a repo's branch")
    sp.add_argument("repo", nargs="?", default="cangjie_compiler",
                    help="repo dir under the workdir (default cangjie_compiler)")
    sp.add_argument("--base", default="origin/main",
                    help="diff base for changed-file detection (default origin/main)")
    sp.add_argument("--check", action="store_true",
                    help="report violations instead of rewriting files")
    sp.set_defaults(func=cmd_fmt)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
