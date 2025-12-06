from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='bottling_energy_sim',
            executable='energy_publisher',
            output='screen'
        )
    ])
