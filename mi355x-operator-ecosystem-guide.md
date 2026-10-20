# MI355X 算子开发：AITER / CK / CK Tile / FlyDSL / Gluon

核查日期：2026-10-16（北京时间）。以下依据官方仓库、具体 tag 的安装脚本、发布资产、CI 配置和 AMD 文档整理；版本是本次查询快照。安装命令供目标 Linux MI355X 环境执行，本次未在你的 GPU 上编译或跑性能。

> 建议：以 AITER 的固定版本建立算子集成基线；开发 C++ kernel 看 CK Tile，开发 Python kernel 比较 Triton/Gluon 与 FlyDSL。把独立编译器实验放进另一个环境。本文中的 Gluon 指 Triton 的实验性 GPU 编程入口。

## 1. 先把五个名字放对位置

| 名称与官方入口 | 实际是什么 | 维护状态与快照证据 | 对 MI355X 的意义 |
|---|---|---|---|
| [AITER](https://github.com/ROCm/aiter) | AI Tensor Engine for ROCm；多后端算子库、Python 接口与集成层 | 活跃；最新发布 v0.1.25（10-12）；10-16 仍在更新 MI355 MLA kernel | 提供现成 attention、MoE、GEMM、norm 等 baseline，也适合把优化结果接回推理框架 |
| [CK / Composable Kernel](https://github.com/ROCm/rocm-libraries/tree/develop/projects/composablekernel) | HIP/C++ 模板算子和组合组件工程 | 活跃；代码迁入 rocm-libraries；CK 路径 10-15 有提交 | 深入 C++ kernel、pipeline、MFMA 与数据搬运；已有大量算子实现 |
| [CK Tile](https://github.com/ROCm/rocm-libraries/tree/develop/projects/composablekernel/include/ck_tile) | CK 工程中的 tile 编程体系；包括 include/ck_tile、example/ck_tile 等 | 活跃；10-14 有 CK Tile 修复；**不是一个独立版本库** | 更显式地组合 tile、分布、pipeline、LDS 和寄存器布局 |
| [FlyDSL](https://github.com/ROCm/FlyDSL) | Python DSL + 独立 Fly dialect / MLIR 编译栈 | 活跃；v0.4.0（10-14）；10-16 有依赖匹配修复 | 显式 layout algebra、tiling、MFMA；有 gfx950 GEMM/MoE 测试与 MI35x CI |
| [Gluon](https://github.com/triton-lang/triton/tree/main/python/triton/experimental/gluon) | Triton 内部的另一种 kernel 编程入口 | 活跃；随 Triton 发布，稳定版 v3.8.0（08-28）；Gluon 10-16 仍有更新 | 比普通 Triton 更显式地控制 layout、shared memory、异步操作；有 AMD CDNA4 API |

**CK 旧仓库的 Deprecated 不等于 CK 停止维护。** [ROCm/composable_kernel](https://github.com/ROCm/composable_kernel) 的说明已明确迁移到 rocm-libraries，旧 develop 为只读镜像。新贡献看 monorepo；AITER 仍通过旧地址固定 CK 子模块 commit，这是正常的版本锁定方式。

**Gluon 不要单独 `pip install gluon`。** 正确入口是 `from triton.experimental import gluon`，它也不是 MXNet 的 Gluon。

来源：[AITER 快照](https://github.com/ROCm/aiter/blob/d81d17e302e5882140864c3bc605fe8b8964343e/README.md)、[AITER 发布](https://github.com/ROCm/aiter/releases/tag/v0.1.25)、[FlyDSL 发布](https://github.com/ROCm/FlyDSL/releases/tag/v0.4.0)、[Triton 发布](https://github.com/triton-lang/triton/releases/tag/v3.8.0)。

## 2. 依赖图：它们不是一条串起来的链

```text
上层：PyTorch / 推理引擎 / 你的算子调用方
                          │
                          ▼
                AITER：算子接口、dispatch、测试、集成
                   │        │          │          │
                   ▼        ▼          ▼          ▼
              CK / CK Tile  Triton     FlyDSL    HIP / ASM / Opus
                   │        ├─ Triton语言   │
                   │        └─ Gluon语言   │
                   ▼             ▼        ▼
             ROCm HIP Clang   Triton编译器  Fly dialect / MLIR
                   │             │        │
                   └──── 各自工具链生成 AMD GPU code ────┘
                                      │
                              HIP / HSA / AMDGPU 驱动
                                      │
                            AMD MI355X：CDNA4 / gfx950
```

图中的 AITER 后端是按算子与调用路径选择的，不意味着一次调用经过所有后端。CK Tile、Triton/Gluon、FlyDSL 也能独立写算子，不必经过 AITER。

| 关系 | 是硬依赖吗？ | 怎样理解 |
|---|---|---|
| CK Tile → CK 工程 | 同一源码工程 | 不用再找一个独立 cktile wheel；版本跟随所选 CK commit |
| Gluon → Triton | 是，同包/同编译基础设施 | 锁 Triton 发行物与 commit，就是锁 Gluon 的 API 与编译器 |
| AITER → CK | 默认 CK 后端使用固定 submodule | 通常无需另装一个系统 CK；`CK_DIR` 覆盖才是主动替换依赖 |
| AITER → FlyDSL | 当前 Linux 完整安装是必需依赖 | v0.1.25 与 main 的 pin 不同；旧资料中的 optional 已不能照搬 |
| AITER → Triton | Triton/Gluon 路径需要匹配版本 | 当前安装脚本选择 AMD 构建，而非任意同号上游 wheel |
| FlyDSL → Triton/CK | 核心编译器不是以它们为后端 | 设计借鉴不等于链接依赖；部分测试/复杂 kernel/baseline 可能用 AITER/Triton |
| FlyDSL → MLIR Python 包 | 内嵌绑定 | wheel 自带 MLIR bindings；无需额外找通用 `pip install mlir` |
| CK → PyTorch | 独立 C++ 使用通常不需要 | Python 主要用于构建/代码生成；通过 AITER 接入时才涉及 PyTorch 集成 |

## 3. 版本匹配：优先锁上层项目的依赖

### 3.1 AITER：发行版与 main 必须分开

| 组件 | 固定发行版方案 | 当前开发快照方案 |
|---|---|---|
| AITER | v0.1.25，`c53e9b3f4285c36ea785e614ce5cf8b04c78b3bd` | main 快照 `d81d17e302e5882140864c3bc605fe8b8964343e` |
| CK 子模块 | `96afae1d54fc79c26857de7e1683b0dde1ff3c6f` | 相同 |
| FlyDSL | **0.3.4.1** | **0.4.0** |
| Triton 安装脚本 | `triton==3.8.0`，AMD release_0914 索引 | 相同 |
| ROCm 7.2 对应实际 Triton wheel | `3.8.0+amd.rocm7.2.0.git7cb7b059` | 相同 |
| triton-kernels | 1.0.0 | 相同 |
| Python | 源码声明 ≥3.10；该发布 wheel 为 cp310/cp312 | 源码声明 ≥3.10 |
| ROCm wheel 档位 | 7.0 / 7.1 / 7.2；预编译目标 gfx942/gfx950 | 源码构建按环境与分支配置 |

**这是一张源码依赖表，不是任意硬件/模型/shape 的完整认证矩阵。** `3.8.0+amd...` 与 PyPI 上游 `3.8.0` 不能仅凭主版本号相同就当成等价产物。

PyTorch 关系尤其容易误解：

- AITER 的 Triton 安装脚本遇到 `torch < 2.9.1` 会跳过 Triton 替换，提示升级；这不是“任意 torch ≥2.9.1 都支持”。
- v0.1.25 release workflow 默认设置 `torch < 2.13`，并记录 2.13 的 custom-op 名称处理兼容问题。这个上界是构建配置证据，也不是对整个区间的全面验证。
- `AITER_USE_SYSTEM_TRITON=1` 只表示保留现有 Triton，**不代表自动验证兼容**。
- setup.py 可能捕获 Triton 安装异常后继续；因此安装命令成功不等于目标算子已经可用。

证据：[v0.1.25 requirements](https://github.com/ROCm/aiter/blob/v0.1.25/requirements.txt)、[v0.1.25 setup](https://github.com/ROCm/aiter/blob/v0.1.25/setup.py)、[main setup 快照](https://github.com/ROCm/aiter/blob/d81d17e302e5882140864c3bc605fe8b8964343e/setup.py)、[Triton 安装脚本](https://github.com/ROCm/aiter/blob/v0.1.25/.github/scripts/install_triton.sh)、[发布工作流](https://github.com/ROCm/aiter/blob/v0.1.25/.github/workflows/aiter-release.yaml)。

### 3.2 CK / CK Tile：ROCm release tag、源码版本号、AITER pin 是三件事

| 场景 | 应固定什么 | 已观察到的要求 |
|---|---|---|
| 在 AITER 里修改/测试 CK 算子 | AITER 的 CK gitlink SHA | 不先升级到 CK develop；否则同时改变了两个变量 |
| 独立 CK，基底 ROCm 7.2.4 | monorepo `rocm-7.2.4` tag | CK 1.2.0；CMake 文件声明 ≥3.14，但 HIP 语言支持实际建议 ≥3.21；Python ≥3.8；默认 C++20 |
| 追踪 CK 新特性 | monorepo develop 的固定 SHA + 对应工具链 | 本次快照 CK 1.3.0；CMake ≥3.21；Python ≥3.8；默认 C++20 |
| 参考当前新 SDK 构建 | 查看所选版本 Dockerfile / TheRock 配置 | develop Dockerfile 已出现 Core SDK 10.1 默认值；不是继续沿用所有 7.2.4 条件 |

monorepo 同时有 `rocm-7.2.4` 与 `therock-10.1` 发布系列。不要把旧仓库显示的 7.2.4 当成整个生态的“最新版本”，也不要把 CK 的 1.2.0/1.3.0 当作 ROCm 版本号。

官方建议：非新特性开发场景，选择与已安装 ROCm 匹配的分支/版本。新的 SDK 配置并不自动证明某个旧编译器绝对不能构建；要以具体 tag 的构建与测试为准。

来源：[CK monorepo](https://github.com/ROCm/rocm-libraries/tree/develop/projects/composablekernel)、[7.2.4 CMake](https://github.com/ROCm/rocm-libraries/blob/rocm-7.2.4/projects/composablekernel/CMakeLists.txt)、[CK 当前源码安装指南](https://github.com/ROCm/rocm-libraries/blob/b3eca66013cc3e77c6f1147836dd2c0cfbd237e8/projects/composablekernel/docs/install/Composable-Kernel-build.rst)。

### 3.3 FlyDSL / Gluon：不要混用 main 的代码与 stable 的编译器

| 项目 | 可复现选择 | 关键匹配点 |
|---|---|---|
| 独立 FlyDSL 实验 | `flydsl==0.4.0` + FlyDSL v0.4.0 源码 | 发布 wheel 为 Linux x86_64 CPython 3.10–3.14；例子/部分 kernels 不包含在 wheel 中 |
| AITER v0.1.25 内的 FlyDSL | `flydsl==0.3.4.1` | 遵循 AITER pin，不套用独立实验的 0.4.0 |
| 独立上游 Gluon 实验 | Triton v3.8.0 wheel + 同 tag 教程 | Gluon 在 experimental 命名空间，API 仍会变化 |
| AITER 的 Gluon 算子 | AITER 对应 AMD Triton 构建 | 使用 AITER 的安装脚本与代码；不拿上游同号 wheel 直接替代 |
| FlyDSL 源码编译 LLVM | v0.4.0 锁 `e2a39f504fee836e4def9581bed817ecc327b9dc` + 该 tag 的补丁 | 当前 main 即使 LLVM hash 相同，补丁集也可能变化 |
| Triton v3.8.0 源码编译 LLVM | `5f07f818b51b786b0a87b4e514882600ecba112f` | 按 Triton 自己的 llvm-info，不复用 FlyDSL 的 LLVM |

FlyDSL 当前 CI 观察到 ROCm 7.2.4 / Ubuntu 24.04 / Python 3.12 / PyTorch 2.10.0 镜像；这是一个 CI 配置事实，不是要求所有用户升级 PyTorch。10-16 的 [FlyDSL 修复](https://github.com/ROCm/FlyDSL/commit/0653ff888bad3787c759eabeeeefbfa1aa2df50b) 正是在 CI 中运行 AITER 的 Triton 安装脚本，解决两者 API 不匹配。

Gluon 3.8.0 已有 CDNA4 `mfma_scaled` 等 API，但当前 main 的 `scaled_downcast` 等新接口不能假定稳定版也具备。NVIDIA TMA/WGMMA/tcgen05 教程也不能原样用于 MI355X。

来源：[FlyDSL v0.4.0 README](https://github.com/ROCm/FlyDSL/blob/v0.4.0/README.md)、[FlyDSL LLVM pin](https://github.com/ROCm/FlyDSL/blob/v0.4.0/thirdparty/llvm-build-info.json)、[Gluon stable CDNA4](https://github.com/triton-lang/triton/blob/v3.8.0/python/triton/experimental/gluon/language/amd/cdna4/__init__.py)、[Triton LLVM pin](https://github.com/triton-lang/triton/blob/v3.8.0/cmake/llvm-info.json)。

## 4. 推荐基底：先把 ROCm / PyTorch / gfx950 对齐

**候选复现基底：Ubuntu 24.04 + ROCm 7.2.4 + Python 3.12 + AMD PyTorch 2.9.1 容器。** AMD 固定版本文档列出了这个组合，本次也查询 Docker Hub 确认标签与 digest 存在。接上前述 AITER v0.1.25 pin 是有源码依据的安装配方，但还需要在你的机器做算子验收。

```bash
# 在有可用 AMDGPU 驱动的 MI355X Linux 主机上执行。
# 镜像内提供 userspace 工具链；容器不会替你安装宿主机内核驱动。
AI_IMAGE='rocm/pytorch@sha256:7fe531fa185af260352fe7fbb3fa64ad749abe72adf0600a648c4692801b125a'
docker pull "$AI_IMAGE"
docker run --rm -it \
  --device=/dev/kfd --device=/dev/dri \
  --group-add video --group-add render \
  --shm-size=16g \
  "$AI_IMAGE" bash
```

该 digest 对应标签 `rocm7.2.4_ubuntu24.04_py3.12_pytorch_release_2.9.1`。如果宿主机/镜像没有 `render` 组，按 `/dev/dri/renderD*` 的实际数字 GID 配置组权限。保留项目文件时，在 `docker run` 中另挂载自己的工作目录。

同一套环境至少核对这五层：宿主驱动支持 MI355X；容器/系统 ROCm userspace；ROCm 版 PyTorch；HIP 编译器支持 gfx950；AITER/DSL 依赖满足所选代码。驱动与 userspace 不必所有小版本逐字一致，但需要落在 AMD 支持的组合里。

```bash
rocminfo | rg 'Name:.*gfx950|Marketing Name'
/opt/rocm/bin/hipcc --version
python3 - <<'PY'
import sys, torch
print('python:', sys.version)
print('torch:', torch.__version__, 'HIP:', torch.version.hip)
assert torch.version.hip is not None, '当前并非 ROCm PyTorch'
assert torch.cuda.is_available(), 'GPU 不可用：检查驱动、设备映射和权限'
p = torch.cuda.get_device_properties(0)
print('device:', p.name, 'arch:', p.gcnArchName)
assert 'gfx950' in p.gcnArchName, '不是当前指南预期的 MI355X/gfx950 目标'
PY
```

`torch.cuda` 在 ROCm PyTorch 中仍是正常接口名。不要用 `HSA_OVERRIDE_GFX_VERSION` 把其他架构伪装成 gfx950 来绕过版本匹配。

来源：[固定 ROCm 7.2.4 兼容矩阵](https://rocm.docs.amd.com/en/docs-7.2.4/compatibility/compatibility-matrix.html)、[固定版本 PyTorch 安装说明](https://rocm.docs.amd.com/projects/install-on-linux/en/docs-7.2.4/install/3rd-party/pytorch-install.html)、[镜像标签](https://hub.docker.com/layers/rocm/pytorch/rocm7.2.4_ubuntu24.04_py3.12_pytorch_release_2.9.1/images/sha256-7fe531fa185af260352fe7fbb3fa64ad749abe72adf0600a648c4692801b125a)。

## 5. 安装 AITER：算子开发优先源码模式

以下在独立开发容器中执行。安装脚本会替换 Triton 发行物；先固定基底，再固定 AITER，而不是在现有生产环境直接升级。

```bash
git clone --branch v0.1.25 --recursive https://github.com/ROCm/aiter.git
cd aiter
git rev-parse HEAD
git submodule status
# HEAD: c53e9b3f4285c36ea785e614ce5cf8b04c78b3bd
# CK:   96afae1d54fc79c26857de7e1683b0dde1ff3c6f

python3 -m pip install -r requirements.txt
bash .github/scripts/install_triton.sh

# 已在上一行安装匹配 Triton，保留它；默认按需 JIT。
# 8 只是示例编译并行度，按 CPU 内存调整。
export GPU_ARCHS=gfx950
export MAX_JOBS=8
AITER_USE_SYSTEM_TRITON=1 python3 setup.py develop

python3 -m pip check
python3 op_tests/test_rmsnorm2d.py --dtype bf16 --m 32 --n 4096
```

需要理解的细节：

- 脚本把 ROCm 7.2.4 归到 `rocm-7.2.0` 的 AMD Triton 索引，这是它按 major.minor 选轮子的设计；不是要求把机器降成 7.2.0。
- 它先清理 `triton`、`pytorch-triton-rocm`、`triton-rocm`、`amd-triton` 等同名模块发行物，再安装目标版本。安装后同时记录 distribution 名称、完整版本和 import 路径。
- `pip check` 若提示 PyTorch 的 Triton 元数据依赖冲突，应记录并核对所选构建，不能用 `pip install -U` 一把覆盖回去。
- 默认 `PREBUILD_KERNELS=0`；算子首次调用可能 JIT。先验收少量目标算子，不一开始预编译所有后端和架构。
- RMSNorm 测试的命令行参数已按 v0.1.25 源码核对；通过它只能说明这条算子路径可用，不代表 GEMM/MoE/attention 全覆盖。

若缺 CK 子模块，在 AITER 根目录运行 `git submodule update --init --recursive`。不要执行 `git submodule update --remote` 把固定依赖追到最新。

只使用预编译库时，可取 [v0.1.25 发布资产](https://github.com/ROCm/aiter/releases/tag/v0.1.25)。包名是 **amd-aiter**，导入名是 **aiter**。例如本基底应选 ROCm7.2 + cp312 + x86_64 的 wheel：

```bash
# 与源码安装二选一；在已装好同 tag requirements 和匹配 Triton 后执行。
python3 -m pip install 'https://github.com/ROCm/aiter/releases/download/v0.1.25/amd_aiter-0.1.25%2Brocm7.2.manylinux.2.28-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl'
```

wheel 安装不等于执行源码 `install_triton.sh`。如果需要最新 MI355 优化，可以换到上表指定 main SHA，再重新同步 submodule 并按该 commit 安装依赖；不要保留 v0.1.25 的 FlyDSL pin。

## 6. 安装 CK / CK Tile：独立 C++ 开发路线

如果只用 AITER 的 CK 算子，本节可以跳过。若要直接开发 CK Tile，则独立 checkout，和 AITER 子模块分开管理。

下面以 ROCm 7.2.4 对应源码为例，只构建一个已存在的 CK Tile GEMM target：

```bash
git clone --filter=blob:none --no-checkout https://github.com/ROCm/rocm-libraries.git
cd rocm-libraries
git sparse-checkout init --cone
git sparse-checkout set projects/composablekernel
git checkout rocm-7.2.4
git rev-parse HEAD
# 应为 dabb6df2b988f8eabed1e2fecefaaf4e818bc7ef
cd projects/composablekernel

cmake -S . -B build-mi355 -G Ninja \
  -DCMAKE_PREFIX_PATH=/opt/rocm \
  -DCMAKE_CXX_COMPILER=/opt/rocm/llvm/bin/clang++ \
  -DCMAKE_BUILD_TYPE=Release \
  -DGPU_TARGETS=gfx950 \
  -DBUILD_TESTING=OFF \
  -DENABLE_CLANG_CPP_CHECKS=OFF

cmake --build build-mi355 --target tile_example_gemm_basic -j 8
```

目标名已在该 tag 的 `example/ck_tile/03_gemm/CMakeLists.txt` 中核实。具体可执行文件参数看同 tag 的 [GEMM README](https://github.com/ROCm/rocm-libraries/blob/rocm-7.2.4/projects/composablekernel/example/ck_tile/03_gemm/README.md)，选择支持的 shape/dtype 后运行验证。这里只做源文件级核对，未执行 CMake/GPU 编译。

注意三个不同的变量语境：

- AITER 常用 `GPU_ARCHS=gfx950` 环境变量。
- CK 例子/测试用 CMake `-DGPU_TARGETS=gfx950`。
- CK 自己的 `GPU_ARCHS` 构建路径有不同语义；当前源码指南指出它用于跨架构族库构建，会清空 `GPU_TARGETS` 并跳过例子/测试。不要把 AITER 的配置直接照抄成 CK 参数。

CK 不一定要 `make install`。开发阶段直接使用源码 headers 和 build 产物更容易跟踪版本。若确需安装，先显式设置项目私有 `CMAKE_INSTALL_PREFIX`，避免覆盖系统 `/opt/rocm`。完整模板实例构建很重；先限定 gfx950 和目标 target，再调整并行度。

典型阅读入口：`include/ck_tile/core/` → `include/ck_tile/ops/` → `example/ck_tile/03_gemm/`。旧 CK 的 device operator/instance 体系与 CK Tile 共存；“Tile 更新”不意味着旧实现完全失去价值。

## 7. 安装 FlyDSL：写 kernel 与改编译器分开

### 7.1 只写 Python kernel：通常装 wheel 即可

在独立实验环境，使用当前发布版：

```bash
python3 -m pip install --index-url https://pypi.org/simple 'flydsl==0.4.0'
python3 - <<'PY'
import flydsl
from flydsl._mlir.ir import Context
print(flydsl.__version__, flydsl.__file__)
PY

# wheel 不包含全部源码例子/kernels，取匹配的源码版本。
git clone --branch v0.4.0 --depth 1 https://github.com/ROCm/FlyDSL.git
cd FlyDSL
python3 examples/01-vectorAdd.py
```

前置条件是已有可用的 ROCm PyTorch；`pip install flydsl` 不负责给你装 PyTorch。当前发布 wheel 内嵌 MLIR bindings。若处于 AITER v0.1.25 环境，用其锁定的 **0.3.4.1**，而不是运行上面的 0.4.0 命令。

### 7.2 改 MLIR pass / lowering：再做源码编译

```bash
# 在前述独立 FlyDSL v0.4.0 checkout 中执行。
python3 -m pip install 'cmake>=3.20' ninja 'nanobind>=2.9,<3' numpy pybind11
bash scripts/build_llvm.sh -j16
bash scripts/build.sh -j16
python3 -m pip install -e .
python3 examples/01-vectorAdd.py
```

工具链要求包括 C++17 编译器；并行度按可用 RAM 调整。脚本会获取该 tag 固定的 LLVM 并应用补丁，默认可能在 FlyDSL 父目录建立 `llvm-project`，因此放在专用开发目录里。

`MLIR_PATH` 只应用于自己明确匹配 hash/补丁/Python ABI 的 MLIR build。不要把系统 `/opt/rocm` 或另一个项目的 LLVM build 直接塞进去。

学习顺序：`01-vectorAdd.py` → `02-tiledCopy.py` → `03-tiledMma.py` → `04-preshuffle_gemm.py`。再读 [layout](https://github.com/ROCm/FlyDSL/blob/v0.4.0/docs/layout_system_guide.md) 与 [tuning](https://github.com/ROCm/FlyDSL/blob/v0.4.0/docs/kernel_tuning_guide.md)。源码 `tests/kernels/test_gemm_a16w16_gfx950.py` 是 MI355X 相关入口；部分 attention kernel 的 README 仍标注 WIP performance tuning，不应默认每个 kernel 都已最优。

## 8. 安装 Gluon：安装的是 Triton

### 8.1 AITER 环境：先验收已有配套 Triton

```bash
python3 - <<'PY'
import torch, triton
from triton.experimental import gluon
from triton.experimental.gluon import language as gl
from triton.experimental.gluon.language.amd import cdna4
print('torch:', torch.__version__, 'HIP:', torch.version.hip)
print('triton:', triton.__version__, triton.__file__)
print('target:', triton.runtime.driver.active.get_current_target())
print('Gluon CDNA4:', cdna4)
PY
```

预期是 HIP 后端、gfx950 目标。import 成功证明接口可见，仍需运行实际 kernel 做编译与正确性验收。

### 8.2 独立上游实验：固定 Triton 与教程版本

下面只适用于没有被 AITER/已有 PyTorch distribution 固定另一套 Triton 的独立环境。多个发行包都可能提供同一个 `import triton`，不要叠装。

```bash
python3 -m pip install 'triton==3.8.0' pytest
git clone --branch v3.8.0 --depth 1 https://github.com/triton-lang/triton.git
cd triton
python3 -m pytest -q python/tutorials/gluon/01-intro.py
```

教程需要已有可用 ROCm PyTorch。用 pytest 跑 correctness case，比直接执行教程末尾的大型 benchmark 更适合初次验收。`01-intro.py`、`02-layouts.py` 用来学习语言；MI355X 专用功能看 `python/triton/experimental/gluon/language/amd/cdna4/` 及 AMD tests。

需要修改 Triton/Gluon 编译器时，在这个固定 tag 的源码根目录：

```bash
python3 -m pip install -r python/requirements.txt
python3 -m pip install -e .
```

按该 tag 的 `cmake/llvm-info.json` 取 LLVM。Gluon 与 FlyDSL 都“使用 MLIR/LLVM”不代表编译器 build 可以共用。

## 9. MI355X 优化时，选哪条开发路线？

| 你的目标 | 首选起点 | 要观察什么 |
|---|---|---|
| 先让服务或模型快起来 | AITER 现成 kernel 与 dispatch | 是否选中预期后端、shape 覆盖、layout/量化转换成本、端到端调用开销 |
| C++ 深度优化 GEMM/attention pipeline | CK Tile；对照已有 CK/ASM baseline | MFMA 指令、tile 大小、流水级数、LDS swizzle、寄存器压力 |
| Python 快速验证融合/布局想法 | 先有 Triton baseline，再比较 Gluon/FlyDSL | fusion 收益、layout 转换、访存合并、async copy、编译时间 |
| 显式控制 Triton 生态里的线程/数据布局 | Gluon | BlockedLayout/AMDMFMALayout、shared memory、CDNA4 intrinsic |
| 实验 layout algebra / tile composition | FlyDSL | shape/stride、partition、copy/MFMA atom、MLIR lowering |
| 修改后端 codegen / ISA 生成 | 对应项目的固定编译器源码 | LLVM pin、补丁、生成 ISA 与 register allocation |

不要预先认定“某 DSL 一定更快”。先固定 **shape、dtype、stride、layout、量化 scale 格式、精度阈值、batch 分布、调用方式**，再比较同一工作负载。AITER 在这里既可以是最终集成入口，也可以是性能对照组。

| MI355X 常见词 | 如何理解 | 调优时怎么用 |
|---|---|---|
| gfx950 / CDNA4 | 编译目标标识 / GPU 架构代际 | 所有 kernel、编译器与设备信息必须一致；不能沿用 gfx942 假设 |
| Wavefront | AMD 的执行线程组；MI355X 常用 wave64 | 不把 CUDA warp32 的 layout 公式直接搬来 |
| MFMA | AMD 矩阵乘加指令 | 检查生成的指令形状、dtype、数据布局是否匹配期望 |
| LDS / Swizzle | 片上共享存储 / 地址重排 | 降低 bank conflict，安排异步搬运与双缓冲 |
| VGPR / AGPR / Occupancy | 寄存器资源 / 驻留工作量 | tile 更大可能提高复用，也可能寄存器过多导致 occupancy 下降或 spill |
| OCP FP8 / FNUZ / MXFP4 | 不同数值/缩放表示 | 核对真实 dtype、scale 粒度、scale layout、packing；同为 8-bit 不等价 |
| Preshuffle | 把权重预排成 kernel 喜欢的布局 | 单看 kernel 可能快，但要交代重排成本与是否可摊销 |
| Split-K | 将 K 维拆给多个工作单元并做合并 | 小 M/N、大 K 时可能增加并行，也会增加 reduction 与额外流量 |
| JIT / Autotune cache | 首次编译与配置搜索结果缓存 | 分开冷启动与稳态；改编译器/版本后不要误用旧缓存作为结论 |
| Roofline | 理论算力与可用带宽形成的性能上限 | 先判 compute-bound 还是 memory-bound，再选优化方向 |

## 10. 验收、排障与复现清单

按顺序做四层验收：**能发现 GPU → 能导入库 → 能编译并通过目标算子正确性 → 在真实 shape 分布上改善性能**。任何前一层通过，都不能代替后一层。

| 症状 | 先检查 |
|---|---|
| no kernel image / invalid device function | 实际 target 是否 gfx950；wheel/code object 是否含 gfx950；编译器是否支持 |
| 找不到 Gluon API | Triton 的完整版本、发行源和源码 SHA；是否把 main 代码配了 stable wheel |
| `import triton` 路径奇怪 | 是否同时安装 triton / pytorch-triton-rocm 等，或 cwd/PYTHONPATH 遮蔽 |
| CK header / 模板接口报错 | AITER gitlink 是否被更新；CK_DIR 是否覆盖到了另一份源码 |
| MLIR .so / symbol load 错误 | FlyDSL 自带绑定、Python ABI、MLIR_PATH、LD_LIBRARY_PATH 是否混版本 |
| 编译 OOM / 首次调用很慢 | 是否全架构、全实例编译；并行度是否过高；是否仍在 JIT/autotune |
| 量化 kernel 输出偏差 | OCP/FNUZ、scale/zero point、block size、padding、packing 与 tolerance |
| kernel benchmark 快、模型没快 | dispatch、数据转换、同步、launch、通信、真实 batch/shape 是否一致 |

每个 benchmark 至少保留：GPU/ROCm/驱动、容器 digest、Python/Torch/HIP、完整 Triton 版本与路径、AITER SHA、CK SHA、FlyDSL 版本、编译器版本、shape/stride/dtype、正确性阈值、warmup、计时方式、并发/时钟条件。

```bash
# 在 AITER checkout 内保存源码状态。
git rev-parse HEAD
git submodule status --recursive
python3 -m pip freeze
python3 -m pip check
```

本目录附带 `mi355x-env-check.py`：只采集相关版本、路径与设备信息，不安装软件；加 `--smoke` 可跑一个很小的 PyTorch GPU 正确性检查。它不证明 AITER/CK/FlyDSL/Gluon 的目标 kernel 已通过，也不替代 profiler。

性能测量应完成 warmup 与 GPU 同步，避免把异步 launch 的 CPU 时间当成 kernel 时间；记录多次测量的分布，区分纯 kernel 时间与端到端时间。首次 JIT、首次权重重排与稳态结果分别报告。

## 11. 官方资料入口与快照

| 内容 | 来源 |
|---|---|
| AITER 最新状态与集成文档 | [AITER main 固定快照](https://github.com/ROCm/aiter/tree/d81d17e302e5882140864c3bc605fe8b8964343e) |
| AITER 发行与精确依赖 | [v0.1.25](https://github.com/ROCm/aiter/tree/v0.1.25)；[CK gitlink](https://github.com/ROCm/aiter/tree/v0.1.25/3rdparty) |
| AITER MI355 新 kernel 证据 | [MI355 MLA FP8 commit](https://github.com/ROCm/aiter/commit/4fac0809203c037a223c6a64a0653d475572568b) |
| AMD Triton 构建索引 | [release_0914 / ROCm7.2.0](https://pypi.amd.com/triton/release_0914/rocm-7.2.0/simple/triton/) |
| CK 旧地址迁移说明 | [ROCm/composable_kernel](https://github.com/ROCm/composable_kernel) |
| CK 当前主库快照 | [rocm-libraries b3eca660](https://github.com/ROCm/rocm-libraries/tree/b3eca66013cc3e77c6f1147836dd2c0cfbd237e8/projects/composablekernel) |
| CK 版本与发布 | [rocm-7.2.4](https://github.com/ROCm/rocm-libraries/tree/rocm-7.2.4/projects/composablekernel)；[releases](https://github.com/ROCm/rocm-libraries/releases) |
| FlyDSL 发行、安装、测试 | [v0.4.0](https://github.com/ROCm/FlyDSL/tree/v0.4.0)；[PyPI](https://pypi.org/project/flydsl/0.4.0/) |
| FlyDSL 当前 CI | [固定工作流](https://github.com/ROCm/FlyDSL/blob/0653ff888bad3787c759eabeeeefbfa1aa2df50b/.github/workflows/flydsl.yaml) |
| Gluon 入门 | [Triton v3.8.0 intro](https://github.com/triton-lang/triton/blob/v3.8.0/python/tutorials/gluon/01-intro.py) |
| Gluon MI355X/CDNA4 | [stable API](https://github.com/triton-lang/triton/tree/v3.8.0/python/triton/experimental/gluon/language/amd/cdna4)；[当前 AMD 测试](https://github.com/triton-lang/triton/blob/6bf64a51df4a9c48f0d575b4ca4ad6c9988d36d2/third_party/amd/python/test/test_gluon_cdna4.py) |
| GPU/软件基底 | [ROCm7.2.4 compatibility](https://rocm.docs.amd.com/en/docs-7.2.4/compatibility/compatibility-matrix.html)；[PyTorch 镜像](https://rocm.docs.amd.com/projects/install-on-linux/en/docs-7.2.4/install/3rd-party/pytorch-install.html) |

这里的维护结论来自仓库迁移声明、实际代码提交、release 与 CI，而不是仅凭 stars 或 pushed_at。没有查到一张覆盖上述所有项目任意版本组合的官方总兼容表；文中的组合建议因此明确区分了硬 pin、构建配置、观察到的 CI 组合与待实机验收的配方。
