# ROS 2 工作空间模板

通用 ROS 2 项目骨架，包含开发容器、colcon 工作空间、Python/C++ 示例、Debian 打包和 GitLab CI，支持以下四个目标：

| Ubuntu | ROS 2 | 平台 |
| --- | --- | --- |
| 24.04 (Noble) | Jazzy（默认） | `linux/amd64`、`linux/arm64` |
| 22.04 (Jammy) | Humble | `linux/amd64`、`linux/arm64` |

开发镜像和 GitLab CI 统一使用清华 **TUNA**：Ubuntu APT（含安全更新，ARM 使用 `ubuntu-ports`）、ROS 2 APT、rosdep 规则和 rosdistro 索引。配置入口为 `scripts/configure-mirrors`，由依赖安装和 CI 安装验证自动调用；ROS 签名密钥已包含在本仓库的 [.devcontainer/ros.key](.devcontainer/ros.key)，Docker 构建和 CI 均直接读取此本地文件。镜像配置参考 [TUNA ROS 2](https://mirrors.tuna.tsinghua.edu.cn/help/ros2/) 和 [rosdistro 说明](https://mirrors.tuna.tsinghua.edu.cn/help/rosdistro/)。

| 路径 | 用途 |
| --- | --- |
| `.devcontainer/`、`Dockerfile` | VS Code 开发环境，按 ROS 发行版和目标架构选择基础镜像 |
| `src/hello_py` | `ament_python` / rclpy 示例 |
| `src/hello_cpp` | `ament_cmake` / rclcpp 示例 |
| `packaging.toml`、`scripts/` | 依赖安装和整个工作空间的 `.deb` 打包 |
| `.gitlab-ci.yml`、`tests/` | 云端构建、消息验证和安装/卸载检查 |

## 开发与运行

开发容器默认面向 **本地 Linux 桌面（X11，或启用 XWayland 的 Wayland）**。宿主机安装 Docker、VS Code、Dev Containers 扩展和 `xauth`（Ubuntu：`sudo apt install xauth`），从桌面会话打开 VS Code，选择 **Dev Containers: Reopen in Container**。首次创建容器会自动安装 `src/` 的依赖；新终端自动加载 ROS 环境。添加依赖后重新执行 `bash scripts/install-deps`。

默认使用 Jazzy；使用 Humble 时，在启动 VS Code 的宿主机环境中设置 `ROS_WORKSPACE_DISTRO=humble`，再重建开发容器。容器架构默认跟随宿主机。切换 ROS 发行版或架构时，先清理旧的 `build/`、`install/`、`log/`，避免复用不兼容的构建产物。

Dockerfile（需要 BuildKit，通过 [`TARGETARCH`](https://docs.docker.com/reference/dockerfile/#automatic-platform-args-in-the-global-scope) 选择架构）和 CI 使用相同的基础镜像映射：

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

[`docker image inspect --platform`](https://docs.docker.com/reference/cli/docker/image/inspect/) 需要 Docker API 1.49+，显式检查 ARM64，避免本地同时缓存多个架构时检查到宿主机架构。[`docker push --platform`](https://docs.docker.com/reference/cli/docker/image/push/) 需要 Docker API 1.46+，确保仅发布 ARM64 清单。开发宿主机和 ARM64 Runner 必须具有此私有镜像的拉取权限；同项目 CI 可使用内置 Registry 认证，跨项目需配置 job token 允许列表和权限，或在 Runner / `DOCKER_AUTH_CONFIG` 中配置凭据，参见 [GitLab 私有镜像认证](https://docs.gitlab.com/ci/docker/using_docker_images/#access-an-image-from-a-private-container-registry)。

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

两个发行版均支持两种架构；在对应架构的宿主机上原生构建。已有 Noble/Jazzy 或 Jammy/Humble 环境可直接运行 `sudo bash scripts/install-build-tools` 和 `bash scripts/install-deps`。脚本根据 Ubuntu 版本自动选择 ROS 发行版；显式设置的 `ROS_DISTRO` 必须与 Ubuntu 匹配。

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

开发容器将宿主机 `~/.codex` 挂载到 `/home/ros/.codex`，共享配置、登录文件、会话和独立安装。宿主机需已有与容器 Linux 架构匹配的 Codex，入口位于 `~/.codex/packages/standalone/current/bin/codex`；共享目录中的改动会同步到宿主机。

容器启动和每次连接时，[link-codex.sh](.devcontainer/link-codex.sh) 会转换宿主机绝对链接路径，并刷新容器内的 `/usr/local/bin/codex`。进入容器即可运行 `codex --version` 和 `codex`；宿主机升级后重新连接即可刷新入口。镜像包含 Linux 沙箱工具 `bubblewrap`，运行要求见 [OpenAI 官方说明](https://learn.chatgpt.com/docs/sandboxing)。

## 打包与安装

修改 `packaging.toml` 的工作空间名（不含 `ros-<发行版>-` 前缀）、维护者、描述及许可证列表，再运行：

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

1. `build_and_package` 展开 Jazzy/Humble × amd64/arm64 四个原生构建作业，安装依赖，运行打包回归测试、colcon 构建/测试和两个节点的真实消息测试，生成 `.deb`。
2. `verify_deb` 同样展开四个作业，在对应 ROS/架构的新容器中仅通过 APT 安装各自产物，验证两个节点、卸载结果和 ROS 环境文件完整性。作业下载构建矩阵的全部产物，但只安装自身目标的 `.deb`。
3. 仅标签流水线运行一个 `release_packages`：全部构建成功且安装验证结束后，将四个 `.deb` 上传到 GitLab Generic Package Registry，并创建包含四个下载链接的 GitLab Release。

测试照常运行，但失败不阻止流水线成功或标签发布：`ci-build` 中的回归测试、colcon 测试和节点消息测试失败时打印警告并继续，保留测试报告；`verify_deb` 允许失败，在 GitLab 中显示警告。构建和打包失败仍会阻止流水线成功。

在作业的 **Artifacts** 下载 `dist/<发行版>/<架构>/*.deb`，对应测试报告和构建日志位于同一目标目录，保留一周。自建 Linux Docker/Kubernetes Runner 必须按真实架构分别设置 **`amd64`**、**`arm64`** 标签；每个目标通过 `TARGET_ARCH` 选择对应 Runner，发布作业使用 `amd64`。Runner 以 root 用户运行容器，并能访问 Docker Hub、极狐 GitLab Registry 和 TUNA 镜像站；无需 Docker-in-Docker、QEMU 或特权容器。脚本会检查容器实际架构与 `TARGET_ARCH` 一致。

普通提交生成 `0.1.0~ci<流水线编号>+<提交>-1` 版本，发布标签使用 `v0.1.0-1` 等合法 Debian 版本。可通过 CI 变量 `DEB_VERSION` 覆盖版本、`BUILD_JOBS` 调整并行度。CI 矩阵通过 `ROS_IMAGE_REPOSITORY` 为每种 ROS/架构组合选择上述基础镜像，发布作业默认使用公开 Jazzy amd64 镜像。本地 Docker 构建通过 `--platform` 自动选择对应基础镜像，支持 `--build-arg ROS_DISTRO=humble` 或 `--build-arg ROS_IMAGE=<对应环境的镜像>` 覆盖。示例 CI 配置参考 [GitLab YAML 文档](https://docs.gitlab.com/ci/yaml/)。

发布使用内置 `CI_JOB_TOKEN`，项目需启用 Package Registry。Registry 包名来自 `packaging.toml` 的 `package.name`（例如 `example-workspace`），版本与构建时的 Debian 版本一致；四个产物以不同文件名存储。Release 标题使用工作空间名和原始标签，例如 `example-workspace v0.1.0`。Release 使用原始标签，可选说明文件为 `docs/release-notes/v<版本>.md`；没有说明文件时使用默认描述。发布包不受作业 Artifacts 的一周过期时间限制；已存在同名标签的 Release 时创建会失败。

## 复用

替换 `src/` 中的示例包，在各自 `package.xml` 声明依赖，同时更新包名、维护者、许可证及 `tests/smoke_nodes.py`、`tests/smoke-installed` 中的示例检查。未写入上游清单的额外 **Debian 包名** 可放在 `packaging.toml` 的 `dependencies.build/runtime`，依赖脚本会一并安装。

本地运行与 CI 相同的构建和测试：`bash scripts/ci-build`，输出位于 `dist/<发行版>/<架构>/`。安装/卸载测试只在对应环境的一次性容器中运行，例如 `ROS_DEB_TEST_DISPOSABLE=1 bash tests/smoke-installed dist/humble/arm64/*.deb`。
