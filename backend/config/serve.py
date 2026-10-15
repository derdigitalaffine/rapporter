"""Use Daphne's normal CLI with bearer-safe access records."""
from daphne.cli import CommandLineInterface
from daphne.server import Server
from family.calendar_subscription_privacy import redact


class RedactingServer(Server):
    def __init__(self, *args, **kwargs):
        original = kwargs.get('action_logger')
        if original:
            def safe_logger(protocol, action, details):
                clean = dict(details)
                if 'path' in clean:
                    clean['path'] = redact(clean['path'])
                original(protocol, action, clean)
            kwargs['action_logger'] = safe_logger
        super().__init__(*args, **kwargs)


class SafeCommandLineInterface(CommandLineInterface):
    server_class = RedactingServer


if __name__ == '__main__':
    SafeCommandLineInterface.entrypoint()
