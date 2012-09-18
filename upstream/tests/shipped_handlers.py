# -*- coding: UTF-8 -*-

'''smoketesting shipped handlers'''

# (c) 2008 Canonical Ltd.
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

import unittest, sys, os.path, re

from jockey.oslib import OSLib
import jockey.detection
import jockey.backend
import jockey.xorg_driver

import sandbox

class ShippedHandlerTest(sandbox.LogTestCase):

    def setUp(self):
        '''Provide an AbstractUI instance for getting _() etc. and save/restore
        /proc/modules, module blacklist, installed packages, and xorg.conf.
        '''
        self.backend = jockey.backend.Backend()

        self.orig_oslib = OSLib.inst
        OSLib.inst = sandbox.AllAvailOSLib()

    def tearDown(self):
        OSLib.inst = self.orig_oslib
        OSLib.inst._make_xorg_conf()

    def test_shipped_handlers(self):
        '''validity of shipped default and example handlers'''

        self._run_tests()

    def test_shipped_handlers_invalid_xorgconf(self):
        '''validity of shipped handlers with invalid xorg.conf'''

        # append some breakage
        f = open(OSLib.inst.xorg_conf_path, 'a')
        print >> f, '''
EndSection

Section "Module"
EndSection
'''
        f.close()

        self._run_tests()

    def _run_tests(self):
        log_offset = sandbox.log.tell()
        basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        if os.path.isdir(os.path.join(basedir, 'examples')):
            handler_dir=[os.path.join(basedir, 'examples', 'handlers'),
                         os.path.join(basedir, 'data', 'handlers')]
        else:
            handler_dir=['/usr/share/jockey/handlers']
        handlers = jockey.detection.get_handlers(self.backend,
                handler_dir=handler_dir, available_only=False)
        log = sandbox.log.getvalue()[log_offset:]

        self.failIf('Could not instantiate Handler' in log, log)

        self.assert_(len(handlers) > 2)
        for h in handlers:
            self.assert_(hasattr(h.id(), 'isspace'), 
                '%s.id() returns a string' % str(h))
            self.assert_(hasattr(h.name(), 'isspace'), 
                '%s.name() returns a string' % str(h))
            s = h.description()
            self.assert_(s is None or hasattr(s, 'isspace'), 
                '%s.description() returns a None or a string' % str(h))
            s = h.rationale()
            self.assert_(s is None or hasattr(s, 'isspace'), 
                '%s.rationale() returns a None or a string' % str(h))
            self.assertEqual(h.changed(), False)
            self.assert_(h.free() in (True, False))
            self.assert_(h.enabled() in (True, False))
            self.assert_(h.used() in (True, False))
            self.assert_(h.available() in (True, False, None))

            # X.org driver handlers
            if isinstance(h, jockey.xorg_driver.XorgDriverHandler):
                if h.xorg_conf:
                    h.enable_config_hook()
                    h.disable_config_hook()
                self.assert_(h.enables_composite() in (True, False, None))

            # note that we cannot do any stronger assumptions here, since
            # drivers might not be available, enabling fails, etc.; but we at
            # least test the code paths
            if not h.can_change():
                h.enable()
                self.assert_(h.enabled() in (True, False))
                self.assert_(h.enabled() in (True, False))
                h.disable()
                self.assert_(h.enabled() in (True, False))
                self.assert_(h.enabled() in (True, False))
