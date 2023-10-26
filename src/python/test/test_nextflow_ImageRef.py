#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2013-2016 DNAnexus, Inc.
#
# This file is part of dx-toolkit (DNAnexus platform client libraries).
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may not
#   use this file except in compliance with the License. You may obtain a copy
#   of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
from __future__ import print_function, unicode_literals, division, absolute_import

import os
import sys
import unittest

from parameterized import parameterized
from dxpy_testutil import DXTestCase
from dxpy.compat import USING_PYTHON2
from dxpy.nextflow.ImageRef import ImageRef, DockerImageRef

if USING_PYTHON2:
    spawn_extra_args = {}
else:
    # Python 3 requires specifying the encoding
    spawn_extra_args = {"encoding": "utf-8"}


class TestImageRef(DXTestCase):

    @parameterized.expand([
        ["proc1", "sha256aasdfadfadfafddasfdsfa", "file-xxxx", "my/docker/repo", "image_name", "v2.0.10"]
    ])
    @unittest.skipIf(USING_PYTHON2,
        'Skipping Python 3 code')
    def test_ImageRef_bundled_depends(self, process, digest, dx_file_id, repository, image_name, tag):
        image_ref = ImageRef(process, digest, dx_file_id, repository, image_name, tag)
        bundled_depends = image_ref.bundled_depends
        bundle_fixture = {"name": "image_name", "id": {"$dnanexus_link": "file-xxxx"}}
        self.assertEqual(bundled_depends, bundle_fixture)

    @parameterized.expand([
        ["proc1", "sha256aasdfadfadfafddasfdsfa", "file-xxxx", "my/docker/repo", "image_name", "v2.0.10"]
    ])
    @unittest.skipIf(USING_PYTHON2,
                     'Skipping Python 3 code')
    def test_ImageRef_cache(self, process, digest, dx_file_id, repository, image_name, tag):
        image_ref = ImageRef(process, digest, dx_file_id, repository, image_name, tag)
        with self.assertRaises(NotImplementedError) as err:
            _ = image_ref.cache()
            self.assertEqual(
                err.exception,
                "Abstract class. Method not implemented. Use the concrete implementations."
            )

    @parameterized.expand([
        ["proc1", "sha256aasdfadfadfafddasfdsfa", "file-xxxx", "my/docker/repo", "image_name", "v2.0.10"]
    ])
    @unittest.skipIf(USING_PYTHON2,
                     'Skipping Python 3 code')
    def test_DockerImageRef_cache(self, process, digest, dx_file_id, repository, image_name, tag):
        image_ref = DockerImageRef(process, digest, dx_file_id, repository, image_name, tag)
        bundle_dx_file_id = image_ref.cache()
        self.assertFalse("")


if __name__ == '__main__':
    if 'DXTEST_FULL' not in os.environ:
        sys.stderr.write(
            'WARNING: env var DXTEST_FULL is not set; tests that create apps or run jobs will not be run\n')
    unittest.main()
