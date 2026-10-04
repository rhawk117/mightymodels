from collections.abc import Callable, Sequence

import pytest
from vibe_code_cli.subagent.tests.support import SECTIONS, AgentRoot, agent_text, section_text

type SectionWriter = Callable[[Sequence[str]], str]


class TestFrontmatterBlock:
    NO_BLOCK = 'Notes about agents, no frontmatter.\n'
    TEXT_BEFORE_THE_OPENING_LINE = '\n' + agent_text()
    BLOCK_NEVER_CLOSED = (
        '---\nname: demo-agent\ndescription: Reviews code. Use when asked.\n\n' + section_text()
    )
    PLUGIN_NOTES = 'Notes, no frontmatter.\n'

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param(NO_BLOCK, id='no-block'),
            pytest.param(TEXT_BEFORE_THE_OPENING_LINE, id='text-before-the-opening-line'),
            pytest.param(BLOCK_NEVER_CLOSED, id='block-never-closed'),
        ],
    )
    def test_va_3_la_1_la_2_file_without_a_frontmatter_block_is_an_error_in_claude_agents(
        self, subagent_root: AgentRoot, text: str
    ) -> None:
        code, output = subagent_root.check(text)

        assert code == 1
        assert 'error: no frontmatter block' in output

    def test_va_3_la_1_la_2_are_left_to_the_builtin_in_a_plugin_agents_directory(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.PLUGIN_NOTES, plugin=True)

        assert code == 0
        assert 'frontmatter block' not in output


class TestName:
    NAME_OF_THE_WRONG_TYPE = agent_text({'name': '[a, b]'})
    NO_NAME = agent_text({'name': None})

    @pytest.mark.parametrize('name', [pytest.param(None, id='None'), pytest.param('', id='')])
    def test_va_5_la_12_missing_name_is_an_error_in_claude_agents(
        self, subagent_root: AgentRoot, name: str | None
    ) -> None:
        code, output = subagent_root.check(agent_text({'name': name}))

        assert code == 1
        assert 'error: name is missing or empty' in output

    def test_a_name_of_the_wrong_type_prints_the_decoder_message(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.NAME_OF_THE_WRONG_TYPE)

        assert code == 1
        assert 'error: Expected `str | null`, got `array` - at `$.name`' in output

    def test_sa_c11_missing_name_in_a_plugin_agents_directory_is_a_warning(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.NO_NAME, plugin=True)

        assert code == 0
        assert 'warning: name is missing or empty' in output
        assert 'loads under its filename' in output

    @pytest.mark.parametrize(
        'name',
        [
            pytest.param('Demo_Agent', id='Demo_Agent'),
            pytest.param('my:agent', id='my:agent'),
            pytest.param('-lead', id='-lead'),
            pytest.param('Demo Agent', id='Demo Agent'),
        ],
    )
    def test_va_7_la_13_invalid_name_is_an_error(self, subagent_root: AgentRoot, name: str) -> None:
        code, output = subagent_root.check(agent_text({'name': f'"{name}"'}))

        assert code == 1
        assert 'error: name' in output
        assert 'must be lowercase letters, digits and single hyphens' in output

    def test_sa_a1_file_name_need_not_match_the_name_or_carry_a_suffix(
        self, subagent_root: AgentRoot
    ) -> None:
        path = subagent_root.write(agent_text(), name='another-name.md')

        code, output = subagent_root.run(path)

        assert code == 0
        assert 'filename' not in output


