from importlib.machinery import SourceFileLoader
import os
from types import SimpleNamespace

# load actions module
path = os.path.join(os.path.dirname(__file__), '..', 'actions', 'actions.py')
path = os.path.normpath(path)
loader = SourceFileLoader('rasa_actions', path)
mod = loader.load_module()

# prepare fake dispatcher
class DummyDispatcher:
    def __init__(self):
        self.messages = []
    def utter_message(self, text=None, **kwargs):
        self.messages.append(text)

# fake tracker with slots
class DummyTracker:
    def __init__(self, slots=None):
        self._slots = slots or {}
    def get_slot(self, name):
        return self._slots.get(name)

# test with coords near a point (example lat/lon)
dispatcher = DummyDispatcher()
tracker = DummyTracker({'user_lat': 10.762622, 'user_lon': 106.660172, 'max_centers': 3})

action = mod.ActionGetCenters()
action.run(dispatcher, tracker, {})
print('Messages:')
print('\n'.join(dispatcher.messages))
