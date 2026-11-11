"""Form-input helpers. HTML forms send numbers as strings, blanks as ''."""


def parse_number(value, cast=float, default=None, minimum=None):
    """'' / None -> default; otherwise cast. Raises ValueError on bad input."""
    if value is None or str(value).strip() == '':
        return default
    n = cast(float(value)) if cast is int else cast(value)
    if cast is int and float(value) != n:
        raise ValueError(f'{value!r} is not a whole number')
    if minimum is not None and n < minimum:
        raise ValueError(f'{value!r} is below {minimum}')
    return n
