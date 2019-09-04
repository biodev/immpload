import os
import csv
import re
import yaml
from bunch import Bunch
import openpyxl
import functools
from deepmerge import always_merger
from . import (MungeError, templates, defaults, validators)

"""The pattern to detect a config configuration pattern."""
PATTERN_PAT = re.compile("r['\"](?P<pattern>.+)['\"]$")


def munge(template, *in_files, config=None, out_dir=None, sheet=None,
          input_filter=None, callback=None, defaults_opt=True,
          validate_opt=True, append_opt=False, **kwargs):
    """
    Builds the Immport upload file for the given input file.
    The template is a supported Immport template name, e.g.
    `assessments`. The output is the Immport upload file,
    e.g. `assessments,txt`, placed in the output directory.

    The keyword arguments (_kwargs_) are static output
    _column_`=`_value_ definitions that are applied to every
    output row. The column name can be underscored, e.g.
    `Study_ID`.

    Output validation is disabled by default, but recommended
    for new uploads. Enable validation by setting the _validate_
    flag parameter to `True`.

    :param template: the required Immport template name
    :param in_files: the input file(s) to munge
    :param config: the configuration dictionary or file name
        of list of file names
    :param out_dir: the target location (default current directory)
    :param sheet: for an Excel workbook input file, the sheet to open
    :param input_filter: optional input row validator which has
        parameter in_row and returns whether the row is valid
    :param callback: optional callback with parameters
        in_row, in_col_ndx_map, out_col_ndx_map and out_row returning
        an array of rows to write to the output file
    :param defaults_opt: flag indicating whether to add defaults to the
        output (default `True`)
    :param validate_opt: flag indicating whether to validate the
        output for required fields (default `True`)
    :param append_opt: append rather than overwrite an existing output
        file (default False)
    :param kwargs: the optional static _column_`=`_value_ definitions
    :return: the output file name
    """
    # Note: this method signature and apidoc is copied in the
    # package README.md file.

    # Load the config file, if necessary.
    if config == None:
        config = {}
    else:
        if isinstance(config, str):
            config_files = [config]
        elif isinstance(config, list):
            config_files = config
        else:
            msg = ("Unsupported config parameter - expected" +
                   " dictionary, string or list of strings: %s" % config)
            raise MungeError(msg)
        config = {}
        for f in config_files:
            with open(f, 'r') as fd:
                always_merger.merge(config, yaml.safe_load(fd))
    # Parse the config to a {name, value} bunch.
    config = _parse_config(config)
    # Collect options into the config.
    config.in_filter = input_filter
    # Capture the append flag.
    config.append = append_opt

    # Remove the template file suffix, if necessary.
    template = re.sub("\.txt$", '', template)
    # Acquire the template object.
    config.template = templates.template_for(template)
    # Make the output column {name: index} dictionary.
    config.out_col_ndx_map = {col: i
                              for i, col in enumerate(config.template.columns)}

    # Add the kwargs to the static config.
    static_kwargs = {key.replace('_', ' '): value
                     for key, value in kwargs.items()}
    config.static.update(static_kwargs)
    # Validate the static definition.
    for out_col in config.static:
        _validate_static_column(out_col, config.template)

    # Add the default template callback, if necessary.
    if defaults_opt:
        def_callback = defaults.get_defaults_callback(template)
        if def_callback:
            callback = functools.partial(_add_defaults, def_callback,
                                         callback=callback)
    # Add validation, if necessary.
    if validate_opt:
        validator = validators.get_validator(template)
        if validator:
            callback = functools.partial(_validate_output, validator,
                                         callback=callback)
    # Set the composite configuration callback.
    config.callback = callback

    # Prepare the output location.
    if out_dir:
        out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)
    else:
        out_dir = os.getcwd()
    out_file = os.path.join(out_dir, template + '.txt')

    # Convert the input to output.
    mode = 'a' if append_opt else 'w'
    with open(out_file, mode) as fd:
        writer = csv.writer(fd, delimiter='\t')
        if in_files:
            for i, in_file in enumerate(in_files):
                reader = _create_reader(in_file, sheet=sheet)
                _munge_file(in_file, reader, writer, config)
                # Subsequent files append the content.
                if i == 0:
                    config.append = True
        else:
            # Only use the configuration to generate output.
            _munge_config(writer, config)

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


