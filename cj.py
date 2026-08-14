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
import os
import shlex
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGE = "cangjie-dev"
WORK = "/work"  # mount point of ROOT inside the container

_docker_ok = None


def _docker_accessible():
    """True if the docker socket is reachable directly from this process."""
    global _docker_ok
    if _docker_ok is None:
        _docker_ok = subprocess.call(
            ["docker", "info"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    return _docker_ok

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


def docker_run(script, cwd=WORK, interactive=False):
    """Run a bash script string inside the build container."""
    flags = ["-it"] if interactive else ["-i"]
    cmd = [
        "docker", "run", "--rm", *flags,
        "-v", f"{ROOT}:{WORK}",
        "-w", cwd,
        IMAGE,
        "bash", "-c", script,
    ]
    return run(cmd)


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
    jobs = f" -j {args.jobs}" if args.jobs else ""
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
    script = f"""set -ex
source {WORK}/cangjie_compiler/output/envsetup.sh
python3 build.py build -t {args.build_type} \\
    --target-lib={WORK}/cangjie_runtime/runtime/output \\
    --target-lib=$OPENSSL_PATH
python3 build.py install
cp -R output/* {WORK}/cangjie_compiler/output/
"""
    return docker_run(script, cwd=COMPONENT_DIRS["std"])


def build_stdx(args):
    script = f"""set -ex
source {WORK}/cangjie_compiler/output/envsetup.sh
python3 build.py build -t {args.build_type} \\
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
        jobs = args.jobs or 8
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
            "python3 build.py test",
            cwd=COMPONENT_DIRS["compiler"])
    print(f"error: no direct test runner wired for '{args.component}' yet; "
          "runtime/std/stdx are tested via the cangjie_test suites",
          file=sys.stderr)
    return 2


def cmd_fmt(args):
    """clang-format files changed on the current branch of a repo (vs its base)."""
    repo = args.repo
    base = args.base
    check = " --dry-run --Werror" if args.check else " -i"
    script = f"""set -e
cd {WORK}/{repo}
files=$(git diff --name-only {base} -- '*.cpp' '*.h' '*.inc' | grep -vE '^third_party/' || true)
if [ -z "$files" ]; then echo "no C/C++ changes vs {base}"; exit 0; fi
echo "$files"
echo "$files" | xargs clang-format{check}
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
                    help="parallel jobs (0 = tool default)")
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
                    help="llt only: parallel jobs (default 8)")
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
