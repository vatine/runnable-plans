#! /usr/bin/env python3
# Copyright (c) 2021 Ingvar Mattsson
# This code is provided under the MIT license, see the file named
# LICENSE for more details.

"""A program to execute plans

This program is used to execute (for some value of execute) a
procedure that is in the process of being converted from manual to
fully automated.

To do that, it relies on plans. Plans are YAML files that are
essentially interpreted in a special way. This allows the program to
interactively ask the user for information, prompt the user to do
things, run external commands on behalf of the user and similar
things.

The program will try its best to randomise the order of "steps that do
not explicitly depend on each other". The purpose of this is to tease
out any actual dependency that may exist between the steps. so that a
fully automated solution takes care of handling them.

A fuller explanation of the plan file format follows below.

variables:
  - <variable>
  ...
actions:
 - <action>
  ...

<variable>
name: variable-name
value: optional initial value

<action>
name: action-name
text: explanatory text
after: # optional
  - <action name>
  ...

For "prompt" actions:
prompt: question 

For "command" actions:
command: shell-command

For "set variable" actions:
variable: <variable name>
default: <default value, optional> 
"""

import argparse
import random
import subprocess
import sys
import tempfile
import yaml

STATES = ["PENDING", "DONE", "FAILED"]
DRYRUN = False


class UnknownAction(Exception):
    pass


class IncorrectPlan(Exception):
    pass


class DoubleRun(Exception):
    pass



class Plan:
    def __init__(self, source_file=None):
        self._source_file = source_file
        self._actions = {}
        self._variables = {}

    def restore(self, data):
        """After having loaded a plan, apply a "save" state."""
        for action in data['actions']:
            name = action['name']
            state = action['state']
            obj = self._actions[name]
            if state == "DONE":
                obj.done()
            elif state == "FAILED":
                obj.fail()

        for name in data['variables']:
            self.set_value(name, data['variables'][name])

    def runnable(self):
        """
        Return a list of runnable actions.
        
        This means all actions that:
        1) have neither completed successfully nor failed
        2) who have "no preconditions" nor "at least one failed precondition".
        """

        rv = []
        for name in self._actions:
            candidate = self._actions[name]
            if candidate.state() != "PENDING":
                # This is either DONE or FAILED, skip to next iteration
                continue
            can_run = True
            for precondition in candidate.preconditions():
                if self._actions[precondition].state() != "DONE":
                    can_run = False

            if can_run:
                rv.append(candidate)
        return rv

    def _next(self):
        """Return the next action to perform.

        We intentionally pick a random element, to comensate for Python3 
        having deterministic iteration of hash tables.
        """

        actions = self.runnable()
        if actions:
            return random.choice(actions)
        return None

    def _any_failed(self):
        """Return True if any action has failed."""
        for name in self._actions:
            candidate = self._actions[name]
            if candidate.state() == "FAILED":
                return True
        return False

    def _well_formed(self):
        """Return True if a plan is well-formed.

        This essentially means that there are no dependency loops
        among the plan's actions. If there are any, an exception will
        be raised.
        """
        try:
            for name in self._actions:
                candidate = self._actions[name]
                if self._circular(name, candidate.preconditions()):
                    return False
        except KeyError:
            return False

        return True

    def _circular(self, start, names):
        for name in names:
            if name == start:
                return True
            candidate = self._actions[name]
            problematic = self._circular(start, candidate.preconditions())
            if problematic:
                return True
        return False

    def add_action(self, action):
        self._actions[action.name()] = action

    def add_variable(self, name, value=None):
        self._variables[name] = value

    def set_value(self, name, value):
        if name not in self._variables:
            raise KeyError(f'Unknown variable {name}.')
        self._variables[name] = value

    def _reset_failed(self):
        for name in self._actions:
            action = self._actions[name]
            if action.state() == "FAILED":
                action.reset()
        
    def run(self):
        if not self._well_formed():
            raise IncorrectPlan("The plan is inconsistent.")
        self._reset_failed()

        next = self._next()
        while next is not None:
            next.run()
            next = self._next()

        return not self._any_failed()

    def expand_variables(self, data):
        try:
            start = data.index("${")
            end = data.index("}", start)
            var = data[start+2:end]
            subst = ""
            if var in self._variables:
                subst = self._variables[var]
            new_data = data[:start]+subst+data[end+1:]
            return self.expand_variables(new_data)
        except ValueError:
            return data
        except AttributeError:
            return ""

    def _state(self):
        """Return a dict describing the current state of the plan."""
        rv = {}

        rv['plan'] = self._source_file
        acts = []
        for name in self._actions:
            action = self._actions[name]
            acts.append({'name': action.name(), 'state': action.state()})
        rv['actions'] = acts
        rv['variables'] = self._variables

        return rv

    def save(self, f):
        yaml.dump(self._state(), stream=f)


    def graph(self, stream):
        stream.write("digraph {\n")
        stream.write('  "start" [ shape=circle fillcolor=gray ]\n')
        stream.write('  "end" [ shape=octagon fillcolor=gray ]\n')
        for name in self._actions:
            self._actions[name].node(stream)
        for name in self._actions:
            self._actions[name].deps(stream)
        for name in self._actions:
            stream.write(f'  "start" -> "{name}"\n')
            stream.write(f'  "{name}" -> "end"\n')
        stream.write("}\n")
        

