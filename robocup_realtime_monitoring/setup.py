import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'robocup_realtime_monitoring'


def collect_static_files():
    """Install the static/ subdirectory structure as-is into share/."""
    data = []
    static_root = os.path.join(package_name, 'static')
    for dirpath, _dirnames, filenames in os.walk(static_root):
        if not filenames:
            continue
        rel = os.path.relpath(dirpath, package_name)
        dest = os.path.join('share', package_name, rel)
        srcs = [os.path.join(dirpath, f) for f in filenames]
        data.append((dest, srcs))
    return data


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    package_data={
        package_name: [
            'static/**/*',
        ],
    },
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ] + collect_static_files(),
    install_requires=['setuptools', 'fastapi', 'uvicorn', 'pyyaml', 'pydantic'],
    zip_safe=True,
    maintainer='robocup_match_analyze_tools',
    maintainer_email='todo@todo.com',
    description='RoboCup realtime monitoring: strategy zone GUI + UDP team communication.',
    license='BSD',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'robocup_strategy_gui_web = robocup_realtime_monitoring.main_web:main',
            'robocup_udp_sender = robocup_realtime_monitoring.udp_sender:main',
        ],
    },
)
