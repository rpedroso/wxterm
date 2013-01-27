#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))

try:
    LONG_DESCRIPTION = open(os.path.join(here, "README")).read()
except IOError:
    LONG_DESCRIPTION = ""


CLASSIFIERS = (
    "Development Status :: 4 - Beta",
    "Environment :: X11 Applications :: GTK",
    "Intended Audience :: Developers",
    "Operating System :: POSIX :: Linux",
    "License :: OSI Approved :: wxWindows Licence",
    "Programming Language :: Python",
    "Topic :: Terminals :: Terminal Emulators/X Terminals",
)


setup(name='wxterm',
      version='0.0.1',
      packages=['wxterm'],
      author='Ricardo Pedroso',
      author_email='rmdpedroso@gmail.com',
      description='wxPython terminal emulator',
      long_description=LONG_DESCRIPTION,
      classifiers=CLASSIFIERS,
      keywords=["pyte", "wxPython", "terminal emulator"],
      license='LICENSE',
      url='https://github.com/rpedroso/wxterm',
      install_requires=[
          "pyte >= 0.4.6",
          ],
     )
