"""Notification: how a finished briefing reaches a human.

Config-driven, two kinds:
- email: SMTP (Gmail-friendly defaults) using stdlib smtplib. Credentials are
  read from environment variables named in the config — never from the config
  itself.
- command: run any executable with the briefing path as its argument.
"""

from __future__ import annotations

import os
import shlex
import smtplib
import subprocess
from dataclasses import dataclass
from email.mime.text import MIMEText
from pathlib import Path


class NotifyError(RuntimeError):
    """Raised when a notification cannot be delivered."""


@dataclass
class EmailNotifier:
    """SMTP delivery; defaults suit a Gmail account with an app password.

    subject_template takes {date} and {count}; template (a Jinja2 file path)
    renders the body — .html templates are delivered as HTML.
    """

    to: str
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    address_env: str = "GMAIL_ADDRESS"
    password_env: str = "GMAIL_APP_PASSWORD"
    subject_template: str = "[Caucus] briefing {date} — {count} decisions"
    template: str | None = None
    smtp_factory: object | None = None  # injectable for tests

    def send(
        self,
        subject: str,
        body: str,
        attachment_path: Path | None = None,
        subtype: str = "plain",
    ) -> None:
        address = os.environ.get(self.address_env)
        password = os.environ.get(self.password_env)
        if not address or not password:
            raise NotifyError(
                f"email notifier needs ${self.address_env} and ${self.password_env} set"
            )
        message = MIMEText(body, subtype, "utf-8")
        message["Subject"] = subject
        message["From"] = address
        message["To"] = self.to
        factory = self.smtp_factory or smtplib.SMTP_SSL
        try:
            with factory(self.smtp_host, self.smtp_port) as server:
                server.login(address, password)
                server.sendmail(address, [self.to], message.as_string())
        except OSError as err:
            raise NotifyError(f"email delivery failed: {err}") from err


@dataclass
class CommandNotifier:
    """Runs a user-configured command with the briefing path appended."""

    command: str

    def send(
        self,
        subject: str,
        body: str,
        attachment_path: Path | None = None,
        subtype: str = "plain",
    ) -> None:
        target = shlex.quote(str(attachment_path)) if attachment_path else ""
        completed = subprocess.run(f"{self.command} {target}".strip(), shell=True)
        if completed.returncode != 0:
            raise NotifyError(f"notify command exited {completed.returncode}")
