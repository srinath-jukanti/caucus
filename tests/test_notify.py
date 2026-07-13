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


def make_briefing():
    from caucus.briefing import Briefing
    from caucus.record import DecisionRecord

    record = DecisionRecord(
        subject="Adopt library X?",
        decision="Proceed.",
        confidence=0.8,
        dissent=[
            {
                "agent": "skeptic",
                "stance": "against",
                "summary": "hidden <costs>",
                "confidence": 0.6,
            }
        ],
        timestamp="2026-07-13T00:00:00+00:00",
    )
    record.hash = record.compute_hash()
    return Briefing(generated_at="2026-07-13T12:00:00+00:00", records=[record])


def test_render_template_markdown(tmp_path):
    from caucus.briefing import render_template, template_subtype

    template = tmp_path / "brief.md.j2"
    template.write_text(
        "{{ generated_at }}\n{% for d in decisions %}{{ d.subject }} -> {{ d.decision }}{% endfor %}"
    )
    body = render_template(make_briefing(), template)
    assert "Adopt library X? -> Proceed." in body
    assert template_subtype(template) == "plain"


def test_render_html_template_escapes_content(tmp_path):
    from caucus.briefing import render_template, template_subtype

    template = tmp_path / "brief.html.j2"
    template.write_text("{% for d in decisions %}{{ d.dissent[0].summary }}{% endfor %}")
    body = render_template(make_briefing(), template)
    # Record content is untrusted model output — HTML must be escaped.
    assert "&lt;costs&gt;" in body
    assert template_subtype(template) == "html"


def test_render_template_fails_loudly_on_unknown_variable(tmp_path):
    from caucus.briefing import TemplateRenderError, render_template

    template = tmp_path / "brief.md.j2"
    template.write_text("{{ nonexistent_variable }}")
    with pytest.raises(TemplateRenderError, match="nonexistent_variable"):
        render_template(make_briefing(), template)


def test_email_notifier_sends_html_subtype(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pass")
    notifier = EmailNotifier(to="you@example.com", smtp_factory=FakeSMTP)
    notifier.send("s", "<h1>hello</h1>", subtype="html")
    assert "Content-Type: text/html" in FakeSMTP.instances[0].sent[0].message


def test_config_parses_email_templates(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
notify:
  type: email
  to: you@example.com
  subject_template: "[Custom] {date} ({count})"
  template: briefing_email.html.j2
"""
    )
    notify = Config.load(path).notify
    assert notify.subject_template == "[Custom] {date} ({count})"
    assert notify.template == "briefing_email.html.j2"


@pytest.mark.parametrize(
    "text",
    [
        "notify:\n  type: email\n  to: a@b.c\n  subject_template: ''\n",
        "notify:\n  type: email\n  to: a@b.c\n  subject_template: '{unknown_thing}'\n",
        "notify:\n  type: email\n  to: a@b.c\n  template: ''\n",
    ],
)
def test_config_rejects_invalid_templates(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    with pytest.raises(ConfigError):
        Config.load(path)
