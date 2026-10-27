"""Find a push in a Bash command by its shell words, never by its text.

A word that is `git`, bare or under a path, followed by git's own options and then the word `push`
is a push wherever it stands in the command: after `&&`, `;`, `|` or a newline, inside `( )`,
`$( )` or backticks, behind an assignment, a keyword or a wrapper such as `sudo`, `env` or `xargs`.
The command a shell is given with `-c`, the words of an `eval`, and a quoted word that holds a
command substitution and no here-document are read the same way. So `echo "git push"`, `git
pushd`, `git stash push` and a commit message that says `git push` are no push. A variable where
git's options go is passed over as an option. A command that cannot be split into words, because
a quote never closes, is held as a push when it has the words `git` and `push`.

Two pushes are not found: one inside an interpreter string, such as `python3 -c "...git push..."`,
and one behind a git alias.
"""

import re
import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

GIT = 'git'
PUSH = 'push'
PUSH_WORDS = (re.compile(rf'\b{GIT}\b'), re.compile(rf'\b{PUSH}\b'))
GIT_OPTIONS_WITH_A_VALUE = frozenset({
    '-C',
    '-c',
    '--git-dir',
    '--work-tree',
    '--namespace',
    '--super-prefix',
    '--config-env',
    '--attr-source',
})
OPTION_OR_VARIABLE = ('-', '$')
SHELLS = frozenset({'sh', 'bash', 'zsh', 'dash', 'ksh'})
EVAL = 'eval'
SHELL_OPERATORS = '();<>|&`'
COMMAND_SUBSTITUTIONS = ('$(', '`')
HERE_DOCUMENT = '<<'
LINE_CONTINUATION = '\\\n'


def shell_words(command: str) -> list[str] | None:
    lexer = shlex.shlex(
        command.replace(LINE_CONTINUATION, ''), posix=True, punctuation_chars=SHELL_OPERATORS
    )
    lexer.whitespace_split = True
    lexer.commenters = ''
    try:
        return list(lexer)
    except ValueError:
        return None


def program(word: str) -> str:
    return word.rpartition('/')[2]


def git_subcommand(arguments: Sequence[str]) -> str | None:
    position = 0
    while position < len(arguments) and arguments[position].startswith(OPTION_OR_VARIABLE):
        position += 2 if arguments[position] in GIT_OPTIONS_WITH_A_VALUE else 1

    return arguments[position] if position < len(arguments) else None


def is_command_option(word: str) -> bool:
    return word.startswith('-') and not word.startswith('--') and 'c' in word


def command_of_shell(arguments: Sequence[str]) -> str | None:
    after_option = next(
        (position + 1 for position, word in enumerate(arguments) if is_command_option(word)), None
    )
    if after_option is None or after_option >= len(arguments):
        return None

    return arguments[after_option]


def nested_command(words: Sequence[str], position: int) -> str | None:
    word = words[position]
    if program(word) == EVAL:
        return ' '.join(words[position + 1 :])

    if program(word) in SHELLS:
        return command_of_shell(words[position + 1 :])

    is_operator = word.strip(SHELL_OPERATORS) == ''
    substitutes = any(mark in word for mark in COMMAND_SUBSTITUTIONS)
    return word if substitutes and not is_operator and HERE_DOCUMENT not in word else None


def pushes_at(words: Sequence[str], position: int) -> bool:
    if program(words[position]) == GIT:
        return git_subcommand(words[position + 1 :]) == PUSH

    nested = nested_command(words, position)
    return nested is not None and names_a_push(nested)


def has_the_words_of_a_push(text: str) -> bool:
    return all(word.search(text) is not None for word in PUSH_WORDS)


def names_a_push(command: str) -> bool:
    words = shell_words(command)
    if words is None:
        return has_the_words_of_a_push(command)

    return any(pushes_at(words, position) for position in range(len(words)))
