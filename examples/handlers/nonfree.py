# (c) 2007 Canonical Ltd.
# Author: Martin Pitt <martin.pitt@ubuntu.com>
# License: GPL v2 or later

'''Demo handler which is nonfree and available.'''

import jockey.handlers

class NonfreeHandler(jockey.handlers.Handler):
    def __init__(self, backend):
        jockey.handlers.Handler.__init__(self, backend, 'Demo nonfree driver',
            'This is just for demonstration and testing purposes.',
            'I will not do anything to your system.')
        self._enabled = False
        self._used = False

    def free(self):
        return False

    def enabled(self):
        return self._enabled

    def used(self):
        return self._used

    def available(self):
        return True

    def enable(self):
        self._enabled = True
        self._used = True

    def disable(self):
        self._enabled = False
        self._used = False

