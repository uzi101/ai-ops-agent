import modal


def call_modal(app_name: str, fn_name: str, **kwargs):
    """Lookup a deployed Modal function by name and execute it."""
    fn = modal.Function.from_name(app_name, fn_name)
    return fn.remote(**kwargs)
