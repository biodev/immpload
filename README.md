 # Immpload - Immport upload preparation

`immpload` extracts input data files into files formatted from
[Immport](http://www.immport.org/home) upload templates.

## Prerequisites

* Python3 with the [pip](https://pypi.org/project/pip/) package installer

## Installation

1. Make a workspace directory.

2. Install `immpload`:

       pip install immpload

## Usage

The simplest case copies input columns whose name matches
the corresponding output
[Immport template](https://www.immport.org/resources/dataTemplates)
column:
```
$ immpload subjectAnimals /path/to/input/subjects.txt
```
which will create the Immport upload file `subjectAnimals.txt`
in the current directory. To place the output in a different
directory, use the `-o` or `--outDir` option:
```
$ immpload -o /path/to/output subjectAnimals /path/to/input/subjects.xslx
```
Note that the input can be either a `.xslx` Excel spreadsheet
or a tab-delimited text file.

The command:
```
$ immpload --help
```
shows all `immpload` arguments and options.

It is often useful to specify the conversion mapping in a
[YAML](https://en.wikipedia.org/wiki/YAML) configuration file.
For example, the following configuration:
```
columns:
    Subject ID: ID
    Arm Or Cohort ID: Cohort
```
converts the `ID` and `Cohort` input values to `Subject ID` and
`Arm Or Cohort ID` output values, resp. The command is invoked
with the `-c` or `--config` option, e.g:
```
$ immpload -o /path/to/output --config /path/to/conf/subjects.yaml \
           subjectAnimals /path/to/input/subjects.xslx
```

The configuration can include value mappings, e.g.:
```
values:
    Species: Mus musculus
```
sets the output `Species` to `Mus musculus` for all rows.

The configuration:
```
columns:
    Gender: Sex
values:
    Gender:
        n/a: Not Specified
```
transforms the input `Sex` value `n/a` to the output `Gender` value
`Not Specified`. Other input values are copied without change.

`immpload` can flatten each input row into several output rows based
on matching input column names against a pattern. The configuration:
```
columns:
    Subject ID: ID
    Arm Or Cohort ID: Cohort
    Study Day: day
patterns:
    Result Value Reported: D(?P<day>\d+)$
```
converts an input row with columns `D1`, `D2` and `D3` into three
output rows with column `Study Day` values `1`, `2` and `3`
and `Result Value Reported` values given by the `D1`, `D2` and `D3`
input values, resp.

`immpload` supplies certain required output columns with a reasonable
default, as follows:

* Assessments
    * `Planned Visit ID` - `Study ID` followed by `d` and the `Study Day`
    * `Panel Name Reported` - copied from the `Assessment Type`
    * `Assessment Panel ID` - derived from the `Panel Name Reported`
    * `User Defined ID` - derived from the `Subject ID`, `Planned Visit ID`
      and `Component Name Reported`

For advanced usage, the `immpload` Python module can be used directly
in a Python script with a callback function, e.g.:
```
from immpload import munger

def add_results(in_row, in_col_ndx_map, out_col_ndx_map, out_row):
    """
    Modifies the output row after the configuration-based conversion.

    :param: in_row: the input data row
    :param: in_col_ndx_map: the input {column: index} dictionary
    :param: out_col_ndx_map: the output {column: index} dictionary
    :param: out_row :the output row
    :return: a list of rows derived from the given output row
    """
    # Modify out_row or create new output rows...
    return [out_row]

# Convert the input file.
munger.munge('assessments', /path/to/input.xslx, callback=add_results)
```

The `munger.munge` method signature is as follows:
```
def munge(template, *in_files, config=None, out_dir=None,
          sheet=None, input_filter=None, callback=None, **kwargs):
    """
    Builds the Immport upload file for the given input file.
    The template is a supported Immport template name, e.g.
    `assessments`. The output is the Immport upload file,
    e.g. `assessments,txt`, placed in the output directory.

    The key word arguments (_kwargs_) are static output
    _column_`=`_value_ definitions that are applied to every
    output row. The column name can be underscored, e.g.
    `Study_ID`.

    :param template: the required Immport template name
    :param in_files: the input file(s) to munge
    :param config: the configuration dictionary or file name
    :param out_dir: the target location (default current directory)
    :param sheet: for an Excel workbook input file, the sheet to open
    :param input_filter: optional generator which has parameter
        input row and yields valid rows
    :param callback: optional callback with parameters
        in_row, in_col_ndx_map, out_col_ndx_map and out_row returning
        an array of rows to write to the output file
    :param kwargs: the optional static _column_`=`_value_ definitions
    :return: the output file name
    """
```
