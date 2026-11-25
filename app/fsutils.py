# -*- coding: utf-8 -*-
"""跨平台文件系统操作：打开文件 / 在文件管理器显示文件 / 打开目录。"""
import os
import platform
import subprocess


def _sys():
    return platform.system()


def _require_file(path):
    if not path or not os.path.isfile(path):
        raise FileNotFoundError("产物文件不存在（可能录制失败或已被删除）")
    return os.path.abspath(path)


def _require_dir(path):
    if not path or not os.path.isdir(path):
        raise FileNotFoundError("目录不存在")
    return os.path.abspath(path)


def open_file(path):
    """用系统默认应用打开文件。"""
    p = _require_file(path)
    try:
        if _sys() == "Darwin":
            subprocess.Popen(["open", p])
        elif _sys() == "Windows":
            os.startfile(p)
        else:
            subprocess.Popen(["xdg-open", p])
    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"无法打开文件：{e}") from e
    return True


def reveal_file(path):
    """在文件管理器中显示并选中该文件。"""
    p = _require_file(path)
    try:
        if _sys() == "Darwin":
            subprocess.Popen(["open", "-R", p])
        elif _sys() == "Windows":
            explorer = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "explorer.exe")
            try:
                subprocess.Popen([explorer, f"/select,{p}"])
            except Exception:
                os.startfile(os.path.dirname(p))
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(p)])
    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"无法定位文件：{e}") from e
    return True


def open_dir(path):
    """在文件管理器中打开目录。"""
    p = _require_dir(path)
    try:
        if _sys() == "Darwin":
            subprocess.Popen(["open", p])
        elif _sys() == "Windows":
            os.startfile(p)
        else:
            subprocess.Popen(["xdg-open", p])
    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"无法打开目录：{e}") from e
    return True
