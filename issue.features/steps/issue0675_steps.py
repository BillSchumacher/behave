# -*- coding: UTF-8 -*-
# issue #678: Support tags with commas and semicolons.

from __future__ import absolute_import, print_function
import os.path
from behave import given, when, then
import six

@given(u'I create a symlink from "{source}" to "{dest}"')
@when(u'I create a symlink from "{source}" to "{dest}"')
def step_create_symlink(context, source, dest):
    print(f"symlink: {source} -> {dest}")
    # assert os.path.exists(source), "FILE-NOT-FOUND: source=%s" % source

    # -- VARIANT 1:
    text = u'When I run "ln -s {source} {dest}"'.format(source=source, dest=dest)
    context.execute_steps(text)

