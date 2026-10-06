#!/usr/bin/env python3
"""
Launcher cho PR Report App:
Nạp và chạy tệp daily_report.py động từ bên ngoài mà không cần rebuild PyInstaller.
"""

import concurrent.futures
import datetime
import enum
import json
import os
import queue
import runpy
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import tkinter.font
import traceback
import urllib.request
from tkinter import messagebox


def get_target_script() -> str:
    # 1. Ưu tiên file trong thư mục làm việc / repo nguồn
    dev_path = "/Applications/Tuan/Fetch PR commit/daily_report.py"
    if os.path.exists(dev_path):
        return dev_path

    # 2. Ưu tiên file trong Application Support (nơi lưu các bản hot-update)
    app_support_dir = os.path.expanduser("~/Library/Application Support/PR Report")
    app_support_script = os.path.join(app_support_dir, "daily_report.py")
    if os.path.exists(app_support_script):
        return app_support_script

    # 3. Thư mục hiện tại nếu launcher đứng cùng daily_report.py
    current_dir_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_report.py")
    if os.path.exists(current_dir_script):
        return current_dir_script

    # 4. Tệp đóng gói sẵn bên trong PyInstaller bundle (_MEIPASS)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled_script = os.path.join(meipass, "daily_report.py")
        if os.path.exists(bundled_script):
            return bundled_script

    return dev_path


def main() -> None:
    script_path = get_target_script()
    if not os.path.exists(script_path):
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "PR Report Error",
            f"Cannot find daily_report.py script at:\n{script_path}"
        )
        sys.exit(1)

    try:
        # Thêm thư mục chứa script vào sys.path để import tương đối nếu cần
        script_dir = os.path.dirname(script_path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

        # Chạy script dưới danh nghĩa __main__
        runpy.run_path(script_path, run_name="__main__")
    except Exception as e:
        err_msg = traceback.format_exc()
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("PR Report Launch Error", f"Error running script:\n{e}\n\n{err_msg[:500]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
