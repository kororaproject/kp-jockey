# -*- coding: UTF-8 -*-

'''D-BUS backend service tests'''

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

import unittest, os, signal, time, sys, shutil, traceback

import dbus

from jockey.oslib import OSLib

import jockey.backend, jockey.handlers, jockey.xorg_driver
import sandbox

server_pid = None

class DbusBackendTest(sandbox.LogTestCase):
    '''D-BUS backend service tests.'''

    def setUp(self):
        global server_pid

        # start server
        if not server_pid:
            signal.signal(signal.SIGUSR1, lambda s, f: True)
            server_pid = os.fork()
            if server_pid == 0:
                try:
                    os.setsid()
                    backend = jockey.backend.Backend.create_dbus_server(session_bus=True)
                    backend.detect()

                    # disabling firmwifi will cause a ZeroDivisionError (for
                    # testing exception propagation)
                    backend.handlers['kmod:firmwifi'].disable = lambda: 1/0

                    backend.run_dbus_service(2, True)
                except:
                    print '********** Backend D-BUS server failed: ***********'
                    traceback.print_exc()
                    os.kill(os.getppid(), signal.SIGTERM)
                    os._exit(1) 
                os._exit(42) # code for "timed out"

            # wait until server is ready
            signal.pause()

        # get the client-side interface
        self.i_drv = jockey.backend.Backend.create_dbus_client(session_bus=True)

    def test_zz_timeout(self):
        '''D-BUS server timeout
        
        This must be the last D-BUS test, since this kills the server.'''

        global server_pid
        self.assertEqual(os.waitpid(server_pid, os.WNOHANG), (0, 0))
        # TODO: should be 2.1, somehow it spills over to the second main iteration
        time.sleep(4.1)
        (p, e) = os.waitpid(server_pid, os.WNOHANG)
        self.assertEqual(p, server_pid)
        self.assertEqual(os.WEXITSTATUS(e), 42)

    def test_available(self):
        '''D-BUS Backend.available()'''

        result = self.i_drv.available('any')
        self.assertEqual(set(result), set(['kmod:foodmi',
            'kmod:mint', 'kmod:vanilla', 'kmod:firmwifi', 'kmod:vanilla3d']))

        result = self.i_drv.available('free')
        self.assertEqual(set(result), set(['kmod:foodmi',
            'kmod:vanilla', 'kmod:firmwifi']))

        result = self.i_drv.available('nonfree')
        self.assertEqual(set(result), set(['kmod:mint', 'kmod:vanilla3d']))

    def test_get_hardware(self):
        '''D-BUS Backend.get_hardware()'''

        # filter out printers, since we cannot predict them
        hw = [h for h in self.i_drv.get_hardware() if not h.startswith('printer_deviceid:')]
        self.assertEqual(set(hw), set([
            'modalias:pci:v00001001d00003D01sv00001234sd00000001bc03sc00i00',
            'modalias:pci:v0000AAAAd000012AAsv00000000sdDEADBEEFbc02sc80i00',
            'modalias:fire:1.2',
            'modalias:pci:v0000FFF0d00000001sv00000000sd00000000bc06sc01i01',
            'modalias:pci:v0000DEAFd00009999sv00000000sd00000000bc99sc00i00',
            'modalias:ssb:v4243id0812rev05',
            'modalias:dmi:foo[A-1]bar',
        ]))

    def test_handler_info(self):
        '''D-BUS Backend.handler_info()'''

        # NoSuchHandlerException
        self.assertRaises(dbus.DBusException, self.i_drv.handler_info,
            'kmod:foo')

        self.assertEqual(self.i_drv.handler_info('kmod:mint'),
            {
                'id': 'kmod:mint',
                'name': sandbox.fake_modinfo['mint']['description'],
                'free': 'False',
                'enabled': 'True',
                'used': 'False',
                'changed': 'False',
                'recommended': 'False',
                'announce': 'True',
                'auto_install': 'False',
            })

    def test_set_enabled(self):
        '''D-BUS Backend.set_enabled()'''

        # NoSuchHandlerException
        self.assertRaises(dbus.DBusException, self.i_drv.set_enabled,
            'kmod:foo', False)

        i = self.i_drv.handler_info('kmod:vanilla')
        self.assertEqual(i['enabled'], 'True')
        self.assertEqual(i['changed'], 'False')

        self.assertEqual(self.i_drv.set_enabled('kmod:vanilla', True), True)
        i = self.i_drv.handler_info('kmod:vanilla')
        self.assertEqual(i['enabled'], 'True')

        self.assertEqual(self.i_drv.set_enabled('kmod:vanilla', False), False)
        i = self.i_drv.handler_info('kmod:vanilla')
        self.assertEqual(i['enabled'], 'False')
        self.assertEqual(i['changed'], 'True')

        self.assertEqual(self.i_drv.set_enabled('kmod:vanilla', True), True)
        i = self.i_drv.handler_info('kmod:vanilla')
        self.assertEqual(i['enabled'], 'True')
        self.assertEqual(i['changed'], 'True')

        # proper exception propagation
        self.assertEqual(self.i_drv.handler_info('kmod:firmwifi')['enabled'], 'True')
        try:
            self.i_drv.set_enabled('kmod:firmwifi', False)
        except dbus.DBusException as e:
            self.assertEqual(e._dbus_error_name,
                'org.freedesktop.DBus.Python.ZeroDivisionError', 'not a ZeroDivisionError:' + str(e))
            return
        self.fail('set_enabled() did not propagate ZeroDivisionError')

    def test_new_used_available(self):
        '''D-BUS Backend.new_used_available()'''

        self.assertEqual(self.i_drv.new_used_available('any'), 
            (['kmod:vanilla'], []))
        self.assertEqual(self.i_drv.new_used_available('any'), 
            ([], []))

        # should be reset after deleting cache
        os.unlink(OSLib.inst.check_cache)
        self.assertEqual(self.i_drv.new_used_available('any'), 
            (['kmod:vanilla'], []))

        # no nonfree drivers
        os.unlink(OSLib.inst.check_cache)
        self.assertEqual(self.i_drv.new_used_available('nonfree'), 
            ([], []))

        # vanilla is free
        os.unlink(OSLib.inst.check_cache)
        self.assertEqual(self.i_drv.new_used_available('free'), 
            (['kmod:vanilla'], []))

        self.assertRaises(dbus.DBusException, self.i_drv.new_used_available,
            'bogus') 

    def test_check_composite(self):
        '''D-BUS Backend.check_composite()'''

        # we can only check general calling/signature compatibility here
        self.assertEqual(self.i_drv.check_composite(), '')

    def test_zz_add_driverdb(self):
        '''D-BUS Backend.add_driverdb()'''

        self.assertRaises(dbus.DBusException, self.i_drv.add_driverdb,
            'UnknownClass', [])
        self.assertRaises(dbus.DBusException, self.i_drv.add_driverdb,
            'XMLRPCDriverDB', [])

        try:
            sandbox.start_driverdb_server()
            self.i_drv.add_driverdb('XMLRPCDriverDB', ['http://localhost:8080'])
            self.i_drv.update_driverdb()
            drvs = set(self.i_drv.available('nonfree'))
        finally:
            sandbox.stop_driverdb_server()

        self.assertEqual(drvs, set(['kmod:mint', 'kmod:mint:UbuOne',
            'kmod:mint:UbunTwo', 'kmod:vanilla3d', 'firmware:firmwifi',
            'kmod:apple:Apple']))

        hi = self.i_drv.handler_info('kmod:apple:Apple')
        self.assertEqual(hi['driver_vendor'], 'Apple')
        self.assertEqual(hi['package'], 'pretzel')
        self.assertEqual(hi['free'], 'False')
        self.assertEqual(hi['license'], 'Kills kittens')

    def test_update_driverdb(self):
        '''D-BUS Backend.update_driverdb()'''

        # poke in a new modalias list
        alias_file = os.path.join(OSLib.inst.modaliases[1], 'spam.alias')
        f = open(alias_file, 'w')
        try:
            f.write('alias pci:v*d*sv*sd*bc03sc*i* spam\n')
            f.close()

            self.i_drv.update_driverdb()
            result = self.i_drv.available('any')
            self.assertEqual(set(result), set(['kmod:foodmi', 'kmod:mint',
                'kmod:vanilla', 'kmod:firmwifi', 'kmod:vanilla3d', 'kmod:spam']))
        finally:
            os.unlink(alias_file)

    def test_search_driver(self):
        '''D-BUS Backend.search_driver()'''

        self.assertEqual(self.i_drv.search_driver('modalias:foo'), [])
        self.assertEqual(self.i_drv.search_driver('modalias:dmi:foo[A-1]bar'), 
            ['kmod:foodmi'])

