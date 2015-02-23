# builtin
import os
import sys
import cStringIO as StringIO
import argparse
import collections

# 3rd party
import web
import argh

class WebuiPage(object):
  _parser = None
  _dispatch = None
  _parsed = True
  _form_template = web.template.frender(os.path.join(os.path.dirname(__file__), "templates/input.html"), globals={'type': type})

  def __init__(self):
    self._actions = collections.OrderedDict()

    form_inputs = self.get_form_inputs()
    self._form = web.form.Form(*form_inputs)

  def GET(self):
    form = self._form()
    yield self._form_template(form)

  def multiple_args(self, nargs):
    if nargs == '?':
      return False
    if nargs == '*' or nargs == '+':
      return True
    if type(nargs) == int and nargs > 1:
      return True
    return False

  def parsable_add_value(self, argv, i):
    nargs = i.attrs.get('nargs')
    if nargs == 0:
      pass
    elif self.multiple_args(nargs):
      argv.extend(i.value)
    else:
      argv.append(i.value)

  def POST(self):
    form = self._form()

    if not form.validates():
      return self._form_template(form)

    # make sure form is filled according to input
    # TODO: accept lists. need to derive on which parameters to do this from _parser
    defs = {}
    #for action_id, action in self._actions.items():
    for action_id in form.value.keys():
      action = self._actions[action_id]
      if self.multiple_args(action.nargs):
        defs[action_id] = []
    i = web.input(**defs)
    form.fill(i)

    # get parameters without prefix
    pos_argv = []
    opt_argv = []

    for action_id in self._actions.keys():
      if not action_id in form.value.keys():
        continue

      if form[action_id].attrs.get('disposition') == 'optional':
        arg_name = "--" + action_id
        opt_argv.append(arg_name)
        self.parsable_add_value(opt_argv, form[action_id])
      elif form[action_id].attrs.get('disposition') == 'positional':
        self.parsable_add_value(pos_argv, form[action_id])

    arg = pos_argv + opt_argv
    print(arg)

    stdout = StringIO.StringIO()
    stderr = StringIO.StringIO()
    old_stderr = None
    old_stdout = None
    try:
      sys.stderr, old_stderr = stderr, sys.stderr
      sys.stdout, old_stdout = stdout, sys.stdout
      if self._parsed:
        arg = self._parser.parse_args(args=arg)
      result = self._dispatch(arg)
    finally:
      if old_stderr:
        sys.stderr = old_stderr
      if old_stdout:
        sys.stdout = old_stdout
    print(stderr.getvalue())

    return "Running: {}\nErrors: {}\nResult: {}\nOutput:\n{}".format(argv, stderr.getvalue(), result, stdout.getvalue())

#class WebuiParser(argh.ArghParser):
#  def __init__(self, *args, **kwargs):
#    super(WebuiParser, self).__init__(*args, **kwargs)
#    self.webui = Webui(self)

  def get_base_id(self, action):
    base_id = action.dest
    for opt_name in action.option_strings:
      if len(base_id) < len(opt_name):
        base_id = opt_name
    if base_id == argparse.SUPPRESS:
      base_id = "command"
    return base_id

  def get_id(self, action):
    return self.get_base_id(action).lstrip('-')

  def get_name(self, action):
    base_id = self.get_base_id(action)
    base_id = base_id.replace('_', ' ').replace('-', ' ').strip()
    return base_id[0].upper() + base_id[1:]

  def get_nargs(self, action):
    if action.nargs is None:
      return 1
    if type(action.nargs) == int:
      return action.nargs
    if action.nargs == '?' or action.nargs == '+' or action.nargs == '*':
      return action.nargs
    if hasattr(action.nargs, 'isdigit') and action.nargs.isdigit():
      return int(action.nargs)
    return 1

  def get_help(self, action):
    if not action.help:
      return ""
    return action.help % action.__dict__

  def filter_input_object(self, action):
    if isinstance(action, argparse._VersionAction):
      return True
    if isinstance(action, argparse._HelpAction):
      return True
    return False

  # TODO: maybe this function should move to be near the opposite in webuipage.POST
  def get_input_object(self, action, prefix):
    input_parameters = {}
    input_parameters['class'] = "_".join(prefix) if prefix else ""
    input_parameters['name'] = self.get_id(action)
    input_parameters['description'] = self.get_name(action)
    input_parameters['nargs'] = self.get_nargs(action)
    input_parameters['help'] = self.get_help(action)

    input_type = web.form.Textbox

    if action.choices:
      input_type = web.form.Dropdown
      input_parameters['args'] = [choice for choice in action.choices]
      if action.nargs:
        if action.nargs == '*' or action.nargs == '+' or (action.nargs.isdigit() and int(action.nargs) > 1):
          input_parameters['multiple'] = 'multiple'
          input_parameters['size'] = 4
    elif isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._StoreConstAction)):
      input_type = web.form.Checkbox
      input_parameters['checked'] = True if action.default else False
      input_parameters['value'] = action.const
    else:
      input_parameters['value'] = action.default if action.default else ""

    if isinstance(action, argparse._SubParsersAction):
      input_parameters['subparser'] = "true"
      input_parameters['onChange'] = "javascript: update_show(this);"
      input_parameters['value'] = action.choices.keys()[0]

    if len(action.option_strings):
      input_parameters['disposition'] = "optional"
      input_parameters['default'] = action.default
      # if optional argument may be present with either 1 or no parameters, the default shifts
      # to being the no parameter's value. this is mearly to properly display actual values to the user
      if action.nargs == '?':
        ipnut_parameters['value'] = action.const
    else:
      input_parameters['disposition'] = "positional"
      
    # TODO: add validators for this
    # TODO: add java validators in web form
    if action.type == int:
      input_parameters['validation_type'] = "int"
    if action.type == float:
      input_parameters['validation_type'] = "float"

    # TODO: support these actions: append, append_const, count
    self._actions[self.get_id(action)] = action
    input_object = input_type(**input_parameters)
    return input_object

  def get_form_inputs(self, parser=None, prefix=[]):
    inputs = []

    if parser is None:
      parser = self._parser

    group_actions = [group_actions
                     for group_actions in parser._mutually_exclusive_groups]
    subparser_actions = parser._subparsers
    actions = [action
               for action in parser._actions
               if action not in group_actions]

    for action in actions:
      if not self.filter_input_object(action):
        inputs.append(self.get_input_object(action, prefix))

      if isinstance(action, argparse._SubParsersAction):
        for choice_name, choice_parser in action.choices.items():
          inputs.extend(self.get_form_inputs(choice_parser, prefix + [choice_name]))

    return inputs
