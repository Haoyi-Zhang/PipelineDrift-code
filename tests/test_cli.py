import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from drift_contracts.__main__ import main
from drift_contracts.cases import named_examples


class CLITests(unittest.TestCase):
    def invoke(self, data, cert=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'case.json'
            path.write_text(json.dumps(data))
            args = ['drift_contracts', str(path)]
            if cert is not None:
                cpath = Path(temp)/'certificate.json'
                cpath.write_text(json.dumps(cert))
                args.extend(['--certificate', str(cpath)])
            out, err = io.StringIO(), io.StringIO()
            with patch('sys.argv', args), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main()
            return code, out.getvalue(), err.getvalue()

    def test_nonobject_case_is_controlled_error(self):
        for data in (None, 3, True, [], 'text'):
            code, _, err = self.invoke(data)
            self.assertEqual(code, 2)
            self.assertIn('JSON object', err)

    def test_both_audit_answers_exit_successfully(self):
        for ex in named_examples()[:2]:
            code, out, err = self.invoke(ex)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)['admissible'], ex['expected_admissible'])
            self.assertEqual(err, '')

    def test_nonobject_certificate_is_rejected(self):
        ex = named_examples()[0]
        for cert in (7, True, [], 'text'):
            code, out, _ = self.invoke(ex, cert)
            self.assertEqual(code, 2)
            self.assertFalse(json.loads(out)['valid_certificate'])
