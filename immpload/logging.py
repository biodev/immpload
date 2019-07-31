# Absolute import (the default in a future Python release) resolves
# the logging import as the Python standard logging module rather
# than this module of the same name.
from __future__ import absolute_import
import os
import logging
import logging.config
import yaml
from . import collections as qicollections

LOG_CFG_ENV_VAR = 'LOG_CONFIG'
"""The user-defined environment variable logging configuration file path."""

LOG_CFG_FILE = 'logging.yaml'
"""The optional current working directory logging configuration file name."""

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
"""The ``immpload`` package directory."""

DEF_LOG_CFG = os.path.join(BASE_DIR, 'conf', LOG_CFG_FILE)
"""The default logging configuration file path."""


def logger(name):
    """
    This method is the preferred way to obtain a logger.

    Example:

    >>> from immpload.logging import logger
    >>> logger(__name__).debug("Starting my application...")

    :Note: Python ``nosetests`` captures log messages and only
        reports them on failure.

    :param name: the caller's context ``__name__``
    :return: the Python Logger instance
    """
    # Configure on demand.
    if not hasattr(logger, 'configured'):
        configure(name)

    return logging.getLogger(name)


def configure(*names, **opts):
    """
    Configures logging. The logging configuration is obtained from from
    the given keyword arguments and the YAML_ logging configuration file.

    The ``opts`` keyword arguments specify simple logging parameters that
    override the configuration file settings. The keyword arguments
    can include the *filename* and *level* short-cuts, which are handled
    as follows:

    - if the *filename* is None, then file logging is disabled. Otherwise,
      the file handler file name is set to the *filename* value.

    - The *level* is set for the logger. In addition, if the logger has a
      file handler, then that file handler level is set. Otherwise, the
      console handler level is set.

    The logging configuration file ``formatters``, ``handlers`` and
    ``loggers`` sections are updated incrementally. For example, the
    ``conf/logging.yaml`` source distribution file defines the ``default``
    formatter ``format`` and ``datefmt``. If the ``logging.yaml`` file in
    the current directory overrides the ``format`` but not the ``datefmt``,
    then the default ``datefmt`` is retained rather than unset. Thus, a custom
    logging configuration file need define only the settings which override
    the default configuration.

    By default, ``ERROR`` level messages are written to the  console.
    If the log file is set, then the default logger writes ``INFO`` level
    messages to a rotating log file.

    If the file handler is enabled, then this :meth:`immpload.logging.configure`
    method ensures that the log file parent directory exists.

    Examples:

    - Write to the log:

      >>> from immpload.logging import logger
      >>> logger(__name__).debug("Started the application...")

      or, in a class instance:

      >>> from immpload.logging import logger
      >>> class MyApp(object):
      ...     def __init__(self):
      ...         self._logger = logger(__name__)
      ...     def start(self):
      ...         self._logger.debug("Started the application...")

    - Write debug messages to the file log:

      >>> import immpload
      >>> immpload.logging.configure(level='DEBUG')

    - Set the log file:

      >>> import immpload
      >>> immpload.logging.configure(filename='log/myapp.log')

    - Define your own logging configuration:

      >>> import immpload
      >>> immpload.logging.configure('/path/to/my/conf/logging.yaml')

    .. _YAML: http://www.yaml.org

    :param names: the logging contexts (default root)
    :param opts: the Python ``logging.conf`` options, as well as the
        following short-cut:
    :keyword level: the file handler log level
    """
    # Load the configuration file.
    config = _load_config()

    # Extract the logger options from the config options.
    logger_opts = {k: opts.pop(k) for k in ['filename', 'level'] if k in opts}

    # The filename option overrides the configuration files.
    fname = logger_opts.get('filename')
    if fname:
        # Reset the log file.
        config['handlers']['file']['filename'] = fname

    # Make the loggers dictionary, if necessary.
    if not 'loggers' in config:
        config['loggers'] = {}
    # Configure the loggers.
    for name in names:
        _configure_logger(name, config, **logger_opts)

    # Ensure that all log file parent directories exist.
    for handler in config['handlers'].values():
        log_file = handler.get('filename')
        if log_file:
            # Make the log file parent directory, if necessary.
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            # Make the log file path absolute for clarity.
            handler['filename'] = os.path.abspath(log_file)

    # Configure logging.
    logging.config.dictConfig(config)

    # Set the logger configured flag.
    setattr(logger, 'configured', True)


def _configure_logger(name, config, **opts):
    loggers = config['loggers']
    logger = loggers.get(name)
    if not logger:
        # Copy the root configuration.
        logger = loggers[name] = dict(propagate=False)
        logger.update(config['root'])

    # If file logging is set, then direct messages to the file.
    if opts.get('filename'):
        logger['handlers'] = ['file']

    # The log level is set in both the logger and the handler,
    # and the more restrictive level applies. Therefore, set
    # the log level in both places.
    level = opts.pop('level', None)
    if level:
        # Set the logger level.
        logger['level'] = level
        # Set the handler levels.
        for handler_key in logger['handlers']:
            handler = config['handlers'][handler_key]
            handler['level'] = level
    # Add the other options, if any.
    qicollections.update(config, opts, recursive=True)

    # Ensure that all log file parent directories exist.
    for handler in config['handlers'].values():
        log_file = handler.get('filename')
        if log_file:
            # Make the log file parent directory, if necessary.
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            # Make the log file path absolute for clarity.
            handler['filename'] = os.path.abspath(log_file)


def _load_config():
    """
    Loads the logger configuration file.

    :return: the logging configuration dictionary
    """
    # The config file.
    config = _load_config_file(DEF_LOG_CFG)

    return config


def _load_config_file(filename):
    """
    Loads the given logger configuration file.

    :param: filename: the log configuration file path
    :return: the parsed configuration parameter dictionary
    """
    with open(filename) as fs:
        return yaml.load(fs)