class TestTools:
    NO_TOOLS = agent_text({'tools': None})
    COMMAND_TOOL_NAMES_OF_ANOTHER_HOST = agent_text({'tools': 'Read, execute, runCommands'})
    WITH_DISALLOWED_TOOLS = agent_text({'disallowedTools': 'Write'})
    DISALLOWED_TOOLS_ALONE = agent_text({'tools': None, 'disallowedTools': 'Write'})
    BASH_WITHOUT_MAX_TURNS = agent_text({'tools': 'Read, Bash(git status *)'})
    BASH_WITH_MAX_TURNS = agent_text({'tools': 'Read, Bash', 'maxTurns': '20'})
    EVERY_ENTRY_MISSPELLED = agent_text({'tools': 'Grpe, Raed'})

    def test_va_12_la_14_omitted_tools_is_a_warning(self, subagent_root: AgentRoot) -> None:
        code, output = subagent_root.check(self.NO_TOOLS)

        assert code == 0
        assert "warning: no 'tools' list, so the agent inherits every tool" in output

    @pytest.mark.parametrize(
        'tools',
        [
            pytest.param('Reed, Grep', id='Reed, Grep'),
            pytest.param('read', id='read'),
            pytest.param('github/pull_request_read', id='github/pull_request_read'),
            pytest.param('mcp__', id='mcp__'),
        ],
    )
    def test_va_13_unknown_tool_name_is_an_error(
        self, subagent_root: AgentRoot, tools: str
    ) -> None:
        code, output = subagent_root.check(agent_text({'tools': f'"{tools}"'}))

        assert code == 1
        assert 'is not a Claude Code tool name' in output

    def test_la_15_sa_b1_sa_c14_tools_with_disallowed_tools_is_a_warning(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.WITH_DISALLOWED_TOOLS)

        assert code == 0
        assert "warning: 'disallowedTools' is applied first" in output

    def test_la_15_sa_b1_sa_c14_disallowed_tools_alone_is_recognised_and_quiet(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.DISALLOWED_TOOLS_ALONE)

        assert code == 0
        assert 'disallowedTools' not in output

    def test_la_16_sa_b3_sa_c13_bash_without_max_turns_is_a_warning(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.BASH_WITHOUT_MAX_TURNS)

        assert code == 0
        assert 'warning: agent can run commands but sets no maxTurns' in output

    def test_la_16_sa_b3_sa_c13_max_turns_silences_it(self, subagent_root: AgentRoot) -> None:
        code, output = subagent_root.check(self.BASH_WITH_MAX_TURNS)

        assert code == 0
        assert 'maxTurns' not in output

    def test_sa_c13_command_tool_names_of_another_host_are_not_command_tools(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.COMMAND_TOOL_NAMES_OF_ANOTHER_HOST)

        assert code == 1
        assert "'execute' is not a Claude Code tool name" in output
        assert 'maxTurns' not in output

    @pytest.mark.parametrize(
        'tools',
        [
            pytest.param(
                'Read, Grep, Glob, Edit, Write, WebFetch, WebSearch, TodoWrite',
                id='Read, Grep, Glob, Edit, Write, WebFetch, WebSearch, TodoWrite',
            ),
            pytest.param('Agent(worker, researcher), Read', id='Agent(worker, researcher), Read'),
            pytest.param('Task, Skill', id='Task, Skill'),
            pytest.param(
                'mcp__github, mcp__github__create_issue, mcp__github__*',
                id='mcp__github, mcp__github__create_issue, mcp__github__*',
            ),
            pytest.param('[Read, Grep]', id='[Read, Grep]'),
        ],
    )
    def test_sa_a7_sa_a9_claude_code_tool_names_and_mcp_references_are_accepted(
        self, subagent_root: AgentRoot, tools: str
    ) -> None:
        code, output = subagent_root.check(agent_text({'tools': tools}))

        assert code == 0
        assert 'tool' not in output

    @pytest.mark.parametrize('tools', [pytest.param('[]', id='[]'), pytest.param('""', id='""')])
    def test_sa_a8_empty_tools_list_means_no_tools_and_is_accepted(
        self, subagent_root: AgentRoot, tools: str
    ) -> None:
        code, output = subagent_root.check(agent_text({'tools': tools}))

        assert code == 0
        assert 'PASS demo-agent.md: 0 error(s), 0 warning(s)' in output

    def test_sa_a8_list_whose_every_entry_is_misspelled_is_an_error(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.EVERY_ENTRY_MISSPELLED)

        assert code == 1
        assert output.count('is not a Claude Code tool name') == 2


