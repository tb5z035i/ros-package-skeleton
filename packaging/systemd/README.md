Add `.service` or `.service.in` files here. The packager installs them into
`/usr/lib/systemd/system/`, replacing `@PREFIX@`, `@ROS_DISTRO@` and
`@DEB_PACKAGE@` in filenames and contents. Use a distro-qualified filename when
Jazzy and Humble packages may coexist, e.g. `robot-@ROS_DISTRO@@.service.in`.

A service can source `@PREFIX@/setup.bash` and invoke `ros2 launch` directly.
Installation/removal only reloads systemd's unit definitions; enabling, starting,
stopping and restarting services are explicit operator actions.

Declare operator-edited installed configuration in `../conffiles`. Normal ROS
configuration/resource installation still belongs in package CMake/setup rules.
