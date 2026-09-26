ARG ROS_IMAGE=ros:jazzy-ros-core
FROM ${ROS_IMAGE}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV ROSDISTRO_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/rosdistro/index-v4.yaml

COPY .devcontainer/ros.key /tmp/ros-workspace/.devcontainer/ros.key
COPY scripts/configure-mirrors scripts/install-build-tools /tmp/ros-workspace/scripts/
RUN bash /tmp/ros-workspace/scripts/install-build-tools \
    && rm -rf /tmp/ros-workspace \
    && rm -rf /var/lib/apt/lists/*

# Desktop and camera tools belong to the dev image; CI uses install-build-tools only.
RUN apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
        libgl1-mesa-dri libglx-mesa0 mesa-utils \
        xauth x11-apps x11-utils usbutils v4l-utils bubblewrap \
    && rm -rf /var/lib/apt/lists/*

# Dev Containers maps this user's UID/GID to the local Linux user.
RUN if id -u ubuntu >/dev/null 2>&1; then userdel -r ubuntu; fi \
    && useradd --create-home --shell /bin/bash --uid 1000 --groups sudo ros \
    && echo 'ros ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ros \
    && chmod 0440 /etc/sudoers.d/ros \
    && mkdir -p /workspaces/ros_ws \
    && chown ros:ros /workspaces/ros_ws

USER ros
RUN echo 'source /opt/ros/jazzy/setup.bash' >> ~/.bashrc \
    && echo 'if [ -f /workspaces/ros_ws/install/setup.bash ]; then source /workspaces/ros_ws/install/setup.bash; fi' >> ~/.bashrc

WORKDIR /workspaces/ros_ws
CMD ["bash"]