class TestSectionStructure:
    @pytest.fixture
    def closing_tag_with_no_open_section(self, sections: SectionWriter) -> str:
        body = sections(SECTIONS[:2]) + '</workflow>\n' + sections(SECTIONS[2:])
        return agent_text(body=body)

    @pytest.fixture
    def section_never_closed(self, sections: SectionWriter) -> str:
        return agent_text(body='<role>\nText.\n\n' + sections(SECTIONS[1:]))

    @pytest.fixture
    def missing_required_section(self, sections: SectionWriter) -> str:
        return agent_text(body=sections(SECTIONS[:3] + SECTIONS[4:]))

    @pytest.fixture
    def required_sections_out_of_order(self, sections: SectionWriter) -> str:
        return agent_text(body=sections(('role', 'workflow', 'context', *SECTIONS[3:])))

    @pytest.fixture
    def body_wrapped_in_a_root_element(self, sections: SectionWriter) -> str:
        return agent_text(body='<agent_prompt>\n' + sections(SECTIONS) + '</agent_prompt>\n')

    def test_va_15a_closing_tag_with_no_open_section_is_an_error(
        self, subagent_root: AgentRoot, closing_tag_with_no_open_section: str
    ) -> None:
        code, output = subagent_root.check(closing_tag_with_no_open_section)

        assert code == 1
        assert 'closes </workflow> but the open section is <none>' in output

    def test_va_15b_section_never_closed_is_an_error(
        self, subagent_root: AgentRoot, section_never_closed: str
    ) -> None:
        code, output = subagent_root.check(section_never_closed)

        assert code == 1
        assert 'error: <role> is never closed' in output

    def test_va_15d_missing_required_section_is_an_error(
        self, subagent_root: AgentRoot, missing_required_section: str
    ) -> None:
        code, output = subagent_root.check(missing_required_section)

        assert code == 1
        assert 'error: required section <constraints> is missing' in output

    def test_va_15e_required_sections_out_of_order_is_an_error(
        self, subagent_root: AgentRoot, required_sections_out_of_order: str
    ) -> None:
        code, output = subagent_root.check(required_sections_out_of_order)

        assert code == 1
        assert 'error: required sections out of order' in output

    def test_va_15f_body_wrapped_in_a_root_element_is_an_error(
        self, subagent_root: AgentRoot, body_wrapped_in_a_root_element: str
    ) -> None:
        code, output = subagent_root.check(body_wrapped_in_a_root_element)

        assert code == 1
        assert 'wrapped in a single root element <agent_prompt>' in output


