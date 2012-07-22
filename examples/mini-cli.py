#!/usr/bin/env python

# (c) 2009 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

'''Skeleton of a pure command line interface.

Note that this is just a gross hack for demo purposes. A real CLI should
inherit and properly implement jockey.ui.AbstractUI.'''

import sys

import jockey.backend
from jockey.oslib import OSLib

if len(sys.argv) not in (1,3):
    print >> sys.stderr, '''Usage:
  %(prog)  - list available drivers
  %(prog) enable <driver>  - enable driver
  %(prog) disable <driver> - disable driver
''' % { 'prog': sys.argv[0] }

OSLib.inst = OSLib()
backend = jockey.backend.Backend()

if len(sys.argv) == 1:
    print backend.available()
    sys.exit(0)

if sys.argv[1] == 'enable':
    backend.set_enabled(sys.argv[2], True)
elif sys.argv[1] == 'disable':
    backend.set_enabled(sys.argv[2], False)
else:
    print >> sys.stderr, 'Invalid mode', sys.argv[1]
    sys.exit(1)
