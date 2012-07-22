# (c) 2009, 2011 Canonical Ltd.
# Author: Martin Owens <doctormo@ubuntu.com>
# License: GPL v2 or later
# Adopted for Fedora: Hedayat Vatankhah <hedayat.fwd@gmail.com>

from jockey.handlers import Handler, KernelModuleHandler

# dummy stub for xgettext
def _(x): return x

class CatalystDriver(KernelModuleHandler):
    '''Handler for the ATI/AMD graphic cards
    Just to provide a better name and description! 
    '''
    def __init__(self, ui):
        KernelModuleHandler.__init__(self, ui, 'fglrx',
                name=_('AMD proprietary Catalyst graphics driver'),
                description=_('3D-accelerated proprietary graphics driver for '
                    'AMD (ATI) cards.'),
                rationale=_('This driver is required to fully utilise the 3D '
                    'potential of some AMD (ATI) graphics cards, as well as provide '
                    '2D acceleration of newer cards.'))

