import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'robocup_match_analyzer'

# Collect static files
static_files = []
static_root = os.path.join(package_name, 'static')
for dirpath, _, filenames in os.walk(static_root):
    if filenames:
        rel = os.path.relpath(dirpath, package_name)
        dest = os.path.join('share', package_name, rel)
        static_files.append((dest, [os.path.join(dirpath, f) for f in filenames]))

setup(
    name=package_name,
    version='0.2.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ] + static_files,
    install_requires=['setuptools', 'fastapi', 'uvicorn'],
    zip_safe=False,
    maintainer='robocup_match_analyze_tools',
    maintainer_email='jeung158@hanyang.ac.kr',
    description='Strategy analysis GUI with merged MCAP download support',
    license='Apache 2.0',
    entry_points={
        'console_scripts': [
            'strategy_analyzer = robocup_match_analyzer.main_web:main',
        ],
    },
)
