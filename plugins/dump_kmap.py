# Volatility
# Copyright (C) 2007-2013 Volatility Foundation
#
# This file is part of Volatility.
#
# Volatility is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Volatility is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Volatility.  If not, see <http://www.gnu.org/licenses/>.
#

"""
@author:       Andrew Case
@license:      GNU General Public License 2.0
@contact:      atcuno@gmail.com
@organization: 
"""

import volatility.obj as obj
import volatility.utils as utils
import volatility.plugins.linux.common as linux_common
from volatility.renderers import TreeGrid
from volatility.renderers.basic import Address

class linux_dump_kmap(linux_common.AbstractLinuxCommand):
    """Dump virt -> phys kernel mapping"""

    def __init__(self, config, *args, **kwargs):
        linux_common.AbstractLinuxCommand.__init__(self, config, *args, **kwargs)


    def userspace_proc(self):
        init_task_addr = self.addr_space.profile.get_symbol("init_task")
        init_task = obj.Object("task_struct", vm = self.addr_space, offset = init_task_addr)
        # print("init_task: 0x%16x" % (init_task.get_process_address_space().dtb))
        for task in init_task.tasks:
            if task.get_process_address_space():
                return task

    def calculate(self):
        linux_common.set_plugin_members(self)
        a = self.userspace_proc().get_process_address_space()
        # a = self.addr_space
        for i,j in a.get_available_pages():
            if i > 0x0000880000000000:
                yield [0, Address(i|0xffff<<48),Address(a.vtop(i))]
        


    def render_text(self, outfd, data):
        self.table_header(outfd, [("A", "[addrpad]"),
                                  ("B", "[addrpad]")])
        for i in data:
            self.table_row(outfd, i[1], i[2])
