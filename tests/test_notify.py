from types import SimpleNamespace

import pytest

from caucus.config import Config, ConfigError
from caucus.notify import CommandNotifier, EmailNotifier, NotifyError


class FakeSMTP:
    """Records logins and sends; usable as a context manager factory."""

    instances = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.logins, self.sent = [], []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, address, password):
        self.logins.append((address, password))

    def sendmail(self, sender, recipients, message):
        self.sent.append(SimpleNamespace(sender=sender, recipients=recipients, message=message))


@pytest.fixture(autouse=True)
def reset_fake():
    FakeSMTP.instances = []


def test_email_notifier_sends_via_smtp(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pass")
    notifier = EmailNotifier(to="you@example.com", smtp_factory=FakeSMTP)
    notifier.send("subject line", "body text")
    server = FakeSMTP.instances[0]
    assert server.host == "smtp.gmail.com"
    assert server.logins == [("me@example.com", "app-pass")]
    sent = server.sent[0]
    assert sent.recipients == ["you@example.com"]
    assert "subject line" in sent.message


def test_email_notifier_requires_env(monkeypatch):
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    notifier = EmailNotifier(to="you@example.com", smtp_factory=FakeSMTP)
    with pytest.raises(NotifyError, match="GMAIL_ADDRESS"):
        notifier.send("s", "b")
    assert FakeSMTP.instances == []


def test_command_notifier_runs_and_fails_loudly(tmp_path):
    marker = tmp_path / "ran.txt"
    CommandNotifier(command=f"touch {marker}").send("s", "b")
    assert marker.exists()
    with pytest.raises(NotifyError, match="exited 3"):
        CommandNotifier(command="exit 3").send("s", "b")


def test_config_parses_email_notifier(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
notify:
  type: email
  to: you@example.com
  address_env: MY_FROM
  password_env: MY_PASS
  smtp_port: 587
"""
    )
    notify = Config.load(path).notify
    assert isinstance(notify, EmailNotifier)
    assert notify.to == "you@example.com"
    assert notify.address_env == "MY_FROM"
    assert notify.smtp_port == 587


def test_config_legacy_notify_command_still_works(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("notify_command: bash send.sh\n")
    notify = Config.load(path).notify
    assert isinstance(notify, CommandNotifier)
    assert notify.command == "bash send.sh"


@pytest.mark.parametrize(
    "text",
    [
        "notify: email\n",
        "notify:\n  type: email\n",
        "notify:\n  type: email\n  to: ''\n",
        "notify:\n  type: email\n  to: a@b.c\n  smtp_port: -5\n",
        "notify:\n  type: email\n  to: a@b.c\n  smtp_port: true\n",
        "notify:\n  type: command\n",
        "notify:\n  type: slack\n",
        "notify:\n  type: command\n  command: x\nnotify_command: y\n",
    ],
)
def test_config_rejects_invalid_notify(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    with pytest.raises(ConfigError):
        Config.load(path)
