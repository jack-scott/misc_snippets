from setuptools import find_packages, setup

package_name = 'cadvisor_monitor'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=[
        'setuptools',
        'requests',
    ],
    zip_safe=True,
    maintainer='Jack',
    maintainer_email='jack@example.com',
    description='ROS 2 node for publishing container metrics from cAdvisor',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'container_stats_publisher = cadvisor_monitor.container_stats_publisher:main',
        ],
    },
)
