from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urljoin

import requests


class CanvasAPIError(RuntimeError):
    pass


@dataclass(slots=True)
class CanvasConnectionResult:
    ok: bool
    message: str
    profile: dict[str, Any] | None = None


class CanvasService:
    """Cliente mínimo y robusto para la API REST de Canvas."""

    def __init__(self, base_url: str, token: str, timeout: int = 45) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "AVE-Alerta-Temprana/1.0",
            }
        )

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        data: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: dict[str, Any] | None = None,
    ) -> requests.Response:
        if not self.token:
            raise CanvasAPIError("Debe ingresar un token de Canvas.")
        try:
            response = self.session.request(
                method,
                self._url(path),
                params=params,
                data=data,
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise CanvasAPIError(f"No fue posible conectarse con Canvas: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:600]
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("errors") or payload.get("message") or payload)
            except ValueError:
                pass
            if response.status_code in {401, 403}:
                raise CanvasAPIError(
                    f"Canvas rechazó la solicitud ({response.status_code}). Revise el token y sus permisos. {detail}"
                )
            raise CanvasAPIError(f"Error de Canvas ({response.status_code}): {detail}")
        return response

    def get(self, path: str, params: dict[str, Any] | list[tuple[str, Any]] | None = None) -> Any:
        return self._request("GET", path, params=params).json()

    def get_paginated(
        self,
        path: str,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        max_pages: int = 100,
    ) -> list[Any]:
        items: list[Any] = []
        url = self._url(path)
        current_params = params
        pages = 0
        while url and pages < max_pages:
            response = self._request("GET", url, params=current_params)
            payload = response.json()
            if isinstance(payload, list):
                items.extend(payload)
            elif isinstance(payload, dict):
                # Algunos endpoints devuelven un contenedor, se conserva como elemento.
                items.append(payload)
            else:
                break
            url = response.links.get("next", {}).get("url")
            current_params = None
            pages += 1
        return items

    def test_connection(self) -> CanvasConnectionResult:
        try:
            profile = self.get("/api/v1/users/self/profile")
            name = profile.get("name") or profile.get("short_name") or "usuario"
            return CanvasConnectionResult(True, f"Conexión correcta como {name}.", profile)
        except CanvasAPIError as exc:
            return CanvasConnectionResult(False, str(exc), None)

    def list_courses(self) -> list[dict[str, Any]]:
        params: list[tuple[str, Any]] = [
            ("per_page", 100),
            ("state[]", "available"),
            ("state[]", "completed"),
            ("include[]", "term"),
            ("include[]", "total_students"),
            ("include[]", "sections"),
        ]
        courses = self.get_paginated("/api/v1/courses", params=params)
        return [course for course in courses if isinstance(course, dict) and course.get("id")]

    def list_sections(self, course_id: int | str) -> list[dict[str, Any]]:
        params: list[tuple[str, Any]] = [("per_page", 100), ("include[]", "total_students")]
        return self.get_paginated(f"/api/v1/courses/{course_id}/sections", params=params)

    def list_enrollments(
        self,
        course_id: int | str,
        section_id: int | str | None = None,
    ) -> list[dict[str, Any]]:
        if section_id:
            path = f"/api/v1/sections/{section_id}/enrollments"
        else:
            path = f"/api/v1/courses/{course_id}/enrollments"
        params: list[tuple[str, Any]] = [
            ("per_page", 100),
            ("type[]", "StudentEnrollment"),
            ("state[]", "active"),
            ("include[]", "total_scores"),
            ("include[]", "avatar_url"),
        ]
        return self.get_paginated(path, params=params)

    def list_assignments(self, course_id: int | str) -> list[dict[str, Any]]:
        params: list[tuple[str, Any]] = [
            ("per_page", 100),
            ("include[]", "all_dates"),
            ("order_by", "due_at"),
        ]
        return self.get_paginated(f"/api/v1/courses/{course_id}/assignments", params=params)

    def list_submissions(
        self,
        course_id: int | str,
        section_id: int | str | None = None,
    ) -> list[dict[str, Any]]:
        if section_id:
            path = f"/api/v1/sections/{section_id}/students/submissions"
        else:
            path = f"/api/v1/courses/{course_id}/students/submissions"
        params: list[tuple[str, Any]] = [
            ("per_page", 100),
            ("student_ids[]", "all"),
            ("grouped", "true"),
            ("include[]", "assignment"),
            ("include[]", "user"),
        ]
        return self.get_paginated(path, params=params)

    def list_page_views(
        self,
        user_id: int | str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        params = {
            "per_page": 100,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }
        return self.get_paginated(f"/api/v1/users/{user_id}/page_views", params=params, max_pages=25)

    def send_message(
        self,
        recipient_ids: list[int | str],
        subject: str,
        body: str,
        *,
        force_new: bool = True,
    ) -> list[dict[str, Any]]:
        if not recipient_ids:
            raise CanvasAPIError("No se seleccionaron destinatarios.")
        data: list[tuple[str, Any]] = [("subject", subject), ("body", body)]
        data.append(("force_new", str(force_new).lower()))
        data.append(("group_conversation", "false"))
        for recipient in recipient_ids:
            data.append(("recipients[]", str(recipient)))
        payload = self._request("POST", "/api/v1/conversations", data=data).json()
        if isinstance(payload, list):
            return payload
        return [payload]

    def get_conversation(self, conversation_id: int | str) -> dict[str, Any]:
        return self.get(f"/api/v1/conversations/{conversation_id}", params={"include_all_conversation_ids": "true"})

    def count_sessions(
        self,
        page_views: list[dict[str, Any]],
        *,
        inactivity_gap_minutes: int = 30,
        course_id: int | str | None = None,
    ) -> int:
        timestamps: list[datetime] = []
        course_token = f"/courses/{course_id}/" if course_id else None
        for view in page_views:
            url = str(view.get("url") or "")
            if course_token and course_token not in url:
                context_id = str(view.get("context_id") or "")
                if context_id != str(course_id):
                    continue
            value = view.get("created_at")
            if not value:
                continue
            try:
                timestamps.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
            except ValueError:
                continue
        if not timestamps:
            return 0
        timestamps.sort()
        sessions = 1
        for previous, current in zip(timestamps, timestamps[1:]):
            if (current - previous).total_seconds() > inactivity_gap_minutes * 60:
                sessions += 1
        return sessions

    def fetch_page_view_sessions(
        self,
        user_ids: list[int | str],
        start_time: datetime,
        end_time: datetime,
        course_id: int | str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[dict[str, int | None], dict[str, str]]:
        """Consulta sesiones una a una; conserva errores de permiso por estudiante."""
        sessions: dict[str, int | None] = {}
        errors: dict[str, str] = {}
        total = len(user_ids)
        for index, user_id in enumerate(user_ids, start=1):
            try:
                views = self.list_page_views(user_id, start_time, end_time)
                sessions[str(user_id)] = self.count_sessions(views, course_id=course_id)
            except CanvasAPIError as exc:
                sessions[str(user_id)] = None
                errors[str(user_id)] = str(exc)
            if progress_callback:
                progress_callback(index, total)
        return sessions, errors
