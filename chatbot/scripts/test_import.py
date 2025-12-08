from importlib.machinery import SourceFileLoader
import os
path = os.path.join(os.path.dirname(__file__), '..', 'actions', 'actions.py')
path = os.path.normpath(path)
loader = SourceFileLoader('rasa_actions', path)
mod = loader.load_module()
print([name for name in dir(mod) if name.startswith('Action')])