class TestBodyContent:
    EMPTY_BODY = agent_text(body='\n')
    MODEL_DIRECTIVE = agent_text(body=section_text() + 'MODEL REQUIREMENT: run on opus.\n')
    REFERENCE_TEMPLATE_SHAPE = agent_text(
        body=(
            '<role>\nYou are demo-agent, a code reviewer. You return a review.\n</role>\n\n'
            '<context>\nThe repository holds Python.\n</context>\n\n'
            '<workflow>\n1. Read the diff.\n2. Check each change.\n</workflow>\n\n'
            '<constraints>\n- Never edit files, because you only review.\n</constraints>\n\n'
            '<output_format>\nReturn exactly:\n\n## Summary\n\n## Findings\n</output_format>\n\n'
            '<verification>\nRe-read each cited line.\n</verification>\n'
        )
    )

    @pytest.fixture
    def stray_tag(self, sections: SectionWriter) -> str:
        return agent_text(body=sections(SECTIONS) + '<widget>\nx\n</widget>\n')

    @pytest.fixture
    def bare_angle_bracket_and_ampersand(self, sections: SectionWriter) -> str:
        return agent_text(body=sections(SECTIONS) + 'Use a < b when comparing & counting.\n')

    @pytest.fixture
    def doctype_declaration(self, sections: SectionWriter) -> str:
        return agent_text(body=sections(SECTIONS) + '<!DOCTYPE foo>\n')

    def test_va_15c_stray_tag_is_a_warning(self, subagent_root: AgentRoot, stray_tag: str) -> None:
        code, output = subagent_root.check(stray_tag)

        assert code == 0
        assert 'warning: <widget> is not a section tag' in output

    def test_va_15g_bare_angle_bracket_and_ampersand_is_a_warning(
        self, subagent_root: AgentRoot, bare_angle_bracket_and_ampersand: str
    ) -> None:
        code, output = subagent_root.check(bare_angle_bracket_and_ampersand)

        assert code == 0
        assert 'warning: not strictly parseable' in output

    def test_va_15h_doctype_declaration_is_a_warning(
        self, subagent_root: AgentRoot, doctype_declaration: str
    ) -> None:
        code, output = subagent_root.check(doctype_declaration)

        assert code == 0
        assert 'warning: document and entity declarations are not supported' in output

    def test_la_9_empty_body_is_an_error(self, subagent_root: AgentRoot) -> None:
        code, output = subagent_root.check(self.EMPTY_BODY)

        assert code == 1
        assert "error: the body is empty; it is the agent's system prompt" in output
        assert 'required section' not in output

    def test_la_11_model_directive_in_the_body_is_a_warning(self, subagent_root: AgentRoot) -> None:
        code, output = subagent_root.check(self.MODEL_DIRECTIVE)

        assert code == 0
        assert 'warning: body contains a model-requirement directive' in output

    def test_la_10_sa_c17_body_in_the_reference_template_shape_passes(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.REFERENCE_TEMPLATE_SHAPE)

        assert code == 0
        assert 'PASS demo-agent.md: 0 error(s), 0 warning(s)' in output
        assert 'inputs_expected' not in output
        assert 'output_contract' not in output


class TestDescription:
    NO_TRIGGER = agent_text({'description': 'Reviews code carefully'})
    QUOTED_COLON = agent_text({'description': '"Reviews code. Use when: asked"'})

    def test_la_7_sa_c16_description_without_a_trigger_is_a_warning(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.NO_TRIGGER)

        assert code == 0
        assert 'warning: description states a capability but no trigger condition' in output

    @pytest.mark.parametrize(
        'description',
        [
            pytest.param('Reviews code. Use when: asked for a review', id='yaml-rejects-it'),
            pytest.param('Reviews code. Use when asked, see http://x.y', id='yaml-reads-it'),
        ],
    )
    def test_la_8_sa_c16_unquoted_colon_in_the_description_is_a_warning_not_a_failure_to_check(
        self, subagent_root: AgentRoot, description: str
    ) -> None:
        text = agent_text({'description': description, 'tools': None})

        code, output = subagent_root.check(text)

        assert code == 0
        assert "warning: description contains ':' and is not quoted" in output
        assert 'inherits every tool' in output

    def test_la_8_a_quoted_description_with_a_colon_is_clean(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.QUOTED_COLON)

        assert code == 0
        assert 'is not quoted' not in output


class TestModel:
    @pytest.mark.parametrize(
        'model',
        [
            pytest.param('gpt4', id='gpt4'),
            pytest.param('Sonnet', id='Sonnet'),
            pytest.param('opus[2m]', id='opus[2m]'),
        ],
    )
    def test_la_17_sa_a10_sa_c15_unknown_model_is_an_error(
        self, subagent_root: AgentRoot, model: str
    ) -> None:
        code, output = subagent_root.check(agent_text({'model': model}))

        assert code == 1
        assert f"error: model '{model}' is not a Claude Code alias" in output

    @pytest.mark.parametrize(
        'model',
        [
            pytest.param('sonnet', id='sonnet'),
            pytest.param('opus', id='opus'),
            pytest.param('haiku', id='haiku'),
            pytest.param('fable', id='fable'),
            pytest.param('inherit', id='inherit'),
            pytest.param('claude-opus-5-5', id='claude-opus-5-5'),
            pytest.param('opus[1m]', id='opus[1m]'),
        ],
    )
    def test_sa_a10_sa_c15_aliases_inherit_and_full_ids_are_accepted(
        self, subagent_root: AgentRoot, model: str
    ) -> None:
        code, output = subagent_root.check(agent_text({'model': model}))

        assert code == 0
        assert 'model' not in output


