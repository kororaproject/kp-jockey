# -*- coding: UTF-8 -*-

'''detection tests'''

# (c) 2007 Canonical Ltd.
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

import unittest, os.path, shutil, locale, subprocess, sys
from glob import glob

import jockey.detection, jockey.backend
from jockey.detection import HardwareID
from jockey.oslib import OSLib

import sandbox, httpd

class DetectionTest(sandbox.LogTestCase):
    def tearDown(self):
        '''Clean handler dir.'''

        shutil.rmtree(OSLib.inst.handler_dir)
        os.mkdir(OSLib.inst.handler_dir)
        OSLib.inst.reset_dmi()
        # remove DriverDB caches
        for f in glob(os.path.join(OSLib.inst.backup_dir, 'driverdb-*.cache')):
            os.unlink(f)

        OSLib.inst.reset_packages()

    def test_get_hardware(self):
        '''get_hardware() returns correct hardware'''

        hw = jockey.detection.get_hardware()
        
        #filter out printers, since we cannot predict them
        self.assertEqual('\n'.join(sorted([str(h) for h in hw if h.type != 'printer_deviceid'])),
            '''HardwareID('modalias', 'dmi:foo[A-1]bar')
HardwareID('modalias', 'fire:1.2')
HardwareID('modalias', 'pci:v00001001d00003D01sv00001234sd00000001bc03sc00i00')
HardwareID('modalias', 'pci:v0000AAAAd000012AAsv00000000sdDEADBEEFbc02sc80i00')
HardwareID('modalias', 'pci:v0000DEAFd00009999sv00000000sd00000000bc99sc00i00')
HardwareID('modalias', 'pci:v0000FFF0d00000001sv00000000sd00000000bc06sc01i01')
HardwareID('modalias', 'ssb:v4243id0812rev05')''')

    def test_hwid_equality(self):
        '''HardwareID equality implementation
        
        This tests modalias pattern matching in particular, since this is
        nontrivial.'''

        # identity
        x = HardwareID('pci', '1234/5678')
        self.assertEqual(x, x)
        self.failIf(x != x)

        # trivial equality
        x = HardwareID('pci', '1234/5678')
        y = HardwareID('pci', '1234/5678')
        self.assertEqual(x, y)
        self.failIf(x != y)
        self.assertEqual(hash(x), hash(y))

        x = HardwareID('modalias', 'pci:v00001001d00003D01sv00001234sd00000001bc03sc00i00') 
        y = HardwareID('modalias', 'pci:v00001001d00003D01sv00001234sd00000001bc03sc00i00') 
        self.assertEqual(x, y)
        self.failIf(x != y)
        self.assertEqual(hash(x), hash(y))

        # trivial inequality
        x = HardwareID('pci', '1234/5678')
        y = HardwareID('pci', '1234/5679')
        self.assertNotEqual(x, y)
        self.assert_(x != y)
        y = HardwareID('dmi', '42')
        self.assertNotEqual(x, y)
        self.assert_(x != y)
        y = 'IamNotAHardwareID'
        self.assertNotEqual(x, y)
        self.assert_(x != y)

        x = HardwareID('modalias', 'pci:v00001001d00003D01sv00001234sd00000001bc03sc00i00') 
        y = HardwareID('modalias', 'pci:v00001001d00003D01sv00001235sd00000001bc03sc00i00') 
        self.assertNotEqual(x, y)
        self.assert_(x != y)

        # modalias pattern equality
        x = HardwareID('modalias', 'pci:v00001*d00003D*sv*sd*1bc03sc00i*') 
        y = HardwareID('modalias', 'pci:v00001001d00003D01sv00001234sd00000001bc03sc00i00') 

        self.assertEqual(x, y)
        self.failIf(x != y)
        self.assertEqual(y, x)
        self.failIf(y != x)
        self.assertEqual(hash(x), hash(y))

        # pattern comparison; this is necessary for usage as dictionary keys,
        # but should just be string comparison
        x = HardwareID('modalias', 'pci:v00001*d00003D*sv*sd*1bc03sc00i*') 
        y = HardwareID('modalias', 'pci:v00001*d00003D*sv*sd*1bc03sc00i*') 
        self.assertEqual(x, y)
        self.assertEqual(hash(x), hash(y))
        y = HardwareID('modalias', 'pci:v00001*d*sv*sd*1bc03sc00i*') 
        self.assertNotEqual(x, y)

        # non-modalias values should not match on patterns
        x = HardwareID('pci', '1234/5678')
        y = HardwareID('pci', '12*/56*')
        self.assertNotEqual(x, y)

    def test_hwid_dictionary(self):
        '''HardwareID can be used as dictionary keys''' 

        d = {
            HardwareID('pci', '1234/5678'): 'pci1',
            HardwareID('pci', '1234/5679'): 'pci2',
            HardwareID('modalias', 'pci:v0000AAAAd000012AAsv00000000sdDEADBEEFbc02sc80i00'): 'ma1',
            HardwareID('modalias', 'pci:v00001*d00003D*sv*sd*1bc03sc00i*'): 'ma_bc03',
            HardwareID('modalias', 'pci:v00001*d00003D*sv*sd*1bc04sc00i*'): 'ma_bc04',
        }

        self.assertEqual(d[HardwareID('pci', '1234/5678')], 'pci1')
        self.assertRaises(KeyError, d.__getitem__, HardwareID('pci', '1235/1111'))
        self.assertEqual(d[HardwareID('modalias',
            'pci:v00001001d00003D01sv00001234sd00000001bc03sc00i00')], 'ma_bc03')
        self.assertEqual(d[HardwareID('modalias',
            'pci:v0000AAAAd000012AAsv00000000sdDEADBEEFbc02sc80i00')], 'ma1')
        self.assertRaises(KeyError, d.__getitem__, HardwareID('modalias',
            'pci:v0000FFF0d00000001sv00000000sd00000000bc06sc01i01'))

    def test_get_handlers_no_driverdb(self):
        '''get_handlers() returns applicable handlers without a driver db'''

        open (os.path.join(OSLib.inst.handler_dir, 'kmod_nodetect.py'), 'w').write(
            sandbox.h_availability_py)

        h = jockey.detection.get_handlers(jockey.backend.Backend())

        self.assertEqual(len(h), 1, 'get_handlers() found one applicable handler')
        for h in h: pass # get single item in set h
        self.assert_(isinstance(h, jockey.handlers.Handler))
        self.assert_(h.available())
        self.assertEqual(str(h.__class__).split('.')[-1], 'AvailMod')
        self.assertEqual(h.module, 'vanilla')
        self.assertEqual(h.name(), 'free module with available hardware, graphics card')

        self.assert_(h.enabled())

    def test_get_handlers_invalid(self):
        '''get_handlers() does not fall over when reading invalid handler
        files'''

        open (os.path.join(OSLib.inst.handler_dir, '01_no_python.py'), 'w').write(
            "Ce n'est ne pas un fichier Python!")
        open (os.path.join(OSLib.inst.handler_dir, '02_valid.py'), 'w').write(
            'import jockey.handlers\n' + sandbox.h_avail_mod)
        open (os.path.join(OSLib.inst.handler_dir, '03_inval_python.py'), 'w').write(
            'import i.do.not.exist\n' + sandbox.h_avail_mod.replace('AvailMod', 'AlsoAvailMod'))

        h = jockey.detection.get_handlers(jockey.backend.Backend())

        self.assertEqual(len(h), 1, 'get_handlers() found one applicable handler')
        for h in h: pass # get single item in set h
        self.assert_(isinstance(h, jockey.handlers.Handler))
        self.assertEqual(h.module, 'vanilla')
        self.assert_('Invalid custom handler' in sandbox.log.getvalue())

    def test_get_handlers_driverdb(self):
        '''get_handlers() returns applicable handlers with querying the driver db'''

        open (os.path.join(OSLib.inst.handler_dir, 'testhandlers.py'), 'w').write('''
import jockey.handlers

%s

class VanillaGfxHandler(jockey.handlers.KernelModuleHandler):
    def __init__(self, backend):
        jockey.handlers.KernelModuleHandler.__init__(self, backend, 'vanilla3d')

class NonexistingModHandler(jockey.handlers.KernelModuleHandler):
    def __init__(self, backend):
        jockey.handlers.KernelModuleHandler.__init__(self, backend, 'nonexisting')
''' % sandbox.h_avail_mod)

        db = sandbox.TestDriverDB()
        backend = jockey.backend.Backend()
        db.update(backend.hardware)
        result = jockey.detection.get_handlers(backend, db)

        out = '\n'.join(sorted([str(h) for h in result]))
        self.assertEqual(out, 
'''firmware:firmwifi([FirmwareHandler, nonfree, disabled] standard module which needs firmware)
kmod:mint([KernelModuleHandler, nonfree, enabled] nonfree module with available hardware, wifi)
kmod:spam([KernelModuleHandler, free, enabled] free mystical module without modaliases)
kmod:vanilla([AvailMod, free, enabled] free module with available hardware, graphics card)
kmod:vanilla3d([VanillaGfxHandler, nonfree, enabled] nonfree, replacement graphics driver for vanilla)''')

        for h in result:
            if h.module == 'firmwifi':
                self.failIf(h.enabled())
                # firmwifi is the only matching driver for this hardware and
                # thus shouldn't be displayed as recommended altough the DB
                # marks it as such
                self.failIf(h.recommended())
            else:
                self.assert_(h.enabled())

    def test_get_handlers_private_class(self):
        '''get_handlers() ignores private base classes starting with _'''

        open(os.path.join(OSLib.inst.handler_dir, 'kmod_baseclass.py'), 'w').write(
            sandbox.h_privateclass_py)

        log_offset = sandbox.log.tell()
        h = jockey.detection.get_handlers(jockey.backend.Backend())
        log = sandbox.log.getvalue()[log_offset:]

        self.assertEqual(len(h), 1)
        for h in h: pass # get single item in set h
        self.assert_(isinstance(h, jockey.handlers.Handler))
        self.assert_(h.available())
        self.assertEqual(str(h.__class__).split('.')[-1], 'MyHandler')

        self.failIf('Could not instantiate Handler' in log, log)

    def test_localkernelmod_driverdb(self):
        '''LocalKernelModulesDriverDB creates appropriate handlers
        
        It should prefer custom handlers over autogenerated standard ones and
        create standard ones for detected hardware.'''

        open (os.path.join(OSLib.inst.handler_dir, 'testhandlers.py'), 'w').write('''
import jockey.handlers

class MintWrapper(jockey.handlers.KernelModuleHandler):
    def __init__(self, backend):
        jockey.handlers.KernelModuleHandler.__init__(self, backend, 'mint',
            'I taste even mintier')
''')

        db = jockey.detection.LocalKernelModulesDriverDB()

        result = jockey.detection.get_handlers(jockey.backend.Backend(), db)

        out = '\n'.join(sorted([str(h) for h in result]))

        self.assertEqual(out, 
'''kmod:firmwifi([KernelModuleHandler, free, enabled] standard module which needs firmware)
kmod:foodmi([KernelModuleHandler, free, enabled] foo DMI driver for [A-1] devices)
kmod:mint([MintWrapper, nonfree, enabled] I taste even mintier)
kmod:vanilla([KernelModuleHandler, free, enabled] free module with available hardware, graphics card)
kmod:vanilla3d([KernelModuleHandler, nonfree, enabled] nonfree, replacement graphics driver for vanilla)''')

        for h in result:
            self.assert_(h.enabled())

        # some invalid/unsupported queries, should not cause crashes or
        # problems
        self.assertEqual(db.query(HardwareID('unknownType', '1234')), [])
        self.assertEqual(db.query(HardwareID('modalias', 'nobus1234')), [])

    def test_localkernelmod_multiple_driverdb(self):
        '''get_handlers queries multiple driver DBs'''

        backend = jockey.backend.Backend()
        tddb = sandbox.TestDriverDB()
        tddb.update(backend.hardware)
        result = jockey.detection.get_handlers(backend,
            [tddb, jockey.detection.LocalKernelModulesDriverDB()])
        out = '\n'.join([str(h) for h in result])

        # LocalKernelModulesDriverDB delivers vanilla3d, TestDriverDB delivers
        # spam
        self.assert_('kmod:vanilla3d' in out)
        self.assert_('kmod:spam' in out)

    def test_localkernelmod_driverdb_ignored_customhandler(self):
        '''LocalKernelModulesDriverDB creates custom handler for ignored module'''

        open (os.path.join(OSLib.inst.handler_dir, 'testhandlers.py'), 
            'w').write(sandbox.h_ignored_custom_mod)

        result = jockey.detection.get_handlers(jockey.backend.Backend(),
            jockey.detection.LocalKernelModulesDriverDB())

        out = '\n'.join(sorted([str(h) for h in result]))

        self.assertEqual(out, 
'''kmod:dullstd([LessDullMod, free, enabled] standard module which should be ignored for detection)
kmod:firmwifi([KernelModuleHandler, free, enabled] standard module which needs firmware)
kmod:foodmi([KernelModuleHandler, free, enabled] foo DMI driver for [A-1] devices)
kmod:mint([KernelModuleHandler, nonfree, enabled] nonfree module with available hardware, wifi)
kmod:vanilla([KernelModuleHandler, free, enabled] free module with available hardware, graphics card)
kmod:vanilla3d([KernelModuleHandler, nonfree, enabled] nonfree, replacement graphics driver for vanilla)''')

        for h in result:
            self.assert_(h.enabled())

    def test_localkernelmod_driverdb_disabled_customhandler(self):
        '''LocalKernelModulesDriverDB properly treats disabled custom handlers
        
        It should prefer custom handlers over autogenerated standard ones even
        if the custom handler is not available, instead of falling back to
        creating a standard handler.
        '''
        open (os.path.join(OSLib.inst.handler_dir, 'testhandlers.py'),
                'w').write(sandbox.h_notavail_mint_mod)
        db = jockey.detection.LocalKernelModulesDriverDB()

        result = jockey.detection.get_handlers(jockey.backend.Backend(), db)

        out = '\n'.join(sorted([str(h) for h in result]))

        self.failIf('kmod:mint' in out, out)

    def test_localkernelmod_driverdb_overrides(self):
        '''LocalKernelModulesDriverDB respects modalias overrides'''

        try:
            f = open(os.path.join(OSLib.inst.modaliases[1], 'ham.alias'), 'w')
            f.write('''# some bogus modaliases
alias abcd foobar
alias usb:v057Cp3500d*dc*dsc*dp*ic*isc*ip* fcdslslusb
alias usb:v0582p0044d*dc*dsc*dp*ic*isc*ip* snd_usb_audio
''')
            f.close()

            # assign spam module to the unknown piece of hardware
            f = open(os.path.join(OSLib.inst.modaliases[1], 'spam'), 'w')
            f.write('''# let's put an use to spam
alias pci:v0000FFF0d*1sv*sd*bc06sc*i* spam
''')
            f.close()

            result = jockey.detection.get_handlers(jockey.backend.Backend(),
                jockey.detection.LocalKernelModulesDriverDB())

            out = '\n'.join(sorted([str(h) for h in result]))

            self.assertEqual(out, 
'''kmod:firmwifi([KernelModuleHandler, free, enabled] standard module which needs firmware)
kmod:foodmi([KernelModuleHandler, free, enabled] foo DMI driver for [A-1] devices)
kmod:mint([KernelModuleHandler, nonfree, enabled] nonfree module with available hardware, wifi)
kmod:spam([KernelModuleHandler, free, enabled] free mystical module without modaliases)
kmod:vanilla([KernelModuleHandler, free, enabled] free module with available hardware, graphics card)
kmod:vanilla3d([KernelModuleHandler, nonfree, enabled] nonfree, replacement graphics driver for vanilla)''')
        finally:
            for f in os.listdir(OSLib.inst.modaliases[1]):
                os.unlink(os.path.join(OSLib.inst.modaliases[1], f))

    def test_localkernelmod_driverdb_modalias_reset(self):
        '''LocalKernelModulesDriverDB resetting of modaliases'''

        try:
            f = open(os.path.join(OSLib.inst.modaliases[1], '01_bad'), 'w')
            f.write('alias pci:v0000FFF0d*sv*sd*bc*sc*i* cherry\n')
            f.close()
            # resets both the original and above bogus cherry entry; resetting
            # vanilla uncovers vanilla3d (which is the second candidate)
            f = open(os.path.join(OSLib.inst.modaliases[1], '02_reset'), 'w')
            f.write('reset cherry\nreset vanilla\n')
            f.close()
            f = open(os.path.join(OSLib.inst.modaliases[1], '03_good'), 'w')
            f.write('alias pci:v0000FFF0d*1sv*sd*bc06sc*i* spam\n')
            f.close()

            result = jockey.detection.get_handlers(jockey.backend.Backend(),
                jockey.detection.LocalKernelModulesDriverDB())

            out = '\n'.join(sorted([str(h) for h in result]))

            self.assertEqual(out, 
'''kmod:firmwifi([KernelModuleHandler, free, enabled] standard module which needs firmware)
kmod:foodmi([KernelModuleHandler, free, enabled] foo DMI driver for [A-1] devices)
kmod:mint([KernelModuleHandler, nonfree, enabled] nonfree module with available hardware, wifi)
kmod:spam([KernelModuleHandler, free, enabled] free mystical module without modaliases)
kmod:vanilla3d([KernelModuleHandler, nonfree, enabled] nonfree, replacement graphics driver for vanilla)''')
        finally:
            for f in os.listdir(OSLib.inst.modaliases[1]):
                os.unlink(os.path.join(OSLib.inst.modaliases[1], f))

    def test_localkernelmod_driverdb_package_headers(self):
        '''LocalKernelModulesDriverDB reads modaliases from package headers'''

        orig_phm = OSLib.inst.package_header_modaliases
        try:
            # assign spam module to the unknown piece of hardware
            OSLib.inst.package_header_modaliases = lambda: { 
                    'pretzel': { 'spam': [
                        'foo:v1234dDEADBEEFx*',
                        'pci:v0000FFF0d*1sv*sd*bc06sc*i*']
                    }
                }

            result = jockey.detection.get_handlers(jockey.backend.Backend(),
                jockey.detection.LocalKernelModulesDriverDB())
        finally:
            OSLib.inst.package_header_modaliases = orig_phm

        for h in result:
            if h.module == 'spam':
                self.assertEqual(h.package, 'pretzel')
                break
        else:
            self.fail('no handler for spam module created')

    def test_localkernelmod_driverdb_packages(self):
        '''LocalKernelModulesDriverDB properly handles package field'''

        # test handler which is unavailable for mesa-vanilla
        open (os.path.join(OSLib.inst.handler_dir, 'testhandlers.py'), 'w').write('''
import jockey.handlers

class PickyHandler(jockey.handlers.KernelModuleHandler):
    def __init__(self, backend):
        jockey.handlers.KernelModuleHandler.__init__(self, backend, 'chocolate')

    def available(self):
        if self.package == 'mesa-vanilla':
            return False
        return jockey.handlers.KernelModuleHandler.available(self)
''')

        try:
            f = open(os.path.join(OSLib.inst.modaliases[1], 'pretzel.alias'), 'w')
            f.write('alias pci:v0000FFF0d*1sv*sd*bc06sc*i* spam pretzel\n')
            f.close()

            f = open(os.path.join(OSLib.inst.modaliases[1], 'picky.alias'), 'w')
            f.write('alias pci:v0000FFF0d*1sv*sd*bc06sc*i* chocolate mesa-vanilla\n')
            f.close()

            result = jockey.detection.get_handlers(jockey.backend.Backend(),
                jockey.detection.LocalKernelModulesDriverDB())

            h_pretzel = None
            for h in result:
                if h.module == 'spam':
                    h_pretzel = h
                    break
                if h.module == 'chocolate':
                    self.fail('PickyHandler was instantiated, although it is unavailable for mesa-vanilla')
            self.assert_(h_pretzel, 'delivered spam kmod handler')

            self.failIf(h_pretzel.free()) # pretzel packge is nonfree
            self.assertEqual(h_pretzel.package, 'pretzel')
            self.failIf(h_pretzel.enabled()) # pretzel packge is not installed
        finally:
            for f in os.listdir(OSLib.inst.modaliases[1]):
                os.unlink(os.path.join(OSLib.inst.modaliases[1], f))

    def test_localkernelmod_driverdb_alternative_handler(self):
        '''LocalKernelModulesDriverDB offers alternative handlers for the same module'''

        # test handler which is unavailable for mesa-vanilla
        open (os.path.join(OSLib.inst.handler_dir, 'testhandlers.py'), 'w').write('''
import jockey.handlers

class VanillaHandler(jockey.handlers.KernelModuleHandler):
    def __init__(self, backend, package=None):
        jockey.handlers.KernelModuleHandler.__init__(self, backend, 'chocolate')
        self.package = package or 'mesa-vanilla'

    def id(self):
        return 'kmod:%s:%s' % (self.module, self.package)

class VanillaUpdatesHandler(VanillaHandler):
    def __init__(self, backend):
        VanillaHandler.__init__(self, backend, 'mesa-vanilla-updates')
''')

        try:
            f = open(os.path.join(OSLib.inst.modaliases[1], 'vanilla.alias'), 'w')
            f.write('''alias pci:v0000FFF0d*1sv*sd*bc06sc*i* chocolate mesa-vanilla
alias pci:v0000FFF0d*1sv*sd*bc06sc*i* chocolate mesa-vanilla-updates
''')
            f.close()

            result = jockey.detection.get_handlers(jockey.backend.Backend(),
                jockey.detection.LocalKernelModulesDriverDB())

            out = '\n'.join(sorted([str(h) for h in result if h.module == 'chocolate']))

            self.assertEqual(out, '''kmod:chocolate:mesa-vanilla([VanillaHandler, nonfree, disabled] free module with nonavailable hardware)
kmod:chocolate:mesa-vanilla-updates([VanillaUpdatesHandler, nonfree, disabled] free module with nonavailable hardware)''')

        finally:
            for f in os.listdir(OSLib.inst.modaliases[1]):
                os.unlink(os.path.join(OSLib.inst.modaliases[1], f))

    def test_localkernelmod_driverdb_alternative_handler_xorg(self):
        '''LocalKernelModulesDriverDB offers alternative X.org handlers for the same module'''

        # test handler which is unavailable for mesa-vanilla
        open (os.path.join(OSLib.inst.handler_dir, 'testhandlers.py'), 'w').write('''
import jockey.handlers

class VanillaHandler(jockey.xorg_driver.XorgDriverHandler):
    def __init__(self, backend, package=None):
        if not package:
            package = 'mesa-vanilla'
        if package and 'update' in package:
            name = 'Vanilla 3D driver (post-release updates)'
        else:
            name = 'Vanilla 3D driver'
        jockey.xorg_driver.XorgDriverHandler.__init__(self, backend,
          'chocolate', package, 'vanilla3d', 'vanilla', 
          name=name)

class VanillaUpdatesHandler(VanillaHandler):
    def __init__(self, backend):
        VanillaHandler.__init__(self, backend, 'mesa-vanilla-updates')

    def id(self):
        return VanillaHandler.id(self) + '-updates'

''')

        try:
            f = open(os.path.join(OSLib.inst.modaliases[1], 'vanilla.alias'), 'w')
            f.write('''alias pci:v0000FFF0d*1sv*sd*bc06sc*i* chocolate mesa-vanilla
alias pci:v0000FFF0d*1sv*sd*bc06sc*i* chocolate mesa-vanilla-updates
''')
            f.close()

            result = jockey.detection.get_handlers(jockey.backend.Backend(),
                jockey.detection.LocalKernelModulesDriverDB())

            out = '\n'.join(sorted([str(h) for h in result if h.module == 'chocolate']))

            self.assertEqual(out, '''xorg:chocolate([VanillaHandler, nonfree, disabled] Vanilla 3D driver)
xorg:chocolate-updates([VanillaUpdatesHandler, nonfree, disabled] Vanilla 3D driver (post-release updates))''')

        finally:
            for f in os.listdir(OSLib.inst.modaliases[1]):
                os.unlink(os.path.join(OSLib.inst.modaliases[1], f))

    def test_xmlrpc_driverdb_no_systemid(self):
        '''XMLRPCDriverDB with a working (local) server and no system ID'''

        backend = jockey.backend.Backend()
        # should *not* contact server, do that before starting server
        OSLib.inst.set_dmi('', '')
        db = jockey.detection.XMLRPCDriverDB('http://localhost:8080')

        # until we update, there is no data
        self.assertEqual(jockey.detection.get_handlers(backend,
            db, hardware=backend.hardware), set())

        sandbox.start_driverdb_server()
        try:
            db.update(backend.hardware)
        finally:
            sandbox.stop_driverdb_server()

        # this should now give the same result as TestDriverDB, except for the
        # custom handlers (which we did not define here, they should be ignored)
        result = jockey.detection.get_handlers(backend, db,
            hardware=backend.hardware)
        out = '\n'.join(sorted([str(h) for h in result]))
        self.assertEqual(out, # note custom description for spam
'''firmware:firmwifi([FirmwareHandler, nonfree, disabled] standard module which needs firmware)
kmod:mint([KernelModuleHandler, nonfree, enabled] nonfree module with available hardware, wifi)
kmod:spam([KernelModuleHandler, free, enabled] free mystical module without modaliases)''')

        # previous DB should have written a cache
        cache_path = db.cache_path
        self.assert_(os.path.exists(db.cache_path))
        db = jockey.detection.XMLRPCDriverDB('http://localhost:8080')
        result = jockey.detection.get_handlers(backend, db,
            hardware=backend.hardware)
        out = '\n'.join(sorted([str(h) for h in result]))
        self.assertEqual(out, 
'''firmware:firmwifi([FirmwareHandler, nonfree, disabled] standard module which needs firmware)
kmod:mint([KernelModuleHandler, nonfree, enabled] nonfree module with available hardware, wifi)
kmod:spam([KernelModuleHandler, free, enabled] free mystical module without modaliases)''')

        # the cache should *not* apply to a different URL; also, invalid URLs
        # should not cause a crash
        db = jockey.detection.XMLRPCDriverDB('http://localhost:12345')
        self.assertEqual(jockey.detection.get_handlers(backend, db,
            hardware=backend.hardware), set())

        # should not fall over on damaged cache files
        open(cache_path, 'wb').write('bogus')
        db = jockey.detection.XMLRPCDriverDB('http://localhost:8080')
        self.assertEqual(jockey.detection.get_handlers(backend, db,
            hardware=backend.hardware), set())

    def test_xmlrpc_driverdb_systemid(self):
        '''XMLRPCDriverDB with a working (local) server and VaporTech system ID'''

        open (os.path.join(OSLib.inst.handler_dir, 'ndmod.py'), 'w').write(
            'import jockey.handlers\n' + sandbox.h_nodetectmod)

        backend = jockey.backend.Backend()
        # should *not* contact server, do that before starting server
        db = jockey.detection.XMLRPCDriverDB('http://localhost:8080')

        # until we update, there is no data
        self.assertEqual(jockey.detection.get_handlers(backend,
            db, hardware=backend.hardware), set())

        sandbox.start_driverdb_server()
        try:
            db.update(backend.hardware)
        finally:
            sandbox.stop_driverdb_server()

        orig_getlocale = locale.getlocale
        try:
            locale.getlocale = lambda c: ('en_US', 'UTF-8')
            result = jockey.detection.get_handlers(backend, db,
                hardware=backend.hardware)
        finally:
            locale.getlocale = orig_getlocale
        out = '\n'.join(sorted([str(h) for h in result]))
        self.assertEqual(out, 
'''firmware:firmwifi([FirmwareHandler, nonfree, disabled] standard module which needs firmware)
kmod:apple:Apple([KernelModuleHandler, nonfree, disabled] Unknown local kmod)
kmod:chocolate:VaporTech([KernelModuleHandler, free, disabled] VaporTech choc handler)
kmod:mint:UbuOne([KernelModuleHandler, nonfree, enabled] UbuOne mintmod)
kmod:mint:UbunTwo([KernelModuleHandler, nonfree, enabled] UbunTwo mintmod)
kmod:spam:Black_Hat([NoDetectMod, free, enabled] BlackHat ndmod)
kmod:spam:White_Hat([NoDetectMod, free, enabled] WhiteHat ndmod)''')

        for h in result:
            if h.module == 'firmwifi':
                self.assertEqual(h.description(), None)
                self.assertEqual(h.version, None)
                self.assertEqual(h.repository, None)
                self.assertEqual(h.package, None)
                self.assertEqual(h.driver_vendor, None)
            if h.module == 'chocolate':
                choc_h = h
            if h.module == 'apple':
                self.assertEqual(h.license, 'Kills kittens')
            else:
                self.assertEqual(h.license, None)
            self.assertEqual(h.recommended(), h.id() == 'kmod:mint:UbunTwo')

        self.assertEqual(choc_h.description(), 'Multi\nline')
        self.assertEqual(choc_h.version, '1.1-foo42-vt3')
        self.assertEqual(choc_h.repository, 'http://vaportech.com/x1')
        self.assertEqual(choc_h.package, 'spam-x1')
        self.assertEqual(choc_h.driver_vendor, 'VaporTech')

        self.assertEqual(choc_h.enabled(), False)
        choc_h.enable()
        self.assertEqual(choc_h.enabled(), True)
        self.assertEqual(OSLib.inst.package_installed(choc_h.package), True)

    def test_xmlrpc_driverdb_i18n(self):
        '''XMLRPCDriverDB return localized strings'''

        backend = jockey.backend.Backend()
        db = jockey.detection.XMLRPCDriverDB('http://localhost:8080')
        sandbox.start_driverdb_server()
        try:
            db.update(backend.hardware)
        finally:
            sandbox.stop_driverdb_server()

        orig_getlocale = locale.getlocale
        try:
            locale.getlocale = lambda c: ('de_DE', 'UTF-8')
            result = jockey.detection.get_handlers(backend, db,
                hardware=backend.hardware)
            self.assertEqual([str(h) for h in result if h.module == 'chocolate'][0],
                'kmod:chocolate:VaporTech([KernelModuleHandler, free, disabled] German description)')

            locale.getlocale = lambda c: ('de_DE', 'ISO8859-1')
            result = jockey.detection.get_handlers(backend, db,
                hardware=backend.hardware)
            self.assertEqual([str(h) for h in result if h.module == 'chocolate'][0],
                'kmod:chocolate:VaporTech([KernelModuleHandler, free, disabled] German description)')

            # DB only has de_DE, thus this should be C
            locale.getlocale = lambda c: ('de', 'UTF-8')
            result = jockey.detection.get_handlers(backend, db,
                hardware=backend.hardware)
            self.assertEqual([str(h) for h in result if h.module == 'chocolate'][0],
                'kmod:chocolate:VaporTech([KernelModuleHandler, free, disabled] VaporTech choc handler)')

            locale.getlocale = lambda c: ('cs', 'UTF-8')
            result = jockey.detection.get_handlers(backend, db,
                hardware=backend.hardware)
            self.assertEqual([str(h) for h in result if h.module == 'chocolate'][0],
                'kmod:chocolate:VaporTech([KernelModuleHandler, free, disabled] Czech description)')

            # DB has cs, cs_CZ should fallback to cs
            locale.getlocale = lambda c: ('cs_CZ', 'UTF-8')
            result = jockey.detection.get_handlers(backend, db,
                hardware=backend.hardware)
            self.assertEqual([str(h) for h in result if h.module == 'chocolate'][0],
                'kmod:chocolate:VaporTech([KernelModuleHandler, free, disabled] Czech description)')
        finally:
            locale.getlocale = orig_getlocale

    def test_get_handlers_license_filter(self):
        '''get_handlers() returns applicable handlers with license filtering'''

        open (os.path.join(OSLib.inst.handler_dir, 'testhandlers.py'), 'w').write('''
import jockey.handlers

%s

class VanillaGfxHandler(jockey.handlers.KernelModuleHandler):
    def __init__(self, backend):
        jockey.handlers.KernelModuleHandler.__init__(self, backend, 'vanilla3d')
''' % sandbox.h_avail_mod)

        backend = jockey.backend.Backend()
        db = sandbox.TestDriverDB()
        db.update(backend.hardware)
        result = jockey.detection.get_handlers(backend,
            db, mode=jockey.detection.MODE_FREE)

        out = '\n'.join(sorted([str(h) for h in result]))
        self.assertEqual(out, 
'''kmod:spam([KernelModuleHandler, free, enabled] free mystical module without modaliases)
kmod:vanilla([AvailMod, free, enabled] free module with available hardware, graphics card)''')

        result = jockey.detection.get_handlers(backend,
            db, mode=jockey.detection.MODE_NONFREE)

        out = '\n'.join(sorted([str(h) for h in result]))
        self.assertEqual(out, 
'''firmware:firmwifi([FirmwareHandler, nonfree, disabled] standard module which needs firmware)
kmod:mint([KernelModuleHandler, nonfree, enabled] nonfree module with available hardware, wifi)
kmod:vanilla3d([VanillaGfxHandler, nonfree, enabled] nonfree, replacement graphics driver for vanilla)''')

    def test_xmlrpc_driverdb_errors(self):
        '''XMLRPCDriverDB with a working (local) server, error conditions'''

        # cache writing error
        backend = jockey.backend.Backend()
        db = jockey.detection.XMLRPCDriverDB('http://localhost:8080')
        db.cache_path = '/proc/null'
        sandbox.start_driverdb_server()
        try:
            db.update(backend.hardware)
        finally:
            sandbox.stop_driverdb_server()
        # survives
        self.assertNotEqual(db.cache, {})

        # return protocol mismatch
        db = jockey.detection.XMLRPCDriverDB('http://localhost:8080')
        sandbox.start_driverdb_server(correct_protocol=False)
        try:
            db.update(backend.hardware)
        finally:
            sandbox.stop_driverdb_server()
        # survives
        self.assertEqual(db.cache, {})

    def test_get_handlers_driverdb_nonexisting_module(self):
        '''get_handlers() ignores nonexisting kernel modules'''

        class MyDDB(jockey.detection.DriverDB):
            '''Always return the same nonexisting kernel module as handler.'''

            def query(self, hwid):
                return [jockey.detection.DriverID(jockey_handler='KernelModuleHandler',
                    kernel_module='superdriver')]

        result = jockey.detection.get_handlers(jockey.backend.Backend(), MyDDB())
        self.assertEqual(result, set())

    def test_get_handlers_all(self):
        '''get_handlers() with available_only=False'''

        open (os.path.join(OSLib.inst.handler_dir, 'kmod_nodetect.py'), 'w').write(
            sandbox.h_availability_py)

        h = jockey.detection.get_handlers(jockey.backend.Backend(),
            available_only=False)

        self.assertEqual(len(h), 3)

    @unittest.skipUnless(OSLib.has_defaultroute(), 'online test')
    def test_openprinting_unknownprinter(self):
        '''OpenPrintingDriverDB with an unknown printer'''

        backend = jockey.backend.Backend()
        backend.hardware = set([HardwareID('printer_deviceid',
            'MFG:FooTech;MDL:X-12;CMD:GDI')])
        backend.driver_dbs.append(jockey.detection.OpenPrintingDriverDB())
        backend.update_driverdb()
        self.assertEqual(backend.available(), [])

    @unittest.skipUnless(OSLib.has_defaultroute(), 'online test')
    def test_openprinting_apt_ppd(self):
        '''OpenPrintingDriverDB, known printer, apt package system, PPD only
        
        Note that this test case does assumptions about the data returned by
        openprinting.org, thus it needs to be adapted over time.
        '''
        prn = HardwareID('printer_deviceid', 'MFG:Hewlett-Packard;MDL:HP DesignJet 3500CP')
        db = jockey.detection.OpenPrintingDriverDB()
        orig_pkgsys = OSLib.inst.packaging_system
        try:
            OSLib.inst.packaging_system = lambda: 'apt'
            db.update(set([prn]))
        finally:
            OSLib.inst.packaging_system = orig_pkgsys

        drv = db.query(prn)
        
        self.assertEqual(len(drv), 1)
        drv = drv[0].properties

        self.assertEqual(drv['driver_type'], 'printer_driver')
        self.assert_('HP' in drv['description']['C'])
        self.assert_('lineart' in drv['long_description']['C'])
        self.assertEqual(drv['package'], 'openprinting-ppds-postscript-hp')
        self.assertEqual(drv['driver_vendor'], 'HP')
        self.assertEqual(drv['free'], True)
        self.assert_(drv['repository'].startswith('deb '))
        self.assert_('license' in drv)

    @unittest.skipUnless(OSLib.has_defaultroute(), 'online test')
    def test_openprinting_apt_binary(self):
        '''OpenPrintingDriverDB, known printer, apt package system, binary

        Note that this test case does assumptions about the data returned by
        openprinting.org, thus it needs to be adapted over time.

        This includes fetching the GPG fingerprint URL and verifying the SSL
        certificate validity and trust.
        '''
        prn = HardwareID('printer_deviceid', 'MFG:EPSON;MDL:Epson ME 320')
        db = jockey.detection.OpenPrintingDriverDB()
        orig_pkgsys = OSLib.inst.packaging_system
        try:
            OSLib.inst.packaging_system = lambda: 'apt'
            db.update(set([prn]))
        finally:
            OSLib.inst.packaging_system = orig_pkgsys

        drv = db.query(prn)
        
        self.assertEqual(len(drv), 1)
        drv = drv[0].properties

        self.assertEqual(drv['driver_type'], 'printer_driver')
        self.assert_('Epson' in drv['description']['C'])
        self.assert_('lineart' in drv['long_description']['C'])
        self.assert_(drv['package'].startswith('epson-inkjet-'))
        self.assert_('Epson' in drv['driver_vendor'])
        self.assert_(drv['repository'].startswith('deb '))
        self.assertEqual(drv['fingerprint'], 'E522 0FB7 014D 0FBD A50D  FC2B E5E8 6C00 8AA6 5D56') 
        self.assert_('license' in drv)

    @unittest.skipUnless(OSLib.has_defaultroute(), 'online test')
    def test_openprinting_handler_ppd(self):
        '''OpenPrintingDriverDB: PrinterDriverHandler for PPD package'''

        backend = jockey.backend.Backend()
        backend.hardware = set([HardwareID('printer_deviceid',
            'MFG:Hewlett-Packard;MDL:HP DesignJet 3500CP')])
        backend.driver_dbs.append(jockey.detection.OpenPrintingDriverDB())
        orig_pkgsys = OSLib.inst.packaging_system
        try:
            OSLib.inst.packaging_system = lambda: 'apt'
            backend.update_driverdb()
        finally:
            OSLib.inst.packaging_system = orig_pkgsys
        handlers = backend.available()
        self.assertEqual(handlers, ['printer:openprinting-ppds-postscript-hp:20091009'])

        hi = backend.handler_info(handlers[0])
        self.assertEqual(hi['package'], 'openprinting-ppds-postscript-hp')
        self.assertEqual(hi['free'], 'True')
        self.assert_('repository' in hi)
        self.assert_('driver_vendor' in hi)

    @unittest.skipUnless(OSLib.has_defaultroute(), 'online test')
    def test_openprinting_handler_binary(self):
        '''OpenPrintingDriverDB: PrinterDriverHandler for binary package'''

        backend = jockey.backend.Backend()
        backend.hardware = set([HardwareID('printer_deviceid',
            'MFG:EPSON;MDL:Epson ME 320')])
        backend.driver_dbs.append(jockey.detection.OpenPrintingDriverDB())
        orig_pkgsys = OSLib.inst.packaging_system
        try:
            OSLib.inst.packaging_system = lambda: 'apt'
            backend.update_driverdb()
        finally:
            OSLib.inst.packaging_system = orig_pkgsys
        handlers = backend.available()
        self.assertEqual(len(handlers), 1)
        self.assertTrue(handlers[0].startswith('printer:epson-inkjet-printer-n10-nx127:1'))

        hi = backend.handler_info(handlers[0])
        self.assert_(hi['package'].startswith('epson-inkjet-'))
        self.assert_(hi['repository'].startswith('deb '))
        self.assert_('repository_sign_fp' in hi)
        self.assert_('driver_vendor' in hi)

    @unittest.skipUnless(OSLib.has_defaultroute(), 'online test')
    def test_openprinting_yum(self):
        '''OpenPrintingDriverDB, known printer, yum package system
        
        Note that this test case does assumptions about the data returned by
        openprinting.org, thus it needs to be adapted over time.
        '''
        prn = HardwareID('printer_deviceid', 'MFG:Hewlett-Packard;MDL:HP DesignJet 3500CP')
        db = jockey.detection.OpenPrintingDriverDB()

        orig_pkgsys = OSLib.inst.packaging_system
        try:
            OSLib.inst.packaging_system = lambda: 'yum'
            db.update(set([prn]))
        finally:
            OSLib.inst.packaging_system = orig_pkgsys

        drv = db.query(prn)
        
        self.assertEqual(len(drv), 1)
        drv = drv[0].properties

        self.assertEqual(drv['driver_type'], 'printer_driver')
        self.assert_('HP' in drv['description']['C'])
        self.assert_('lineart' in drv['long_description']['C'])
        self.assertEqual(drv['package'], 'openprinting-ppds-postscript-hp')
        self.assertEqual(drv['driver_vendor'], 'HP')
        self.assertEqual(drv['free'], True)
        self.assert_('rpms' in drv['repository'].lower())
        self.assert_('license' in drv)

    @unittest.skipUnless(OSLib.has_defaultroute(), 'online test')
    def test_openprinting_unknownpkg(self):
        '''OpenPrintingDriverDB, known printer, unknown package system'''

        prn = HardwareID('printer_deviceid', 'MFG:Hewlett-Packard;MDL:HP DesignJet 3500CP')
        db = jockey.detection.OpenPrintingDriverDB()
        orig_pkgsys = OSLib.inst.packaging_system
        try:
            OSLib.inst.packaging_system = lambda: 'foo'
            db.update(set([prn]))
        finally:
            OSLib.inst.packaging_system = orig_pkgsys

        drv = db.query(prn)
        self.assertEqual(len(drv), 0)

