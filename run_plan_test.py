#! /usr/bin/env python3
# Copyright (c) 2021 Ingvar Mattsson
# This code is provided under the MIT license, see the file named
# LICENSE for more details.


import io
import unittest

import run_plan


class TestBuildAction(unittest.TestCase):
    def test_blank_data(self):
        data = {}
        self.assertRaises(run_plan.UnknownAction, run_plan.build_action, data)

    def test_command(self):
        data = {
            "name": "name",
            "command": "/bin/false",
        }
        rv = run_plan.build_action(data)
        self.assertEqual(type(rv), run_plan.Command)
        self.assertEqual(rv.name(), "name")
        self.assertEqual(rv._command, "/bin/false")

    def test_command_and_set(self):
        data = {
            'name': 'test',
            'command': '/bin/false',
            'variable': 'testvar',
        }
        self.assertRaises(run_plan.UnknownAction, run_plan.build_action, data)

    def test_set(self):
        data = {
            "name": "name",
            "variable": "/bin/false",
            "default": '12',
        }
        rv = run_plan.build_action(data)
        self.assertEqual(type(rv), run_plan.Set)
        self.assertEqual(rv.name(), "name")
        self.assertEqual(rv._variable, "/bin/false")
        self.assertEqual(rv._default, "12")

    def test_prompt(self):
        data = {
            "name": "name",
            "text": "/bin/false",
            "prompt": '12',
        }
        rv = run_plan.build_action(data)
        self.assertEqual(type(rv), run_plan.Prompt)
        self.assertEqual(rv.name(), "name")
        self.assertEqual(rv._text, "/bin/false")
        self.assertEqual(rv._prompt, "12 ")

    def test_empty_prompt(self):
        data = {
            "name": "name",
            "text": "/bin/false",
        }
        rv = run_plan.build_action(data)
        self.assertEqual(type(rv), run_plan.Prompt)
        self.assertEqual(rv.name(), "name")
        self.assertEqual(rv._text, "/bin/false")
        self.assertEqual(rv._prompt, "Done? ")

    def test_unknown(self):
        data = {'name': "test"}
        self.assertRaises(run_plan.UnknownAction, run_plan.build_action, data)


    def test_prompt_and_set(self):
        data = {
            'name': 'test',
            'text': '/bin/false',
            'variable': 'testvar',
        }
        self.assertRaises(run_plan.UnknownAction, run_plan.build_action, data)
 
    def test_prompt_plan_propagated(self):
        data = {
            "name": "name",
            "text": "/bin/false",
            "prompt": '12',
            "plan": "9"
        }
        rv = run_plan.build_action(data)
        self.assertEqual(type(rv), run_plan.Prompt)
        self.assertEqual(rv._plan, "9")
        


