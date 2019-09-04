import functools
from . import MungeError


class ValidationError(MungeError):
    pass


def get_validator(template):
    """
    Returns the callback function to validate output rows.

    The callback function takes two parameters:
    * `out_col_ndx_map` - the output column {name: index} dictionary
    * `row` - the output row

    The callback function modifies the given row in place. It does
    not return a value.

    *Note*: although the callback raises an exception if certain
    values necessary to make a default are missing, it does not
    fully validate the output row. The :mod:`validators` module
    serves that purpose.
    :param template: the template name
    :return: the validator, if any
    """
    required = _get_required(template)
    if required:
        return functools.partial(_validate, required)


def _get_required(template):
    """
    :param template: the template name
    :return: the required columns, if any
    """
    required = REQUIRED_COLUMNS.get(template)
    if required:
        return required
    elif '.' in template:
        prefix = template.split('.')[0]
        return REQUIRED_COLUMNS.get(prefix)


def _validate(required, row, out_col_ndx_map):
    missing = [col for col in required
               if row[out_col_ndx_map[col]] == None]
    if missing:
        raise ValidationError("Missing values for columns: %s" % missing)


"""The validation functions."""
REQUIRED_COLUMNS = dict(
    subjectAnimals=['Subject ID', 'Arm Or Cohort ID', 'Gender',
                    'Min Subject Age', 'Age Unit', 'Age Event',
                    'Subject Location', 'Species', 'Strain'],
    subjectHumans=['Subject ID', 'Arm Or Cohort ID', 'Gender',
                   'Min Subject Age', 'Age Unit', 'Age Event',
                   'Subject Location', 'Ethnicity', 'Race'],
    protocols=['User Defined ID', 'File Name', 'Name'],
    experimentSamples=['Study ID', 'Expsample ID', 'Reagent ID(s)',
                       'Treatment ID(s)', 'Biosample ID', 'Subject ID',
                       'Planned Visit ID', 'Study Time Collected',
                       'Study Time Collected Unit', 'Study Time T0 Event',
                       'Protocol ID(s)', 'Experiment ID', 'Experiment Name',
                       'Measurement Technique'],
    treatments=['User Defined ID', 'Name', 'Use Treatment?'],
    reagents=['User Defined ID', 'Manufacturer', 'Catalog Number',
              'Analyte Reported'],
    assessments=['Subject ID', 'Assessment Panel ID', 'Study ID',
                 'Panel Name Reported', 'Component Name Reported',
                 'User Defined ID', 'Planned Visit ID', 'Study Day'],
    FCM_Derived_data=['Expsample ID', 'Population Name Reported',
                      'Gating Definition Reported',
                      'Population Statistic (count, percentile, etc)',
                      'Population Stat Unit Reported', 'Workspace File'])

# ELISA samples require values.
REQUIRED_COLUMNS['experimentSamples.ELISA'] = (
    REQUIRED_COLUMNS['experimentSamples'] +
    ['Analyte Reported', 'Value Reported', 'Unit Reported'])

# Flow samples require the .fcs file name.
REQUIRED_COLUMNS['experimentSamples.Flow_Cytometry'] = (
    REQUIRED_COLUMNS['experimentSamples'] + ['.Fcs Result File'])
