import re
import inflection
import functools
from . import MungeError

TREATMENT_QUALIFIER_TYPES = ['Amount', 'Temperature', 'Duration']


def get_defaults_callback(template):
    """
    Returns the callback function to set default output row values.

    The callback function takes two parameters:
    * `row` - the output row
    * `out_col_ndx_map` - the output column {name: index} dictionary

    The callback function modifies the given row in place. It does
    not return a value.

    *Note*: although the callback raises an exception if certain
    values necessary to make a default are missing, it does not
    fully validate the output row. The :mod:`validators` module
    serves that purpose.

    :param template: the template name
    :return: the callback function to set default values, or `None`
        if there is no defaults function for the given template
    :raise MungeError: if an output row column value required to
        add a default is missing
    """
    callback = DEF_CALLBACKS.get(template)
    if callback:
        return callback
    elif '.' in template:
        # The experiment type, e.g. ELISA.
        prefix, exp_type = template.split('.')
        callback = DEF_CALLBACKS.get(prefix)
        if callback:
            return functools.partial(callback, experiment_type=exp_type)


def _add_protocols_defaults(row, out_col_ndx_map, experiment_type=None):
    """
    Makes default values as necessary for the following required columns:
    * `Name` - `File Name` without extension formatted as a title
    * `Description` - copied from `Name`
    * `User Defined ID` - lower-case, underscored `File Name`
    """
    file_name_ndx = out_col_ndx_map['File Name']
    file_name = row[file_name_ndx]
    if not file_name:
        raise MungeError("The File Name value is missing")
    file_name_sans_ext = re.sub('\..*$', '', file_name)
    name_ndx = out_col_ndx_map['Name']
    name = row[name_ndx]
    if not name:
        name = row[name_ndx] = _titleize(file_name_sans_ext)
    desc_ndx = out_col_ndx_map['Description']
    if not row[desc_ndx]:
        row[desc_ndx] = name
    user_id_ndx = out_col_ndx_map['User Defined ID']
    if not row[user_id_ndx]:
        row[user_id_ndx] = (
            inflection.underscore(file_name_sans_ext).replace(' ', '_')
        )


def _add_reagents_defaults(row, out_col_ndx_map, experiment_type=None):
    """
    Makes default values as necessary for the following required columns:
    * `Name` - derived from the `Analyte Reported` and `Catalog Number`
    * `Catalog Number` - `NA`
    * `User Defined ID` - lower-case `Catalog Number` followed by `_reagent`
    * `Description` copied from `Name`
    """
    cat_nbr_ndx = out_col_ndx_map['Catalog Number']
    cat_nbr = row[cat_nbr_ndx]
    if not cat_nbr:
        cat_nbr = row[cat_nbr_ndx] = 'NA'
    analyte = row[out_col_ndx_map['Analyte Reported']]
    if not analyte:
        raise MungeError("Required Analyte Reported value is missing")
    # The default name is used for both the name and the default
    # user id.
    if cat_nbr.lower() == 'na':
        name_parts = [analyte]
        if experiment_type:
            name_parts.append(experiment_type)
    else:
        name_parts = [cat_nbr]
    name_parts.append('Reagent')
    def_name = ' '.join(name_parts)
    name_ndx = out_col_ndx_map['Name']
    name = row[name_ndx]
    if not name:
        name = row[name_ndx] = def_name
    # The default user id is derived from the name.
    user_id_ndx = out_col_ndx_map['User Defined ID']
    if not row[user_id_ndx]:
        row[user_id_ndx] = _name_to_id(def_name)
    # The default description is the name.
    desc_ndx = out_col_ndx_map['Description']
    if not row[desc_ndx]:
        row[desc_ndx] = name


def _add_treatments_defaults(row, out_col_ndx_map, experiment_type=None):
    """
    Makes default values as necessary for the following required columns:
    * `Name` - derived from the treatment values
    * `User Defined ID` - lower-case, underscored `Name` and `Amount Value`
    * `Use Treatment?` - default is `Yes`
    """
    name_ndx = out_col_ndx_map['Name']
    name = row[name_ndx]
    if not name:
        name = _default_treatment_name(row, out_col_ndx_map)
        if not name:
            raise MungeError("Required Name value could not be inferred from " +
                             "the " + ','.join(attrs) + " attributes")
        row[name_ndx] = name
    user_id_ndx = out_col_ndx_map['User Defined ID']
    if not row[user_id_ndx]:
        row[user_id_ndx] = _name_to_id(name)
    use_treatment_ndx = out_col_ndx_map['Use Treatment?']
    if not row[use_treatment_ndx]:
        row[use_treatment_ndx] = 'Yes'


