import types
from typing import Dict, Text, Union, Optional, Any

GuestModule = Any
StatefulFrame = Any


class InterpreterState:

    last_frame: Optional[StatefulFrame]

    def __init__(self, script_directory: Optional[Text]):
        self.sys_modules = {
        }  # type: Dict[Text, Union[types.ModuleType, GuestModule]]

        # sys.path: "module search path; path[0] is the script directory, else
        # ''"
        self.paths = [script_directory] if script_directory else []
        self.last_frame = None
        self.import_depth = 0
