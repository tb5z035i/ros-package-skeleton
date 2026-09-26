from setuptools import find_packages, setup

package_name = 'hello_py'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'LICENSE']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Team',
    maintainer_email='team@example.com',
    description='Minimal rclpy publisher example.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': ['talker = hello_py.talker:main']},
)
