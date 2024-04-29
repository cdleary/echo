from typing import Dict, Union, Optional, Any

import types

EModule = Any
StatefulFrame = Any


class InterpreterState:

    last_frame: Optional[StatefulFrame]

    def __init__(self, script_directory: Optional[str]):
        self.sys_modules: Dict[str, Union[types.ModuleType, EModule]] = {}

        # sys.path: "module search path; path[0] is the script directory, else
        # ''"
        self.paths = [script_directory] if script_directory else []
        self.last_frame = None
        self.import_depth = 0
