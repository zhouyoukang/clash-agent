# PyInstaller runtime hook: provide pyexpat stub for compatibility
import importlib
try:
    importlib.import_module('pyexpat')
except ImportError:
    import types
    import sys
    mod = types.ModuleType('pyexpat')
    mod.ErrorString = lambda code: f'XML error {code}'
    mod.errors = type('errors', (), {})()
    mod.ParserCreate = lambda encoding=None, namespace_separator=None: None
    sys.modules['pyexpat'] = mod
