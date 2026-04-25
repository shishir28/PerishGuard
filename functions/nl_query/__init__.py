"""HTTP entrypoint for Task 4 natural-language dashboard queries."""

from __future__ import annotations

import os

try:
    from functions._http import authenticated, current_session, json_response, parse_json
    from functions.service_factory import natural_language_query_service
except ModuleNotFoundError:
    from _http import authenticated, current_session, json_response, parse_json
    from service_factory import natural_language_query_service


@authenticated
def main(req):
    ctx = current_session()
    if os.getenv("DISABLE_NL_QUERY", "").lower() == "true":
        return json_response({"error": "nl_query disabled"}, 503)
    body = parse_json(req, required=("question",))
    return json_response(natural_language_query_service().answer(body["question"].strip(), ctx.active_customer_id))
