import pytest

from caucus.backends import ClaudeCodeBackend, OpenAICompatibleBackend
from caucus.config import Config, ConfigError
from caucus.engine import DEFAULT_PANEL


def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def test_empty_config_uses_defaults(tmp_path):
    config = Config.load(write(tmp_path, ""))
    assert str(config.log) == "decisions.jsonl"
    assert isinstance(config.backend, ClaudeCodeBackend)
    assert config.panel == DEFAULT_PANEL


def test_full_config(tmp_path):
    config = Config.load(
        write(
            tmp_path,
            """
log: state/audit.jsonl
backend:
  type: openai
  model: llama3.1
  base_url: http://localhost:11434/v1
  api_key_env: MY_KEY
panel:
  - name: quant
    charge: Argue from the numbers.
  - name: contrarian
    charge: Take the other side.
""",
        )
    )
    assert str(config.log) == "state/audit.jsonl"
    assert isinstance(config.backend, OpenAICompatibleBackend)
    assert config.backend.model == "llama3.1"
    assert config.backend.base_url == "http://localhost:11434/v1"
    assert config.backend.api_key_env == "MY_KEY"
    assert [a.name for a in config.panel] == ["quant", "contrarian"]


def test_claude_backend_mcp_options(tmp_path):
    config = Config.load(
        write(
            tmp_path,
            """
backend:
  type: claude
  mcp_config: .mcp.json
  allowed_tools:
    - mcp__quotes__get_equity_quotes
""",
        )
    )
    backend = config.backend
    assert isinstance(backend, ClaudeCodeBackend)
    command = backend._command("hello")
    assert command[:3] == ["claude", "-p", "hello"]
    assert "--mcp-config" in command
    assert command[command.index("--mcp-config") + 1] == ".mcp.json"
    assert command[command.index("--allowedTools") + 1] == "mcp__quotes__get_equity_quotes"


@pytest.mark.parametrize(
    "text",
    [
        "- just\n- a list\n",
        "backend:\n  type: gemini\n",
        "backend:\n  type: openai\n",
        "backend:\n  type: openai\n  model: m\n  base_url: [not, a, string]\n",
        "backend:\n  type: openai\n  model: m\n  api_key_env: 42\n",
        "backend:\n  type: claude\n  mcp_config: [list]\n",
        "backend:\n  type: claude\n  allowed_tools: mcp__one__tool\n",
        "panel: []\n",
        "panel:\n  - name: onlyname\n",
        "{unclosed\n",
    ],
)
def test_invalid_configs_are_rejected(tmp_path, text):
    with pytest.raises(ConfigError):
        Config.load(write(tmp_path, text))


def test_missing_config_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        Config.load(tmp_path / "does-not-exist.yaml")


def test_mcp_backend_carries_tool_output_guard(tmp_path):
    from caucus.backends import TOOL_OUTPUT_GUARD

    config = Config.load(write(tmp_path, "backend:\n  type: claude\n  mcp_config: .mcp.json\n"))
    command = config.backend._command("hello")
    assert TOOL_OUTPUT_GUARD in command
    assert command[command.index("--append-system-prompt") + 1] == TOOL_OUTPUT_GUARD


def test_plain_claude_backend_has_no_tool_guard():
    from caucus.backends import TOOL_OUTPUT_GUARD, ClaudeCodeBackend

    command = ClaudeCodeBackend()._command("hello")
    assert TOOL_OUTPUT_GUARD not in command
