"""Publish a greeting once a second."""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String


class Talker(Node):
    def __init__(self):
        super().__init__('hello_py')
        self.publisher = self.create_publisher(String, 'hi', 10)
        self.timer = self.create_timer(1.0, self.publish_hi)

    def publish_hi(self):
        message = String()
        message.data = 'hi from rclpy'
        self.publisher.publish(message)
        self.get_logger().info(message.data)


def main(args=None):
    rclpy.init(args=args)
    node = Talker()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
