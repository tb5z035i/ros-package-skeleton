# ROS 2 工作空间模板

通用 ROS 2 项目骨架，使用 **Ubuntu 24.04 + ROS 2 Jazzy**。包含开发容器、colcon 工作空间、Python/C++ 示例、Debian 打包和 GitLab CI。

开发镜像和 GitLab CI 统一使用清华 **TUNA**：Ubuntu APT（含安全更新，ARM 使用 `ubuntu-ports`）、ROS 2 APT、rosdep 规则和 rosdistro 索引。配置入口为 `scripts/configure-mirrors`，由依赖安装和 CI 安装验证自动调用；ROS 签名密钥已包含在本仓库的 [.devcontainer/ros.key](.devcontainer/ros.key)，Docker 构建和 CI 均直接读取此本地文件。镜像配置参考 [TUNA ROS 2](https://mirrors.tuna.tsinghua.edu.cn/help/ros2/) 和 [rosdistro 说明](https://mirrors.tuna.tsinghua.edu.cn/help/rosdistro/)。

| 路径 | 用途 |
| --- | --- |
| `.devcontainer/`、`Dockerfile` | VS Code 开发环境，默认公开镜像 `ros:jazzy-ros-core` |
| `src/hello_py` | `ament_python` / rclpy 示例 |
| `src/hello_cpp` | `ament_cmake` / rclcpp 示例 |
| `packaging.toml`、`scripts/` | 依赖安装和整个工作空间的 `.deb` 打包 |
| `.gitlab-ci.yml`、`tests/` | 云端构建、消息验证和安装/卸载检查 |

## 开发与运行

开发容器默认面向 **本地 Linux 桌面（X11，或启用 XWayland 的 Wayland）**。宿主机安装 Docker、VS Code、Dev Containers 扩展和 `xauth`（Ubuntu：`sudo apt install xauth`），从桌面会话打开 VS Code，选择 **Dev Containers: Reopen in Container**。首次创建容器会自动安装 `src/` 的依赖；新终端自动加载 ROS 环境。添加依赖后重新执行 `bash scripts/install-deps`。

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

不使用 VS Code 时，也可执行 `docker build -t ros-workspace:jazzy .`，再将仓库挂载到容器的 `/workspaces/ros_ws`，运行 `bash scripts/install-deps`。已有 Noble/Jazzy 环境可直接运行 `sudo bash scripts/install-build-tools` 和 `bash scripts/install-deps`。

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
sudo apt install ros-jazzy-rqt-image-view ros-jazzy-usb-cam
ros2 run rqt_image_view rqt_image_view
```

宿主机 `/dev` 和只读 udev 信息已挂载，设备规则允许 V4L2（主设备号 81）和 USB（189）访问，支持重新插拔；网络相机通过宿主机网络访问。相机驱动或厂商 SDK 按项目需要安装。默认补充组为 Ubuntu 的 `video`（GID 44）和 USB 设备组（GID 0）；其他宿主机若组号不同，在启动 VS Code 的环境中设置 `ROS_CAMERA_VIDEO_GID` / `ROS_CAMERA_USB_GID` 为 `stat -c '%g' <设备路径>` 的结果后重建。设备本身仍需具有相应的组读写权限或桌面用户的 udev ACL。

桌面重新登录后，重启容器以刷新显示认证；若 `DISPLAY` 改变则重建容器。Docker Desktop、远程 Docker 和无桌面服务器需另外配置显示服务与设备转发。直接 `docker run` 不会读取 devcontainer 配置，需要显式提供同样的环境变量、挂载和设备规则。

## 共享宿主机 Codex

开发容器将宿主机 `~/.codex` 挂载到 `/home/ros/.codex`，共享配置、登录文件、会话和独立安装。宿主机需已有与容器 Linux 架构匹配的 Codex，入口位于 `~/.codex/packages/standalone/current/bin/codex`；共享目录中的改动会同步到宿主机。

容器启动和每次连接时，[link-codex.sh](.devcontainer/link-codex.sh) 会转换宿主机绝对链接路径，并刷新容器内的 `/usr/local/bin/codex`。进入容器即可运行 `codex --version` 和 `codex`；宿主机升级后重新连接即可刷新入口。镜像包含 Linux 沙箱工具 `bubblewrap`，运行要求见 [OpenAI 官方说明](https://learn.chatgpt.com/docs/sandboxing)。

## 打包与安装

修改 `packaging.toml` 的包名、维护者、描述及许可证列表，再运行：

```bash
./scripts/build-deb --version 0.1.0-1
# 将 dist/*.deb 复制到已配置 ROS Jazzy APT 软件源的同架构 Ubuntu 24.04 机器：
sudo apt update
sudo apt install ./ros-jazzy-example-workspace_0.1.0-1_amd64.deb
source /opt/ros/jazzy/setup.bash
ros2 run hello_py talker
```

打包器在临时目录重新构建，将两种 ROS 包合并安装到 `/opt/ros/jazzy`，保留 ROS 自身环境文件，并生成外部 APT 依赖；不会使用开发目录的符号链接安装。卸载命令为 `sudo apt remove ros-jazzy-example-workspace`。参数与限制见 [scripts/README.md](scripts/README.md)。

## GitLab 云端构建

推送到 GitLab 后流水线自动运行（分支、合并请求及标签）：

1. `build_and_package` 安装依赖，运行打包回归测试、colcon 构建/测试和两个节点的真实消息测试，生成 `.deb`。
2. `verify_deb` 在新的 ROS 基础容器中仅通过 APT 安装 `.deb`，验证两个节点、卸载结果和 ROS 环境文件完整性。
3. 仅标签流水线运行 `release_packages`：前两步成功后，将 `dist/*.deb` 上传到 GitLab Generic Package Registry，并创建带下载链接的 GitLab Release。

在作业的 **Artifacts** 下载 `dist/*.deb`，测试报告和构建日志保留一周。需要可运行无标签作业的 Linux Docker/Kubernetes Runner，以 root 用户运行容器，并能访问 Docker Hub 和 TUNA 镜像站；无需 Docker-in-Docker 或特权容器。自建 Runner 若强制标签，请在 `default.tags` 中填写实际标签。

普通提交生成 `0.1.0~ci<流水线编号>+<提交>-1` 版本，发布标签使用 `v0.1.0-1` 等合法 Debian 版本。可通过 CI 变量 `DEB_VERSION` 覆盖版本、`BUILD_JOBS` 调整并行度、`ROS_IMAGE` 指定等价的公开/内部 Jazzy Noble 镜像；本地 Docker 构建对应 `--build-arg ROS_IMAGE=...`。示例 CI 配置参考 [GitLab YAML 文档](https://docs.gitlab.com/ci/yaml/)。

发布使用内置 `CI_JOB_TOKEN`，项目需启用 Package Registry。Registry 包名来自 `packaging.toml` 的 `package.name`，版本与构建时的 Debian 版本一致。Release 使用原始标签，可选说明文件为 `docs/release-notes/v<版本>.md`；没有说明文件时使用默认描述。发布包不受作业 Artifacts 的一周过期时间限制；已存在同名标签的 Release 时创建会失败。

## 复用

替换 `src/` 中的示例包，在各自 `package.xml` 声明依赖，同时更新包名、维护者、许可证及 `tests/smoke_nodes.py`、`tests/smoke-installed` 中的示例检查。未写入上游清单的额外 **Debian 包名** 可放在 `packaging.toml` 的 `dependencies.build/runtime`，依赖脚本会一并安装。

本地运行与 CI 相同的构建和测试：`bash scripts/ci-build`。安装/卸载测试只在一次性容器中运行：`ROS_DEB_TEST_DISPOSABLE=1 bash tests/smoke-installed dist/*.deb`。
