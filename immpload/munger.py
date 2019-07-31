import os
import csv
import re
import yaml
from bunch import Bunch
import openpyxl
import functools
from . import templates

"""The pattern to detect a config configuration pattern."""
PATTERN_PAT = re.compile("r['\"](?P<pattern>.+)['\"]$")


class MungeError(Exception):
    pass


def munge(template, *in_files, config=None, out_dir=None,
          sheet=None, input_filter=None, callback=None, **kwargs):
    """
    Builds the Immport upload file for the given input file.
    The template is a supported Immport template name, e.g.
    `assessments`. The output is the Immport upload file,
    e.g. `assessments,txt`, placed in the output directory.

    The keyword arguments (_kwargs_) are static output
    _column_`=`_value_ definitions that are applied to every
    output row. The column name can be underscored, e.g.
    `Study_ID`.

    :param template: the required Immport template name
    :param in_files: the input file(s) to munge
    :param config: the configuration dictionary or file name
    :param out_dir: the target location (default current directory)
    :param sheet: for an Excel workbook input file, the sheet to open
    :param input_filter: optional input row validator which has
        parameter in_row and returns whether the row is valid
    :param callback: optional callback with parameters
        in_row, in_col_ndx_map, out_col_ndx_map and out_row returning
        an array of rows to write to the output file
    :param kwargs: the optional static _column_`=`_value_ definitions
    :return: the output file name
    """
    # Note: this method signature and apidoc is copied in the
    # package README.md file.

    # If neither a config nor a callback, then auto-convert
    # the input.
    auto_convert = config == None and callback == None

    # Load the config file, if necessary.
    if config == None:
        config = {}
    elif isinstance(config, str):
        with open(config, 'r') as fs:
            config = yaml.safe_load(fs)
    # Parse the config to a {name, value} bunch.
    config = _parse_config(config)
    config.auto_convert = auto_convert
    config.in_filter = input_filter

    # Remove the template file suffix, if necessary.
    template = re.sub("\.txt$", '', template)
    # Acquire the template object.
    tmpl = templates.template_for(template)
    # Make the output column {name: index} dictionary.
    config.out_col_ndx_map = {col: i for i, col in enumerate(tmpl.columns)}
    # Add the kwargs to the config.
    static_kwargs = {key.replace('_', ' '): value
                     for key, value in kwargs.items()}
    config.static.update(static_kwargs)
    # Validate the static definition.
    for out_col in config.static:
        _validate_static_column(out_col, tmpl)
    # Add the default template callback, if necessary.
    def_callback = DEF_CALLBACKS.get(template)
    if not def_callback and '.' in template:
        prefix = template.split('.')[0]
        def_callback = DEF_CALLBACKS.get(prefix)
    if def_callback:
        config.callback = functools.partial(_add_defaults, def_callback,
                                            callback=callback)
    else:
        config.callback = callback

    # Prepare the output location.
    if out_dir:
        out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)
    else:
        out_dir = os.getcwd()
    out_file = os.path.join(out_dir, template + '.txt')

    # Convert the input to output.
    with open(out_file, 'w') as fs:
        writer = csv.writer(fs, delimiter='\t')
        for in_file in in_files:
            reader = _create_reader(in_file, sheet=sheet)
            _munge_file(tmpl, reader, writer, config=config)

    return out_file

def _validate_static_column(out_col, template):
    if not out_col in template.columns:
        # Check for a column name alias.
        aliases = [col for col, alias in template.aliases.items()
                   if alias == out_col]
        if aliases:
            msg = (("Output column '%s' must be disambiguated as " +
                    "one of the following: %s") % (out_col, aliases))
        else:
            msg = "Output column not found: %s" % out_col
        raise MungeError(msg)

def _is_valid_row(row, config):
    """
    Filters blank rows and applies the optional row filter
    argument as necessary.
    """
    # Filter blank rows.
    if all(value == None for value in row):
        return False
    # Apply the config filter, if any.
    return config.in_filter(row) if config.in_filter else True


