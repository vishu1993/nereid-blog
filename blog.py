# -*- coding: utf-8 -*-
"""
    blog

    Blog

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import warnings
from datetime import datetime

from wtforms import Form, TextField, TextAreaField, BooleanField, validators
from wtforms.validators import ValidationError
from flask_wtf import RecaptchaField
from trytond.model import ModelSQL, ModelView, Workflow, fields
from trytond.pyson import Bool, Eval
from trytond.pool import Pool, PoolMeta
from trytond.config import CONFIG
from trytond.transaction import Transaction

from nereid import (
    request, abort, render_template, login_required, url_for, redirect, flash,
    jsonify, current_user, route
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

    def validate_uri(self, field):
        BlogPost = Pool().get('blog.post')

        if not field.data and not self.data['title']:
            return
        field.process_data(slugify(field.data or self.data['title']))
        domain = [('uri', '=', field.data)]
        if Transaction().context.get('blog_id'):
            # blog_id in context means editing form
            domain.append(('id', '!=', Transaction().context['blog_id']))
        if BlogPost.search(domain):
            raise ValidationError(
                'Blog with the same URL exists. Please change title or modify'
            )


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

    def serialize(self, purpose=None):
        '''
        Return serializable dict for `self`
        '''
        res = {
            'id': self.id,
            'title': self.title,
            'uri': self.uri,
            'post_date': self.post_date.isoformat()
                if self.post_date else None,
            'allow_guest_comments': self.allow_guest_comments,
            'state': self.state,
            'nereid_user': self.nereid_user.id,
            'displayName': self.rec_name,
        }
        if purpose == 'activity_stream':
            res['objectType'] = self.__name__
            res['content'] = self.content[0:50]
        else:
            res['content'] = self.content

        return res

    @classmethod
    @route('/post/-new', methods=['GET', 'POST'])
    @login_required
    def new_post(cls):
        """Create a new post
        """
        post_form = BlogPostForm(request.form)

        if request.method == 'POST' and post_form.validate():
            post, = cls.create([{
                'title': post_form.title.data,
                'uri': post_form.uri.data,
                'content': post_form.content.data,
                'nereid_user': request.nereid_user.id,
                'allow_guest_comments': post_form.allow_guest_comments.data,
            }])
            if post_form.publish.data:
                cls.publish([post])
                flash('Your post has been published.')
            else:
                flash('Your post has been saved.')

            if request.is_xhr:
                return jsonify(success=True, item=post.serialize())
            return redirect(url_for(
                'blog.post.render', user_id=post.nereid_user.id,
                uri=post.uri
            ))
        if request.is_xhr:
            return jsonify(
                success=request.method != 'POST',  # False for POST, else True
                errors=post_form.errors or None,
            )
        return render_template('blog_post_form.jinja', form=post_form)

    @classmethod
    def get_post_for_uri(cls, uri):
        """
            Return post for current user and uri
        """
        posts = cls.search([
            ('uri', '=', uri),
            ('nereid_user', '=', request.nereid_user.id),
        ])

        if not posts:
            abort(404)

        return posts[0]

    @classmethod
    @route('/post/<uri>/-edit', methods=['GET', 'POST'])
    @login_required
    def edit_post_for_uri(cls, uri):
        """
            Edit an existing post from uri
        """
        return cls.get_post_for_uri(uri).edit_post()

    @route('/post/<int:active_id>/-edit', methods=['GET', 'POST'])
    @login_required
    def edit_post(self):
        """
            Edit an existing post
        """
        if self.nereid_user != request.nereid_user:
            abort(404)

        # Search for a post with same uri
        post_form = BlogPostForm(request.form, obj=self)

        with Transaction().set_context(blog_id=self.id):
            if request.method == 'POST' and post_form.validate():
                self.title = post_form.title.data
                self.content = post_form.content.data
                self.allow_guest_comments = post_form.allow_guest_comments.data
                self.save()
                flash('Your post has been updated.')
                if request.is_xhr:
                    return jsonify(success=True, item=self.serialize())
                return redirect(url_for(
                    'blog.post.render', user_id=self.nereid_user.id,
                    uri=self.uri
                ))
        if request.is_xhr:
            return jsonify(
                success=request.method != 'POST',  # False for POST, else True
                errors=post_form.errors or None,
            )
        return render_template(
            'blog_post_edit.jinja', form=post_form, post=self
        )

    @classmethod
    @route('/post/<uri>/-change-state', methods=['POST'])
    @login_required
    def change_state_for_uri(cls, uri):
        "Change the state of the post for uri"

        return cls.get_post_for_uri(uri).change_state()

    @route('/post/<int:active_id>/-change-state', methods=['POST'])
    @login_required
    def change_state(self):
        "Change the state of the post"
        if self.nereid_user != request.nereid_user:
            abort(404)

        state = request.form.get('state')
        assert(state in ('publish', 'archive', 'draft'))
        getattr(self, str(state))([self])

        if request.is_xhr:
            return jsonify({
                'success': True,
                'new_state': self.state,
            })
        flash('Your post is now %s' % self.state)
        return redirect(url_for(
            'blog.post.render', user_id=self.nereid_user.id,
            uri=self.uri
        ))

    @classmethod
    @route('/post/<uri>/-change-guest-permission', methods=['POST'])
    @login_required
    def change_guest_permission_for_uri(cls, uri):
        "Change guest permission for uri"

        return cls.get_post_for_uri(uri).change_guest_permission()

    @route('/post/<int:active_id>/-change-guest-permission', methods=['POST'])
    @login_required
    def change_guest_permission(self):
        "Change guest permission of the post"
        if self.nereid_user != request.nereid_user:
            abort(404)

        allow_guest_comment = request.form.get('allow_guest_comments')
        self.allow_guest_comments = True if allow_guest_comment == 'true' \
            else False
        self.save()

        if request.is_xhr:
            return jsonify({
                'success': True,
            })
        return redirect(url_for(
            'blog.post.render', user_id=self.nereid_user.id,
            uri=self.uri
        ))

    @classmethod
    @route('/post/<int:user_id>/<uri>')
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

        if request.is_xhr:
            return jsonify(post.serialize())
        return render_template(
            'blog_post.jinja', post=post, comment_form=comment_form,
            poster=user
        )

    @classmethod
    @route('/posts/<int:user_id>')
    @route('/posts/<int:user_id>/<int:page>')
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
        if request.is_xhr:
            return jsonify({
                'has_next': posts.has_next,
                'has_prev': posts.has_prev,
                'items': [post.serialize() for post in posts],
            })

        return render_template(
            'blog_posts.jinja', posts=posts, poster=user
        )

    @classmethod
    @route('/posts/-my')
    @route('/posts/-my/<int:page>')
    @login_required
    def my_posts(self, page=1):
        """Render all the posts of the logged in user
        """
        posts = Pagination(self, [
            ('nereid_user', '=', request.nereid_user.id),
        ], page, self.per_page)
        if request.is_xhr:
            return jsonify({
                'has_next': posts.has_next,
                'has_prev': posts.has_prev,
                'items': [post.serialize() for post in posts],
            })

        return render_template('my_blog_posts.jinja', posts=posts)

    @classmethod
    @route('/post/<int:user_id>/<uri>/-comment', methods=['GET', 'POST'])
    def add_comment(cls, user_id, uri):
        '''
        Add a comment
        '''
        warnings.warn(
            "add_comment will be deprecated in 3.2 use render_comment instead.",
            DeprecationWarning,
        )
        # Comments can only be added to published posts
        posts = cls.search([
            ('nereid_user', '=', user_id),
            ('uri', '=', uri),
        ], limit=1)
        if not posts:
            abort(404)

        return posts[0].render_comments()

    @route('/post/<int:active_id>/-comment', methods=['GET', 'POST'])
    def render_comments(self):
        """
        Render comments

        GET: Return json of all the comments of this post.
        POST: Create new comment for this post.
        """
        if self.state != 'Published':
            abort(404)

        # Add re_captcha if the configuration has such an option and user
        # is guest
        if 're_captcha_public' in CONFIG.options and request.is_guest_user:
            comment_form = GuestCommentForm(
                request.form, captcha={'ip_address': request.remote_addr}
            )
        else:
            comment_form = PostCommentForm(request.form)

        if request.method == 'GET':
            if self.nereid_user == request.nereid_user:
                return jsonify(comments=[
                    comment.serialize() for comment in self.comments
                ])
            return jsonify(comments=[
                comment.serialize() for comment in self.comments
                if not comment.is_spam
            ])

        # If post does not allow guest comments,
        # then dont allow guest user to comment
        if not self.allow_guest_comments and request.is_guest_user:
            flash('Guests are not allowed to write comments')
            if request.is_xhr:
                return jsonify(
                    success=False,
                    errors=['Guests are not allowed to write comments']
                )
            return redirect(url_for(
                'blog.post.render', user_id=self.nereid_user.id, uri=self.uri
            ))

        if request.method == 'POST' and comment_form.validate():
            self.write([self], {
                'comments': [('create', [{
                    'nereid_user': current_user.id
                        if not current_user.is_anonymous() else None,
                    'name': current_user.display_name
                        if not current_user.is_anonymous()
                            else comment_form.name.data,
                    'content': comment_form.content.data,
                }])]
            })

        if request.is_xhr:
            return jsonify(success=True) if comment_form.validate() \
                else jsonify(success=False, errors=comment_form.errors)
        return redirect(url_for(
            'blog.post.render', user_id=self.nereid_user.id, uri=self.uri
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

    def serialize(self):
        """
        Return Serializable dict. for this comment.
        """
        return {
            'post': self.post.id,
            'id': self.id,
            'nereid_user': self.nereid_user.id if self.nereid_user else None,
            'name': self.name,
            'content': self.content,
            'create_date': self.create_date.isoformat(),
            'is_spam': self.is_spam,
        }

    @route('/comment/<int:active_id>/-spam', methods=['POST'])
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
