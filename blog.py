# -*- coding: utf-8 -*-
"""
    blog

    Blog

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
from datetime import datetime

from wtforms import Form, TextField, TextAreaField, BooleanField, validators
from wtfrecaptcha.fields import RecaptchaField
from trytond.model import ModelSQL, ModelView, Workflow, fields
from trytond.pyson import Bool, Eval
from trytond.pool import Pool
from trytond.config import CONFIG
from nereid import (
    request, abort, render_template, login_required, url_for, redirect, flash,
    jsonify,
)
from nereid.contrib.pagination import Pagination
from nereid.helpers import slugify


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
    _name = 'blog.post'
    _description = __doc__
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

    def default_state(self):
        return 'Draft'

    def get_published_comments(self, ids, name):
        "Returns the published comments, i.e., comments not marked as spam"
        comment_obj = Pool().get('blog.post.comment')

        res = {}
        for post in self.browse(ids):
            comments = comment_obj.search([
                ('post', '=', post.id),
                ('is_spam', '=', False)
            ])
            res[post.id] = comments
        return res

    def __init__(self):
        super(BlogPost, self).__init__()
        self._sql_constraints += [
            (
                'nereid_user_uri_uniq', 'UNIQUE(nereid_user, uri)',
                'URI must be unique for a nereid user'
            ),
        ]
        self._transitions |= set((
            ('Draft', 'Published'),
            ('Published', 'Draft'),
            ('Draft', 'Archived'),
            ('Published', 'Archived'),
            ('Archived', 'Draft'),
        ))
        self._buttons.update({
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
        self.per_page = 10

    @ModelView.button
    @Workflow.transition('Draft')
    def draft(self, ids):
        pass

    @ModelView.button
    @Workflow.transition('Published')
    def publish(self, ids):
        self.write(ids, {'post_date': datetime.utcnow()})

    @ModelView.button
    @Workflow.transition('Archived')
    def archive(self, ids):
        pass

    def on_change_with_uri(self, vals):
        if vals.get('title'):
            if not vals.get('uri'):
                vals['uri'] = slugify(vals['title'])
            return vals['uri']
        else:
            return {}

    @login_required
    def new_post(self):
        """Create a new post
        """
        post_form = BlogPostForm(request.form)

        if request.method == 'POST' and post_form.validate():
            # Search for a post with same uri
            uri = post_form.uri.data or slugify(post_form.title.data)
            existing_post = self.search([
                ('uri', '=', uri),
                ('nereid_user', '=', request.nereid_user.id),
            ])
            if existing_post:
                flash(
                    'A post with same URL exists. '
                    'Please change the title or modify the URL'
                )
                return redirect(request.referrer)
            post_id = self.create({
                'title': post_form.title.data,
                'uri': uri,
                'content': post_form.content.data,
                'nereid_user': request.nereid_user.id,
                'allow_guest_comments': post_form.allow_guest_comments.data,
            })
            if post_form.publish.data:
                self.publish([post_id])
                flash('Your post has been published.')
            else:
                flash('Your post has been saved.')

            post = self.browse(post_id)

            return redirect(url_for(
                'blog.post.render', user_id=post.nereid_user.id,
                uri=post.uri
            ))
        return render_template('blog_post_form.jinja', form=post_form)

    @login_required
    def edit_post(self, uri):
        """Edit an existing post
        """
        # Search for a post with same uri
        post_ids = self.search([
            ('uri', '=', uri),
            ('nereid_user', '=', request.nereid_user.id),
        ])

        if not post_ids:
            abort(404)

        post = self.browse(post_ids[0])
        post_form = BlogPostForm(request.form, obj=post)

        if request.method == 'POST' and post_form.validate():
            self.write(post.id, {
                'title': post_form.title.data,
                'uri': uri,
                'content': post_form.content.data,
                'allow_guest_comments': post_form.allow_guest_comments.data,
            })
            flash('Your post has been updated.')

            # Reload the browse record
            post = self.browse(post.id)

            return redirect(url_for(
                'blog.post.render', user_id=post.nereid_user.id,
                uri=post.uri
            ))
        return render_template(
            'blog_post_edit.jinja', form=post_form, post=post
        )

    @login_required
    def change_state(self, uri):
        "Change the state of the post"
        post_ids = self.search([
            ('uri', '=', uri),
            ('nereid_user', '=', request.nereid_user.id),
        ])

        if not post_ids:
            abort(404)

        if request.method == 'POST':
            state = request.form.get('state')
            getattr(self, str(state))(post_ids)

            post = self.browse(post_ids[0])

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

    def render(self, user_id, uri):
        "Render the blog post"
        nereid_user_obj = Pool().get('nereid.user')

        if 're_captcha_public' in CONFIG.options and request.is_guest_user:
            comment_form = GuestCommentForm(
                captcha={'ip_address': request.remote_addr}
            )
        else:
            comment_form = PostCommentForm()

        user = nereid_user_obj.browse(user_id)

        post_ids = self.search([
            ('nereid_user', '=', user.id),
            ('uri', '=', uri),
        ])
        if not post_ids:
            abort(404)

        # if only one post is found then it is rendered and
        # if more than one are found then the first one is rendered
        post = self.browse(post_ids[0])

        if not (
            post.state == 'Published' or
            request.nereid_user == post.nereid_user
        ):
            abort(403)

        return render_template(
            'blog_post.jinja', post=post, comment_form=comment_form,
            poster=user
        )

    def render_list(self, user_id, page=1):
        """Render the blog posts for a user
        This should render the list of only published posts of the user
        """
        nereid_user_obj = Pool().get('nereid.user')

        user = nereid_user_obj.browse(user_id)

        posts = Pagination(self, [
            ('nereid_user', '=', user.id),
            ('state', '=', 'Published'),
        ], page, self.per_page)

        return render_template(
            'blog_posts.jinja', posts=posts, poster=user
        )

    @login_required
    def my_posts(self, page=1):
        """Render all the posts of the logged in user
        """
        posts = Pagination(self, [
            ('nereid_user', '=', request.nereid_user.id),
        ], page, self.per_page)

        return render_template('my_blog_posts.jinja', posts=posts)

    def add_comment(self, user_id, uri):
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
        post_ids = self.search([
            ('nereid_user', '=', user_id),
            ('uri', '=', uri),
            ('state', '=', 'Published'),
        ], limit=1)
        if not post_ids:
            abort(404)

        post = self.browse(post_ids[0])

        # If post does not allow guest comments,
        # then dont allow guest user to comment
        if not post.allow_guest_comments and request.is_guest_user:
            flash('Guests are not allowed to write comments')
            return redirect(url_for(
                'blog.post.render', user_id=post.nereid_user.id, uri=post.uri
            ))

        if request.method == 'POST' and comment_form.validate():
            self.write(post.id, {
                'comments': [('create', {
                    'nereid_user': request.nereid_user.id,
                    'name': comment_form.name.data,
                    'content': comment_form.content.data,
                })]
            })

        if request.is_xhr:
            return jsonify({
                'success': True,
            })
        return redirect(url_for(
            'blog.post.render', user_id=post.nereid_user.id, uri=post.uri
        ))

BlogPost()


class BlogPostComment(ModelSQL, ModelView):
    'Blog Post Comment'
    _name = 'blog.post.comment'
    _description = __doc__
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

    def default_is_spam(self):
        return False

    @login_required
    def manage_spam(self, comment_id):
        "Mark the comment as spam"
        comment = self.browse(comment_id)

        if not comment:
            abort(404)

        if not comment.post.nereid_user == request.nereid_user:
            abort(403)

        self.write(comment.id, {
            'is_spam': request.form.get('spam', False, type=bool)
        })

        if request.is_xhr:
            return jsonify({
                'success': True,
            })
        else:
            flash('The comment has been updated')
            return redirect(url_for(
                'blog.post.render', user_id=comment.post.nereid_user.id,
                uri=comment.post.uri
            ))

BlogPostComment()