def _is_valid_input_row(row, conf_filter=None):
    """
    Filters blank rows and applies the optional configuration filter
    argument if necessary.

    :param row: the input row
    :param conf_filter: the optional template-specific configuration filter
    :return: whether the row should be converted
    """
    # Filter blank rows.
    if all(value == None for value in row):
        return False
    # Apply the config filter, if any.
    return conf_filter(row) if conf_filter else True


def _validate_output(validator, in_row, in_col_ndx_map, out_col_ndx_map,
                     out_row, callback=None):
    if callback:
        out_rows = callback(in_row, in_col_ndx_map, out_col_ndx_map, out_row)
    else:
        out_rows = [out_row]
    for row in out_rows:
        validator(row, out_col_ndx_map)

    return out_rows


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
    in_out_names = {in_col: [] for in_col in out_in_columns.values()}
    for out_col, in_col in out_in_columns.items():
        in_out_names[in_col].append(out_col)
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


def _munge_file(in_file, reader, writer, config):
    in_cols = None
    for i, in_row in enumerate(reader):
        # The first (possibly filtered) input file row is
        # the input column names.
        if i == 0:
            # Capture the input column names and indexes.
            _capture_input_columns(in_row, config, writer)
            # If the output is entirely determined by column name matching,
            # then generate the output and skip the remaining lines.
            if _is_column_match_only(config):
                _munge_row(in_file, in_row, i, config, writer)
                return
        elif _is_valid_input_row(in_row, config.in_filter):
            _munge_row(in_file, in_row, i, config, writer)


def _is_column_match_only(config):
    """
    Returns whether the output generation is determined solely by
    extracting values from the input column name first row.

    :return: whether the configuration *names* and *patterns*
        dictionaries are non-empty and map to the same values
    """
    if not config.names:
        return False
    # Flatten the output column lists into a set.
    out_cols = {col for cols in config.names.values() for col in cols}
    return out_cols == set(config.patterns.values())

def _capture_input_columns(in_row, config, writer):
    # Capture the input column names and indexes.
    config.in_col_ndx_map = {name: i for i, name in enumerate(in_row)}
    # Auto-convert the input columns which match
    # output column names.
    for in_col in config.in_col_ndx_map:
        if (in_col in config.out_col_ndx_map and
            not in_col in config.names):
            config.names[in_col] = [in_col]
    # Write the Immport template header lines.
    if not config.append:
        _write_header(config.template, writer)
    # Parse the config patterns, now that we have input
    # columns to match against.
    _make_embedded_config(config)


def _munge_row(in_file, in_row, index, config, writer):
    # The output row generator.
    out_rows = _generate_output(in_row, config)
    # Write the generated rows.
    try:
        writer.writerows(out_rows)
    except Exception as e:
        msg = ("Error generating %s output for input row %d in %s" %
               (config.template.name, index + 1, in_file))
        raise MungeError(msg) from e

def _munge_config(writer, config):
    """
    Generates output based solely on the configuration.
    """
    # Make an empty input {column: index} and embedded map.
    config.in_col_ndx_map = {}
    config.embedded = {}
    # Write the Immport template header lines.
    if not config.append:
        _write_header(config.template, writer)
    # The output row generator.
    out_rows = _generate_output([], config)
    # Write the generated rows.
    try:
        writer.writerows(out_rows)
    except Exception as e:
        msg = "Error generating %s output" % config.template.name
        raise MungeError(msg) from e


def _write_header(template, writer):
    # Write the Immport template header lines.
    _write_prequel(template, writer)
    # Write the template column names.
    _write_column_names(template, writer)


