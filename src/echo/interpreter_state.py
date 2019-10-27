import types
from typing import Dict, Text, Union, Optional, Any

GuestModule = Any


class InterpreterState:

    def __init__(self, script_directory: Optional[Text]):
        self.sys_modules = {
        }  # type: Dict[Text, Union[types.ModuleType, GuestModule]]

        # sys.path: "module search path; path[0] is the script directory, else
        # ''"
        self.paths = [script_directory] if script_directory else []
