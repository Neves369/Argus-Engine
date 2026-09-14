from __future__ import annotations

from app.scanning.spec import FormField, HtmlForm


def select_login_form(forms: list[HtmlForm]) -> HtmlForm | None:
    """Pick the first form with a password field (the login form candidate)."""
    for form in forms:
        if any(fld.type == "password" for fld in form.fields):
            return form
    return None


def login_payload(form: HtmlForm, username: str, password: str) -> dict[str, str]:
    """Map the login form fields to submitted values, deterministically.

    The username goes into the first unfilled text-like field (so prefilled or
    CSRF-bearing text inputs are left alone); hidden fields keep their value.
    """
    data: dict[str, str] = {}
    text_fields: list[FormField] = []
    for fld in form.fields:
        if not fld.name:
            continue
        if fld.type == "password":
            data[fld.name] = password
        elif fld.type == "hidden":
            if fld.value:
                data[fld.name] = fld.value
        elif fld.type in ("text", "email", "username", "tel", "search"):
            if fld.value:
                data[fld.name] = fld.value
            else:
                text_fields.append(fld)
    username_field = text_fields[0] if text_fields else None
    if username_field is not None:
        data[username_field.name] = username
    return data