class TestFrontmatterKeys:
    UNKNOWN_KEYS = agent_text({'bogus-field': 'x', 'infer': 'false'})
    BYPASS_PERMISSIONS = agent_text({'permissionMode': 'bypassPermissions'})
    KEYS_IGNORED_IN_PLUGINS = agent_text(
        {
            'permissionMode': 'acceptEdits',
            'hooks': '{}',
            'mcpServers': '[slack]',
            'initialPrompt': 'Go',
        }
    )

    def test_la_18_sa_a14_unknown_key_is_a_warning(self, subagent_root: AgentRoot) -> None:
        code, output = subagent_root.check(self.UNKNOWN_KEYS)

        assert code == 0
        assert "warning: 'bogus-field' is not a documented frontmatter key" in output
        assert "warning: 'infer' is not a documented frontmatter key" in output

    @pytest.mark.parametrize(
        ('key', 'value'),
        [
            pytest.param('initialPrompt', 'Start', id='initialPrompt-Start'),
            pytest.param('experimental', '{cacheTtl: 1h}', id='experimental-{cacheTtl: 1h}'),
            pytest.param('omitClaudeMd', 'true', id='omitClaudeMd-true'),
            pytest.param('skills', '[demo-skill]', id='skills-[demo-skill]'),
            pytest.param('memory', 'project', id='memory-project'),
            pytest.param('isolation', 'worktree', id='isolation-worktree'),
        ],
    )
    def test_sa_b11_sa_b12_sa_c2_documented_keys_are_recognised(
        self, subagent_root: AgentRoot, key: str, value: str
    ) -> None:
        code, output = subagent_root.check(agent_text({key: value}))

        assert code == 0
        assert 'not a documented frontmatter key' not in output

    def test_la_19_sa_c12_bypass_permissions_warning_says_the_main_mode_wins(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.BYPASS_PERMISSIONS)

        assert code == 0
        assert "keeps the main conversation's permission mode" in output
        assert '.vscode' not in output

    def test_sa_b2_sa_b13_permission_mode_is_quiet_in_claude_agents(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.KEYS_IGNORED_IN_PLUGINS)

        assert code == 0
        assert 'ignored' not in output

    @pytest.mark.parametrize(
        ('key', 'value'),
        [
            pytest.param('permissionMode', 'acceptEdits', id='permissionMode-acceptEdits'),
            pytest.param('hooks', '{}', id='hooks-{}'),
            pytest.param('mcpServers', '[slack]', id='mcpServers-[slack]'),
            pytest.param('initialPrompt', 'Go', id='initialPrompt-Go'),
        ],
    )
    def test_sa_b2_sa_b13_four_keys_warn_in_a_plugin_agents_directory(
        self, subagent_root: AgentRoot, key: str, value: str
    ) -> None:
        code, output = subagent_root.check(agent_text({key: value}), plugin=True)

        assert code == 0
        assert f"warning: '{key}' is ignored in a plugin agents/ directory" in output

    def test_sa_b2_sa_b13_bypass_permissions_in_a_plugin_gets_only_the_ignored_warning(
        self, subagent_root: AgentRoot
    ) -> None:
        code, output = subagent_root.check(self.BYPASS_PERMISSIONS, plugin=True)

        assert code == 0
        assert output.count('warning:') == 1
        assert 'is ignored in a plugin agents/ directory' in output