def _parse_config(config):
    """
    Converts the input config to a
    {names, patterns, static, keys, values_dict} bunch, where
    _names_ is the {input column: output column} dictionary,
    _patterns_ is the {pattern: output column} dictionary,
    _static_ is the {output column: value} dictionary,
    _key_ is the [output columns] uniqueness list, and
    *value_dict* is the {output column: value conversion} dictionary.
    """
    # Convert the configuration {output: spec} dictionary to
    # {input: name} and {input: value} dictionaries.
    out_in_columns = config.get('columns', {})
    # Partition the config columns and patterns.
    out_in_pat_dict = config.get('patterns', {})
    out_in_patterns = {out_col: _compile_config_pattern(pattern, out_col)
                       for out_col, pattern in out_in_pat_dict.items()}
    conf_values = config.get('values', {})
    values_dict = {out_col: value for out_col, value in conf_values.items()
                   if isinstance(value, dict)}
    static = {out_col: value for out_col, value in conf_values.items()
              if out_col not in values_dict}

    # Invert the {out: in} dictionaries.
    in_out_names = {in_col: out_col
                    for out_col, in_col in out_in_columns.items()}
    in_out_patterns = {pattern: out_col
                       for out_col, pattern in out_in_patterns.items()}

    return Bunch(names=in_out_names, patterns=in_out_patterns,
                 static=static, values_dict=values_dict)


def _compile_config_pattern(pattern, out_col):
    try:
        return re.compile(pattern)
    except re.error as e:
        msg = "Configuration %s pattern %s error" % (out_col, pattern)
        raise MungeError() from e


def _munge_file(template, reader, writer, config):
    in_cols = None
    for i, in_row in enumerate(reader):
        # The first (possibly filtered) input file row is
        # the input column names.
        if i == 0:
            # Capture the input column names and indexes.
            config.in_col_ndx_map = {name: i for i, name in enumerate(in_row)}
            # If auto-convert is set, then map the input
            # to the output based on matching column names.
            if config.auto_convert:
                for in_col in config.in_col_ndx_map:
                    if (in_col in config.out_col_ndx_map and
                        not in_col in config.names):
                        config.names[in_col] = in_col
            # Write the Immport template header lines.
            _write_header(template, writer)
            # Write the template column names.
            _write_column_names(template, writer)
            # Parse the config patterns, now that we have input
            # columns to match against.
            _make_embedded_config(config)
        elif _is_valid_row(in_row, config):
            # Format the output rows.
            out_rows = _generate_output(in_row, template, config)
            # Write the generated rows.
            if out_rows:
                writer.writerows(out_rows)


def _make_embedded_config(config):
    """
    Matches config patterns against the input columns to create a
    new config attribute _embedded_ holding a list of
    (output column index: matches) tuples, where _matches_ is a list
    of (input column index, match dictionary) tuples. The patterns
    are removed from _config.names_.
    """
    # Make the {output column: {output column: value}} dictionary.
    config.embedded = {out_col: _match_input_columns(pattern, config)
                       for pattern, out_col in config.patterns.items()}


def _match_input_columns(pattern, config):
    """
    :return: the {input column: {output column: value}} dictionary
    """
    matches = [(in_col, pattern.match(in_col))
               for in_col in config.in_col_ndx_map]
    return {in_col: _parse_group_dictionary(match.groupdict(), config)
            for in_col, match in matches if match}


def _parse_group_dictionary(match_dict, config):
    """
    :return: the {output column: value} dictionary
    """
    return {config.names[name]: value
            for name, value in match_dict.items()
            if name in config.names}


def _create_reader(in_file, sheet=None):
    if not os.path.exists(in_file):
        raise IOError("Input file not found: %s" % in_file)
    _, ext = os.path.splitext(in_file)
    if ext == '.csv' or ext == '.txt':
        reader = _read_csv(in_file)
    elif ext == '.xlsx':
        reader = _read_excel(in_file, sheet=sheet)
    else:
        raise ValueError("Input file type not supported: %s" % in_file)

    return reader


def _write_header(template, writer):
    # Write the Immport template header lines.
    for hdg in template.header:
        writer.writerow(hdg)


def _write_column_names(template, writer):
    # Write the template column names.
    columns = template.columns.copy()
    for col, alias in template.aliases.items():
        index = columns.index(col)
        columns[index] = alias
    writer.writerow(columns)


