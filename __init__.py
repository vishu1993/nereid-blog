# -*- coding: utf-8 -*-
"""
    __init__

    Blog Module for Nereid

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from blog import BlogPost, BlogPostComment

from trytond.pool import Pool


def register():
    '''
        Register classes
    '''
    Pool.register(
        BlogPost,
        BlogPostComment,
        module='nereid_blog', type_='model'
    )
