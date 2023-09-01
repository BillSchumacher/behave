#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
Explore encoding settings on a platform.
"""

from __future__ import print_function
import sys
import platform
import locale
from behave.textutil import select_best_encoding

def explore_platform_encoding():
    python_version = platform.python_version()
    print(
        f"python {python_version} (platform: {sys.platform}, {platform.python_implementation()}, {platform.platform()})"
    )
    print(f"sys.getfilesystemencoding():   {sys.getfilesystemencoding()}")
    print(f"locale.getpreferredencoding(): {locale.getpreferredencoding()}")
    print(f"behave.textutil.select_best_encoding(): {select_best_encoding()}")
    return 0

if __name__ == "__main__":
    sys.exit(explore_platform_encoding())