class GPGFingerPrintTest(sandbox.LogTestCase):
    def setUp(self):
        self.data_dir = os.path.join(os.path.dirname(__file__), 'data')
        self.localhost_pem = os.path.join(self.data_dir, 'localhost.pem')
        self.localhost_expired_pem = os.path.join(self.data_dir, 'localhost-expired.pem')
        self.orig_cert_file_paths = OSLib.inst.ssl_cert_file_paths
        OSLib.inst.ssl_cert_file_paths = [self.localhost_pem]

    def tearDown(self):
        httpd.stop()
        OSLib.inst.ssl_cert_file_paths = self.orig_cert_file_paths

    def test_valid(self):
        '''GPG fingerprint: valid certificate, hostname, and fingerprint'''

        httpd.start(4443, self.data_dir, True, self.localhost_pem)

        result = jockey.detection.download_gpg_fingerprint(
                'https://localhost:4443/fingerprint')
        self.assertEqual(result, '0000 1111 2222 3333 4444  5555 6666 7777 8888 9999')

    def test_bad_fingerprint_syntax(self):
        '''GPG fingerprint: no fingerprint found'''

        httpd.start(4443, self.data_dir, True, self.localhost_pem)

        result = jockey.detection.download_gpg_fingerprint(
                'https://localhost:4443/bad_fingerprint')
        self.assertEqual(result, None, result)

    def test_404(self):
        '''GPG fingerprint: nonexisting address'''

        httpd.start(4443, self.data_dir, True, self.localhost_pem)

        result = jockey.detection.download_gpg_fingerprint(
                'https://localhost:4443/nonexisting')
        self.assertEqual(result, None, result)

    def test_wrong_host(self):
        '''GPG fingerprint: unknown hostname'''

        httpd.start(4443, self.data_dir, True, self.localhost_pem)

        result = jockey.detection.download_gpg_fingerprint(
                'https://127.0.0.1:4443/fingerprint')
        self.assertEqual(result, None, result)

    def test_expired_cert(self):
        '''expired certificate'''

        httpd.start(4443, self.data_dir, True, self.localhost_expired_pem)

        result = jockey.detection.download_gpg_fingerprint(
                'https://127.0.0.1:4443/fingerprint')
        self.assertEqual(result, None, result)

    def test_wrong_cert(self):
        '''wrong certificate'''

        OSLib.inst.ssl_cert_file_paths = [self.localhost_expired_pem]
        httpd.start(4443, '.', True, self.localhost_pem)
        result = jockey.detection.download_gpg_fingerprint(
                'https://127.0.0.1:4443/fingerprint')
        self.assertEqual(result, None, result)

    def test_system_cert(self):
        '''system-wide trusted certificate shouldn't match local test server'''

        if not self.orig_cert_file_paths:
            print('[SKIP, not available]')
            return

        OSLib.inst.ssl_cert_file_paths = self.orig_cert_file_paths
        httpd.start(4443, '.', True, self.localhost_pem)

        result = jockey.detection.download_gpg_fingerprint(
                'https://127.0.0.1:4443/fingerprint')
        self.assertEqual(result, None, result)

if __name__ == '__main__':
    OSLib.inst = sandbox.TestOSLib()
    unittest.main()
