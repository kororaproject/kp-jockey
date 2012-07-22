# (c) 2009, 2011 Canonical Ltd.
# Author: Martin Owens <doctormo@ubuntu.com>
# License: GPL v2 or later
# Adapted for Fedora: Hedayat Vatankhah <hedayat.fwd@gmail.com>, Chris Smart <chris@kororaa.org>

from jockey.handlers import Handler, KernelModuleHandler
from jockey.oslib import OSLib

# dummy stub for xgettext
def _(x): return x

class Staging_clearpad_tm1217_Driver(KernelModuleHandler):
    '''Handler for staging modules provided by kmod-staging package.
    '''
    def __init__(self, ui):
        KernelModuleHandler.__init__(self, ui, 'clearpad_tm1217',
                name=_('Staging kernel modules'),
                description=_('WARNING: Experimental drivers.'),
                rationale=_('Staging can provide this module: clearpad_tm1217\n\n'
                    'You probably only want to enable this if '
                    'your hardware does not work at all.\n\n'
                    'These are drivers which are not yet in the '
                    'stable kernel tree, but due to be merged soon.'))

    def id(self):
        '''Return an unique identifier of the handler.'''
        return self.package