def _default_treatment_name(row, out_col_ndx_map, experiment_type=None):
    qualifiers = [_treatment_name_qualifier(row, out_col_ndx_map, type)
                  for type in TREATMENT_QUALIFIER_TYPES]
    qualifier_s = ', '.join(filter(None, qualifiers))
    return qualifier_s if qualifier_s else None


def _treatment_name_qualifier(row, out_col_ndx_map, treatment_type):
    value_ndx = out_col_ndx_map[treatment_type + ' Value']
    value = row[value_ndx]
    if value != None:
        unit_ndx = out_col_ndx_map[treatment_type + ' Unit']
        unit = row[unit_ndx]
        if unit != 'Not Specified':
            return ' '.join((value, unit))


def _add_subjectAnimals_defaults(row, out_col_ndx_map):
    """
    Makes default values as necessary for the following required columns:
    * `Age Unit` - `Days`
    * `Age Event` - `Age at infection`
    """
    age_unit_ndx = out_col_ndx_map['Age Unit']
    age_unit = row[age_unit_ndx]
    if not age_unit:
        row[age_unit_ndx] = 'Days'
    age_event_ndx = out_col_ndx_map['Age Event']
    age_event = row[age_event_ndx]
    if not age_event:
        row[age_event_ndx] = 'Age at infection'


def _add_samples_defaults(row, out_col_ndx_map, experiment_type=None):
    """
    Makes default values as necessary for the following required columns:
    * `Experiment ID` - lower-case, underscored `Experiment Name`
    * `Planned Visit ID` - `Study ID` followed by `d` and the
      `Study Time Collected`
    * `Biosample ID` - lower-case, underscored `Biosample Name`,
      if present, otherwise the `Expsample ID`, if present,
      otherwise derived from the `Subject ID`, `Treatment ID(s)`
      and `Experiment ID`
    * `Expsample ID` - derived from the `Biosample ID`, `Treatment ID`
      and Experiment ID
    """
    experiment_id_ndx = out_col_ndx_map['Experiment ID']
    if not row[experiment_id_ndx]:
        name_ndx = out_col_ndx_map['Experiment Name']
        name = row[name_ndx]
        if not name:
            msg = "Both the Experiment ID and Name values are missing"
            raise MungeError(msg)
        row[experiment_id_ndx] = _name_to_id(name)
    visit_id_ndx = out_col_ndx_map['Planned Visit ID']
    visit_id = row[visit_id_ndx]
    if not visit_id:
        visit_id = _default_visit_id(out_col_ndx_map, 'Study Time Collected',
                                     row)
        row[visit_id_ndx] = visit_id

    biosample_id_ndx = out_col_ndx_map['Biosample ID']
    biosample_id = row[biosample_id_ndx]
    if not biosample_id:
        biosample_id = _default_biosample_id(row, out_col_ndx_map)
        row[biosample_id_ndx] = biosample_id
    expsample_id_ndx = out_col_ndx_map['Expsample ID']
    if not row[expsample_id_ndx]:
        row[expsample_id_ndx] = biosample_id


def _default_biosample_id(row, out_col_ndx_map):
    expsample_id_ndx = out_col_ndx_map['Expsample ID']
    expsample_id = row[expsample_id_ndx]
    if expsample_id:
        return expsample_id
    name_ndx = out_col_ndx_map['Biosample Name']
    name = row[name_ndx]
    if name:
        return _name_to_id(name)
    subject_id_ndx = out_col_ndx_map['Subject ID']
    subject_id = row[subject_id_ndx]
    if not subject_id:
        raise MungeError("The Biosample ID, Expsample ID, Biosample Name" +
                         " and Subject ID values are missing")
    experiment_id_ndx = out_col_ndx_map['Experiment ID']
    experiment_id = row[experiment_id_ndx]
    if not experiment_id:
        raise MungeError("The Biosample ID, Expsample ID, Biosample Name" +
                         " and Experiment ID values are missing")
    time_ndx = out_col_ndx_map['Study Time Collected']
    time = row[time_ndx]
    if not time:
        raise MungeError("The Biosample ID, Expsample ID, Biosample Name" +
                         " and Study Time Collected values are missing")
    time_unit_ndx = out_col_ndx_map['Study Time Collected Unit']
    time_unit = row[time_unit_ndx]
    if not time_unit:
        raise MungeError("The Biosample ID, Expsample ID, Biosample Name" +
                         " and Study Time Collected Unit values are missing")
    treatment_ids_ndx = out_col_ndx_map['Treatment ID(s)']
    treatment_ids = row[treatment_ids_ndx]
    if not treatment_ids:
        raise MungeError("The Biosample ID, Expsample ID, Biosample Name" +
                         " and Treatment ID(s) values are missing")

    return '_'.join((subject_id, re.sub(', *', '_', treatment_ids),
                     time_unit[0].lower() + time, experiment_id))


