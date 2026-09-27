# Debian 打包

`build-deb` 和 `deb_packaging.py` 支持 Ubuntu 24.04 / ROS 2 Jazzy 与 Ubuntu 22.04 / ROS 2 Humble 的 `ament_cmake` 和 `ament_python`，架构为 amd64、arm64。使用系统 `/usr/bin/python3`，按当前容器架构构建；Humble 的 Python 3.10 通过 `python3-tomli` 读取 TOML。

`ros_platform.py` 统一选择 ROS 发行版、Ubuntu 代号、安装路径和架构，shell 脚本通过 `ros-environment` 使用同一配置。默认根据 Ubuntu 自动选择，或使用与 Ubuntu 匹配的 `ROS_DISTRO`；设置 `TARGET_ARCH` 时必须与容器的 `dpkg --print-architecture` 一致。

`install-build-tools`、`install-deps` 和安装验证脚本会先调用 `configure-mirrors`，将 Ubuntu（含安全更新）、ROS APT 和 rosdep 切换到 TUNA。镜像与 CI 设置 `ROSDISTRO_INDEX_URL`，系统 rosdistro 配置也提供同一索引作为默认值；不需要再执行 `rosdep init`。

```bash
bash scripts/install-deps
./scripts/build-deb --version 0.1.0-1 --jobs 2
```

| 参数 | 说明 |
| --- | --- |
| `--version` | 必填，合法 Debian 版本 |
| `--maintainer 'Name <email@example.com>'` | 覆盖配置中的维护者 |
| `--workspace PATH` | 工作空间，默认本仓库；包含 `src/` 和 `packaging.toml` |
| `--output PATH` | 产物目录，默认工作空间的 `dist/` |
| `--jobs N` | 包内编译并行度，默认 2；包之间按顺序构建 |
| `--keep-build` | 保留成功构建的临时目录；失败时始终保留 |

`packaging.toml` 的 `package.name` 是不含 ROS 前缀的工作空间名，例如 `example-workspace`，Debian 包名自动生成为 `ros-jazzy-example-workspace` 或 `ros-humble-example-workspace`。各 ROS 包的 LICENSE/COPYING 和 manifest license file 自动收集；`package.license_files` 可补充其他分发许可证。`dependencies.build/runtime` 接受在两个目标环境均可用的 Debian 包名；ROS 依赖及发行版条件应写入 `package.xml`，由对应发行版的 rosdep 解析。`install-deps` 会安装清单依赖（含测试依赖）及两类补充依赖；发布打包器本身不会安装依赖。

`install-deps` 和 `ci-build` 的构建范围包括 `src/` 与可选的 `third_party/`。CI 的包测试和交付测试仍针对 `src/`。本地可通过 `colcon build --symlink-install` 构建整个工作空间用于调试。

打包过程独立加载 `/opt/ros/<发行版>`，在临时目录对 `src/` 和 `third_party/` 进行非符号链接的 Release 构建，每个包有独立的安装目录；只将 `src/` 包的安装文件合并到交付 ROS 路径。第三方包的库、头文件、Python 模块、许可证、pip 输入和测试不自动进入 `.deb`。版本、包清单和 `Conflicts` 也只包含 `src/` 包。运行依赖通过对应 Ubuntu/ROS 的 rosdep 与 ELF 分析生成；运行时需要的第三方包须能通过 rosdep 解析为独立安装的依赖，构建时有其源码不会消除这项运行依赖。仅用于构建的包应声明为 `build_depend` / `buildtool_depend`。许可证和 ROS 包版本清单写入 `/usr/share/doc/<Debian包名>/`。根级 ROS 环境文件不会进入产物，包内的环境钩子会保留。

直接运行 `build-deb` 默认输出到 `dist/`；`ci-build` 输出到 `dist/<发行版>/<架构>/`，避免合并矩阵产物时覆盖。发布脚本递归收集所有 `.deb`，上传到以工作空间名分组的 Registry，在一个 Release 中列出全部目标的下载链接。

打包器拒绝源码路径泄漏、外部或失效符号链接、与现有 ROS 文件冲突的载荷。外部依赖支持 APT 和 pip；pip 通过 TUNA 在开发安装及 deb 配置阶段安装，vendor wheel 原样存放于 share，详见 [模板比较](../docs/template-comparison.md)。不提供交叉编译、APT 仓库或离线依赖集合。开发环境不要先安装自身发布包，否则文件冲突检查会失败。

快速回归测试：`/usr/bin/python3 -m unittest discover -s tests -v`。完整构建及包内交付测试：`bash scripts/ci-build`；其中测试失败会打印警告并继续，仍保留测试报告，构建或打包失败则返回非零状态。失败的发布构建会打印保留的临时目录路径，可在其中查看 `log/`。

模板扩展约定及三仓库比较见 [docs/template-comparison.md](../docs/template-comparison.md)。
`packaging/lfs.toml` 可按仓库路径选择 LFS 文件；未配置时使用仓库自身默认值。
`tests/smoke-installed` 的 `ROS_DEB_TEST_REPORTS` 可指定 JUnit 目录，CI 自动保留安装测试报告。
共享 pip 的真实安装/卸载回归仅在一次性 root 容器中运行：
`ROS_DEB_TEST_DISPOSABLE=1 /usr/bin/python3 -m unittest discover -s tests -p test_pip_lifecycle.py -v`。
