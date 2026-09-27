# ROS 2 工作空间模板

通用 ROS 2 项目骨架，包含开发容器、colcon 工作空间、Python/C++ 示例、Debian 打包和 GitLab CI，支持以下四个目标：

| Ubuntu | ROS 2 | 平台 |
| --- | --- | --- |
| 24.04 (Noble) | Jazzy（默认） | `linux/amd64`、`linux/arm64` |
| 22.04 (Jammy) | Humble | `linux/amd64`、`linux/arm64` |

开发镜像和 GitLab CI 统一使用清华 **TUNA**：Ubuntu APT（含安全更新，ARM 使用 `ubuntu-ports`）、ROS 2 APT、rosdep 规则、rosdistro 索引和 pip 包索引。配置入口为 `scripts/configure-mirrors`，由依赖安装和 CI 安装验证自动调用；ROS 签名密钥已包含在本仓库的 [.devcontainer/ros.key](.devcontainer/ros.key)，Docker 构建和 CI 均直接读取此本地文件。镜像配置参考 [TUNA ROS 2](https://mirrors.tuna.tsinghua.edu.cn/help/ros2/) 和 [rosdistro 说明](https://mirrors.tuna.tsinghua.edu.cn/help/rosdistro/)。

| 路径 | 用途 |
| --- | --- |
| `.devcontainer/`、`Dockerfile` | VS Code 开发环境，按 ROS 发行版和目标架构选择基础镜像 |
| `src/hello_py` | `ament_python` / rclpy 示例 |
| `src/hello_cpp` | `ament_cmake` / rclcpp 示例 |
| `packaging.toml`、`scripts/` | 依赖安装和整个工作空间的 `.deb` 打包 |
| `.gitlab-ci.yml`、`tests/` | 云端构建、消息验证和安装/卸载检查 |

## 基于模板开发：需要修改什么

首次复用时设置根目录的 `packaging.toml`，之后将日常开发集中在 `src/`。服务、现场配置保护和 LFS 下载范围使用 `packaging/` 下的可选配置。通用构建、依赖安装、打包和测试脚本会自动发现这些内容。

| 修改位置 | 何时修改 | 需要填写或实现的内容 |
| --- | --- | --- |
| `packaging.toml` | 首次创建项目 | 整个工作空间的名称、维护者、描述；按需补充许可证和 APT 依赖 |
| `src/<ROS包>/` | 日常开发 | 源码、`package.xml`、CMake/setup 安装规则、launch、配置、模型、许可证和测试 |
| `src/<ROS包>/requirements.txt` | 有额外 pip 运行依赖时 | Python 包名及版本要求；已有 rosdep key 的依赖优先写入 `package.xml` |
| `src/<ROS包>/pip-constraints.txt` | 需要限制 pip 依赖版本时 | 约束直接或间接依赖的版本；约束文件本身不会引入新依赖 |
| `src/<ROS包>/wheels/*.whl` | 使用厂商 wheel 时 | 放入厂商原始 wheel，由框架选择与目标 Python、架构兼容的文件 |
| `src/<ROS包>/test/installed/test_*.py` | 需要验证安装后行为时 | pytest 交付测试，例如入口可运行、资源可读取、消息可收发 |
| `packaging/systemd/` | 需要 systemd 服务时 | `.service` 或 `.service.in` 服务定义 |
| `packaging/conffiles` | 需要保留现场修改时 | 已安装配置文件的绝对路径或通配模式 |
| `.gitmodules`、`.gitattributes`、`packaging/lfs.toml` | 引入子模块或大文件时 | 上游仓库位置、LFS 跟踪规则、各仓库的可选下载范围 |

通常可直接沿用 `scripts/`、根目录 `tests/`、`Dockerfile`、`.devcontainer/` 和 `.gitlab-ci.yml`。只有基础环境或 CI 基础设施发生变化时，才需要调整相应文件，例如更换镜像仓库或 Runner 标签。应用自己的测试放在 `src/`，根目录 `tests/` 用于验证模板框架。

### 1. 设置项目身份并替换示例包

先修改 `packaging.toml`，例如：

```toml
[package]
name = "my-robot"
maintainer = "Robot Team <robot@example.com>"
description = "ROS 2 robot application"
license_files = []

[dependencies]
build = []
runtime = []
```

这里的 `name` 是整个交付包的名称，生成 `ros-jazzy-my-robot` 或 `ros-humble-my-robot`；各 ROS 包的名称由自己的 `package.xml` 定义。`license_files` 可补充相对仓库根目录的许可证路径，各 ROS 包内的 `LICENSE*`、`COPYING*` 和 manifest 指定的许可证文件会自动收集。

随后替换 `src/hello_py`、`src/hello_cpp`，或以它们为起点重命名。同步修改 `package.xml` 中的包名、版本、维护者、描述和许可证，以及 Python 包的 `setup.py`、`setup.cfg`、`resource/<包名>`、模块名和入口，或 C++ 包的 `CMakeLists.txt` 中的 `project()`、编译目标和安装规则。示例消息测试位于 `src/hello_py/test/installed/test_publishers.py`，同时检查两个 hello 包，替换示例时也应改成自己的交付测试。

例如，项目可以组织为：

```text
src/
  my_robot_driver/
    package.xml
    setup.py                         # Python 包；C++ 包使用 CMakeLists.txt
    setup.cfg
    resource/my_robot_driver
    my_robot_driver/
    LICENSE
    requirements.txt                 # 以下依赖和测试目录均按需添加
    pip-constraints.txt
    wheels/
    test/
      test_driver.py
      installed/test_runtime.py
  my_robot_bringup/
    package.xml
    CMakeLists.txt
    LICENSE
    launch/
    config/
```

launch、YAML、URDF、网格等运行资源仍需在各包的 `setup.py` 或 `CMakeLists.txt` 中明确安装到 `share/<ROS包名>/`。框架负责收集构建结果，应用需要保证资源在安装后可用；运行时通过 ROS 包的 share 路径定位资源，避免引用源码目录或开发机的绝对路径。

### 2. 声明依赖和厂商资源

ROS 包之间的依赖、系统依赖以及有 rosdep key 的 pip 依赖写入 `package.xml`，并区分构建、运行和测试用途。`scripts/install-deps` 会安装开发所需依赖，打包时再分别生成 APT 运行依赖和 pip 安装清单。无法在 manifest 中声明的额外 Debian 包名可填写到 `packaging.toml` 的 `dependencies.build/runtime`。

没有合适 rosdep key 的 Python 运行依赖放在包内 `requirements.txt`，每行一个包名及版本要求，例如 `pymodbus>=3,<4`。需要固定依赖版本时再添加 `pip-constraints.txt`。这些文件支持命名的 PEP 508 依赖及环境条件，不接受索引选项、URL、本地源码路径或嵌套 `-r` 文件；pip 索引由框架统一配置为 TUNA。

厂商 wheel 放在 `src/<ROS包>/wheels/`，保留原始文件名和内容。同一工作空间内由一个 ROS 包声明同一厂商分发包，并保持一个版本；可以同时提供该版本的不同 Python/架构 wheel，以覆盖 CI 的四个目标。缺少兼容 wheel 或文件仍是 LFS 指针时，准备依赖或打包会失败。

开发环境通过 `bash scripts/install-deps` 安装这些 Python 依赖。deb 将 vendor wheel 原样放在 `/opt/ros/<发行版>/share/<Debian包名>/python/wheels/<ROS包名>/`，安装或升级配置 deb 时调用系统 pip，经 TUNA 安装公开依赖，并安装本地 vendor wheel。这个阶段可能需要联网；卸载 deb 会保留共享的 pip 依赖，因此不同应用仍需使用兼容的 Python 版本约束。

模板已将 `*.whl`、`*.stl`、`*.STL` 配置为 Git LFS 文件。添加其他大文件类型时更新 `.gitattributes`；引入上游模型时添加 Git 子模块。若只需子模块的一部分 LFS 文件，可在 `packaging/lfs.toml` 中配置：

```toml
[repositories."third_party/robot_descriptions"]
include = ["products/my_robot/**"]
exclude = []
```

仓库路径以工作空间为基准，`"."` 表示主仓库；未配置的仓库按自身 LFS 设置下载。更新子模块或下载范围后执行 `bash scripts/prepare-sources`，更新依赖后执行 `bash scripts/install-deps`。模型转换等应用逻辑放在消费这些资源的 ROS 包内，并接入该包的构建规则。

### 3. 按需添加服务和配置保护

将交付用的服务定义放入 `packaging/systemd/`。文件名和内容可使用 `@PREFIX@`（例如 `/opt/ros/jazzy`）、`@ROS_DISTRO@`、`@DEB_PACKAGE@`，打包器会替换这些占位符并将服务安装到 `/usr/lib/systemd/system/`。例如 `my-robot-@ROS_DISTRO@.service.in` 在 Jazzy 下生成 `my-robot-jazzy.service`；服务可以加载 `@PREFIX@/setup.bash` 后执行自己的 ROS launch。

需要保留操作者修改的配置，先通过 ROS 包的安装规则交付，再在 `packaging/conffiles` 中登记，例如：

```text
@PREFIX@/share/my_robot_bringup/config/*.yaml
```

这些文件会登记为 Debian conffile；安装验证会检查重新安装时保留现场修改。模式必须匹配实际交付的文件。服务安装时只刷新 systemd 定义，启用、启动、停止和重启由操作者明确执行。

### 4. 开发、验证与交付

进入开发容器后，在仓库根目录运行以下 Bash 命令。使用本地已有 ROS 环境时，先加载 `/opt/ros/<发行版>/setup.bash`。

```bash
bash scripts/prepare-sources          # 首次准备或更新子模块/LFS 时执行
bash scripts/install-deps             # 首次准备或更新依赖时执行
colcon build --base-paths src --symlink-install
source install/setup.bash
colcon test --base-paths src --return-code-on-test-failure
colcon test-result --verbose
# 单独运行包内交付测试：
/usr/bin/python3 scripts/run_installed_tests.py --source src
```

普通单元/集成测试放在各包的 `test/` 下，并接入该包的测试机制。`test/installed/` 中的测试会自动随 deb 交付，并在 CI 的全新容器中运行；它们只能依赖已安装的运行环境和 pytest，不能依赖源码、构建目录或仅供开发使用的依赖。即使没有添加交付测试，安装验证也会检查每个已打包 ROS 包是否可发现。

完成日常验证后，运行 `bash scripts/ci-build` 执行与 CI 相同的构建、测试和打包流程，产物位于 `dist/<发行版>/<架构>/`。此入口的测试失败只告警，构建/打包失败才终止，所以应同时查看测试报告；前面的 `colcon test` 命令可用于直接检查测试失败。仅需生成 deb 时，可执行 `./scripts/build-deb --version 0.1.0-1`，默认输出到 `dist/`。

创建新 GitLab 项目时，还需配置镜像访问变量、对应架构的 Runner 和 Package Registry；使用私有子模块时配置跨项目的 CI job token 读取权限，详见下文「GitLab 云端构建」。普通提交的开发版本来自 `src/` 中最高的 ROS manifest 版本；发布时使用自己的版本标签。新增或替换 ROS 包无需维护 CI 中的包名列表。

详细的打包参数见 [scripts/README.md](scripts/README.md)，三仓库差异和已验证范围见 [模板比较](docs/template-comparison.md)。

## 开发与运行

开发容器默认面向 **本地 Linux 桌面（X11，或启用 XWayland 的 Wayland）**。宿主机安装 Docker、VS Code、Dev Containers 扩展和 `xauth`（Ubuntu：`sudo apt install xauth`），从桌面会话打开 VS Code，选择 **Dev Containers: Reopen in Container**。镜像包含 Git LFS；首次创建容器先运行 `bash scripts/prepare-sources`，递归初始化子模块，并分别下载主仓库和各子模块的 LFS 文件，成功后安装 `src/` 的依赖。新终端自动加载 ROS 环境。更新子模块后重新运行 `bash scripts/prepare-sources`；添加依赖后重新执行 `bash scripts/install-deps`。私有仓库需可用的 Git/SSH 读取凭据，可使用 Dev Containers 转发的宿主机 SSH agent。根目录的 `git lfs pull` 不会递归处理子模块。

默认使用 Jazzy；使用 Humble 时，在启动 VS Code 的宿主机环境中设置 `ROS_WORKSPACE_DISTRO=humble`，再重建开发容器。容器架构默认跟随宿主机。切换 ROS 发行版或架构时，先清理旧的 `build/`、`install/`、`log/`，避免复用不兼容的构建产物。

本地 Dockerfile（需要 BuildKit，通过 [`TARGETARCH`](https://docs.docker.com/reference/dockerfile/#automatic-platform-args-in-the-global-scope) 选择架构）使用以下基础镜像映射；CI 镜像配置见下文「GitLab 云端构建」：

| ROS 2 | 架构 | 基础镜像 |
| --- | --- | --- |
| Jazzy | amd64 | `ros:jazzy-ros-core` |
| Jazzy | arm64 | `registry.jihulab.com/discoverrobotics/s2-restricted/data-factory/registry/ros:jazzy-ros-core` |
| Humble | amd64 | `ros:humble-ros-core` |
| Humble | arm64 | `registry.jihulab.com/discoverrobotics/s2-restricted/data-factory/registry/ros:humble-ros-core` |

Jazzy 和 Humble 的 ARM64 镜像需先同步到内部仓库。在已安装 Docker 的宿主机上登录并执行（这两个内部标签仅用于 ARM64）：

```bash
docker login registry.jihulab.com
for distro in jazzy humble; do
  image="ros:${distro}-ros-core"
  mirror="registry.jihulab.com/discoverrobotics/s2-restricted/data-factory/registry/${image}"
  docker pull --platform linux/arm64 "$image"
  docker image inspect --platform linux/arm64 "$image" --format '{{.Os}}/{{.Architecture}}' # 应为 linux/arm64
  docker tag "$image" "$mirror"
  docker push --platform linux/arm64 "$mirror"
done
```

[`docker image inspect --platform`](https://docs.docker.com/reference/cli/docker/image/inspect/) 需要 Docker API 1.49+，显式检查 ARM64，避免本地同时缓存多个架构时检查到宿主机架构。[`docker push --platform`](https://docs.docker.com/reference/cli/docker/image/push/) 需要 Docker API 1.46+，确保仅发布 ARM64 清单。开发宿主机必须通过 `docker login` 获得私有镜像的拉取权限；CI 使用 GitLab 中配置的 `ROS_IMAGE_ACCESS_KEY`，详见下文。

```bash
colcon build --symlink-install --cmake-args -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
source install/setup.bash
ros2 run hello_py talker
# 在另一个已 source install/setup.bash 的终端运行：
ros2 run hello_cpp talker
# 第三个终端观察两个节点每秒发布的消息：
ros2 topic echo /hi std_msgs/msg/String
```

消息分别为 `hi from rclpy`、`hi from rclcpp`，按 Ctrl+C 退出。容器默认使用宿主机网络，支持局域网 ROS 发现和网络相机。

不使用 VS Code 时，可按目标构建开发镜像，再将仓库挂载到容器的 `/workspaces/ros_ws`，运行 `bash scripts/install-deps`：

```bash
docker build --platform linux/amd64 --build-arg ROS_DISTRO=jazzy -t ros-workspace:jazzy .
docker build --platform linux/arm64 --build-arg ROS_DISTRO=humble -t ros-workspace:humble .
```

两个发行版均支持两种架构；在对应架构的宿主机上原生构建。已有 Noble/Jazzy 或 Jammy/Humble 环境可依次运行 `sudo bash scripts/install-build-tools`、`bash scripts/prepare-sources` 和 `bash scripts/install-deps`。脚本根据 Ubuntu 版本自动选择 ROS 发行版；显式设置的 `ROS_DISTRO` 必须与 Ubuntu 匹配。

## GUI 与相机

在 VS Code 中执行 **Dev Containers: Rebuild and Reopen in Container** 应用配置。启动时会自动将当前桌面的 X11 认证写入本地忽略目录 `.devcontainer/.local/` 并只读挂载，无需手动运行 `xhost`。GUI 应用直接显示在宿主机桌面，Qt 使用 X11，OpenGL 默认使用 Mesa 软件渲染。

```bash
xclock                         # 验证桌面窗口
glxinfo -B                     # 验证 OpenGL
ls -l /dev/video*              # 查看实际 V4L2 设备编号
v4l2-ctl -d /dev/video2 --info  # 按实际设备名替换；编号不一定从 0 开始
lsusb                         # 枚举 USB / USB3 Vision 设备
# 按需安装 ROS 图像工具及普通 USB 相机驱动：
sudo apt update
sudo apt install "ros-$ROS_DISTRO-rqt-image-view" "ros-$ROS_DISTRO-usb-cam"
ros2 run rqt_image_view rqt_image_view
```

宿主机 `/dev` 和只读 udev 信息已挂载，设备规则允许 V4L2（主设备号 81）和 USB（189）访问，支持重新插拔；网络相机通过宿主机网络访问。相机驱动或厂商 SDK 按项目需要安装。默认补充组为 Ubuntu 的 `video`（GID 44）和 USB 设备组（GID 0）；其他宿主机若组号不同，在启动 VS Code 的环境中设置 `ROS_CAMERA_VIDEO_GID` / `ROS_CAMERA_USB_GID` 为 `stat -c '%g' <设备路径>` 的结果后重建。设备本身仍需具有相应的组读写权限或桌面用户的 udev ACL。

桌面重新登录后，重启容器以刷新显示认证；若 `DISPLAY` 改变则重建容器。Docker Desktop、远程 Docker 和无桌面服务器需另外配置显示服务与设备转发。直接 `docker run` 不会读取 devcontainer 配置，需要显式提供同样的环境变量、挂载和设备规则。

## 共享宿主机 Codex

开发容器将宿主机整个 `~/.codex` 挂载到与宿主机相同的绝对路径，再将 `/home/ros/.codex` 链接到该目录，共享配置、登录文件、会话、CLI 和 daemon 安装。宿主机需已有与容器 Linux 架构匹配的 Codex，入口位于 `~/.codex/packages/standalone/current/bin/codex`；共享目录中的改动会同步到宿主机。

保留原始挂载路径后，CLI 和 `app-server-daemon/current` 中的宿主机绝对链接均可直接解析，无需改写共享安装。容器启动和每次连接时，[link-codex.sh](.devcontainer/link-codex.sh) 创建容器用户的目录别名，并将 `/usr/local/bin/codex` 链接到 `standalone/current/bin/codex`，宿主机升级立即可见。进入容器即可运行 `codex --version` 和 `codex`。修改挂载后执行 **Dev Containers: Rebuild and Reopen in Container**。镜像包含 Linux 沙箱工具 `bubblewrap`，运行要求见 [OpenAI 官方说明](https://learn.chatgpt.com/docs/sandboxing)。

## 打包与安装

首次复用时设置 `packaging.toml` 的工作空间名（不含 `ros-<发行版>-` 前缀）、维护者及描述；包内 LICENSE/COPYING 自动发现，额外许可证可列入配置。再运行：

```bash
./scripts/build-deb --version 0.1.0-1
# 例如 Jazzy/amd64：复制到已配置 ROS APT 软件源的 Ubuntu 24.04 amd64 机器：
sudo apt update
sudo apt install ./ros-jazzy-example-workspace_0.1.0-1_amd64.deb
source /opt/ros/jazzy/setup.bash
ros2 run hello_py talker
```

打包器在临时目录重新构建，将两种 ROS 包合并安装到 `/opt/ros/<发行版>`，保留 ROS 自身环境文件，并生成对应 Ubuntu/ROS 的外部 APT 依赖。包名为 `ros-<发行版>-<工作空间名>`，文件名包含 Debian 架构，例如 `ros-humble-example-workspace_0.1.0-1_arm64.deb`。只在相同 Ubuntu/ROS 版本及架构的机器上安装；Humble 使用 `/opt/ros/humble/setup.bash`。卸载时使用对应完整 Debian 包名。参数与限制见 [scripts/README.md](scripts/README.md)。

## GitLab 云端构建

推送到 GitLab 后流水线自动运行（分支、合并请求及标签）：

1. `build_and_package` 展开 Jazzy/Humble × amd64/arm64 四个原生构建作业，安装依赖，运行打包回归测试、colcon 构建/测试和 `src/*/test/installed/` 的交付测试，生成 `.deb`。
2. `verify_deb` 同样展开四个作业，在对应 ROS/架构的新容器中通过 APT 安装各自产物（有 pip 依赖时由 postinst 安装），运行各包交付测试，验证重新安装、配置保留、卸载、purge 和 ROS 环境文件完整性。作业下载构建矩阵的全部产物，但只安装自身目标的 `.deb`。
3. 仅标签流水线运行一个 `release_packages`：全部构建成功且安装验证结束后，将四个 `.deb` 上传到 GitLab Generic Package Registry，并创建包含四个下载链接的 GitLab Release。

测试照常运行，但失败不阻止流水线成功或标签发布：`ci-build` 中的回归测试、colcon 测试和节点消息测试失败时打印警告并继续，保留测试报告；`verify_deb` 允许失败，在 GitLab 中显示警告。构建和打包失败仍会阻止流水线成功。

在作业的 **Artifacts** 下载 `dist/<发行版>/<架构>/*.deb`，对应测试报告和构建日志位于同一目标目录，保留一周。自建 Linux Docker/Kubernetes Runner 必须按真实架构分别设置 **`amd64`**、**`arm64`** 标签；每个目标通过 `TARGET_ARCH` 选择对应 Runner，发布作业使用 `amd64`。Runner 以 root 用户运行容器，并能访问 Docker Hub、极狐 GitLab Registry 和 TUNA 镜像站；无需 Docker-in-Docker、QEMU 或特权容器。脚本会检查容器实际架构与 `TARGET_ARCH` 一致。

普通提交从 `src/` 的最高 ROS manifest 版本生成 `<版本>~ci<流水线编号>+<提交>-1`，发布标签使用 `v0.1.0-1` 等合法 Debian 版本。可通过 CI 变量 `DEB_VERSION` 覆盖版本、`BUILD_JOBS` 调整并行度。CI 构建和验证矩阵通过 `ROS_IMAGE_REPOSITORY` 为两种架构统一选择 `registry.jihulab.com/discoverrobotics/s2-restricted/data-factory/registry/ros`，使用对应发行版的 `jazzy-ros-core` / `humble-ros-core` 标签；发布作业默认使用公开 Jazzy amd64 镜像。本地 Docker 构建通过 `--platform` 自动选择对应基础镜像，支持 `--build-arg ROS_DISTRO=humble` 或 `--build-arg ROS_IMAGE=<对应环境的镜像>` 覆盖。示例 CI 配置参考 [GitLab YAML 文档](https://docs.gitlab.com/ci/yaml/)。

私有 ROS 镜像的访问令牌已在 GitLab **Settings > CI/CD > Variables** 中配置为 `ROS_IMAGE_ACCESS_KEY`，值为原始访问令牌（变量类型为 **Variable**，不是 File、Base64 或 Docker JSON），需具有镜像仓库的 `read_registry` 权限。变量应设为 **Masked**，且作用域和 Protected 设置需允许目标分支、合并请求及标签流水线读取它；不可用时 Runner 无法拉取私有镜像。`.gitlab-ci.yml` 将其作为 `DOCKER_AUTH_CONFIG` 中 `registry.jihulab.com` 的密码，用户名固定为 `oauth2`；对于个人访问令牌，GitLab 要求用户名非空，但不验证其值，参见 [GitLab 访问令牌说明](https://docs.gitlab.com/user/profile/personal_access_tokens/)。Runner 在启动作业容器前读取此认证配置，因此无需在 `before_script` 中执行 `docker login`，参见 [GitLab 私有镜像认证](https://docs.gitlab.com/ci/docker/using_docker_images/#access-an-image-from-a-private-container-registry)。令牌值仅保存在 GitLab 变量中。

发布使用内置 `CI_JOB_TOKEN`，项目需启用 Package Registry。Registry 包名来自 `packaging.toml` 的 `package.name`（例如 `example-workspace`），版本与构建时的 Debian 版本一致；四个产物以不同文件名存储。Release 标题使用工作空间名和原始标签，例如 `example-workspace v0.1.0`。Release 使用原始标签，可选说明文件为 `docs/release-notes/v<版本>.md`；没有说明文件时使用默认描述。发布包不受作业 Artifacts 的一周过期时间限制；已存在同名标签的 Release 时创建会失败。