def _make_embedded_config(config):
    """
    Matches config patterns against the input columns to create a
    new config attribute _embedded_ holding a list of
    (output column index: matches) tuples, where _matches_ is a list
    of (input column index, match dictionary) tuples.
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
    cols_values = [(config.names[name], value)
                   for name, value in match_dict.items()
                   if name in config.names]
    return {col: value
            for cols, value in cols_values
            for col in cols}


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


def _write_prequel(template, writer):
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


def _generate_output(in_row, config):
    # Map the columns.
    out_row = _map_row(in_row, config)
    # Expand each embedded config into a separate row.
    if config.embedded:
        out_rows = _generate_embedded_output(in_row, out_row, config)
    else:
        out_rows = (out_row,)
    for out_row in out_rows:
        if config.callback:
            for row in _apply_callback(in_row, config, out_row):
                yield row
        else:
            yield out_row


def _apply_callback(in_row, config, out_row):
    return config.callback(in_row, config.in_col_ndx_map,
                           config.out_col_ndx_map, out_row)


def _map_row(in_row, config):
    # Map the output columns to output values.
    cols_values_tuples = [(config.names[col], _map_values(col, in_row[i], config))
                          for i, col in enumerate(config.in_col_ndx_map)
                          if col in config.names]
    col_value_dict = {col: values[i]
                      for cols, values in cols_values_tuples
                      for i, col in enumerate(cols)}
    out_row = [col_value_dict.get(col) for col in config.out_col_ndx_map]
    # Set the statically defined column values.
    for out_col, value in config.static.items():
        # Get the static definition output column index.
        out_col_ndx = config.out_col_ndx_map[out_col]
        out_row[out_col_ndx] = value

    return out_row


def _map_values(in_col, value, config):
    out_cols = config.names[in_col]
    col_values = [config.values_dict.get(out_col)
                  for out_col in out_cols]
    return [value_dict.get(value, value) if value_dict else value
            for value_dict in col_values]


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
    """
    Copies the given output row and assigns the given pattern match
    group values to the corresponding output row columns defined by
    the configuration.

    :return: the new output row
    """
    # Make a new output row.
    row = out_row.copy()
    # Set the embedded column.
    row[out_col_ndx] = value
    # Assign the match group values to the associated output column.
    for grp_col, grp_value in group_values.items():
        # Map the output columns to output values.
        value_dict = config.values_dict.get(grp_col)
        value = value_dict.get(grp_value, grp_value) if value_dict else grp_value
        col_ndx = config.out_col_ndx_map[grp_col]
        row[col_ndx] = value

    return row


def _add_defaults(def_callback, in_row, in_col_ndx_map, out_col_ndx_map,
                  out_row, callback=None):
    """
    Assigns defaults to the generated output rows.

    :return: the generated output rows
    :rtype: list
    """
    if callback:
        out_rows = callback(in_row, in_col_ndx_map, out_col_ndx_map, out_row)
    else:
        out_rows = [out_row]
    for row in out_rows:
        def_callback(row, out_col_ndx_map)

    return out_rows


def _read_csv(in_file):
    """
    Reads the given comma- or tab-separated file.

    :param in_file: the `.csv` CSV file or `.txt` TSV file
    :yield: each non-empty input row
    """
    kwargs = {}
    if in_file.endswith('.txt'):
        kwargs['delimiter'] = '\t'
    with open(in_file) as fd:
        reader = csv.reader(fd, **kwargs)
        for row in reader:
            # Skip empty rows.
            if row and any(row):
                yield row


def _read_excel(in_file, sheet=None):
    """
    Reads the given Excel file.

    :param in_file: the `.xslx` workbook file
    :param sheet: the optional worksheet (default is the worksheet
        displayed when the workbook was last saved)
    :yield: each worksheet row as a list of cell values
    """
    wb = openpyxl.load_workbook(in_file, read_only=True)
    ws = wb.get_sheet_by_name(sheet) if sheet else wb.active
    for row in ws:
        if row:
            yield [cell.value for cell in row]