class Action:
    def __init__(self, plan=None, name=None, state=None, after=None, under_test=False, **kwargs):
        self._name = name
        self._state = "PENDING"
        self._plan = plan
        self._under_test = under_test
        if state is not None:
            self._state = state
        if after is not None:
            self._after = after
        else:
            self._after = []

    def _header(self, header):
        if not self._is_pending():
            raise DoubleRun(f'Command {self._name} executed twice')
        if self._under_test:
            return
        print(f'---[ {self._name} ] ---------------------')
        if header:
            print(header)

    def name(self):
        return self._name

    def _is_pending(self):
        return self._state == "PENDING"
        
    def run(self):

        """Perform the intended run-time action. 

        This is by necessity different for each action type. The base
        class simply raises a NotImplementedError exception.

        """
        raise NotImplementedError

    def state(self):
        return self._state

    def preconditions(self):
        return self._after

    def done(self):
        self._state = "DONE"

    def fail(self):
        self._state = "FAILED"

    def _color(self):
        if self._state == "DONE":
            return "green"
        if self._state == "FAILED":
            return "red"
        return "gray"
    
    def reset(self):
        self._state = "PENDING"

    def node(self, stream):
        raise NotImplementedError

    def deps(self, stream):
        for node in self._after:
            stream.write(f'  "{node}" -> "{self._name}"\n')


class Prompt(Action):
    def __init__(self, text=None, prompt=None, fail=False, **kwargs):
        super().__init__(**kwargs)
        if prompt is None:
            prompt = "Done?"
        self._prompt = prompt + ' '
        self._text = text
        self._fail = fail

    def _get_answer(self):
        if self._under_test:
            return not self._fail
        response = input(self._prompt)
        return parse_response(response)

    def run(self):
        self._header("")
        print(make_wrapped(self._plan.expand_variables(self._text)))
        if self._get_answer():
            self.done()
        else:
            self.fail()

    def node(self, stream):
        stream.write(f' "{self._name}" [ shape=note fillcolor={self._color()} ]\n')


class Set(Action):
    def __init__(self, variable=None, default=None, **kwargs):
        self._variable = variable
        self._default = default
        if self._default is None:
            self._default = ""
        super().__init__(**kwargs)

    def run(self):
        self._header(f'\tSetting the value of variable {self._variable}')
        default = self._plan.expand_variables(self._default)
        new_value = default
        if not self._under_test:
            answer = input(f'Provide a value for {self._variable}\n (just pressing enter defaults it to {default}) ')
            if answer != "":
                new_value = answer
        try:
            self._plan.set_value(self._variable, new_value)
            self.done()
        except KeyError:
            self.fail()

    def node(self, stream):
        stream.write(f' "{self._name}" [ shape=polygon fillcolor={self._color()} ]\n')


class Command(Action):
    def __init__(self, command=None, **kwargs):
        self._command = command
        super().__init__(**kwargs)

    def run(self):
        if not self._is_pending():
            raise DoubleRun(f'Command {self._name} executed twice')
        cmd = self._plan.expand_variables(self._command)
        try:
            self._header("\tRunning the following command:\n\t\t"+cmd)
            if DRYRUN:
                self._dryrun()
                return
            rv = subprocess.call(cmd.split())
            if rv == 0:
                self.done()
            else:
                self.fail()
        except FileNotFoundError:
            self.fail()

    def _dryrun(self):
        print('\t\tAction not done, because this is a dry-run')
        self.done()

    def node(self, stream):
        stream.write(f' "{self._name}" [ shape=component fillcolor={self._color()} ]\n')


