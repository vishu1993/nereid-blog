# -*- coding: utf-8 -*-
"""
     Nereid Blog

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import sys
import os
DIR = os.path.abspath(os.path.normpath(os.path.join(__file__,
    '..', '..', '..', '..', '..', 'trytond')))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import test_view, test_depends


class TestNereidBlog(unittest.TestCase):
    '''
    Test Blog module.
    '''

    def setUp(self):
        trytond.tests.test_tryton.install_module('nereid_blog')

    def test0005views(self):
        '''
        Test views.
        '''
        test_view('nereid_blog')

    def test0006depends(self):
        '''
        Test depends.
        '''
        test_depends()


def suite():
    "Nereid Blog Test Suite"
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestNereidBlog)
    )
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
