# -*- coding: UTF-8 -*-
# -- FILE: features/steps/my_steps.py

from __future__ import print_function
from behave import when
import os
import sys

# -- VARIANT 1:
@when(u'I click on ${environment_variable:w}')
def step_impl(context, environment_variable):
      env_value = os.environ.get(environment_variable, None)
      if env_value is None:
            raise LookupError(
                f"Environment variable '{environment_variable}' is undefined")
      print(
          f"USE ENVIRONMENT-VAR: {environment_variable} = {env_value}  (variant 1)"
      )


# -- VARIANT 2: Use type converter
from behave import register_type
import parse

@parse.with_pattern(r"\$\w+")  # -- ONLY FOR: $WORD
def parse_environment_var(text):
    assert text.startswith("$")
    env_name = text[1:]
    env_value = os.environ.get(env_name, None)
    return (env_name, env_value)

register_type(EnvironmentVar=parse_environment_var)

@when(u'I use the environment variable {environment_variable:EnvironmentVar}')
def step_impl(context, environment_variable):
      env_name, env_value = environment_variable
      if env_value is None:
            raise LookupError(f"Environment variable '{env_name}' is undefined")
      print(f"USE ENVIRONMENT-VAR: {env_name} = {env_value}  (variant 2)")

