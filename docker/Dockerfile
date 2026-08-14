# Build environment for the CangJie toolchain (compiler, runtime, stdlib, stdx).
#
# Based on the official build guide (cangjie_build/doc_en/{env,linux}.md, Ubuntu 22.04)
# and the community example https://gitcode.com/filaco/cjdev (Dockerfile).
# Interop-only extras from the example (GNUstep, JDK) are intentionally omitted.
FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# System tools per cangjie_build/doc_en/linux.md §2.2 (+ python3, git, ca-certificates)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
    ca-certificates git python3 python-is-python3 \
    tar unzip wget curl libcurl4 expat openssl make gcc g++ gettext \
    libtool sqlite3 zlib1g-dev libssl-dev cmake ninja-build \
    libcurl4-openssl-dev sudo autoconf build-essential rapidjson-dev \
    texinfo binutils libelf-dev libdwarf-dev \
    dos2unix clang clang-15 libedit-dev \
    zip bzip2 gdb libclang-15-dev libgtest-dev \
    patch libtinfo5 libncurses5 libncurses5-dev strace swig; \
    rm -rf /var/lib/apt/lists/*

# Deps missing from the official list, discovered during the build:
# - libffi-dev: cjc links against -lffi
# - python3-pexpect: cjdb LLT tests drive the debugger via pexpect
# - tzdata: std/time LLT tests need /usr/share/zoneinfo
# - clang-format-15: project code style (.clang-format), version-matched to the toolchain
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends libffi-dev python3-pexpect tzdata clang-format-15 ccache; \
    ln -sf /usr/bin/clang-format-15 /usr/local/bin/clang-format; \
    rm -rf /var/lib/apt/lists/*

# Compiler cache: cmake picks the launcher up from the environment at configure time;
# the cache lives on the bind mount so it survives containers (builds are very slow
# on this machine — ccache is the main mitigation for iterative development).
ENV CMAKE_C_COMPILER_LAUNCHER=ccache
ENV CMAKE_CXX_COMPILER_LAUNCHER=ccache
ENV CCACHE_DIR=/work/.ccache
ENV CCACHE_MAXSIZE=20G

# Environment per cangjie_build/doc_en/linux.md §2.4 (x86_64 host)
ENV OPENSSL_PATH=/usr/lib/x86_64-linux-gnu
ENV LD_LIBRARY_PATH=$OPENSSL_PATH
ENV PATH=/usr/lib/llvm-15/bin:$PATH
ENV ARCH=x86_64
ENV CANGJIE_VERSION=1.0.0
ENV STDX_VERSION=1
ENV SDK_NAME=linux-x64

# Non-root user matching the host UID/GID so bind-mounted files stay owned by the host user
ARG UID=1000
ARG GID=1000
RUN set -eux; \
    groupadd -g "$GID" cj || true; \
    useradd -m -u "$UID" -g "$GID" -s /bin/bash cj; \
    echo 'cj ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/cj

USER cj
WORKDIR /work
