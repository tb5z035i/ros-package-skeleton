# Debian 打包

`build-deb` 和 `deb_packaging.py` 支持 Ubuntu 24.04 / ROS 2 Jazzy 的 `ament_cmake` 与 `ament_python`。使用系统 `/usr/bin/python3`，按本机架构构建。

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

`packaging.toml` 中 `package.license_files` 必须列出随二进制分发的许可证。`dependencies.build/runtime` 接受 Debian 包名，常规 ROS 依赖应写入 `package.xml`。`install-deps` 会安装清单依赖（含测试依赖）及两类补充依赖；发布打包器本身不会安装依赖。

打包过程独立加载 `/opt/ros/jazzy`，在临时目录进行非符号链接的 Release 构建，合并到 `/opt/ros/jazzy`。运行依赖通过 rosdep 与 ELF 分析生成；许可证和 ROS 包版本清单写入 `/usr/share/doc/<Debian包名>/`。根级 ROS 环境文件不会进入产物，包内的环境钩子会保留。

打包器拒绝源码路径泄漏、外部或失效符号链接、与现有 ROS 文件冲突的载荷。外部依赖必须可映射到 APT 包；不提供交叉编译、APT 仓库或离线依赖集合。开发环境不要先安装自身发布包，否则文件冲突检查会失败。

快速回归测试：`/usr/bin/python3 -m unittest discover -s tests -v`。完整构建及两个节点的消息测试：`bash scripts/ci-build`。失败的发布构建会打印保留的临时目录路径，可在其中查看 `log/`。
