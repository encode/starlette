import inspect

from starlette.routing import Route


class SchemaGenerator:
    def get_schema(self, routes):
        paths = {}

        for route in routes:
            if not isinstance(route, Route):
                continue

            if inspect.isfunction(route.endpoint) or inspect.ismethod(route.endpoint):
                docstring = route.endpoint.__doc__
                for method in route.methods:
                    if method == "HEAD":
                        continue
                    if route.path not in paths:
                        paths[route.path] = {}
                    paths[route.path][method.lower()] = docstring
            else:
                for method in route.methods:
                    if method == "HEAD":
                        continue
                    docstring = getattr(route.endpoint, method.lower()).__doc__
                    if route.path not in paths:
                        paths[route.path] = {}
                    paths[route.path][method.lower()] = docstring

        return paths
