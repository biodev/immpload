
from bunch import Bunch
import requests

# The templates location.
URL_DIR = 'https://www.immport.org/downloads/data/upload/templates/txt-templates'

# The template name: mapping dictionary.
tmpl_dict = {}


class TemplateError(Exception):
    pass


def assessments():
    """
    Fetches the assessments template on demand.

    :return: the assessments template {header, columns} dictionary
    """
    return template_for('assessments')


def template_for(name):
    """
    Fetches the given template on demand.

    :param name: the template name
    :return: the template {header, columns} dictionary
    """
    mapping = tmpl_dict.get(name)
    if not mapping:
        mapping = tmpl_dict[name] = _load(name)

    return mapping


def _load(name):
    """
    Loads the given template from the Immport web site.

    :param name: the template name
    :return: the template {header, columns} dictionary
    """
    url = URL_DIR + '/' + name + '.txt'
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
    except Exception as e:
        msg = "The online template could not be accessed: " + url
        raise TemplateError(msg) from e
    rows = [line.decode('utf-8').split("\t") for line in response.iter_lines()]
    cols_row_ndx = next((i for i, row in enumerate(rows)
                         if row[0] == 'Column Name'), -1)
    if cols_row_ndx == -1:
        raise TemplateError("The online template %s could not be parsed: %s" %
                            (name, url))
    header = rows[0:cols_row_ndx]
    columns = rows[cols_row_ndx]
    # Special case: assessments has a duplicate column name for
    # different purposes.
    if name == 'assessments':
        indexes = [index for index, col in enumerate(columns)
                   if col == 'Name Reported']
        if len(indexes) == 2:
            columns[indexes[0]] = 'Panel Name Reported'
            columns[indexes[1]] = 'Component Name Reported'
        aliases = {'Panel Name Reported': 'Name Reported',
                   'Component Name Reported': 'Name Reported'}
    else:
        aliases = {}

    return Bunch(name=name, header=header, columns=columns, aliases=aliases)
