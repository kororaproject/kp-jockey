# (c) 2007 Canonical Ltd.
# Author: Martin Pitt <martin.pitt@ubuntu.com>
# License: GPL v2 or later

'''Demo handler which is available and installs a package.'''

import jockey.handlers

class DemoPkgHandler(jockey.handlers.Handler):
    def __init__(self, backend):
        jockey.handlers.Handler.__init__(self, backend, None)
        self.package = 'pmount'

    def available(self):
        return True

    def used(self):
        return self.enabled()
