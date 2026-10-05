"""Tool calls the server refuses, reported to the caller as messages, not tracebacks."""

from python_harness.core.errors import PythonHarnessError


class ProjectRootUnsetError(PythonHarnessError):
    def __init__(self, variable: str) -> None:
        super().__init__(f'{variable} is not set, so there is no project to read')
        self.variable = variable


class ProjectRootRelativeError(PythonHarnessError):
    def __init__(self, variable: str, declared: str) -> None:
        super().__init__(f'{variable} is {declared!r}, which is not an absolute path')
        self.variable = variable
        self.declared = declared


class DocumentChoiceError(PythonHarnessError):
    def __init__(self) -> None:
        super().__init__('give exactly one of path and text')


class PathsWithDiffBaseError(PythonHarnessError):
    def __init__(self) -> None:
        super().__init__('give paths or diff_base, not both')


class HeadWithoutBaseError(PythonHarnessError):
    def __init__(self, head: str) -> None:
        super().__init__(f'diff_head {head} needs diff_base')
        self.head = head
