#!/usr/bin/env python

# (c) 2007 Canonical Ltd.
# Author: Martin Pitt <martin.pitt@ubuntu.com>

# This script needs python-distutils-extra, an extension to the standard
# distutils which provides i18n, icon support, etc.
# https://launchpad.net/python-distutils-extra

from glob import glob
from distutils.version import StrictVersion

try:
    import DistUtilsExtra.auto
except ImportError:
    import sys
    print >> sys.stderr, 'To build Jockey you need https://launchpad.net/python-distutils-extra'
    sys.exit(1)

assert StrictVersion(DistUtilsExtra.auto.__version__) >= '2.4', 'needs DistUtilsExtra.auto >= 2.4'

DistUtilsExtra.auto.setup(
    name='jockey',
    version='0.9.7',
    description='UI for managing third-party and non-free drivers',
    url='https://launchpad.net/jockey',
    license='GPL v2 or later',
    author='Martin Pitt',
    author_email='martin.pitt@ubuntu.com',

    data_files = [
        ('share/jockey', ['backend/jockey-backend']),
        ('share/jockey', ['gtk/jockey-gtk.ui']), # bug in DistUtilsExtra.auto 2.2
        ('share/jockey', glob('kde/*.ui')), # don't use pykdeuic4
        ],
    scripts = ['gtk/jockey-gtk', 'kde/jockey-kde', 'text/jockey-text'],
)
