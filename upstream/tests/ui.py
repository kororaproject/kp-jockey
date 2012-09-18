# -*- coding: UTF-8 -*-

'''AbstractUI tests'''

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

import unittest, sys, os, signal, time, traceback, tempfile
from cStringIO import StringIO

import jockey.ui, jockey.handlers
from jockey.oslib import OSLib
from jockey.xorg_driver import XorgDriverHandler

import sandbox, httpd

class UITest(sandbox.LogTestCase):
    '''User interface tests.

    These save and restore sys.argv, so the individual tests are free to modify
    it to test various behaviours of the UI. It also captures sys.stdout and
    sys.stderr to self.stdout/self.stderr.
    
    A 50 kB dummy file is created in the OSLib workdir (path in self.big_file),
    which can be used for testing downloading.'''

    def setUp(self):
        self.orig_argv = sys.argv
        self.orig_stdout = sys.stdout
        sys.stdout = StringIO()
        self.orig_stderr = sys.stderr
        sys.stderr = StringIO()
        self.capturing = True

        # create a 50 kB demo file
        self.big_file_contents = 'AB' * 25000
        self.big_file = os.path.join(OSLib.inst.workdir, 'stuff')
        f = open(self.big_file, 'w')
        f.write(self.big_file_contents)
        f.close()

    def tearDown(self):
        sys.argv = self.orig_argv
        self.stop_capture()

        # remove all test handlers
        for f in os.listdir(OSLib.inst.handler_dir):
            os.unlink(os.path.join(OSLib.inst.handler_dir, f))

        # undo the effect of enabling/disabling handlers
        OSLib.inst._make_proc_modules()
        OSLib.inst.reset_packages()
        OSLib.inst._make_xorg_conf()
        jockey.handlers.KernelModuleHandler.read_loaded_modules()
        try:
            os.unlink(OSLib.inst.module_blacklist_file)
        except OSError:
            pass
        OSLib.inst._load_module_blacklist()

        os.unlink(self.big_file)

    def stop_capture(self):
        '''Stop redirecting and capturing stdout/stderr.'''

        if self.capturing:
            self.capturing = False
            sys.stdout.flush()
            sys.stderr.flush()
            self.stdout = sys.stdout.getvalue()
            self.stderr = sys.stderr.getvalue()
            sys.stdout = self.orig_stdout
            sys.stderr = self.orig_stderr

    def test_cli_help(self):
        '''calling with --help'''

        # --help will exit, so we have to fork
        self.stop_capture()
        out = tempfile.TemporaryFile()
        if os.fork() == 0:
            sys.stdout = out
            sys.argv = ['ui-test', '--help']
            try:
                jockey.ui.AbstractUI()
            except SystemExit:
                out.flush()
                os._exit(0)
            os._exit(42) # we should not get here

        self.assertEqual(os.wait()[1], 0)
        out.seek(0)
        self.assert_('--update-db' in out.read())

    def test_list(self):
        '''calling with --list'''

        open (os.path.join(OSLib.inst.handler_dir, 'kmod_nodetect.py'), 'w').write(
            sandbox.h_availability_py)
        sys.argv = ['ui-test', '--list']
        self.assertEqual(sandbox.TestUI().run(), 0)

        self.stop_capture()

        self.assertEqual(len(self.stdout.strip().splitlines()), 5)
        self.assert_('free module with available hardware, graphics card' in self.stdout)
        self.assert_('kmod:mint ' in self.stdout)
        self.assert_('kmod:vanilla ' in self.stdout)
        self.assert_('kmod:vanilla3d ' in self.stdout)
        self.assert_('kmod:firmwifi ' in self.stdout)

    def test_hwids(self):
        '''calling with --hardware-ids'''

        sys.argv = ['ui-test', '--hardware-ids']
        self.assertEqual(sandbox.TestUI().run(), 0)
        self.stop_capture()

        # filter out printers, since we cannot predict them
        lines = [l for l in self.stdout.strip().splitlines() 
            if not l.startswith('printer_deviceid:')]

        self.assertEqual(len(lines), 7)
        self.assert_('modalias:fire:1.2' in lines)

    def test_update(self):
        '''calling with --update'''

        sys.argv = ['ui-test', '--update']
        ui = sandbox.TestUI()
        ui.backend().driver_dbs.append(sandbox.TestDriverDB())
        self.assertEqual(ui.run(), 0)

        self.stop_capture()

        handlers = ui.backend().available()
        self.assert_('kmod:vanilla3d' in handlers) # from LocalKMod
        self.assert_('kmod:spam' in handlers) # from TestDriverDB

    def test_disable(self):
        '''calling with --disable'''

        open (os.path.join(OSLib.inst.handler_dir, 'h.py'), 'w').write(
            sandbox.h_availability_py)

        sys.argv = ['ui-test', '--disable', 'kmod:mint']
        ui = sandbox.TestUI()
        self.assertEqual(ui.run(), 0)
        self.stop_capture()

        for h in ui.backend().available():
            en = jockey.ui.bool(ui.backend().handler_info(h)['enabled'])
            self.assertEqual(en, h != 'kmod:mint')

    def test_disable_nochange(self):
        '''calling with --disable on a non-changeable handler'''

        open (os.path.join(OSLib.inst.handler_dir, 'h.py'), 'w').write(
            'import jockey.handlers' + sandbox.h_nochangemod)

        sys.argv = ['ui-test', '--disable', 'kmod:vanilla']
        ui = sandbox.TestUI()
        self.assertNotEqual(ui.run(), 0)
        self.stop_capture()

        for h in ui.backend().available():
            self.assert_(jockey.ui.bool(ui.backend().handler_info(h)['enabled']))

        self.assert_('I must live' in self.stderr)

    def test_disable_confirm_cancel(self):
        '''calling with --disable --confirm cancelling'''

        open (os.path.join(OSLib.inst.handler_dir, 'h.py'), 'w').write(
            sandbox.h_availability_py)

        sys.argv = ['ui-test', '--confirm', '--disable', 'kmod:mint']
        ui = sandbox.TestUI()
        ui.confirm_response = False
        self.assertEqual(ui.run(), 1)
        self.stop_capture()

        for h in ui.backend().available():
            self.assert_(jockey.ui.bool(ui.backend().handler_info(h)['enabled']))

    def test_disable_confirm(self):
        '''calling with --disable --confirm OKing'''

        open (os.path.join(OSLib.inst.handler_dir, 'h.py'), 'w').write(
            sandbox.h_availability_py)

        sys.argv = ['ui-test', '--confirm', '--disable', 'kmod:mint']
        ui = sandbox.TestUI()
        ui.confirm_response = True
        self.assertEqual(ui.run(), 0)
        self.stop_capture()

        for h in ui.backend().available():
            en = jockey.ui.bool(ui.backend().handler_info(h)['enabled'])
            self.assertEqual(en, h != 'kmod:mint')

    def test_enable(self):
        '''calling with --enable'''

        open (os.path.join(OSLib.inst.handler_dir, 'h.py'), 'w').write(
            sandbox.h_availability_py)
        
        # disable mint driver and verify that in --list
        sys.argv = ['ui-test', '--list']
        ui = sandbox.TestUI()
        ui.backend().set_enabled('kmod:mint', False)
        self.assertEqual(ui.run(), 0)

        # enable it using the CLI
        sys.argv = ['ui-test', '--enable', 'kmod:mint']
        ui = sandbox.TestUI()
        self.assertEqual(ui.run(), 0)

        self.stop_capture()

        mint_disabled = False
        for l in self.stdout.strip().splitlines():
            if l.startswith('kmod:mint'):
                if ui.string_disabled in l:
                    mint_disabled = True
                break
        self.assert_(mint_disabled)

        for h in ui.backend().available():
            self.assert_(jockey.ui.bool(ui.backend().handler_info(h)['enabled']))

    def test_enable_invalid(self):
        '''calling with --enable on a nonexisting handler'''

        sys.argv = ['ui-test', '--enable', 'kmod:unknown']
        ui = sandbox.TestUI()
        self.assertNotEqual(ui.run(), 0)
        self.stop_capture()
        self.assert_(ui.string_unknown_driver in self.stderr)
        self.assert_('--list' in self.stderr)

    def test_set_handler_enable_error(self):
        '''set_handler_enable() on errors'''

        open (os.path.join(OSLib.inst.handler_dir, 'h.py'), 'w').write(
            'import jockey.handlers' + sandbox.h_nochangemod)

        sys.argv = ['ui-test']
        ui = sandbox.TestUI()
        self.stop_capture()

        for h_id in ui.backend().available():
            self.assert_(jockey.ui.bool(ui.backend().handler_info(h_id)['enabled']))
            if 'can_change' in ui.backend().handler_info(h_id):
                no_change_h = h_id
            else:
                change_h = h_id
        assert no_change_h
        assert change_h

        # change an unchangeable handler
        # note: don't set a confirmation response, it shouldn't ask here
        self.assertEqual(ui.set_handler_enable(no_change_h, 'enable', True), False)
        self.assertEqual(ui.pop_error()[1], 'I must live')
        self.assertRaises(IndexError, ui.pop_error)
        self.assertEqual(ui.set_handler_enable(no_change_h, 'disable', True), False)
        self.assertEqual(ui.pop_error()[1], 'I must live')
        self.assertRaises(IndexError, ui.pop_error)
        self.assertEqual(ui.set_handler_enable(no_change_h, 'toggle', True), False)
        self.assertEqual(ui.pop_error()[1], 'I must live')
        self.assertRaises(IndexError, ui.pop_error)

        # invalid operation
        self.assertRaises(ValueError, ui.set_handler_enable, no_change_h, 'foo', True)

        # package install failure
        ui.backend().handlers['kmod:mint'].package = 'pretzel'
        self.assertEqual(jockey.ui.bool(ui.backend().handler_info('kmod:mint')['enabled']),
            False)
        OSLib.inst.pending_install_remove_exception = 'OMGbroken'
        self.assertEqual(ui.set_handler_enable('kmod:mint', 'enable',
            False), False)
        self.assertEqual(jockey.ui.bool(ui.backend().handler_info('kmod:mint')['enabled']),
            False)
        # one error message about install failure
        (etitle, etext) = ui.pop_error()
        self.assert_('OMGbroken' in etext, '%s: %s' % (etitle, etext))
        self.assertRaises(IndexError, ui.pop_error)

        # install it now
        self.assertEqual(ui.set_handler_enable('kmod:mint', 'enable',
            False), True)
        self.assertEqual(jockey.ui.bool(ui.backend().handler_info('kmod:mint')['enabled']),
            True)

        # package removal failure
        OSLib.inst.pending_install_remove_exception = 'OMGZombie'
        self.assertEqual(ui.set_handler_enable('kmod:mint', 'disable',
            False), False)
        self.assertEqual(jockey.ui.bool(ui.backend().handler_info('kmod:mint')['enabled']),
            True)
        # one error message about removal failure
        (etitle, etext) = ui.pop_error()
        self.assert_('OMGZombie' in etext, '%s: %s' % (etitle, etext))
        self.assertRaises(IndexError, ui.pop_error)

    def test_set_handler_enable(self):
        '''set_handler_enable()'''

        sys.argv = ['ui-test']
        ui = sandbox.TestUI()
        self.stop_capture()

        def case(confirm_response, action, confirm, expected_return, expected_enabled):
            ui.confirm_response = confirm_response
            self.assertEqual(ui.set_handler_enable('kmod:vanilla', action,
                confirm), expected_return)
            self.assertEqual(jockey.ui.bool(ui.backend().handler_info('kmod:vanilla')['enabled']),
                expected_enabled)
            self.assertRaises(IndexError, ui.pop_error)

        # unconfirmed mode

        # already enabled
        case(None, 'enable', False, False, True)
        # disabling changes something
        case(None, 'disable', False, True, False)
        # already disabled
        case(None, 'disable', False, False, False)
        # toggling always changes something
        case(None, 'toggle', False, True, True)
        case(None, 'toggle', False, True, False)

        # confirmed mode

        # already disabled, doesn't need confirm_respose
        case(None, 'disable', True, False, False)
        # enable, cancel confirmation
        case(False, 'enable', True, False, False)
        # enable, ack confirmation
        case(True, 'enable', True, True, True)
        # disable, cancel confirmation
        case(False, 'disable', True, False, True)
        # disable, ack confirmation
        case(True, 'disable', True, True, False)
        # toggle, cancel confirmation
        case(False, 'toggle', True, False, False)
        # toggle, ack confirmation
        case(True, 'toggle', True, True, True)
        case(True, 'toggle', True, True, False)

    def test_mode_any(self):
        '''calling with --mode any'''

        sys.argv = ['ui-test', '--list', '--mode', 'any']
        ui = sandbox.TestUI()
        self.assertEqual(sandbox.TestUI().run(), 0)
        displayed = set(ui.get_displayed_handlers())

        self.stop_capture()

        self.assertEqual(len(self.stdout.strip().splitlines()), 5)
        self.assert_('free module with available hardware, graphics card' in self.stdout)
        self.assert_('kmod:mint ' in self.stdout)
        self.assert_('kmod:vanilla ' in self.stdout)
        self.assert_('kmod:vanilla3d ' in self.stdout)
        self.assert_('kmod:firmwifi ' in self.stdout)

        self.assertEqual(displayed, set(['kmod:mint', 'kmod:vanilla',
            'kmod:vanilla3d', 'kmod:firmwifi', 'kmod:foodmi']))

        # mint is not enabled by default
        self.failIf('Restricted' in ui.main_window_title())
        (h, s) = ui.main_window_text()
        self.assert_('No proprietary drivers are in use' in h)
        self.assert_('cannot fix or improve' in s)

        # enable mint
        ui.backend().set_enabled('kmod:mint', True)
        (h, s) = ui.main_window_text()
        self.assert_('Proprietary drivers are being used' in h)
        self.assert_('cannot fix or improve' in s)

    def test_mode_free(self):
        '''calling with --mode free'''

        sys.argv = ['ui-test', '--list', '--mode', 'free']
        ui = sandbox.TestUI()
        self.assertEqual(sandbox.TestUI().run(), 0)
        displayed = set(ui.get_displayed_handlers())
        self.stop_capture()

        self.assertEqual(displayed, set(['kmod:vanilla',
            'kmod:firmwifi', 'kmod:foodmi']))

        self.assertEqual(len(self.stdout.strip().splitlines()), 3)
        self.assert_('free module with available hardware, graphics card' in self.stdout)
        self.assert_('kmod:vanilla ' in self.stdout)
        self.assert_('kmod:firmwifi ' in self.stdout)
        self.assert_('kmod:foodmi ' in self.stdout)

        self.failIf('Restricted' in ui.main_window_title())

        (h, s) = ui.main_window_text()
        self.assert_('No proprietary drivers are in use' in h)
        self.assertEqual(s, '')

    def test_mode_nonfree(self):
        '''calling with --mode nonfree'''

        sys.argv = ['ui-test', '--list', '--mode', 'nonfree']
        ui = sandbox.TestUI()
        self.assertEqual(sandbox.TestUI().run(), 0)
        displayed = set(ui.get_displayed_handlers())
        self.stop_capture()

        self.assertEqual(displayed, set(['kmod:mint', 'kmod:vanilla3d']))

        self.assertEqual(len(self.stdout.strip().splitlines()), 2)
        self.assert_('kmod:vanilla3d ' in self.stdout)
        self.assert_('kmod:mint ' in self.stdout)

        self.assert_('Restricted' in ui.main_window_title())

        (h, s) = ui.main_window_text()
        self.assert_('No proprietary drivers are in use' in h, h)
        self.assert_('cannot fix or improve' in s)

    def test_check(self):
        '''calling with --check'''

        try:
            # new free and nonfree drivers which are already enabled -> no notification
            sys.argv = ['ui-test', '--check']
            ui = sandbox.TestUI()
            self.assertEqual(ui.run(), 1)
            self.stop_capture()

            self.assertRaises(IndexError, ui.pop_error)
            self.assertRaises(IndexError, ui.pop_notification)
            self.failIf(ui.main_loop_active)

            self.assert_(os.path.exists(OSLib.inst.check_cache))
            os.unlink(OSLib.inst.check_cache)

            # new free and nonfree drivers which are not enabled -> nonfree notification
            ui = sandbox.TestUI()
            for h in ui.backend().available():
                ui.backend().set_enabled(h, False)
            self.assertEqual(ui.run(), 0)

            self.assertRaises(IndexError, ui.pop_error)
            self.assertEqual('Restricted drivers available', ui.pop_notification()[0])
            
            # the next run does not report anything new
            self.assertEqual(ui.run(), 1)
            self.assertRaises(IndexError, ui.pop_error)
            self.assertRaises(IndexError, ui.pop_notification)
            self.assert_(ui.main_loop_active)
            os.unlink(OSLib.inst.check_cache)

            # non-announced handlers do not cause notifications
            ui = sandbox.TestUI()
            for h in ui.backend().available():
                ui.backend().handlers[h].announce = False
            self.assertEqual(ui.run(), 1)

            self.assertRaises(IndexError, ui.pop_error)
            self.assertRaises(IndexError, ui.pop_notification)
            self.failIf(ui.main_loop_active)
            os.unlink(OSLib.inst.check_cache)

            # new free drivers which are not enabled -> free notification
            sys.argv = ['ui-test', '--check', '-m', 'free']
            ui = sandbox.TestUI()
            self.assertEqual(ui.run(), 0)

            self.assertRaises(IndexError, ui.pop_error)
            self.assertEqual('New drivers available', ui.pop_notification()[0])
            self.assert_(ui.main_loop_active)

            # enable the free drivers again and load them -> no notification
            ui.main_loop_active = False
            for h in ui.backend().available('free'):
                ui.backend().set_enabled(h, True)
                assert jockey.ui.bool(ui.backend().handler_info(h)['used'])
            self.assertEqual(ui.run(), 1)
            self.assertRaises(IndexError, ui.pop_error)
            self.assertRaises(IndexError, ui.pop_notification)
            self.failIf(ui.main_loop_active)

            # enable the non-free drivers again, too and load them ->
            # notification about usage
            sys.argv = ['ui-test', '--check', '-m', 'nonfree']
            ui = sandbox.TestUI()
            for h in ui.backend().available('nonfree'):
                ui.backend().set_enabled(h, True)
                self.assert_(jockey.ui.bool(ui.backend().handler_info(h)['used']))
            self.assertEqual(ui.run(), 1)
            self.assertRaises(IndexError, ui.pop_error)
            self.assertEqual('New restricted drivers in use', ui.pop_notification()[0])
            self.assert_(ui.main_loop_active)

            # the next run does not report anything new
            ui.main_loop_active = False
            self.assertEqual(ui.run(), 1)
            self.assertRaises(IndexError, ui.pop_error)
            self.assertRaises(IndexError, ui.pop_notification)
            self.failIf(ui.main_loop_active)
        finally:
            try:
                os.unlink(OSLib.inst.check_cache)
            except OSError:
                pass

    def test_download_local_nocancel(self):
        '''download_url(), local file://, no cancelling'''

        ui = sandbox.TestUI()

        # temporary file
        (fname, h) = ui.download_url('file://' + self.big_file)
        self.assertEqual(open(fname).read(), self.big_file_contents)
        os.unlink(fname)

        self.assertRaises(IndexError, ui.pop_error)

        # we got progress reports
        self.assertEqual(ui.cur_progress, ['file://' + self.big_file,
            len(self.big_file_contents), len(self.big_file_contents)])

        # specified file name
        dest = os.path.join(OSLib.inst.workdir, 'destfile')
        (fname, h) = ui.download_url('file://' + self.big_file, dest)
        self.assertEqual(fname, dest)
        self.assertEqual(open(dest).read(), self.big_file_contents)
        os.unlink(dest)

        self.assertRaises(IndexError, ui.pop_error)

        # we got progress reports
        self.assertEqual(ui.cur_progress, ['file://' + self.big_file,
            len(self.big_file_contents), len(self.big_file_contents)])

        # nonexisting file
        (fname, h) = ui.download_url('file://junk/nonexisting')
        self.assertEqual(fname, None)

        # one error message about download failure
        self.assert_(ui.pop_error())
        self.assertRaises(IndexError, ui.pop_error)

    def test_download_local_cancel(self):
        '''download_url(), local file://, cancelling'''

        ui = sandbox.TestUI()

        # temporary file
        ui.cancel_progress = True
        (fname, h) = ui.download_url('file://' + self.big_file)
        self.assertEqual(fname, None)

        # we got progress reports
        self.assertEqual(ui.cur_progress[0], 'file://' + self.big_file)
        self.assertEqual(ui.cur_progress[2], len(self.big_file_contents))
        ratio = float(ui.cur_progress[1])/len(self.big_file_contents)
        self.assert_(ratio >= 0.3, ratio)
        self.assert_(ratio < 0.5)

        # specified file name
        dest = os.path.join(OSLib.inst.workdir, 'destfile')
        ui.cancel_progress = True
        (fname, h) = ui.download_url('file://' + self.big_file, dest)
        self.assertEqual(fname, None)

        # we got progress reports
        self.assertEqual(ui.cur_progress[0], 'file://' + self.big_file)
        self.assertEqual(ui.cur_progress[2], len(self.big_file_contents))
        ratio = float(ui.cur_progress[1])/len(self.big_file_contents)
        self.assert_(ratio >= 0.3, ratio)
        self.assert_(ratio < 0.5)

    def test_download_http_nocancel(self):
        '''download_url(), HTTP, no cancelling'''

        self.stop_capture()

        ui = sandbox.TestUI()

        # temporary file
        httpd.start(8427, OSLib.inst.workdir)
        (fname, h) = ui.download_url('http://localhost:8427/stuff')
        httpd.stop()
        self.assertEqual(open(fname).read(), self.big_file_contents)
        os.unlink(fname)

        self.assertRaises(IndexError, ui.pop_error)

        # we got progress reports
        self.assertEqual(ui.cur_progress, ['http://localhost:8427/stuff',
            len(self.big_file_contents), len(self.big_file_contents)])

        # specified file name
        dest = os.path.join(OSLib.inst.workdir, 'destfile')
        httpd.start(8427, OSLib.inst.workdir)
        (fname, h) = ui.download_url('http://localhost:8427/stuff', dest)
        httpd.stop()
        self.assertEqual(fname, dest)
        self.assertEqual(open(dest).read(), self.big_file_contents)
        os.unlink(dest)

        self.assertRaises(IndexError, ui.pop_error)

        # we got progress reports
        self.assertEqual(ui.cur_progress, ['http://localhost:8427/stuff',
            len(self.big_file_contents), len(self.big_file_contents)])

        # nonexisting file
        httpd.start(8427, OSLib.inst.workdir)
        (fname, h) = ui.download_url('http://localhost:8427/nonexisting')
        httpd.stop()
        self.assertEqual(fname, None)

        # one error message about download failure
        self.assert_(ui.pop_error())
        self.assertRaises(IndexError, ui.pop_error)

        # nonexisting server
        httpd.start(8427, OSLib.inst.workdir)
        (fname, h) = ui.download_url('http://i.do.not.exist:8080/nonexisting')
        httpd.stop()
        self.assertEqual(fname, None)

        # one error message about download failure
        self.assert_(ui.pop_error())
        self.assertRaises(IndexError, ui.pop_error)

    def test_download_http_cancel(self):
        '''download_url(), HTTP, cancelling'''

        self.stop_capture()

        ui = sandbox.TestUI()

        # temporary file
        httpd.start(8427, OSLib.inst.workdir)
        ui.cancel_progress = True
        (fname, h) = ui.download_url('http://localhost:8427/stuff')
        httpd.stop()
        self.assertEqual(fname, None)

        self.assertRaises(IndexError, ui.pop_error)

        # we got progress reports
        self.assertEqual(ui.cur_progress[2], len(self.big_file_contents))
        ratio = float(ui.cur_progress[1])/len(self.big_file_contents)
        self.assert_(ratio >= 0.3, ratio)
        self.assert_(ratio < 0.5)

        # specified file name
        dest = os.path.join(OSLib.inst.workdir, 'destfile')
        ui.cancel_progress = True
        httpd.start(8427, OSLib.inst.workdir)
        (fname, h) = ui.download_url('http://localhost:8427/stuff', dest)
        httpd.stop()
        self.assertEqual(fname, None)

        self.assertRaises(IndexError, ui.pop_error)

        # we got progress reports
        self.assertEqual(ui.cur_progress[2], len(self.big_file_contents))
        ratio = float(ui.cur_progress[1])/len(self.big_file_contents)
        self.assert_(ratio >= 0.3, ratio)
        self.assert_(ratio < 0.5)

    def test_check_composite_noavail(self):
        '''calling with --check-composite and no available driver'''

        sys.argv = ['ui-test', '--check-composite']
        ui = sandbox.TestUI()

        h = XorgDriverHandler(ui, 'vanilla3d', 'mesa-vanilla', 'v3d',
            'vanilla')
        self.failIf(h.enabled())
        ui.backend().handlers[h.id()] = h

        self.assertEqual(ui.run(), 1)
        self.stop_capture()

        self.assert_('no available' in self.stderr)

    def test_check_composite_avail(self):
        '''calling with --check-composite and available driver'''

        sys.argv = ['ui-test', '--check-composite']
        ui = sandbox.TestUI()

        class XorgComp(XorgDriverHandler):
            def __init__(self, ui):
                XorgDriverHandler.__init__(self, ui, 'vanilla3d',
                    'mesa-vanilla', 'v3d', 'vanilla')
            def enables_composite(self):
                return True

        h = XorgComp(ui.backend())
        h_id = h.id()
        self.failIf(h.enabled())
        ui.backend().handlers[h_id] = h

        ui.confirm_response = True
        self.assertEqual(ui.run(), 0)

        self.stop_capture()
        self.assert_(jockey.ui.bool(ui.backend().handler_info(h_id)['enabled']))

    def test_check_composite_enabled(self):
        '''calling with --check-composite and already enabled driver'''

        sys.argv = ['ui-test', '--check-composite']
        ui = sandbox.TestUI()

        class XorgComp(XorgDriverHandler):
            def __init__(self, ui):
                XorgDriverHandler.__init__(self, ui, 'vanilla3d',
                    'mesa-vanilla', 'v3d', 'vanilla')
            def enables_composite(self):
                return True
            def enabled(self):
                return True

        h = XorgComp(ui)
        ui.backend().handlers[h.id()] = h

        # note: do not set confirm_response here, shouldn't ask
        self.assertEqual(ui.run(), 1)

        self.stop_capture()
        self.assert_('already supports' in self.stderr, self.stderr)

    # TODO: disabled, this currently breaks
    def teest_ui_dbus(self):
        '''UI --dbus-server'''

        svr_pid = os.fork()
        if svr_pid == 0:
            sys.argv = ['ui-test', '--dbus-server']
            try:
                sandbox.TestUI().run()
            except:
                print '********** UI D-BUS server failed: ***********'
                traceback.print_exc()
                os._exit(1)
            os._exit(0)

        time.sleep(2)
        iface = sandbox.TestUI.get_dbus_client()

        self.assertEqual(iface.search_driver('unknown:foo'), False)

        # shuts down after one request
        try:
            iface.search_driver('unknown:bar')
            fail('should only accept one method call and then terminate')
        except Exception as e:
            self.assertEqual(e._dbus_error_name, 'org.freedesktop.DBus.Error.NoReply')

        # give the daemon a second to terminate
        timeout = 10
        while timeout >= 0:
            (pid, exitcode) = os.waitpid(svr_pid, os.WNOHANG)
            if pid > 0:
                self.assertEqual(svr_pid, pid)
                self.assertEqual(exitcode, 0)
                break
            time.sleep(0.1)
            timeout -= 1
        if timeout <= 0:
            os.kill(svr_pid, signal.SIGKILL)
            os.waitpid(svr_pid, 0)
            self.fail('UI D-BUS server does not auto-terminate, killing')

    def test_search_driver_errors(self):
        '''D-BUS API: Search for drivers which cannot be enabled'''

        ui = sandbox.TestUI()
        self.stop_capture()

        # does not exist
        self.assertEqual(ui.search_driver('unknown:foo'), (False, []))
        self.assertEqual(ui.get_displayed_handlers(), [])

        # kmod:vanilla, already enabled
        self.assertEqual(ui.search_driver(
            'modalias:pci:v00001001d0sv0sd0bc03sc00i00'), (False, []))
        self.assertEqual(ui.get_displayed_handlers(), ['kmod:vanilla'])

    def test_search_driver_disabled(self):
        '''D-BUS API: Search for a noninstalled driver'''

        # search_driver() should not display available==True handlers
        open (os.path.join(OSLib.inst.handler_dir, 'kmod_avail.py'), 'w').write(
            sandbox.h_availability_py)
        ui = sandbox.TestUI()

        self.assert_('kmod:spam' not in ui.backend().available())

        sandbox.start_driverdb_server()
        try:
            ui.backend().add_driverdb('XMLRPCDriverDB', ['http://localhost:8080'])
            # first match is kmod:mint:UbuOne in our fake db
            result = ui.search_driver('pci:9876/FEDC')
        finally:
            sandbox.stop_driverdb_server()

        self.stop_capture()
        self.assertEqual(result, (False, []))
        self.assertEqual(ui.get_displayed_handlers(), ['kmod:spam'])

        info = ui.backend().handler_info('kmod:spam')
        self.assertEqual(info['enabled'], 'True')

    def test_search_driver_enable(self):
        '''D-BUS API: Search for a driver which gets enabled'''

        ui = sandbox.TestUI()
        self.stop_capture()

        ui.backend().handlers['kmod:vanilla3d'].package = 'mesa-vanilla'

        # don't enable the driver
        result = ui.search_driver('modalias:pci:v00001001d00003D0sv0sd0bc03sc0i0')
        self.assertEqual(set(ui.get_displayed_handlers()),
            set(['kmod:vanilla3d', 'kmod:vanilla']))
        self.assertEqual(result, (False, []))
        self.assertEqual(ui.backend().handler_info('kmod:vanilla3d')['enabled'],
            'False')

        # enable it now
        ui.ui_main_loop = lambda: ui.set_handler_enable('kmod:vanilla3d',
            'enable', False, False) # fake main loop to enable kmod:vanilla3d
        result = ui.search_driver('modalias:pci:v00001001d00003D0sv0sd0bc03sc0i0')
        self.assertEqual(set(ui.get_displayed_handlers()),
            set(['kmod:vanilla3d', 'kmod:vanilla']))
        self.assertEqual(result, (True, sandbox.fake_pkginfo['default']['mesa-vanilla']['files']))
        self.assertEqual(ui.backend().handler_info('kmod:vanilla3d')['enabled'],
            'True')

    def test_hwid_to_display_string(self):
        '''hwid_to_display_string()'''

        ui = sandbox.TestUI()
        self.stop_capture()

        self.assertEqual(ui.hwid_to_display_string('foo'), 'foo')
        self.assertEqual(ui.hwid_to_display_string('foo:bar'), 'foo:bar')
        self.assertEqual(ui.hwid_to_display_string('printer_deviceid:MFG:Samsung;MDL:ML-1610;CMD:GDI'), 
            'Samsung ML-1610')
        self.assertEqual(ui.hwid_to_display_string('printer_deviceid:MDL:InkShot 12;CMD:GDI;MFG:PH'), 
            'PH InkShot 12')

    def test_check_auto_install(self):
        '''calling with --auto-install'''

        open (os.path.join(OSLib.inst.handler_dir, 'h.py'), 'w').write(
            sandbox.h_auto_install_mod)

        ui = sandbox.TestUI()
        for h in ui.backend().available():
            if ui.backend().handler_info(h)['enabled']:
                ui.backend().set_enabled(h, False)
        self.assertEqual(ui.run(), 0)
        self.stop_capture()

        sys.argv = ['ui-test', '--auto-install']
        ui = sandbox.TestUI()
        self.assertEqual(ui.run(), 0)

        for h in ui.backend().available():
            enabled = jockey.ui.bool(ui.backend().handler_info(h)['enabled'])
            if h == 'kmod:vanilla':
                self.assert_(enabled)
            else:
                self.assert_(not enabled, '%s shouldn\'t be enabled' % h)