def _generate_output(in_row, template, config):
    # Map the output columns to output values.
    values = {config.names[col]: _map_value(col, in_row[i], config)
              for i, col in enumerate(config.in_col_ndx_map)
              if col in config.names}
    out_row = [values.get(col) for col in config.out_col_ndx_map]
    # Set the statically defined column values.
    for out_col, value in config.static.items():
        # Get the static definition output column index.
        out_col_ndx = config.out_col_ndx_map[out_col]
        out_row[out_col_ndx] = value
    # Expand each embedded config into a separate row.
    if config.embedded:
        out_rows = _generate_embedded_output(in_row, out_row, config)
    else:
        out_rows = (out_row,)
    i = 0
    for out_row in out_rows:
        if config.callback:
            for row in config.callback(in_row, config.in_col_ndx_map,
                                       config.out_col_ndx_map, out_row):
                yield row
        else:
            yield out_row


def _map_value(in_col, value, config):
    out_col = config.names[in_col]
    col_values = config.values_dict.get(out_col)
    return col_values.get(value, value) if col_values else value


def _generate_embedded_output(in_row, out_row, config):
    """
    :yield: each output row
    """
    for out_col, matches in config.embedded.items():
        for in_col, group_values in matches.items():
            in_col_ndx = config.in_col_ndx_map[in_col]
            # There must be an input value.
            value = in_row[in_col_ndx]
            if value:
                out_col_ndx = config.out_col_ndx_map[out_col]
                yield _create_embedded_row(value, out_row, out_col_ndx,
                                           config, group_values)


def _create_embedded_row(value, out_row, out_col_ndx, config, group_values):
    # Make a new output row.
    row = out_row.copy()
    # Set the embedded column.
    row[out_col_ndx] = value
    # Assign the match group values to the associated output column.
    for grp_out_col, grp_value in group_values.items():
        grp_out_col_ndx = config.out_col_ndx_map[grp_out_col]
        row[grp_out_col_ndx] = grp_value

    return row


def _add_defaults(def_callback, in_row, in_col_ndx_map, out_col_ndx_map,
                  out_row, callback=None):
    if callback:
        out_rows = callback(in_row, in_col_ndx_map, out_col_ndx_map, out_row)
    else:
        out_rows = [out_row]
    for row in out_rows:
        def_callback(out_col_ndx_map, row)

    return out_rows


def _add_assessments_defaults(out_col_ndx_map, row):
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
        study_id = row[out_col_ndx_map['Study ID']]
        if not study_id:
            raise MungeError("Required Study ID value is missing")
        day = row[out_col_ndx_map['Study Day']]
        if day == None:
            raise MungeError("Required Study Day value is missing")
        day_id = 'd' + str(day)
        visit_id = row[visit_id_ndx] = '.'.join((study_id.lower(), day_id))
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
        row[user_id_ndx] = '.'.join((subject_id, visit_id, component_name.lower()))


def _add_reagents_defaults(out_col_ndx_map, row):
    """
    Makes default values as necessary for the following required columns:
    * `Name` - copied from the `Analyte Reported`
    * `User Defined ID` - derived from the `Name`
    * `Description` copied from `Name`
    """
    name_ndx = out_col_ndx_map['Name']
    name = row[name_ndx]
    if not name:
        analyte = row[out_col_ndx_map['Analyte Reported']]
        if not analyte:
            raise MungeError("Required Analyte Reported value is missing")
        name = row[name_ndx] = analyte
    user_id_ndx = out_col_ndx_map['User Defined ID']
    if not row[user_id_ndx]:
        row[user_id_ndx] = re.sub(r'[^\w]', '_', name).lower()
    desc_ndx = out_col_ndx_map['Description']
    if not row[desc_ndx]:
        row[desc_ndx] = name


def _read_csv(in_file):
    kwargs = {}
    if in_file.endswith('.txt'):
        kwargs['delimiter'] = '\t'
    with open(in_file) as fs:
        reader = csv.reader(fs, **kwargs)
        for row in reader:
            # Skip empty rows.
            if row and any(row):
                yield row


def _read_excel(in_file, sheet=None):
    wb = openpyxl.load_workbook(in_file, read_only=True)
    ws = wb.get_sheet_by_name(sheet) if sheet else wb.active
    for row in ws:
        if row:
            yield [cell.value for cell in row]


"""The default callbuck functions."""
DEF_CALLBACKS = dict(assessments=_add_assessments_defaults,
                     reagents=_add_reagents_defaults)
