# -*- coding: utf-8 -*-
"""
    blog

    Blog

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
from datetime import datetime

from wtforms import Form, TextField, TextAreaField, BooleanField, validators
from trytond.model import ModelSQL, ModelView, Workflow, fields
from trytond.pyson import Bool, Eval
from nereid import (request, abort, render_template, login_required, url_for,
    redirect, flash, jsonify)
from nereid.helpers import slugify


STATES = {'readonly': Eval('state') != 'Draft',}


class BlogPostForm(Form):
    "Blog Post Form"
    title = TextField('Title', [validators.Required(),])
    uri = TextField('URL')
    content = TextAreaField('Content', [validators.Required(),])
    publish = BooleanField('Publish', default=False)


class PostCommentForm(Form):
    "Post Comment Form"
    name = TextField('Name', [validators.Required(),])
    content = TextAreaField('Content', [validators.Required(),])


class BlogPost(Workflow, ModelSQL, ModelView):
    'Blog Post'
    _name = 'blog.post'
    _description = __doc__
    _rec_name = 'title'

    title = fields.Char('Title', required=True, select=True,
        states=STATES
    )
    uri = fields.Char('URI', required=True, select=True,
        on_change_with=['title', 'uri'], states=STATES
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
    state = fields.Selection([
        ('Draft', 'Draft'),
        ('Published', 'Published'),
        ('Archived', 'Archived'),
    ], 'State', readonly=True)

    def default_state(self):
        return 'Draft'

    def __init__(self):
        super(BlogPost, self).__init__()
        self._sql_constraints += [(
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
            post_id = self.create({
                'title': post_form.title.data,
                'content': post_form.content.data,
                'state': 'Published' if post_form.publish.data else 'Draft'
            })
            if post_form.publish.data:
                flash('Your post has been published.')
            else:
                flash('Your post has been saved.')

            return redirect(url_for(
                'blog.post.render', post_id=post_id
            ))
        return render_template('blog_post_form.jinja', form=post_form)

    def render(self, post_id):
        "Render the blog post"
        post = self.browse(post_id)
        if not post:
            abort(404)

        return render_template('blog_post.jinja', post=post)

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
    name = fields.Char('Name', select=True, depends=['nereid_user'],
        states={
            'required': ~Eval('nereid_user'),
            'invisible': Bool(Eval('nereid_user')),
    })
    content = fields.Text('Content', required=True)
    create_date = fields.DateTime('Create Date', readonly=True)

BlogPostComment()
