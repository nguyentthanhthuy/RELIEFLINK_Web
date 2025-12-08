import os
import sys
from pprint import pprint

# ensure package path
root = os.path.dirname(os.path.dirname(__file__))
if root not in sys.path:
    sys.path.insert(0, root)

from actions.actions import ActionGetCenters

class DummyDispatcher:
    def __init__(self):
        self.messages = []
    def utter_message(self, text=None, **kwargs):
        msg = {'text': text}
        msg.update(kwargs)
        self.messages.append(msg)
        print('UTTER_MESSAGE:', msg)

class DummyTracker:
    def __init__(self, slots=None):
        self._slots = slots or {}
    def get_slot(self, name):
        return self._slots.get(name)

if __name__ == '__main__':
    # ensure DATABASE_URL is read from env if set
    print('DATABASE_URL=', os.environ.get('DATABASE_URL'))
    dispatcher = DummyDispatcher()
    tracker = DummyTracker()
    action = ActionGetCenters()
    result = action.run(dispatcher, tracker, {})
    print('ACTION_RESULT:', result)
