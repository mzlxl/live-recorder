# -*- coding: utf-8 -*-
"""跨平台文件系统操作：打开文件 / 在文件管理器显示文件 / 打开目录。"""
import os
import platform
import subprocess


def _sys():
    return platform.system()


def open_file(path):
    """用系统默认应用打开文件。"""
    if not os.path.exists(path):
        return False
    s = _sys()
    if s == "Darwin":
        subprocess.Popen(["open", path])
    elif s == "Windows":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
    return True


def reveal_file(path):
    """在文件管理器中显示并选中该文件。"""
    if not os.path.exists(path):
        return False
    s = _sys()
    if s == "Darwin":
        subprocess.Popen(["open", "-R", path])
    elif s == "Windows":
        subprocess.Popen(["explorer", f"/select,{os.path.abspath(path)}"])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])
    return True


def open_dir(path):
    """在文件管理器中打开目录。"""
    if not os.path.exists(path):
        return False
    s = _sys()
    if s == "Darwin":
        subprocess.Popen(["open", path])
    elif s == "Windows":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
    return True
