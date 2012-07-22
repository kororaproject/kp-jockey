# -*- coding: UTF-8 -*-

'''Serve a directory through http'''

# (c) 2007 - 2011 Canonical Ltd.
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

import traceback, time, urllib, os, signal, ssl
try:
    from http.server import HTTPServer
    from http.server import BaseHTTPRequestHandler as HTTPRequestHandler
except ImportError:
    from SimpleHTTPServer import BaseHTTPServer as HTTPServer
    from SimpleHTTPServer import SimpleHTTPRequestHandler as HTTPRequestHandler

__server_pid = None

def start(port, dir, use_ssl=False, certfile=None):
    '''Start HTTP server on given port and directory

    If use_ssl is True, this starts a HTTPS server. In that case, a certificate
    file can be given.

    This listens on localhost only.
    '''
    global __server_pid

    assert __server_pid == None, 'There is already a server running'

    pid = os.fork()
    if pid == 0:
        try:
            import sys
            # quiesce server log
            os.dup2(os.open('/dev/null', os.O_WRONLY), sys.stderr.fileno())
            os.chdir(dir)
            httpd = HTTPServer.HTTPServer(('localhost', port), HTTPRequestHandler)
            if use_ssl:
                httpd.socket = ssl.wrap_socket (httpd.socket,
                        certfile=certfile, server_side=True)
            httpd.serve_forever()
            os._exit(0)
        except:
            print('********** HTTP server failed: ***********')
            traceback.print_exc()
            os._exit(1)
    else:
        __server_pid = pid
        # wait until server is ready
        while True:
            time.sleep(0.1)
            try:
                f = urllib.urlopen('http%s://localhost:%i' % (use_ssl and 's' or '', port))
            except IOError:
                continue
            f.read()
            f.close()
            break

def stop():
    '''Stop the HTTP server.'''

    global __server_pid
    assert __server_pid != None, 'There is no server running'

    os.kill(__server_pid, signal.SIGTERM)
    os.wait() # undefined exit code
    __server_pid = None

