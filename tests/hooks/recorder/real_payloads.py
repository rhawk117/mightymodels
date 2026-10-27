"""AskUserQuestion `toolUseResult` objects copied from this project's Claude Code transcripts.

Keys and nesting are as recorded. Long question, description, preview and note strings are
shortened, and every answer still equals its question's key in `answers`.
"""

PLAIN_QUESTION = 'Which part of .ref is the different thread approach you want gone?'
PLAIN_TOOLS_QUESTION = 'What does decompose the tool list into separate tools mean?'
PREVIEW_QUESTION = 'Should T4 also port the redaction hit count and the length-limited variant?'
PREVIEW_TEXT = '### T4 (sm): redaction into RedactedText, with hit count and the length limit'
NOTES_QUESTION = (
    'Fix the unit-of-work group list (each bundle = repositories opened over one Unit):'
)
NOTES_TEXT = 'These are good but closing is a terrible ticket name; use ticket_closing.'
MULTI_GATE_QUESTION = 'Round 2 gate. Both design changes now have their facts. How do we proceed?'
MULTI_E48_QUESTION = 'How should e48 be resolved now that the facts are in?'
MULTI_SPLIT_QUESTION = 'Which parts of the main-session/subagent hook split do you want gone?'
MULTI_SPLIT_ANSWER = 'Bash wrappers and fallbacks, Two PreToolUse entries'


def option(label: str, description: str) -> dict[str, str]:
    return {'label': label, 'description': description}


PLAIN: dict[str, object] = {
    'questions': [
        {
            'question': PLAIN_QUESTION,
            'header': 'Threads',
            'options': [
                option('Sync work sent to worker threads', 'Handlers push sync calls to a thread.'),
                option('A dedicated background thread', 'A long-lived thread owned by the server.'),
                option('Not sure, have scouts find it', 'Round one locates every threading use.'),
            ],
            'multiSelect': False,
        },
        {
            'question': PLAIN_TOOLS_QUESTION,
            'header': 'Tools',
            'options': [
                option('One MCP tool per action (Recommended)', 'Each action gets its own schema.'),
                option('Regroup actions by concept', 'Keep some multi-action tools.'),
            ],
            'multiSelect': False,
        },
    ],
    'answers': {
        PLAIN_QUESTION: 'Not sure, have scouts find it',
        PLAIN_TOOLS_QUESTION: 'One MCP tool per action (Recommended)',
    },
    'annotations': {},
}

PREVIEW: dict[str, object] = {
    'questions': [
        {
            'question': PREVIEW_QUESTION,
            'header': 'T4 scope',
            'options': [
                {
                    'label': 'Port whole module (Recommended)',
                    'description': 'T4 gains AC-3.',
                    'preview': PREVIEW_TEXT,
                },
                option('Patterns only, as planned', 'T4 stays at AC-1 and AC-2.'),
            ],
            'multiSelect': False,
        }
    ],
    'answers': {PREVIEW_QUESTION: 'Port whole module (Recommended)'},
    'annotations': {PREVIEW_QUESTION: {'preview': PREVIEW_TEXT}},
}

NOTES: dict[str, object] = {
    'questions': [
        {
            'question': NOTES_QUESTION,
            'header': 'UoW groups',
            'options': [
                {
                    'label': 'Six groups',
                    'description': '(recommended) ticket, task, review, close, journal, snapshot',
                    'preview': 'TicketWork     tickets, investigations(ledger)',
                },
                option("I don't know", 'Record as Open'),
            ],
            'multiSelect': False,
        }
    ],
    'answers': {NOTES_QUESTION: "I don't know"},
    'annotations': {NOTES_QUESTION: {'notes': NOTES_TEXT}},
}

AFK: dict[str, object] = {
    'questions': [
        {
            'question': 'T10 is verified, but its repository has no read-back. When is it added?',
            'header': 'T10 gap',
            'options': [
                option('Residual now (Recommended)', 'Add R1 before T11.'),
                option('Carry to T24', "T24's investigation service adds it."),
            ],
            'multiSelect': False,
        }
    ],
    'answers': {},
    'annotations': {},
    'afkTimeoutMs': 300000,
}

MULTI: dict[str, object] = {
    'questions': [
        {
            'question': MULTI_GATE_QUESTION,
            'header': 'Round 2',
            'options': [option('Dig further (Recommended)', 'Run the Next items.')],
            'multiSelect': False,
        },
        {
            'question': MULTI_E48_QUESTION,
            'header': 'e48',
            'options': [option('Keep e48, all tools async def (Recommended)', 'No split.')],
            'multiSelect': False,
        },
        {
            'question': MULTI_SPLIT_QUESTION,
            'header': 'Hook split',
            'options': [
                option('Bash wrappers and fallbacks', 'The shell wrappers.'),
                option('Two PreToolUse entries', 'The duplicated entries.'),
            ],
            'multiSelect': True,
        },
    ],
    'answers': {
        MULTI_GATE_QUESTION: 'Dig further (Recommended)',
        MULTI_E48_QUESTION: 'Keep e48, all tools async def (Recommended)',
        MULTI_SPLIT_QUESTION: MULTI_SPLIT_ANSWER,
    },
    'annotations': {},
}
