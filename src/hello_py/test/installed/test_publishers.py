"""Exercise both installed ros2 run entry points over real ROS topics."""

import os
import signal
import subprocess
import tempfile
import time
import unittest

import rclpy
from std_msgs.msg import String


class PublisherTests(unittest.TestCase):
    def check_publisher(self, package, expected):
        if os.environ.get('ROS_DISTRO') == 'humble':
            os.environ.setdefault('ROS_LOCALHOST_ONLY', '1')
        else:
            os.environ.setdefault('ROS_AUTOMATIC_DISCOVERY_RANGE', 'LOCALHOST')
        os.environ.setdefault('ROS_DOMAIN_ID', '108')
        prefix = os.environ.get('ROS_SMOKE_EXPECT_PREFIX')
        if prefix:
            actual = subprocess.check_output(['ros2', 'pkg', 'prefix', package], text=True)
            self.assertEqual(actual.strip(), prefix)

        rclpy.init()
        self.addCleanup(rclpy.try_shutdown)
        node = rclpy.create_node('smoke_' + package)
        self.addCleanup(node.destroy_node)
        received = []
        topic = '/smoke_' + package
        subscription = node.create_subscription(String, topic, lambda msg: received.append(msg.data), 10)
        with tempfile.TemporaryFile(mode='w+') as output:
            process = subprocess.Popen(
                ['ros2', 'run', package, 'talker', '--ros-args', '-r', 'hi:=' + topic],
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + 30
                while expected not in received and time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    rclpy.spin_once(node, timeout_sec=0.2)
                output.seek(0)
                self.assertIn(expected, received, f'{package} did not publish: {output.read()}')
            finally:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                node.destroy_subscription(subscription)

    def test_rclpy_entry_point_publishes(self):
        self.check_publisher('hello_py', 'hi from rclpy')

    def test_rclcpp_entry_point_publishes(self):
        self.check_publisher('hello_cpp', 'hi from rclcpp')


if __name__ == '__main__':
    unittest.main(verbosity=2)
