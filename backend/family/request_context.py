from contextvars import ContextVar


_actor = ContextVar("famuhle_notification_actor", default=None)
_path = ContextVar("famuhle_notification_path", default="")


def set_current_actor(user, path=""):
    _actor.set(user if getattr(user, "is_authenticated", False) else None)
    if path is not None:
        _path.set(path or "")


def current_actor():
    return _actor.get()


def current_path():
    return _path.get()


def clear_current_actor():
    _actor.set(None)
    _path.set("")


class ActorContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_current_actor()
        forced = getattr(request, "_force_auth_user", None)
        if getattr(forced, "is_authenticated", False):
            set_current_actor(forced, request.path)
        try:
            return self.get_response(request)
        finally:
            clear_current_actor()
