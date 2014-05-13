# -*- coding: utf-8 -*-
"""
     Nereid Blog

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import sys
import os
DIR = os.path.abspath(os.path.normpath(
    os.path.join(__file__, '..', '..', '..', '..', '..', 'trytond')
))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import unittest
import simplejson as json
import trytond.tests.test_tryton
from trytond.tests.test_tryton import test_view, test_depends, \
    POOL, USER, DB_NAME, CONTEXT
from nereid.testing import NereidTestCase
from trytond.transaction import Transaction


class TestNereidBlog(NereidTestCase):
    '''
    Test Blog module.
    '''

    def setUp(self):
        trytond.tests.test_tryton.install_module('nereid_blog')
        self.Currency = POOL.get('currency.currency')
        self.Website = POOL.get('nereid.website')
        self.Company = POOL.get('company.company')
        self.NereidUser = POOL.get('nereid.user')
        self.UrlMap = POOL.get('nereid.url_map')
        self.Party = POOL.get('party.party')
        self.Locale = POOL.get('nereid.website.locale')
        self.Language = POOL.get('ir.lang')

        self.BlogPost = POOL.get('blog.post')
        self.BlogPostComment = POOL.get('blog.post.comment')

        self.templates = {
            'localhost/blog_post_form.jinja':
            '{{ form.errors }} {{ get_flashed_messages() }}',
            'localhost/blog_post.jinja': '{{ post.title }} {{ post.content }}'
            '{{ get_flashed_messages() }}',
            'localhost/blog_posts.jinja': '{{ posts|count }}',
            'localhost/my_blog_posts.jinja': '{{ posts|count }}',
            'localhost/blog_post_edit.jinja':
            '{{ form.errors }} {{ get_flashed_messages() }}',
        }

    def get_template_source(self, name):
        """
        Return templates
        """
        return self.templates.get(name)

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

    def setup_defaults(self):
        "Setup defaults"
        currency, = self.Currency.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])
        company_party, = self.Party.create([{
            'name': 'openlabs'
        }])
        company, = self.Company.create([{
            'party': company_party,
            'currency': currency,
        }])
        guest_party, = self.Party.create([{
            'name': 'Non registered user'
        }])
        guest_user, = self.NereidUser.create([{
            'party': guest_party,
            'display_name': 'Guest User',
            'email': 'guest@openlabs.co.in',
            'company': company,
        }])

        # Create Locale
        en_us, = self.Language.search([('code', '=', 'en_US')])
        locale_en_us, = self.Locale.create([{
            'code': 'en_US',
            'language': en_us,
            'currency': currency,
        }])

        # Create website
        url_map, = self.UrlMap.search([], limit=1)
        self.Website.create([{
            'name': 'localhost',
            'url_map': url_map,
            'company': company,
            'application_user': USER,
            'default_locale': locale_en_us,
            'guest_user': guest_user,
            'currencies': [('set', [currency])],
        }])

        # test party
        test_party, = self.Party.create([{
            'name': 'test party'
        }])

        self.registered_user, = self.NereidUser.create([{
            'party': test_party,
            'display_name': 'Registered User',
            'email': 'email@example.com',
            'password': 'password',
            'company': company,
        }])
        self.registered_user2, = self.NereidUser.create([{
            'party': test_party,
            'display_name': 'Registered User ',
            'email': 'email2@example.com',
            'password': 'password2',
            'company': company,
        }])

    def test_0010_guest_cannot_create_blogs(self):
        "Guests cannot create blogs so blow up"
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/post/-new')
                self.assertEqual(rv.status_code, 302)

    def test_0020_create_blog(self):
        "Login and create a blog"
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post('/login', data={
                    'email': 'email@example.com',
                    'password': 'password',
                })
                rv = c.get('/post/-new')
                self.assertEqual(rv.status_code, 200)

                rv = c.post('/post/-new', data={})
                self.assertTrue('title' in rv.data)
                self.assertTrue('content' in rv.data)

                rv = c.post('/post/-new', data={
                    'title': 'This is a blog post',
                    'content': 'Some test content'
                })
                self.assertEqual(rv.status_code, 302)
                posts = self.BlogPost.search([])
                self.assertEqual(len(posts), 1)
                post = posts[0]
                self.assertEqual(post.state, 'Draft')
                self.assertFalse(post.post_date)

                self.BlogPost.publish([post])
                self.assertEqual(post.state, 'Published')

                rv = c.get('/post/%s/%s' % (
                    self.registered_user.id, 'this-is-a-blog-post'
                ))
                self.assertEqual(rv.status_code, 200)

                self.BlogPost.archive([post])
                self.assertEqual(post.state, 'Archived')

    def test_0025_create_blog_in_published_state(self):
        "Login and create a blog and publish directly"
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post('/login', data={
                    'email': 'email@example.com',
                    'password': 'password',
                })
                rv = c.get('/post/-new')
                self.assertEqual(rv.status_code, 200)

                rv = c.post('/post/-new', data={})
                self.assertTrue('title' in rv.data)
                self.assertTrue('content' in rv.data)

                rv = c.post('/post/-new', data={
                    'title': 'This is a blog post',
                    'content': 'Some test content',
                    'publish': True,
                })
                self.assertEqual(rv.status_code, 302)
                posts = self.BlogPost.search([])
                self.assertEqual(len(posts), 1)
                post = posts[0]

                self.assertEqual(post.state, 'Published')
                self.assertTrue(post.post_date)

                rv = c.get('/post/%s/%s' % (
                    self.registered_user.id, 'this-is-a-blog-post'
                ))
                self.assertEqual(rv.status_code, 200)

    def test_0030_create_blog_with_same_uri(self):
        "Login and create a blog with same URI and it should not create a new"
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post('/login', data={
                    'email': 'email@example.com',
                    'password': 'password',
                })
                rv = c.get('/post/-new')
                self.assertEqual(rv.status_code, 200)

                rv = c.post('/post/-new', data={})
                self.assertTrue('title' in rv.data)
                self.assertTrue('content' in rv.data)

                # Create a new blog
                rv = c.post('/post/-new', data={
                    'title': 'This is a blog post',
                    'content': 'Some test content'
                })
                self.assertEqual(rv.status_code, 302)
                posts = self.BlogPost.search([])
                self.assertEqual(len(posts), 1)

                # Publish this post
                post = posts[0]
                self.BlogPost.publish([post])
                self.assertEqual(post.state, 'Published')

                # Create a new blog with same URI
                rv = c.post('/post/-new', data={
                    'title': 'This is a blog post',
                    'content': 'Some test content',
                })
                self.assertEqual(rv.status_code, 200)
                posts = self.BlogPost.search([])
                self.assertEqual(len(posts), 1)

                # Create a new blog with different URI
                rv = c.post('/post/-new', data={
                    'title': 'This is a blog post',
                    'uri': 'this-is-a-blog-post-2',
                    'content': 'Some test content',
                })
                self.assertEqual(rv.status_code, 302)
                posts = self.BlogPost.search([])
                self.assertEqual(len(posts), 2)

                # Get the list of Blogs
                rv = c.get('/posts/%s/1' % self.registered_user.id)
                self.assertEqual(rv.status_code, 200)
                # This should show only 1 as only 1 has been published
                self.assertEqual(rv.data, '1')

                # Get the list of user's blogs [My blogs]
                rv = c.get('/posts/-my')
                self.assertEqual(rv.status_code, 200)
                self.assertEqual(rv.data, '2')

    def test_0040_create_blog_n_edit(self):
        "Login and create a blog and edit"
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post('/login', data={
                    'email': 'email@example.com',
                    'password': 'password',
                })
                rv = c.get('/post/-new')
                self.assertEqual(rv.status_code, 200)

                rv = c.post('/post/-new', data={})
                self.assertTrue('title' in rv.data)
                self.assertTrue('content' in rv.data)

                # Create a new blog
                rv = c.post('/post/-new', data={
                    'title': 'This is a blog post',
                    'content': 'Some test content'
                })
                self.assertEqual(rv.status_code, 302)
                posts = self.BlogPost.search([])
                self.assertEqual(len(posts), 1)
                self.assertEqual(posts[0].uri, 'this-is-a-blog-post')

                # Edit the post
                rv = c.post(
                    '/post/%s/-edit' % 'this-is-a-blog-post',
                    data={
                        'title': 'This is a blog post edited',
                        'content': 'Some test content'
                    }
                )
                self.assertEqual(rv.status_code, 302)
                posts = self.BlogPost.search([])
                self.assertEqual(len(posts), 1)
                post = posts[0]
                self.assertEqual(post.title, 'This is a blog post edited')
                self.assertEqual(post.uri, 'this-is-a-blog-post')
                self.assertEqual(post.state, 'Draft')

                # Edit the post with id
                rv = c.post(
                    '/post/%d/-edit' % post.id,
                    data={
                        'title': 'This is a blog post edited2',
                        'content': 'Some test content2'
                    }
                )
                self.assertEqual(rv.status_code, 302)
                posts = self.BlogPost.search([])
                self.assertEqual(len(posts), 1)
                post = posts[0]
                self.assertEqual(post.title, 'This is a blog post edited2')
                self.assertEqual(post.content, 'Some test content2')
                self.assertEqual(post.uri, 'this-is-a-blog-post')
                self.assertEqual(post.state, 'Draft')

                # Publish the blog via web request
                rv = c.post(
                    '/post/%s/-change-state' % 'this-is-a-blog-post',
                    data={
                        'state': 'publish'
                    }
                )
                post = posts[0]
                self.assertEqual(post.state, 'Published')

                # Archive the blog via web request
                rv = c.post(
                    '/post/%s/-change-state' % 'this-is-a-blog-post',
                    data={
                        'state': 'archive'
                    }
                )
                post = posts[0]
                self.assertEqual(post.state, 'Archived')

                # Draft the blog via web request
                rv = c.post(
                    '/post/%d/-change-state' % post.id,
                    data={
                        'state': 'draft'
                    }
                )
                post = posts[0]
                self.assertEqual(post.state, 'Draft')

    def test_0050_create_blog_n_comment(self):
        "Login and create a blog and comment on it"
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post('/login', data={
                    'email': 'email@example.com',
                    'password': 'password',
                })
                rv = c.get('/post/-new')
                self.assertEqual(rv.status_code, 200)

                rv = c.post('/post/-new', data={})
                self.assertTrue('title' in rv.data)
                self.assertTrue('content' in rv.data)

                # Create a new blog
                rv = c.post('/post/-new', data={
                    'title': 'This is a blog post',
                    'content': 'Some test content'
                })
                self.assertEqual(rv.status_code, 302)
                posts = self.BlogPost.search([])
                self.assertEqual(len(posts), 1)

                # Publish the blog via web request
                rv = c.post(
                    '/post/%s/-change-state' % 'this-is-a-blog-post',
                    data={
                        'state': 'publish'
                    }
                )
                post = posts[0]
                self.assertEqual(post.state, 'Published')

                # Logout
                c.get('/logout')

                # Comment on the above post
                rv = c.post(
                    '/post/%s/%s/-comment' % (
                        self.registered_user.id, 'this-is-a-blog-post'
                    ), data={
                        'name': 'John Doe',
                        'content': 'This is an awesome post'
                    }, headers=[('X-Requested-With', 'XMLHttpRequest')]
                )
                self.assertFalse(json.loads(rv.data)['success'])
                post = posts[0]
                self.assertEqual(len(post.comments), 0)

                # login as another user
                c.post('/login', data={
                    'email': 'email2@example.com',
                    'password': 'password2',
                })

                # Comment on the above post
                rv = c.post(
                    '/post/%s/%s/-comment' % (
                        self.registered_user.id, 'this-is-a-blog-post'
                    ), data={
                        'name': 'John Doe',
                        'content': 'This is an awesome post'
                    }, headers=[('X-Requested-With', 'XMLHttpRequest')]
                )
                self.assertEqual(rv.status_code, 200)

                comments = self.BlogPostComment.search([])
                self.assertEqual(len(comments), 1)
                comment = comments[0]
                self.assertFalse(comment.is_spam)
                post = posts[0]
                self.assertEqual(len(post.published_comments), 1)

                # try to modify the comment as not the owner of post
                rv = c.post('/comment/%s/-spam' % comment.id, data={
                    'spam': True
                })
                self.assertTrue(rv.status_code, 403)

                # Logout and login as first user
                c.get('/logout')
                c.post('/login', data={
                    'email': 'email@example.com',
                    'password': 'password',
                })

                # try to modify the comment as the owner of post
                rv = c.post('/comment/%s/-spam' % comment.id, data={
                    'spam': True
                }, headers=[('X-Requested-With', 'XMLHttpRequest')])
                self.assertTrue(rv.status_code, 200)
                self.assertTrue(comment.is_spam)
                post = posts[0]
                self.assertEqual(len(post.published_comments), 0)


def suite():
    "Nereid Blog Test Suite"
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestNereidBlog)
    )
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