def _default_visit_id(out_col_ndx_map, study_day_column, row, experiment_type=None):
    """
    :return: the `Study ID` followed by `d` and the study day
    """
    study_id = row[out_col_ndx_map['Study ID']]
    if not study_id:
        raise MungeError("Required Study ID value is missing")
    day = row[out_col_ndx_map[study_day_column]]
    if day == None:
        raise MungeError("Required %s value is missing" % study_day_column)
    day_id = 'd' + str(day)
    return '_'.join((study_id.lower(), day_id))


def _add_assessments_defaults(row, out_col_ndx_map, experiment_type=None):
    """
    Makes default values as necessary for the following required columns:
    * `Planned Visit ID` - `Study ID` followed by `d` and the `Study Day`
    * `Panel Name Reported` - copied from the `Assessment Type`
    * `Assessment Panel ID` - derived from the `Panel Name Reported`
    * `User Defined ID` - derived from the `Subject ID`, `Planned Visit ID`
      and `Component Name Reported`
    """
    visit_id_ndx = out_col_ndx_map['Planned Visit ID']
    visit_id = row[visit_id_ndx]
    if not visit_id:
        visit_id = _default_visit_id(out_col_ndx_map, 'Study Day', row)
        row[visit_id_ndx] = visit_id
    panel_name_ndx = out_col_ndx_map['Panel Name Reported']
    panel_name = row[panel_name_ndx]
    if not panel_name:
        type = row[out_col_ndx_map['Assessment Type']]
        if not type:
            raise MungeError("Neither the Panel Name Reported nor the " +
                             "Assessment Type value is missing")
        panel_name = row[panel_name_ndx] = type
    panel_id_ndx = out_col_ndx_map['Assessment Panel ID']
    panel_id = row[panel_id_ndx]
    if not panel_id:
        panel_id = row[panel_id_ndx] = panel_name.lower().replace(' ', '_')
    user_id_ndx = out_col_ndx_map['User Defined ID']
    if not row[user_id_ndx]:
        subject_id = row[out_col_ndx_map['Subject ID']]
        if not subject_id:
            raise MungeError("Required Subject ID value is missing")
        component_name_ndx = out_col_ndx_map['Component Name Reported']
        component_name = row[component_name_ndx]
        if not component_name:
            raise MungeError("Required Component Name Reported value is missing")
        row[user_id_ndx] = '_'.join((subject_id, visit_id, component_name.lower()))


def _name_to_id(name):
    return re.sub(r'[^\w]', '_', name).lower()


def _titleize(s):
    """
    Tweaks `inflection.titleize` to preserve acronyms.

    >>> print(inflection.titleize('AB_CdeXYZ_Name'))
    Ab Cde Xyz Name

    >>> print(defaults._titleize('AB_CdeXYZ_Name'))
    AB Cde XYZ Name
    """
    acronyms = re.findall('[A-Z][A-Z]+', s)
    recapitalize = {acronym.capitalize(): acronym for acronym in acronyms}
    title = inflection.titleize(s)
    for k, v in recapitalize.items():
        title = title.replace(k, v)
    return title


"""The default callbuck functions."""
DEF_CALLBACKS = dict(protocols=_add_protocols_defaults,
                     treatments=_add_treatments_defaults,
                     reagents=_add_reagents_defaults,
                     subjectAnimals=_add_subjectAnimals_defaults,
                     experimentSamples=_add_samples_defaults,
                     assessments=_add_assessments_defaults)
