import os
import re
import csv
from nose.tools import (assert_equal, assert_not_equal, assert_in,
                        assert_is_not_none, assert_raises)
from immpload import munger
from immpload.munger import MungeError
from .. import ROOT

FIXTURES = os.path.join(ROOT, 'fixtures')
INPUTS = os.path.join(FIXTURES, 'input')
CONFIGURATIONS = os.path.join(FIXTURES, 'conf')
RESULTS = os.path.join(ROOT, 'results')
EXPECTED = os.path.join(ROOT, 'expected')


class TestMunger(object):

    def __init__(self):
        if not os.path.exists(RESULTS):
            os.mkdir(RESULTS)

    def test_auto_convert(self):
        munged = self._munge('subjectAnimals', fixture='subjects_auto_convert',
                             auto_convert=True)
        # Compare output to expected.
        expected_file = os.path.join(EXPECTED, 'subjects_auto_convert.txt')
        expected = self._read_result_file(expected_file, 'subjectAnimals')
        assert_equal(expected, munged, "Output differs from expected")

    def test_patterns(self):
        munged = self._munge('assessments', config='assessments_patterns',
                             Study_ID='Test', Assessment_Type='Physical Exam',
                             Component_Name_Reported='Weight')
        required = ['Subject ID', 'Study ID', 'Study Day',
                    'Assessment Panel ID', 'Result Value Reported']
        for i, row in enumerate(munged):
            for col in required:
                assert_is_not_none(row.get(col),
                                   "Row %s missing %s" % (i + 1, col))
            assert_equal(row.get('Study ID'), 'Test')
            assert_is_not_none(row.get('Name Reported'),
                               "Row %s missing %s" % (i + 1, col))
        # Compare output to expected.
        expected_file = os.path.join(EXPECTED, 'assessments.txt')
        expected = self._read_result_file(expected_file, 'assessments')
        assert_equal(expected, munged, "Output differs from expected")

    def test_callback(self):
        munged = self._munge('assessments', config='assessments_flat',
                             callback=_add_weights,
                             Study_ID='Test', Assessment_Type='Physical Exam',
                             Component_Name_Reported='Weight')
        required = ['Subject ID', 'Study ID', 'Study Day',
                    'Assessment Panel ID', 'Result Value Reported']
        for i, row in enumerate(munged):
            for col in required:
                assert_is_not_none(row.get(col),
                                   "Row %s missing %s" % (i + 1, col))
            assert_equal(row.get('Study ID'), 'Test')
            assert_is_not_none(row.get('Name Reported'),
                               "Row %s missing %s" % (i + 1, col))
        # Compare output to expected.
        expected_file = os.path.join(EXPECTED, 'assessments.txt')
        expected = self._read_result_file(expected_file, 'assessments')
        assert_equal(expected, munged, "Output differs from expected")

    def test_values(self):
        munged = self._munge('subjectAnimals', fixture='subjects',
                             config='subjects_values')
        # Compare output to expected.
        expected_file = os.path.join(EXPECTED, 'subjectAnimals.txt')
        expected = self._read_result_file(expected_file, 'subjectAnimals')
        assert_equal(expected, munged, "Output differs from expected")

    def test_bogus_column(self):
        with assert_raises(MungeError):
            self._munge('assessments', config='assessments_flat', Bogus='bogus')
        with assert_raises(MungeError) as context:
            self._munge('assessments', config='assessments_flat', Name_Reported='bogus')
        msg = str(context.exception)
        assert_in('disambiguated', msg, "Error message incorrect")

    def _munge(self, template, fixture=None, config=None, callback=None,
               auto_convert=False, **kwargs):
        if not fixture:
            fixture = template
        if not auto_convert and not config:
            config = fixture
        in_file = os.path.join(INPUTS, fixture + '.xlsx')
        if config:
            config_file = os.path.join(CONFIGURATIONS, config + '.yaml')
        else:
            config_file = None
        out_subdir = config if config else 'auto_convert'
        out_dir = os.path.join(RESULTS, template, out_subdir)
        out_file = munger.munge(template, in_file, config=config_file,
                                out_dir=out_dir, callback=callback,
                                **kwargs)
        assert_is_not_none(out_file, "%s not munged" % template)
        return self._read_result_file(out_file, template)

    def _read_result_file(self, in_file, template):
        with open(in_file) as fs:
            # Skip the header.
            next(fs)
            next(fs)
            # The next line is the column names.
            cols = self._parse_columns(next(fs), template)
            # Convert the remaining lines to a list of dictionary objects.
            reader = csv.reader(fs, delimiter='\t')
            return [{cols[i]: value for i, value in enumerate(row)}
                    for row in reader]

    def _parse_columns(self, row, template):
            # The column names.
            cols = row.split('\t')
            if template == 'assessments':
                panel_name_ndx = cols.index('Name Reported')
                assert_not_equal(-1, panel_name_ndx,
                                 "Assessment file is missing column: Name Reported")
                cols[panel_name_ndx] = 'Panel Name Reported'
                component_name_ndx = cols[::-1].index('Name Reported')
                assert_not_equal(panel_name_ndx, component_name_ndx,
                                 "Assessment file has only one 'Name Reported' column")
                cols[component_name_ndx] = 'Component Name Reported'
            return cols


def _add_weights(in_row, in_cols, out_col_ndx_map, out_row):
    return [_add_weight(out_row, out_col_ndx_map, col, in_row[i])
            for i, col in enumerate(in_cols)
            if re.match(r'D\d+$', col) and in_row[i]]


def _add_weight(out_row, out_col_ndx_map, col, weight):
    day_ndx = out_col_ndx_map['Study Day']
    day = int(col[1:])
    amended = out_row.copy()
    amended[day_ndx] = day
    value_ndx = out_col_ndx_map['Result Value Reported']
    amended[value_ndx] = weight

    return amended
