from nose.tools import (assert_equal, assert_is_not_none)
from immpload import templates


class TestTemplates(object):

    def test_assessments(self):
        tmpl = templates.assessments()
        self._verify(tmpl, 'assessments')

    def _verify(self, template, name):
        assert_is_not_none(template, "%s template not loaded" % name)
        assert_is_not_none(template.header, "%s template header not loaded" % name)
        assert_is_not_none(template.columns, "%s template columns not loaded" % name)