class LocalBackendTest(sandbox.LogTestCase):
    '''Backend service tests.
    
    In those we need more control over the backend, so that we cannot do them
    over the D-BUS interface.'''

    def tearDown(self):
        # remove all test handlers
        for f in os.listdir(OSLib.inst.handler_dir):
            os.unlink(os.path.join(OSLib.inst.handler_dir, f))

        # undo the effect of enabling/disabling handlers
        OSLib.inst._make_proc_modules()
        jockey.handlers.KernelModuleHandler.read_loaded_modules()
        try:
            os.unlink(OSLib.inst.module_blacklist_file)
        except OSError:
            pass
        try:
            os.unlink(os.path.join(OSLib.inst.backup_dir,
                'installed_packages'))
        except OSError:
            pass
        try:
            os.unlink(OSLib.inst.check_cache)
        except OSError:
            pass
        OSLib.inst._load_module_blacklist()
        OSLib.inst.reset_packages()

    def test_install_packages(self):
        '''Backend.{install,remove}_package() and installed_packages logging'''

        pkglog = os.path.join(OSLib.inst.backup_dir, 'installed_packages')
        b = jockey.backend.Backend()
        self.failIf(os.path.exists(pkglog))

        # coreutils package is already installed
        self.assert_(OSLib.inst.package_installed('coreutils'))
        b.install_package('coreutils')
        self.failIf(os.path.exists(pkglog))

        # install mesa-vanilla
        self.failIf(OSLib.inst.package_installed('mesa-vanilla'))
        b.install_package('mesa-vanilla')
        self.assert_(OSLib.inst.package_installed('mesa-vanilla'))
        self.assertEqual(open(pkglog).read(), 'mesa-vanilla\n')

        # install pretzel
        self.failIf(OSLib.inst.package_installed('pretzel'))
        b.install_package('pretzel')
        self.assert_(OSLib.inst.package_installed('pretzel'))
        inst = sorted(open(pkglog).readlines())
        self.assertEqual(inst, ['mesa-vanilla\n', 'pretzel\n'])

        # remove mesa-vanilla
        b.remove_package('mesa-vanilla')
        self.failIf(OSLib.inst.package_installed('mesa-vanilla'))
        self.assertEqual(open(pkglog).read(), 'pretzel\n')

        # remove pretzel
        b.remove_package('pretzel')
        self.failIf(OSLib.inst.package_installed('pretzel'))
        self.failIf(os.path.exists(pkglog))

        # remove uninstalled package
        b.remove_package('pretzel')
        self.failIf(OSLib.inst.package_installed('pretzel'))
        self.failIf(os.path.exists(pkglog))

    def test_handler_info(self):
        '''Backend.handler_info()'''

        b = jockey.backend.Backend()
        b.handlers['kmod:mint'].package = 'mesa-vanilla'

        # NoSuchHandlerException
        self.assertRaises(jockey.backend.UnknownHandlerException,
            b.handler_info, 'kmod:foo')

        self.assertEqual(b.handler_info('kmod:mint'),
            {
                'id': 'kmod:mint',
                'name': sandbox.fake_modinfo['mint']['description'],
                'description': sandbox.fake_pkginfo['default']['mesa-vanilla']['description'][1],
                'free': 'False',
                'enabled': 'False', # package not installed
                'used': 'False',
                'changed': 'False',
                'package': 'mesa-vanilla',
                'recommended': 'False',
                'announce': 'True',
                'auto_install': 'False',
            })

    def test_handler_files(self):
        '''Backend.handler_files()'''

        b = jockey.backend.Backend()

        # NoSuchHandlerException
        self.assertRaises(jockey.backend.UnknownHandlerException,
            b.handler_files, 'kmod:foo')

        # no package
        self.assertEqual(b.handler_files('kmod:mint'), [])

        # package, not installed
        b.handlers['kmod:mint'].package = 'mesa-vanilla'
        self.failIf(b.handlers['kmod:mint'].enabled())
        self.assertEqual(b.handler_files('kmod:mint'), [])

        # package, installed
        b.handlers['kmod:mint'].enable()
        self.assert_(b.handlers['kmod:mint'].enabled())
        self.assert_('/lib/X11/vesa.drv' in b.handler_files('kmod:mint'))

    def test_check_composite_noavail(self):
        '''Backend.check_composite(), no available driver'''

        b = jockey.backend.Backend()
        h = jockey.xorg_driver.XorgDriverHandler(b, 'vanilla3d',
            'mesa-vanilla', 'v3d', 'vanilla')
        self.failIf(h.enabled())
        b.handlers[h.id()] = h

        self.assertEqual(b.check_composite(), '')

    def test_check_composite_avail(self):
        '''Backend.check_composite(), available driver'''

        class XorgComp(jockey.xorg_driver.XorgDriverHandler):
            def __init__(self, backend):
                jockey.xorg_driver.XorgDriverHandler.__init__(self, backend,
                    'vanilla3d', 'mesa-vanilla', 'v3d', 'vanilla')
            def enables_composite(self):
                return True

        b = jockey.backend.Backend()
        h = XorgComp(b)
        self.failIf(h.enabled())
        b.handlers[h.id()] = h
        self.assertEqual(b.check_composite(), 'xorg:vanilla3d')

    def test_check_composite_enabled(self):
        '''Backend.check_composite(), available driver, already enabled'''

        class XorgComp(jockey.xorg_driver.XorgDriverHandler):
            def __init__(self, backend):
                jockey.xorg_driver.XorgDriverHandler.__init__(self, backend,
                    'vanilla3d', 'mesa-vanilla', 'v3d', 'vanilla')
            def enables_composite(self):
                return True
            def enabled(self):
                return True

        b = jockey.backend.Backend()
        h = XorgComp(b)
        b.handlers[h.id()] = h
        self.assertEqual(b.check_composite(), '')

    def test_update_driverdb(self):
        '''Backend.update_driverdb() and new_used_available()'''

        b = jockey.backend.Backend()

        b.driver_dbs.append(sandbox.TestDriverDB())
        b.update_driverdb()
        # enabled ones would not appear in new_used_available()
        b.set_enabled('kmod:spam', False)

        self.assertEqual(b.new_used_available(), 
            (['kmod:vanilla'], ['kmod:spam', 'firmware:firmwifi']))
        self.assertEqual(b.new_used_available(), ([], []))

        result = b.available()
        self.assertEqual(set(result), set(['kmod:foodmi', 'kmod:mint',
            'kmod:vanilla', 'kmod:firmwifi', 'firmware:firmwifi',
            'kmod:vanilla3d', 'kmod:spam']))

        b.set_enabled('kmod:spam', True)
        self.assertEqual(b.new_used_available(), (['kmod:spam'], []))
        self.assertEqual(b.new_used_available(), ([], []))

    def test_set_enabled(self):
        '''Backend.set_enabled()'''

        b = jockey.backend.Backend()

        # NoSuchHandlerException
        self.assertRaises(jockey.backend.UnknownHandlerException,
            b.set_enabled, 'kmod:foo', True)

    def test_handler_dir(self):
        '''Backend with custom handler_dir'''

        mydir = os.path.join(OSLib.inst.workdir, 'customdir')
        try:
            os.mkdir(mydir)
            open (os.path.join(mydir, 'kmod_nodetect.py'), 'w').write(
                sandbox.h_availability_py)
            b = jockey.backend.Backend(mydir)

            self.assertEqual(set(b.available()), set(['kmod:mint',
                'kmod:vanilla', 'kmod:vanilla3d', 'kmod:firmwifi',
                'kmod:foodmi']))

            self.assert_('free module with available hardware, graphics card'
                in b.handler_info('kmod:vanilla')['name'])
        finally:
            shutil.rmtree(mydir)

    def test_search_driver(self):
        '''Backend.search_driver()'''

        # search_driver() should not display available==True handlers
        open (os.path.join(OSLib.inst.handler_dir, 'k.py'), 'w').write(
            sandbox.h_availability_py)

        b = jockey.backend.Backend()

        self.assertEqual(b.search_driver('modalias:foo'), [])

        # hardware present; no DriverDB, thus yet unknown
        self.assertEqual(b.search_driver(
            'modalias:pci:v0000FFF0d00000001sv00000000sd00000000bc06sc01i01'), 
            [])

        # now add TestDriver, which adds spam/mint
        b.driver_dbs.append(sandbox.TestDriverDB())
        b.update_driverdb()

        # hardware present, now there due to DriverDB
        self.assertEqual(set(b.search_driver(
            'modalias:pci:v0000FFF0d00000001sv00000000sd00000000bc06sc01i01')), 
            set(['kmod:spam', 'kmod:mint']))

        # should also find hardware which isn't present locally
        self.assertEqual(set(b.search_driver(
            'modalias:pci:v00001001d00003D01sv01sd02bc03sc01i00')),
            set(['kmod:vanilla3d', 'kmod:vanilla']))

        # ... and add it to set of available handlers
        self.assert_('printer:openprinting-ppds-postscript-hp:HP' not in b.available())
        self.assertEqual(b.search_driver(
            'printer_deviceid:MFG:Hewlett-Packard;MDL:HP DesignJet 3500CP'),
            ['printer:openprinting-ppds-postscript-hp:20091009'])
        self.assert_('printer:openprinting-ppds-postscript-hp:20091009' in b.available())

    def test_driver_search_redundancy(self):
        '''Backend.add_driverdb() and search_driver() avoid redundant actions'''

        b = jockey.backend.Backend()

        self.assertRaises(dbus.DBusException, b.add_driverdb,
            'UnknownClass', [])

        self.assertEqual(b.search_driver('pci:9876/FEDC'), [])

        log_offset = sandbox.log.tell()

        try:
            sandbox.start_driverdb_server()
            b.add_driverdb('XMLRPCDriverDB', ['http://localhost:8080'])
            #b.update_driverdb()
            drvs = set(b.available())

            log_add = sandbox.log.getvalue()[log_offset:]
            log_offset = sandbox.log.tell()

            self.assertEqual(b.search_driver('pci:9876/FEDC'), ['kmod:spam'])

            log_search = sandbox.log.getvalue()[log_offset:]
        finally:
            sandbox.stop_driverdb_server()

        # add_driverdb() checks new DB against all devices
        self.assert_("about HardwareID('modalias', 'fire:1.2'" in log_add)
        self.assert_("about HardwareID('modalias', 'pci:v0000AAAAd" in log_add)

        # search_driver() queries all databases
        self.assert_('LocalKernelModulesDriverDB' in log_search)
        self.assert_('OpenPrintingDriverDB' in log_search)
        self.assert_('XMLRPCDriverDB' in log_search)

        # no redundant actions
        self.failIf('all custom handlers loaded' in log_add, 
            'add_driverdb() does not re-read local handlers')
        self.failIf('reading modalias' in log_add, 
            'add_driverdb() does not re-read modaliases')
        self.assert_('reading modalias' in log_search, 
            'search_driver() updates all driver DBs')
        self.failIf('querying driver db <jockey.detection.LocalKernelModulesDriverDB ' in log_add, 
            'add_driverdb() does not query unrelated DBs again')
        self.failIf('OpenPrinting' in log_add, 
            'add_driverdb() should not use OpenPrintingDriverDB')
        self.failIf('openprinting.org' in log_add, 
            'add_driverdb() should not query OpenPrinting.org')

