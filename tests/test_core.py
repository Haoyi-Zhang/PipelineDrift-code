import copy
import unittest
from drift_contracts import Contract, analyze, verify
from drift_contracts.model import run
from drift_contracts.oracle import oracle
from drift_contracts.cases import named_examples, parameters, from_parameters


class CoreTests(unittest.TestCase):
    def example(self, name):
        ex = next(e for e in named_examples() if e['case'] == name)
        return Contract.from_dict(ex['contract'])

    def test_all_named_scenarios(self):
        for ex in named_examples():
            with self.subTest(case=ex['case']):
                c = Contract.from_dict(ex['contract'])
                a = analyze(c)
                self.assertEqual(a['admissible'], ex['expected_admissible'])
                self.assertTrue(verify(c, a['certificate']))

    def test_future_only_negative_control(self):
        c = self.example('case-d')
        a = analyze(c)
        self.assertTrue(a['current_only_admissible'])
        self.assertFalse(a['admissible'])
        self.assertEqual(a['certificate']['cost'], 3)
        self.assertEqual(oracle(c)['minimum_cost'], 3)

    def test_state_equality_false_rejection(self):
        a = analyze(self.example('case-e'))
        self.assertTrue(a['admissible'])
        self.assertFalse(a['state_equality_admissible'])

    def test_joint_label_marginals(self):
        ex = next(e for e in named_examples() if e['case'] == 'case-c')
        self.assertEqual(ex['per_function_histograms'][0], ex['per_function_histograms'][1])
        self.assertNotEqual(ex['disagreement_counts'][0], ex['disagreement_counts'][1])
        a = analyze(Contract.from_dict(ex['contract']))
        self.assertEqual(a['certificate']['history_left'], [0])
        self.assertEqual(a['certificate']['history_right'], [1])
        self.assertEqual(a['certificate']['cost'], 2)

    def test_reset_negative_control(self):
        c = self.example('case-h')
        cert = analyze(c)['certificate']
        self.assertTrue(verify(c, cert))
        cert['map'] = [0,0,0]
        self.assertFalse(verify(c, cert))
        q = run(c.history, c.initial_target, [1])
        self.assertNotEqual(c.output[run(c.future, q, [1])], c.output[run(c.future, 0, [1])])

    def test_unreachable_states(self):
        c = Contract(((0,), (1,)), ((0,), (1,)), ((0,), (1,)), (0,1))
        a = analyze(c)
        self.assertTrue(a['admissible'])
        self.assertIsNone(a['certificate']['map'][1])
        self.assertTrue(verify(c, a['certificate']))

    def test_different_alphabets_and_nonzero_initial_states(self):
        c = Contract(((0,), (0,)), ((0,), (0,)), ((0,1),(0,1)), (0,1), 1, 1)
        a = analyze(c)
        self.assertTrue(a['admissible'])
        self.assertTrue(verify(c, a['certificate']))
        self.assertTrue(oracle(c)['admissible'])

    def test_empty_history_may_be_a_witness(self):
        c = Contract(((0,),), ((1,), (1,)), ((0,), (1,)), (0,1))
        a = analyze(c)
        self.assertEqual(a['certificate']['history_left'], [])
        self.assertEqual(a['certificate']['cost'], 1)

    def test_false_positive_certificate_mutations(self):
        c = self.example('case-a')
        good = analyze(c)['certificate']
        corruptions = []
        x = copy.deepcopy(good); x['reachable'] = []; corruptions.append(x)
        x = copy.deepcopy(good); x['future_relation'] = []; corruptions.append(x)
        x = copy.deepcopy(good); x['map'] = [0]*3; corruptions.append(x)
        x = copy.deepcopy(good); x['future_relation'].append([0,2]); corruptions.append(x)
        x = copy.deepcopy(good); x['reachable'].append(x['reachable'][0]); corruptions.append(x)
        x = copy.deepcopy(good); x['map'][0] = True; corruptions.append(x)
        x = copy.deepcopy(good); x['map'][0] = 99; corruptions.append(x)
        x = copy.deepcopy(good); x['extra'] = 1; corruptions.append(x)
        for x in corruptions:
            with self.subTest(certificate=x):
                self.assertFalse(verify(c, x))

    def test_false_negative_certificate_mutations(self):
        c = self.example('case-d')
        good = analyze(c)['certificate']
        corruptions = []
        for key, value in [('history_left', [0]), ('history_right', [0]), ('suffix', []),
                           ('retained_state', 99), ('target_left', 99), ('target_right', 99),
                           ('cost', 0), ('cost', True), ('suffix', [99])]:
            x = copy.deepcopy(good); x[key] = value
            if x != good:
                corruptions.append(x)
        for x in corruptions:
            with self.subTest(certificate=x):
                self.assertFalse(verify(c, x))

    def test_bad_relations(self):
        c = self.example('case-a')
        cert = analyze(c)['certificate']
        for value in (None, {}, [[-1,0]], [[True,0]], [[0]], [[0,0,0]]):
            x = copy.deepcopy(cert); x['future_relation'] = value
            self.assertFalse(verify(c, x))

    def test_malformed_specifications(self):
        c = self.example('case-a').to_dict()
        corruptions = [dict(c, retain=[]), dict(c, retain=[[0],[0,1]]),
                       dict(c, history=[[99,0]]), dict(c, output=[True,0,1]),
                       dict(c, output=[0,2,1]), dict(c, initial_target=-1),
                       dict(c, initial_retain=True), dict(c, future=[[0,0]]),
                       dict(c, arbitrary_code='raise SystemExit')]
        for x in corruptions:
            with self.subTest(contract=x):
                self.assertRaises(ValueError, Contract.from_dict, x)

    def test_missing_contract_fields(self):
        self.assertRaises(ValueError, Contract.from_dict, {})

    def test_word_symbol_validation(self):
        for w in ([True], [-1], [2], ['0']):
            self.assertRaises(ValueError, run, ((0,0),), 0, w)

    def test_oracle_resource_guard(self):
        c = self.example('case-f')
        self.assertRaises(ValueError, oracle, c)

    def test_enumeration_cardinality(self):
        counts = {1:0, 2:0}
        last = -1
        for row in parameters():
            self.assertEqual(row[0], last+1)
            counts[row[1]] += 1
            last = row[0]
        self.assertEqual(counts, {1:29490, 2:17442})
        self.assertEqual(last, 46931)

    def test_fixed_pilot_against_oracle(self):
        selected = {i*46931//63 for i in range(64)}
        for row in parameters():
            if row[0] in selected:
                c = from_parameters(row)
                a, o = analyze(c), oracle(c)
                self.assertEqual(a['admissible'], o['admissible'])
                minimum = None if a['admissible'] else a['certificate']['cost']
                self.assertEqual(minimum, o['minimum_cost'])
                self.assertTrue(verify(c, a['certificate']))


if __name__ == '__main__':
    unittest.main()
