"""Check the public ROS topic produced by the Python node."""

import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String

from hello_py.talker import Talker


def test_talker_publishes_hi(monkeypatch):
    monkeypatch.setenv('ROS_AUTOMATIC_DISCOVERY_RANGE', 'LOCALHOST')
    monkeypatch.setenv('ROS_DOMAIN_ID', '109')
    rclpy.init(args=['--ros-args', '-r', 'hi:=/test_hello_py'])
    talker = Talker()
    listener = rclpy.create_node('hello_py_test')
    executor = SingleThreadedExecutor()
    try:
        received = []
        listener.create_subscription(String, 'hi', lambda message: received.append(message.data), 10)
        executor.add_node(talker)
        executor.add_node(listener)
        deadline = time.monotonic() + 10
        while not received and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.1)
        assert 'hi from rclpy' in received
    finally:
        executor.shutdown()
        listener.destroy_node()
        talker.destroy_node()
        rclpy.try_shutdown()
