from starlette import Response
import re


class Path:
    def __init__(self, path, app):
        self.path = path
        self.app = app
        regex = "^" + path + "$"
        regex = re.sub("{([a-zA-Z_][a-zA-Z0-9_]*)}", r"(?P<\1>[^/]*)", regex)
        self.path_regex = re.compile(regex)

    def matches(self, scope):
        match = self.path_regex.match(scope["path"])
        if match:
            kwargs = dict(scope.get("kwargs", {}))
            kwargs.update(match.groupdict())
            child_scope = scope.copy()
            child_scope["kwargs"] = kwargs
            return True, child_scope
        return False, {}

    def __call__(self, scope):
        return self.app(scope)


class PathPrefix:
    def __init__(self, path, app):
        self.path = path
        self.app = app
        regex = "^" + path
        regex = re.sub("{([a-zA-Z_][a-zA-Z0-9_]*)}", r"(?P<\1>[^/]*)", regex)
        self.path_regex = re.compile(regex)

    def matches(self, scope):
        match = self.path_regex.match(scope["path"])
        if match:
            kwargs = dict(scope.get("kwargs", {}))
            kwargs.update(match.groupdict())
            child_scope = scope.copy()
            child_scope["kwargs"] = kwargs
            child_scope["root_path"] = scope.get("root_path", "") + match.string
            child_scope["path"] = scope["path"][match.span()[1] :]
            return True, child_scope
        return False, {}

    def __call__(self, scope):
        return self.app(scope)


class Router:
    def __init__(self, routes, default=None):
        self.routes = routes
        self.default = self.not_found if default is None else default

    def __call__(self, scope):
        for route in self.routes:
            matched, child_scope = route.matches(scope)
            if matched:
                return route(child_scope)
        return self.not_found(scope)

    def not_found(self, scope):
        return Response("Not found", 404, media_type="text/plain")
