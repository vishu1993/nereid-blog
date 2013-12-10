# -*- coding: utf-8 -*-
"""
    blog

    Blog

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from datetime import datetime

from wtforms import Form, TextField, TextAreaField, BooleanField, validators
from wtfrecaptcha.fields import RecaptchaField
from trytond.model import ModelSQL, ModelView, Workflow, fields
from trytond.pyson import Bool, Eval
from trytond.pool import Pool, PoolMeta
from trytond.config import CONFIG
from nereid import (
    request, abort, render_template, login_required, url_for, redirect, flash,
    jsonify,
)
from nereid.contrib.pagination import Pagination
from nereid.helpers import slugify

__all__ = ['BlogPost', 'BlogPostComment']
__classmeta__ = PoolMeta

STATES = {'readonly': Eval('state') != 'Draft'}


class BlogPostForm(Form):
    "Blog Post Form"
    title = TextField('Title', [validators.Required()])
    uri = TextField('URL')
    content = TextAreaField('Content', [validators.Required()])
    publish = BooleanField('Publish', default=False)
    allow_guest_comments = BooleanField('Allow Guest Comments ?', default=True)


class PostCommentForm(Form):
    "Post Comment Form"
    name = TextField('Name', [validators.Required()])
    content = TextAreaField('Content', [validators.Required()])


class GuestCommentForm(PostCommentForm):
    "Add captcha if a guest is commenting"
    if 're_captcha_public' in CONFIG.options:
        captcha = RecaptchaField(
            public_key=CONFIG.options['re_captcha_public'],
            private_key=CONFIG.options['re_captcha_private'],
            secure=True
        )


class BlogPost(Workflow, ModelSQL, ModelView):
    'Blog Post'
    __name__ = 'blog.post'
    _rec_name = 'title'

    title = fields.Char('Title', required=True, select=True, states=STATES)
    uri = fields.Char(
        'URI', required=True, select=True, on_change_with=['title', 'uri'],
        states=STATES,
    )
    nereid_user = fields.Many2One(
        'nereid.user', 'Nereid User', required=True, select=True,
        states=STATES
    )
    post_date = fields.DateTime('Post Date', states=STATES)
    content = fields.Text('Content', states=STATES)
    allow_guest_comments = fields.Boolean(
        'Allow Guest Comments ?', select=True
    )
    comments = fields.One2Many(
        'blog.post.comment', 'post', 'Comments'
    )
    published_comments = fields.Function(
        fields.One2Many(
            'blog.post.comment', None, 'Published Comments'
        ), 'get_published_comments'
    )
    state = fields.Selection([
        ('Draft', 'Draft'),
        ('Published', 'Published'),
        ('Archived', 'Archived'),
    ], 'State', readonly=True)

    @staticmethod
    def default_state():
        return 'Draft'

    def get_published_comments(self, name):
        "Returns the published comments, i.e., comments not marked as spam"
        Comment = Pool().get('blog.post.comment')

        return map(int, Comment.search([
            ('post', '=', self.id),
            ('is_spam', '=', False)
        ]))

    @classmethod
    def __setup__(cls):
        super(BlogPost, cls).__setup__()
        cls._sql_constraints += [
            (
                'nereid_user_uri_uniq', 'UNIQUE(nereid_user, uri)',
                'URI must be unique for a nereid user'
            ),
        ]
        cls._transitions |= set((
            ('Draft', 'Published'),
            ('Published', 'Draft'),
            ('Draft', 'Archived'),
            ('Published', 'Archived'),
            ('Archived', 'Draft'),
        ))
        cls._buttons.update({
            'publish': {
                'invisible': Eval('state') != 'Draft',
            },
            'draft': {
                'invisible': Eval('state') == 'Draft',
            },
            'archive': {
                'invisible': Eval('state') != 'Published',
            }
        })
        cls.per_page = 10

    @classmethod
    @ModelView.button
    @Workflow.transition('Draft')
    def draft(cls, posts):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('Published')
    def publish(cls, posts):
        cls.write(posts, {'post_date': datetime.utcnow()})

    @classmethod
    @ModelView.button
    @Workflow.transition('Archived')
    def archive(cls, posts):
        pass

    def on_change_with_uri(self):
        if self.title and not self.uri:
            return slugify(self.title)
        return self.uri

    @classmethod
    @login_required
    def new_post(cls):
        """Create a new post
        """
        post_form = BlogPostForm(request.form)

        if request.method == 'POST' and post_form.validate():
            # Search for a post with same uri
            uri = post_form.uri.data or slugify(post_form.title.data)
            existing_post = cls.search([
                ('uri', '=', uri),
                ('nereid_user', '=', request.nereid_user.id),
            ])
            if existing_post:
                flash(
                    'A post with same URL exists. '
                    'Please change the title or modify the URL'
                )
                return redirect(request.referrer)
            post, = cls.create([{
                'title': post_form.title.data,
                'uri': uri,
                'content': post_form.content.data,
                'nereid_user': request.nereid_user.id,
                'allow_guest_comments': post_form.allow_guest_comments.data,
            }])
            if post_form.publish.data:
                cls.publish([post])
                flash('Your post has been published.')
            else:
                flash('Your post has been saved.')

            return redirect(url_for(
                'blog.post.render', user_id=post.nereid_user.id,
                uri=post.uri
            ))
        return render_template('blog_post_form.jinja', form=post_form)

    @classmethod
    @login_required
    def edit_post(cls, uri):
        """Edit an existing post
        """
        # Search for a post with same uri
        posts = cls.search([
            ('uri', '=', uri),
            ('nereid_user', '=', request.nereid_user.id),
        ])

        if not posts:
            abort(404)

        post = posts[0]
        post_form = BlogPostForm(request.form, obj=post)

        if request.method == 'POST' and post_form.validate():
            post.title = post_form.title.data
            post.uri = uri
            post.content = post_form.content.data
            post.allow_guest_comments = post_form.allow_guest_comments.data
            post.save()
            flash('Your post has been updated.')

            return redirect(url_for(
                'blog.post.render', user_id=post.nereid_user.id,
                uri=post.uri
            ))
        return render_template(
            'blog_post_edit.jinja', form=post_form, post=post
        )

    @classmethod
    @login_required
    def change_state(cls, uri):
        "Change the state of the post"
        posts = cls.search([
            ('uri', '=', uri),
            ('nereid_user', '=', request.nereid_user.id),
        ])

        if not posts:
            abort(404)

        if request.method == 'POST':
            state = request.form.get('state')
            getattr(cls, str(state))(posts)

            post = posts[0]

            if request.is_xhr:
                return jsonify({
                    'success': True,
                    'message': 'Your post is now %s' % post.state
                })
            else:
                flash('Your post is now %s' % post.state)
                return redirect(url_for(
                    'blog.post.render', user_id=post.nereid_user.id,
                    uri=post.uri
                ))

    @classmethod
    def render(cls, user_id, uri):
        "Render the blog post"
        NereidUser = Pool().get('nereid.user')

        if 're_captcha_public' in CONFIG.options and request.is_guest_user:
            comment_form = GuestCommentForm(
                captcha={'ip_address': request.remote_addr}
            )
        else:
            comment_form = PostCommentForm()

        user = NereidUser(user_id)

        posts = cls.search([
            ('nereid_user', '=', user.id),
            ('uri', '=', uri),
        ])
        if not posts:
            abort(404)

        # if only one post is found then it is rendered and
        # if more than one are found then the first one is rendered
        post = posts[0]

        if not (post.state == 'Published' or
                request.nereid_user == post.nereid_user):
            abort(403)

        return render_template(
            'blog_post.jinja', post=post, comment_form=comment_form,
            poster=user
        )

    @classmethod
    def render_list(cls, user_id, page=1):
        """Render the blog posts for a user
        This should render the list of only published posts of the user
        """
        NereidUser = Pool().get('nereid.user')

        user = NereidUser(user_id)

        posts = Pagination(cls, [
            ('nereid_user', '=', user.id),
            ('state', '=', 'Published'),
        ], page, cls.per_page)

        return render_template(
            'blog_posts.jinja', posts=posts, poster=user
        )

    @classmethod
    @login_required
    def my_posts(self, page=1):
        """Render all the posts of the logged in user
        """
        posts = Pagination(self, [
            ('nereid_user', '=', request.nereid_user.id),
        ], page, self.per_page)

        return render_template('my_blog_posts.jinja', posts=posts)

    @classmethod
    def add_comment(cls, user_id, uri):
        "Add a comment"
        # Add re_captcha if the configuration has such an option and user
        # is guest
        if 're_captcha_public' in CONFIG.options and request.is_guest_user:
            comment_form = GuestCommentForm(
                request.form, captcha={'ip_address': request.remote_addr}
            )
        else:
            comment_form = PostCommentForm(request.form)

        # Comments can only be added to published posts
        posts = cls.search([
            ('nereid_user', '=', user_id),
            ('uri', '=', uri),
            ('state', '=', 'Published'),
        ], limit=1)
        if not posts:
            abort(404)

        post = posts[0]

        # If post does not allow guest comments,
        # then dont allow guest user to comment
        if not post.allow_guest_comments and request.is_guest_user:
            flash('Guests are not allowed to write comments')
            return redirect(url_for(
                'blog.post.render', user_id=post.nereid_user.id, uri=post.uri
            ))

        if request.method == 'POST' and comment_form.validate():
            cls.write([post], {
                'comments': [('create', [{
                    'nereid_user': request.nereid_user.id,
                    'name': comment_form.name.data,
                    'content': comment_form.content.data,
                }])]
            })

        if request.is_xhr:
            return jsonify({
                'success': True,
            })
        return redirect(url_for(
            'blog.post.render', user_id=post.nereid_user.id, uri=post.uri
        ))


class BlogPostComment(ModelSQL, ModelView):
    'Blog Post Comment'
    __name__ = 'blog.post.comment'
    _rec_name = 'blog_post'

    post = fields.Many2One(
        'blog.post', 'Blog Post', required=True, select=True
    )
    nereid_user = fields.Many2One('nereid.user', 'Nereid User')
    name = fields.Char(
        'Name', select=True, depends=['nereid_user'],
        states={
            'required': ~Eval('nereid_user'),
            'invisible': Bool(Eval('nereid_user')),
        }
    )
    content = fields.Text('Content', required=True)
    create_date = fields.DateTime('Create Date', readonly=True)
    is_spam = fields.Boolean('Is Spam ?')

    @staticmethod
    def default_is_spam():
        return False

    @login_required
    def manage_spam(self):
        "Mark the comment as spam"
        if not self.post.nereid_user == request.nereid_user:
            abort(403)

        self.is_spam = request.form.get('spam', False, type=bool)
        self.save()

        if request.is_xhr:
            return jsonify({
                'success': True,
            })
        else:
            flash('The comment has been updated')
            return redirect(url_for(
                'blog.post.render', user_id=self.post.nereid_user.id,
                uri=self.post.uri
            ))
