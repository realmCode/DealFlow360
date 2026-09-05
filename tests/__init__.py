"""DealFlow360 test suite.

This file exists for a specific reason: an unrelated third-party package in the
user site-packages directory installs a top-level ``tests`` package. Without an
``__init__.py`` here, the local ``tests`` directory is only a *namespace*
portion, and Python's import machinery prefers a regular package found later on
``sys.path`` over a namespace portion found earlier. The installed package
therefore shadowed this one and ``from tests.conftest import ...`` failed with
``ImportError: cannot import name 'TMP' from 'tests'``.

Making this directory a regular package means the ``pythonpath = .`` entry in
``pytest.ini`` resolves ``tests`` here first.
"""
