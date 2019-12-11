from __future__ import print_function, unicode_literals, division, absolute_import
import unittest
from . import isolated_dir

import dxpy
from dxpy.sugar import available_memory


class TestUpload(unittest.TestCase):
    def test_available_memory(self):
        # Make it look like we're running on a worker
        dxpy.JOB_ID = "dummy"

        # Use a mock /proc/meminfo
        with isolated_dir():
            with open("meminfo", "w") as out:
                out.write("MemAvailable: 1048576 kB")

            assert available_memory("K", "meminfo") == 1048576.0
            assert available_memory("M", "meminfo") == 1024.0
            assert available_memory("G", "meminfo") == 1.0