def build_action(data):
    """Build an Action.

    Builds an action based on the contents of an input dict.  If it is
    not possible to determine what type of action should be built,
    raise a custom exception, detailing what the problem is.
    """

    action_type = None

    if 'name' not in data:
        raise UnknownAction('No name for action')
    
    if 'command' in data:
        action_type = Command

    if ('variable' in data) or ('default' in data):
        if action_type is not None:
            raise UnknownAction('Action %s seems to be a mix of Command and Set' % data['name'])
        action_type = Set

    if ('text' in data) or ('prompt' in data):
        if action_type is not None:
            raise UnknownAction('Action %s seems to be a mix of Prompt, and one or more of Command or Set' % data['name'])
        action_type = Prompt

    if action_type is None:
        raise UnknownAction('Unknown action, keys are %s' % (data.keys(),))

    return action_type(**data)


def parse_response(data):
    """Parse a "did this succeed" from a user. Only takes positive "yes" as OK."""

    data = data.lower()

    return data in {'t', 'true', 'y', 'yes'}


def load_plan(filename):
    """Loads a plan from a file."""

    rv = Plan(source_file=filename)
    
    with open(filename) as f:
        data = yaml.safe_load(f)

        for var in data.get('variables', []):
            rv.add_variable(var['name'], var.get('value', ''))

        for act in data.get('actions', []):
            act['plan'] = rv
            rv.add_action(build_action(act))

    return rv


def make_wrapped(text):
    """Wrap text so it does not wrap on a 80-column display, with extra tabs."""

    outbuf = ['\t']
    pos = 8
    last_space = -1
    for ch in text:
        outbuf.append(ch)
        pos = pos + 1
        if ch == '\n':
            outbuf.append('\t')
            pos = 8
        if ch == ' ':
            last_space = len(outbuf)-1

        if pos >= 72:
            if last_space == -1:
                outbuf.append("\n\t")
                pos = 8
            else:
                outbuf[last_space] = "\n\t"
                pos = 8
                last_space = -1

    return ''.join(outbuf).rstrip()


def restore(filename):
    """Load a save-file and return the resoted plan."""
    with open(filename) as f:
        data = yaml.safe_load(f)

        plan = load_plan(data['plan'])
        plan.restore(data)

    return plan


def load(filename):
    with open(filename) as f:
        data = yaml.safe_load(f)
        if 'plan' in data:
            return restore(filename)
        return load_plan(filename)

def run(filename):
    plan = load_plan(filename)
    if plan.run():
        # Everything is OK.
        return

    with tempfile.NamedTemporaryFile(delete=False) as f:
        plan.save(f)

        print()
        print()
        print(f"Execution failed, you can resume by running\n\trun_plan.py resume {f.name}")

def resume(filename):
    plan = load_restore(filename)
    if plan.run():
        # Everything is OK.
        return

    with tempfile.NamedTemporaryFile(delete=False) as f:
        plan.save(f)

        print()
        print()
        print(f"Execution failed, you can resume by running\n\trun_plan.py resume {f.name}")


def graph(filename ,out=sys.stdout):
    plan = load(filename)
    plan.graph(out)


def main():
    global DRYRUN
    
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers()

    runcmd = subs.add_parser("run")
    runcmd.set_defaults(cmd=run)
    runcmd.add_argument('--dryrun', default=False, action='store_true')
    runcmd.add_argument("file", nargs=1)

    resumecmd = subs.add_parser("resume")
    resumecmd.set_defaults(cmd=resume)
    resumecmd.add_argument("file", nargs=1)

    graphcmd = subs.add_parser("graph")
    graphcmd.set_defaults(cmd=graph)
    graphcmd.add_argument("file", nargs=1)
    

    args = parser.parse_args()
    if args.cmd == run:
        if args.dryrun:
            DRYRUN = True
    args.cmd(args.file[0])


if __name__ == '__main__':
    main()
