# Deprecation Policy

The goal of this policy is to reduce the impact of changes on users and developers of the project by providing
clear guidelines and a well-defined process for deprecating functionalities. This policy applies to both features
and API interfaces.

## Starlette Versions

Starlette follows [Semantic Versioning](https://semver.org/), with some additional constraints.

## Deprecation Types

We'll consider two kinds of deprecations: **Python version** and **feature** deprecations.

### Python Version Deprecation

Starlette will aim to support a Python version until the [EOL date of that version](https://endoflife.date/python).
When a Python version reaches EOL, Starlette will drop support for that version in the next **minor** release.

The drop of Python version support will be documented in the release notes, but the user will **not** be warned it.

### Feature Deprecation

Starlette will deprecate a feature in the next **minor** release after the feature is marked as deprecated.

The deprecation of a feature needs to be followed by a warning message using `warnings.warn` in the code that
uses the deprecated feature. The warning message should include the version in which the feature will be removed.

The format of the message should follow:

> *`code` is deprecated and will be removed in version `version`.*

The `code` can be a *function*, *module* or *feature* name, and the `version` should be the next major release.

The deprecation warning may include an advice on how to replace the deprecated feature.

> *Use `alternative` instead.*

As a full example, imagine we are in version 1.0.0, and we want to deprecate the `potato` function.
We would add the follow warning:

```python
def potato():
    warnings.warn(
        "potato is deprecated and will be removed in version 2.0.0. "
        "Use banana instead.",
        DeprecationWarning,
    )

def banana():
    ...
```

The deprecation of a feature will be documented in the release notes, and the user will be warned about it.
