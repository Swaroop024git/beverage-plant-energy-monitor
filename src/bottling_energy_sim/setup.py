from setuptools import setup

package_name = 'bottling_energy_sim'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    install_requires=['setuptools', 'PyYAML'],
    zip_safe=True,
    maintainer='YourName',
    maintainer_email='you@example.com',
    description='Simulated bottling line energy publisher for ROS2',
    license='Apache-2.0',
    include_package_data=True,
    package_data={
        'bottling_energy_sim': ['data/*.yaml'],
    },
    data_files=[
        # ament resource index marker
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        # install package.xml
        ('share/' + package_name, ['package.xml']),
        # install launch files
        ('share/' + package_name + '/launch', ['launch/energy_pub_launch.py']),
        ('share/' + package_name + '/launch', ['launch/rosbridge_websocket_launch.py']),
    ],
    entry_points={
        'console_scripts': [
            'energy_publisher = bottling_energy_sim.energy_publisher:main',
        ],
    },
)
