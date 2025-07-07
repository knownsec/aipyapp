"""
This is a setup.py script for packaging the aipyapp application.
"""

from setuptools import setup
import os
import sys

# 确保py2app可用
try:
    import py2app
except ImportError:
    print("Error: py2app is not installed. Please install it with 'pip install py2app'")
    sys.exit(1)

# 获取所有资源文件
def get_resource_files():
    resource_files = []
    res_dir = 'aipyapp'
    for file in os.listdir(res_dir):
        if os.path.isfile(os.path.join(res_dir, file)):
            resource_files.append(os.path.join(res_dir, file))
    return resource_files

# 只有在py2app命令时才使用这些选项
if 'py2app' in sys.argv:
    extra_options = {
        'app': ['aipyapp_gui_launcher.py'],
        'data_files': [('res', get_resource_files())],
        'options': {
            'py2app': {
                'argv_emulation': False,
                'packages': [
                    'aipyapp',
                    'wx',
                    'matplotlib',
                    'rich',
                    'anthropic',
                    'PIL',
                    'loguru',
                    'dynaconf',
                ],
                'includes': [
                    'pathlib',
                    'importlib',
                    'json',
                    'queue',
                    'threading',
                    'wx.adv',
                    'wx.html',
                    'wx.html2',
                    'matplotlib.backends.backend_wxagg',
                    'numpy',
                    'argparse',
                    'base64',
                    'mimetypes',
                ],
                'excludes': [
                    'tkinter',
                    'PyQt5',
                    'PyQt6',
                    'PySide2',
                    'PySide6',
                ],
                'frameworks': [],
                'iconfile': './aipyapp/aipy.icns',
                'plist': {
                    'CFBundleName': 'AiPy',
                    'CFBundleDisplayName': 'AiPy',
                    'CFBundleIdentifier': 'com.aipy.aipyapp',
                    'CFBundleVersion': '1.0.0',
                    'CFBundleShortVersionString': '1.0.0',
                    'NSHumanReadableCopyright': '© 2025 AiPy',
                    'NSHighResolutionCapable': True,
                    'CFBundleDocumentTypes': [],
                    'NSPrincipalClass': 'NSApplication',
                },
                'semi_standalone': False,
                'site_packages': True,
                'strip': False,
            }
        }
    }
else:
    extra_options = {}

setup(
    name="AiPy",
    version="0.1.27",
    description="AiPy, Your AI is just like a drudge, Help earn money, Help slack off, Help find lover, anything goes.",
    author="AiPy Team",
    author_email="luol2@knownsec.com",
    url="https://aipy.app",
    packages=['aipyapp'],
    **extra_options
)
