import types
from typing import Dict, Text, Union

from guest_objects import GuestModule


class InterpreterState:

    def __init__(self):
        self.sys_modules = {
        }  # type: Dict[Text, Union[types.ModuleType, GuestModule]]
