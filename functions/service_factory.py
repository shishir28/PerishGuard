"""Shared service cache for HTTP Azure Function endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, TypeVar

if TYPE_CHECKING:
    try:
        from functions.auth_service import AuthService
        from functions.model_training_service import ModelTrainingService
        from functions.nl_query.query_service import NaturalLanguageQueryService
        from functions.ops_service import OperationsService
    except ModuleNotFoundError:
        from auth_service import AuthService
        from model_training_service import ModelTrainingService
        from nl_query.query_service import NaturalLanguageQueryService
        from ops_service import OperationsService


T = TypeVar("T")

_CACHE: dict[str, object] = {}


def _cached(name: str, factory: Callable[[], T]) -> T:
    if name not in _CACHE:
        _CACHE[name] = factory()
    return _CACHE[name]  # type: ignore[return-value]


def auth_service() -> "AuthService":
    try:
        from functions.auth_service import AuthService
    except ModuleNotFoundError:
        from auth_service import AuthService

    return _cached("auth", AuthService.from_environment)


def operations_service() -> "OperationsService":
    try:
        from functions.ops_service import OperationsService
    except ModuleNotFoundError:
        from ops_service import OperationsService

    return _cached("operations", OperationsService.from_environment)


def model_training_service() -> "ModelTrainingService":
    try:
        from functions.model_training_service import ModelTrainingService
    except ModuleNotFoundError:
        from model_training_service import ModelTrainingService

    return _cached("model_training", ModelTrainingService.from_environment)


def natural_language_query_service() -> "NaturalLanguageQueryService":
    try:
        from functions.nl_query.query_service import NaturalLanguageQueryService
    except ModuleNotFoundError:
        from nl_query.query_service import NaturalLanguageQueryService

    return _cached("natural_language_query", NaturalLanguageQueryService.from_environment)


def clear_service_cache() -> None:
    _CACHE.clear()
