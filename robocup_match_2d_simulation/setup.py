import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'robocup_match_2d_simulation'

static_files = []
static_root = os.path.join(package_name, 'static')
for dirpath, _, filenames in os.walk(static_root):
    if filenames:
        rel = os.path.relpath(dirpath, package_name)
        dest = os.path.join('share', package_name, rel)
        static_files.append((dest, [os.path.join(dirpath, f) for f in filenames]))

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/sim.launch.py']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ] + static_files,
    install_requires=['setuptools', 'fastapi', 'uvicorn', 'pydantic', 'PyYAML'],
    zip_safe=False,
    maintainer='robocup_match_analyze_tools',
    maintainer_email='jeung158@hanyang.ac.kr',
    description='2D simulator for robocup_realtime_monitoring with built-in web UI',
    license='Apache 2.0',
    entry_points={
        'console_scripts': [
            'robocup_match_2d_simulation = robocup_match_2d_simulation.sim_node:main',
        ],
    },
)