class TestPlanCircularity(unittest.TestCase):
    def test_no_actions(self):
        p = run_plan.Plan()
        self.assertTrue(p._well_formed())

    def test_single_action(self):
        p = run_plan.Plan()
        a = run_plan.Action(name="test")
        p.add_action(a)
        self.assertTrue(p._well_formed())

    def test_trivial_loop(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2"])
        a2 = run_plan.Action(name= "a2", after=["a1"])
        p.add_action(a1)
        p.add_action(a2)
        self.assertFalse(p._well_formed())

    def test_broken_deps(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2"])
        a2 = run_plan.Action(name= "a2", after=["a3"])
        p.add_action(a1)
        p.add_action(a2)
        self.assertFalse(p._well_formed())

    def test_triple_loop(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2"])
        a2 = run_plan.Action(name= "a2", after=["a3"])
        a3 = run_plan.Action(name= "a3", after=["a1"])
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        self.assertFalse(p._well_formed())
        
    def test_dag(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2", "a3"])
        a2 = run_plan.Action(name= "a2", after=["a4"])
        a3 = run_plan.Action(name= "a3", after=["a4"])
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        p.add_action(a4)
        self.assertTrue(p._well_formed())

    def test_no_deps(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1")
        a2 = run_plan.Action(name= "a2")
        a3 = run_plan.Action(name= "a3")
        a4 = run_plan.Action(name= "a4")
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        p.add_action(a4)
        self.assertTrue(p._well_formed())


class TestPlanVariables(unittest.TestCase):
    def test_existing(self):
        p = run_plan.Plan()
        p.add_variable("test")
        p.set_value("test", "value")
        self.assertEqual(p._variables["test"], "value")

    def test_non_existing(self):
        p = run_plan.Plan()
        self.assertRaises(KeyError, p.set_value, "test", "value")


class TestPlanRunnable(unittest.TestCase):
    def test_simple_dependency(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name="a1")
        a2 = run_plan.Action(name="a2", after=["a1"])
        p.add_action(a1)
        p.add_action(a2)
        saw = set(p.runnable())
        want = set([a1])
        self.assertEqual(saw, want)
        self.assertFalse(p._any_failed())

    def test_no_dependency_one_failed(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name="a1")
        a2 = run_plan.Action(name="a2")
        p.add_action(a1)
        p.add_action(a2)
        a2.fail()
        saw = set(p.runnable())
        want = set([a1])
        self.assertEqual(saw, want)
        self.assertTrue(p._any_failed())

    def test_dag_all_pending(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2", "a3"])
        a2 = run_plan.Action(name= "a2", after=["a4"])
        a3 = run_plan.Action(name= "a3", after=["a4"])
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        p.add_action(a4)
        saw = set(p.runnable())
        want = set([a4])
        self.assertEqual(saw, want)

    def test_dag_a4_done(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2", "a3"])
        a2 = run_plan.Action(name= "a2", after=["a4"])
        a3 = run_plan.Action(name= "a3", after=["a4"])
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        p.add_action(a4)
        a4.done()
        saw = set(p.runnable())
        want = set([a2, a3])
        self.assertEqual(saw, want)

    def test_dag_a4_failed(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2", "a3"])
        a2 = run_plan.Action(name= "a2", after=["a4"])
        a3 = run_plan.Action(name= "a3", after=["a4"])
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        p.add_action(a4)
        a4.fail()
        saw = set(p.runnable())
        want = set()
        self.assertEqual(saw, want)

    def test_dag_a4_failed_next(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2", "a3"])
        a2 = run_plan.Action(name= "a2", after=["a4"])
        a3 = run_plan.Action(name= "a3", after=["a4"])
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        p.add_action(a4)
        a4.fail()
        saw = p._next()
        want = None
        self.assertEqual(saw, want)

    def test_dag_a4_done_a2_failed(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2", "a3"])
        a2 = run_plan.Action(name= "a2", after=["a4"])
        a3 = run_plan.Action(name= "a3", after=["a4"])
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        p.add_action(a4)
        a4.done()
        a2.fail()
        saw = set(p.runnable())
        want = set([a3])
        self.assertEqual(saw, want)


    def test_dag_a4_done_a2_done(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2", "a3"])
        a2 = run_plan.Action(name= "a2", after=["a4"])
        a3 = run_plan.Action(name= "a3", after=["a4"])
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        p.add_action(a4)
        a4.done()
        a2.done()
        saw = set(p.runnable())
        want = set([a3])
        self.assertEqual(saw, want)

    def test_dag_a4_done_a2_done2(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name= "a1", after=["a2"])
        a2 = run_plan.Action(name= "a2", after=["a4"])
        a3 = run_plan.Action(name= "a3", after=["a4"])
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a1)
        p.add_action(a2)
        p.add_action(a3)
        p.add_action(a4)
        a4.done()
        a2.done()
        saw = set(p.runnable())
        want = set([a1, a3])
        self.assertEqual(saw, want)

    def test_reset(self):
        p = run_plan.Plan()
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a4)
        a4.fail()
        p._reset_failed()
        self.assertEqual(a4.state(), "PENDING")

    def test_trivial_next(self):
        p = run_plan.Plan()
        a4 = run_plan.Action(name= "a4", after=[])
        p.add_action(a4)
        self.assertEqual(p._next(), a4)


class TestRunnableAction(unittest.TestCase):
    def test_true_pending(self):
        p = run_plan.Plan()
        a = run_plan.Command(name="test", command="true", state="PENDING", plan=p)
        a.run()
        self.assertEqual(a.state(), "DONE")
        self.assertRaises(run_plan.DoubleRun, a.run)

    def test_false_pending(self):
        p = run_plan.Plan()
        a = run_plan.Command(name="test", command="false", state="PENDING", plan=p)
        a.run()
        self.assertEqual(a.state(), "FAILED")
        self.assertRaises(run_plan.DoubleRun, a.run)

    def test_false_pending_dryrun(self):
        p = run_plan.Plan()
        a = run_plan.Command(name="test", command="false", state="PENDING", plan=p)
        saved = run_plan.DRYRUN
        run_plan.DRYRUN = True
        a.run()
        run_plan.DRYRUN = saved
        self.assertEqual(a.state(), "DONE")
        self.assertRaises(run_plan.DoubleRun, a.run)

    def test_non_existing_pending(self):
        p = run_plan.Plan()
        a = run_plan.Command(name="test", command="/slemslemslem/syzygy", state="PENDING", plan=p)
        a.run()
        self.assertEqual(a.state(), "FAILED")
        self.assertRaises(run_plan.DoubleRun, a.run)


class TestSet(unittest.TestCase):
    def test_no_registry(self):
        p = run_plan.Plan()
        a = run_plan.Set(name="test", plan=p, variable="foo", under_test=True)
        a.run()
        self.assertEqual(a.state(), "FAILED")
        self.assertRaises(run_plan.DoubleRun, a.run)

    def test_registry(self):
        p = run_plan.Plan()
        a = run_plan.Set(name="test", plan=p, variable="foo", default="bar", under_test=True)
        p.add_variable("foo")
        a.run()
        self.assertEqual(p._variables["foo"], "bar")
        self.assertEqual(a.state(), "DONE")
        self.assertRaises(run_plan.DoubleRun, a.run)


class TestPrompt(unittest.TestCase):
    def test_response(self):
        should_true = ["y", "yes", "t", "true", "YeS", "Y", "yeS", "tRuE"]
        should_false = ["n", "no", "f", "false", "slemslemslem", ""]

        for answer in should_true:
            self.assertTrue(run_plan.parse_response(answer), msg=f'input was {answer}')

        for answer in should_false:
            self.assertFalse(run_plan.parse_response(answer), msg=f'input was {answer}')

    def test_pass(self):
        p = run_plan.Plan()
        a = run_plan.Prompt(name="test", plan=p, under_test=True)
        a.run()
        self.assertEqual(a.state(), "DONE")
        self.assertRaises(run_plan.DoubleRun, a.run)
            
    def test_fail(self):
        p = run_plan.Plan()
        a = run_plan.Prompt(name="test", plan=p, under_test=True, fail=True)
        a.run()
        self.assertEqual(a.state(), "FAILED")
        self.assertRaises(run_plan.DoubleRun, a.run)


class TestRunning(unittest.TestCase):
    def test_loop(self):
        p = run_plan.Plan()
        a1 = run_plan.Action(name="a1", after=["a2"])
        a2 = run_plan.Action(name="a2", after=["a1"])
        p.add_action(a1)
        p.add_action(a2)
        self.assertRaises(run_plan.IncorrectPlan, p.run)

    def test_single_action_fail(self):
        p = run_plan.Plan()
        a1 = run_plan.Set(name="test", plan=p, variable="foo", under_test=True)
        p.add_action(a1)
        self.assertFalse(p.run())
        self.assertTrue(p._any_failed())

    def test_single_action_pass(self):
        p = run_plan.Plan()
        a1 = run_plan.Set(name="test", plan=p, variable="foo", under_test=True)
        p.add_action(a1)
        p.add_variable("foo")
        self.assertTrue(p.run())
        self.assertFalse(p._any_failed())
    

class TestPlanExpansion(unittest.TestCase):
    def test_none(self):
        p = run_plan.Plan()
        p.add_variable("foo", "bar")
        self.assertEqual(p.expand_variables("foo"), "foo")

    def test_one(self):
        p = run_plan.Plan()
        p.add_variable("foo", "bar")
        self.assertEqual(p.expand_variables("${foo}"), "bar")


class TestLoading(unittest.TestCase):
    def test_small1(self):
        p = run_plan.load_plan("testdata/plan_small1.yaml")
        self.assertEqual(len(p._variables), 0)
        self.assertEqual(len(p._actions), 1)
        self.assertEqual(p._source_file, "testdata/plan_small1.yaml")
        p.run()
        self.assertFalse(p._any_failed())

    def test_small2(self):
        p = run_plan.load_plan("testdata/plan_small2.yaml")
        self.assertEqual(len(p._variables), 0)
        self.assertEqual(len(p._actions), 1)
        self.assertEqual(p._source_file, "testdata/plan_small2.yaml")
        p.run()
        self.assertTrue(p._any_failed())

    def test_cmdvar(self):
        p = run_plan.load_plan("testdata/plan_cmdvar.yaml")
        self.assertEqual(len(p._variables), 1)
        self.assertEqual(len(p._actions), 2)
        self.assertEqual(p._source_file, "testdata/plan_cmdvar.yaml")
        p.run()
        self.assertFalse(p._any_failed())


class TestPlanSaveRestore(unittest.TestCase):
    def test_small1(self):
        p = run_plan.load_plan("testdata/plan_small1.yaml")
        want = {
            'plan': 'testdata/plan_small1.yaml',
            'variables': {},
            'actions': [{'name': 'test', 'state': 'PENDING'}],
            }
        saw = p._state()
        self.assertEqual(saw, want)

    def test_small1_fail(self):
        p = run_plan.load_plan("testdata/plan_small1.yaml")
        want = {
            'plan': 'testdata/plan_small1.yaml',
            'variables': {},
            'actions': [{'name': 'test', 'state': 'FAILED'}],
            }
        p._actions['test'].fail()
        saw = p._state()
        self.assertEqual(saw, want)

    def test_small1_done(self):
        p = run_plan.load_plan("testdata/plan_small1.yaml")
        want = {
            'plan': 'testdata/plan_small1.yaml',
            'variables': {},
            'actions': [{'name': 'test', 'state': 'DONE'}],
            }
        p._actions['test'].done()
        saw = p._state()
        self.assertEqual(saw, want)

    def test_cmdvar(self):
        p = run_plan.load_plan("testdata/plan_cmdvar.yaml")
        want = {
            'plan': 'testdata/plan_cmdvar.yaml',
            'variables': {'command': 'true'},
            'actions': [{'name': 'act1', 'state': 'PENDING'}, {'name': 'act2', 'state': 'PENDING'}],
            }
        saw = p._state()
        self.assertEqual(saw, want)
        
    def test_restore_small1(self):
        p = run_plan.restore('testdata/restore_small1.yaml')
        self.assertEqual(p._source_file, "testdata/plan_small1.yaml")
        self.assertEqual(p._variables, {})
        self.assertEqual(len(p._actions), 1)
        self.assertEqual(p._actions['test'].state(), 'FAILED')

    def test_restore_cmdvar(self):
        p = run_plan.restore('testdata/restore_cmdvar.yaml')
        self.assertEqual(p._source_file, "testdata/plan_cmdvar.yaml")
        self.assertEqual(p._variables, {'command': 'restored'})
        self.assertEqual(len(p._actions), 2)
        self.assertEqual(p._actions['act1'].state(), 'DONE')
        self.assertEqual(p._actions['act2'].state(), 'FAILED')


class TestMakeWrapped(unittest.TestCase):
    def test_no_wrap(self):
        saw = run_plan.make_wrapped("text")
        want = "\ttext"
        self.assertEqual(saw, want)

    def test_no_wrap_longer(self):
        saw = run_plan.make_wrapped("text that is still not long enough to wrap")
        want = "\ttext that is still not long enough to wrap"
        self.assertEqual(saw, want)

    def test_wrap_once(self):
        saw = run_plan.make_wrapped("This is simply a long, and frankly boring, test text that intends to tickle a line wrap.")
        want = "\tThis is simply a long, and frankly boring, test text that\n\tintends to tickle a line wrap."
        self.assertEqual(saw, want)

    def test_linebreak(self):
        saw = run_plan.make_wrapped("line 1\nline 2")
        want = "\tline 1\n\tline 2"
        self.assertEqual(saw, want)

    def test_forced_linebreak(self):
        saw = run_plan.make_wrapped("12345678901234567890123456789012345678901234567890123456789012345678901234567890")
        want = "\t1234567890123456789012345678901234567890123456789012345678901234\n\t5678901234567890"
        self.assertEqual(saw, want)


class TestGraph(unittest.TestCase):
    def test_simple_graph(self):
        plan = run_plan.load("testdata/plan_small1.yaml")
        sink = io.StringIO()
        plan.graph(sink)
        want = '''digraph {\n  "start" [ shape=circle fillcolor=gray ]\n  "end" [ shape=octagon fillcolor=gray ]\n  "test" [ shape=component fillcolor=gray ]\n  "start" -> "test"\n  "test" -> "end"\n}\n'''
        self.assertEqual(sink.getvalue(), want)
        sink.close()

    def test_restored_graph(self):
        plan = run_plan.load("testdata/restore_graph.yaml")
        sink = io.StringIO()
        plan.graph(sink)
        want = '''digraph {\n  "start" [ shape=circle fillcolor=gray ]\n  "end" [ shape=octagon fillcolor=gray ]\n  "prompter" [ shape=note fillcolor=green ]\n  "runner" [ shape=component fillcolor=red ]\n  "setvar" [ shape=polygon fillcolor=gray ]\n  "prompter" -> "runner"\n  "prompter" -> "setvar"\n  "start" -> "prompter"\n  "runner" -> "end"\n  "setvar" -> "end"\n}\n'''
        self.assertEqual(sink.getvalue(), want)
        sink.close()

    def test_graph(self):
        sink = io.StringIO()
        run_plan.graph("testdata/plan_small1.yaml", out=sink)
        want = '''digraph {\n  "start" [ shape=circle fillcolor=gray ]\n  "end" [ shape=octagon fillcolor=gray ]\n  "test" [ shape=component fillcolor=gray ]\n  "start" -> "test"\n  "test" -> "end"\n}\n'''
        self.assertEqual(sink.getvalue(), want)
        sink.close()
        
class TestSaves(unittest.TestCase):
    def test_save_graph(self):
        plan = run_plan.load("testdata/restore_graph.yaml")
        sink = io.StringIO()
        run_plan.save(plan, sink, "foo")

if __name__ == '__main__':
    unittest.main()
