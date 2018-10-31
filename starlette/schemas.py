import inspect
import typing

import yaml

from starlette.routing import BaseRoute, Route


class SchemaGenerator:
    def get_schema(self, routes: typing.List[BaseRoute]) -> dict:
        paths = {}  # type: dict

        for route in routes:
            if not isinstance(route, Route):
                continue

            if inspect.isfunction(route.endpoint) or inspect.ismethod(route.endpoint):
                docstring = route.endpoint.__doc__
                for method in route.methods or ["GET"]:
                    if method == "HEAD":
                        continue
                    if route.path not in paths:
                        paths[route.path] = {}
                    data = yaml.safe_load(docstring) if docstring else {}
                    paths[route.path][method.lower()] = data
            else:
                for method in ["get", "post", "put", "patch", "delete", "options"]:
                    if not hasattr(route.endpoint, method):
                        continue
                    docstring = getattr(route.endpoint, method).__doc__
                    if route.path not in paths:
                        paths[route.path] = {}
                    data = yaml.safe_load(docstring) if docstring else {}
                    paths[route.path][method] = data

        return paths
