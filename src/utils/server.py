"""
Utilities for the server.
"""

# =============================================================================

from flask import make_response, render_template, request

# =============================================================================

__all__ = (
    "AppRoutes",
    "_render",
    "get_request_json",
    "print_records",
)

# =============================================================================


class AppRoutes:
    """Contains all the routes defined in a module.

    Acts as a mock Flask "app" that can have routes added to it. For
    example:

    ```python
    # In views.py
    app = AppRoutes()

    @app.route("/", methods=["GET"])
    def index():
        return "Hello, world!"

    # In app.py
    app = Flask(__name__)
    views.app.register(app)
    ```

    In this way, routes can easily be moved to other modules without any
    other changes.
    """

    def __init__(self):
        self._routes = []

    def route(self, rule, **options):
        """A decorator to create a route.

        Accepts the same args as `@app.route()`.
        """

        def wrapper(func):
            self._routes.append((rule, func, options))
            return func

        return wrapper

    def register(self, app):
        """Registers all the routes to the app."""
        for rule, func, options in self._routes:
            app.add_url_rule(rule, view_func=func, **options)


# =============================================================================


def _render(template_file, **kwargs):
    """Renders the given template file."""
    html = render_template(template_file, **kwargs)
    response = make_response(html)
    return response


# =============================================================================


def unsuccessful(error_msg, error_while=None, **kwargs):
    if error_while is None:
        error_while = "Error"
    print(" ", f"{error_while}:", error_msg)
    return {"success": False, "reason": error_msg, **kwargs}


# =============================================================================


def get_request_json(*keys, top_level=dict):
    """Gets the values for the given keys in the request JSON data.

    Returns:
        Union[Tuple[str, None], Tuple[None, Any]]:
            An error message, or the JSON data for the requested keys.
    """
    if top_level not in (dict, list):
        raise ValueError("`top_level` must be `dict` or `list`")
    if top_level is list and len(keys) > 0:
        raise ValueError("Cannot get key values for a top level of `list`")
    json_data = request.get_json(silent=True)
    if json_data is None:
        return "Invalid JSON data", None
    if not isinstance(json_data, top_level):
        expected = {dict: "mapping", list: "list"}
        return f"Invalid JSON data: expected {expected[top_level]}", None
    if len(keys) == 0:
        return None, json_data
    result = {}
    missing = []
    wrong_type = {}
    for key in keys:
        expect_type = str
        if isinstance(key, tuple):
            key, expect_type = key
        if key not in json_data:
            missing.append(f'"{key}"')
            continue
        try:
            value = expect_type(json_data[key])
        except ValueError:
            if expect_type not in wrong_type:
                wrong_type[expect_type] = []
            wrong_type[expect_type].append(f'"{key}"')
            continue
        result[key] = value

    def key_list(key_values):
        if len(key_values) == 1:
            return f"key {key_values[0]}"
        key_values_str = ", ".join(key_values)
        return f"keys: {key_values_str}"

    if len(missing) > 0:
        return f"Invalid JSON data: missing {key_list(missing)}", None
    if len(wrong_type) > 0:
        wrong_type_list = []
        for expect_type, wrong_keys in wrong_type.items():
            wrong_type_list.append(
                f"{expect_type.__class__.__name__} for {key_list(wrong_keys)}"
            )
        return f"Invalid JSON data: expected {'; '.join(wrong_type_list)}"
    return None, result


# =============================================================================


def print_records(headers, records, indent=0, padding=2):
    """Prints the given records in a table format, for server logs.

    Args:
        headers (Union[Iterable[str], Dict[str, str]]):
            Either an iterable of header values (which should also be
            keys in each record), or a mapping from keys in each record
            to the header value for that column. Any keys not in the
            headers will not be printed.
        records (List[Dict[str, Any]]): The records to print.
        indent (int): The number of spaces to prefix each row with.
        padding (int): The number of spaces between each column.
    """
    indent_str = " " * indent
    padding_str = " " * padding

    if isinstance(headers, dict):
        headers_enumerated = list(enumerate(headers.keys()))
        headers_values = list(headers.values())
    else:
        # iterable of strings
        headers_list = list(headers)
        headers_enumerated = list(enumerate(headers_list))
        headers_values = headers_list

    col_widths = [len(h) for h in headers_values]
    rows = []
    for record in records:
        row = []
        for i, key in headers_enumerated:
            value = str(record.get(key, "!MISSING!"))
            row.append(value)
            col_widths[i] = max(col_widths[i], len(value))
        rows.append(row)

    def print_row(values):
        if values == "":
            segments = [" " * width for width in col_widths]
        elif isinstance(values, str):
            segments = [
                (values * int(width / len(values)))[:width]
                for width in col_widths
            ]
        else:
            # assume `values` is an iterable of strings
            segments = []
            for value, width in zip(values, col_widths):
                if value == "":
                    segments.append(" " * width)
                    continue
                segments.append(value.ljust(width))
        print(f"{indent_str}{padding_str.join(segments)}")

    print_row(headers_values)
    print_row("-")
    for row in rows:
        print_row(row)
