from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    port = LaunchConfiguration('port')

    return LaunchDescription([
        DeclareLaunchArgument(
            'port',
            default_value='9090',
            description='Port for rosbridge_websocket'
        ),
        LogInfo(msg=['rosbridge_websocket serving on port ', port]),
        Node(
            package='rosbridge_server',
            executable='rosbridge_websocket',
            name='rosbridge_websocket',
            output='screen',
            parameters=[{'port': port}],
            remappings=[('/rosout', '/rosout')]
        ),
    ])
