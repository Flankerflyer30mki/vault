"""Email backend used when no SMTP server is configured (EMAIL_HOST unset).

Django's console backend prints the raw MIME message. Its body is quoted-printable, so every "=" in a link becomes
"=3D" and long lines are split with a trailing "=": a verification or reset link copied from the log doesn't work.
This backend prints the plain text instead, so the link is on one line exactly as the email would show it.
"""
from django.core.mail.backends.console import EmailBackend as ConsoleBackend


class PlainTextConsoleBackend(ConsoleBackend):
    def write_message(self, message):
        self.stream.write(f"Subject: {message.subject}\nTo: {', '.join(message.to)}\n\n{message.body}\n{'-' * 79}\n")
