cmake_minimum_required(VERSION 3.8)
project(hello_cpp)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(talker src/talker.cpp)
target_compile_features(talker PUBLIC cxx_std_17)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(talker PRIVATE -Wall -Wextra -Wpedantic)
endif()
ament_target_dependencies(talker rclcpp std_msgs)

install(TARGETS talker DESTINATION lib/${PROJECT_NAME})
install(FILES LICENSE DESTINATION share/${PROJECT_NAME})
ament_package()
