"""Phase 2 Foundation Cleanup, goal 2: "verify RBAC on every admin
endpoint" -- a static walk of every registered route, not a live HTTP
round-trip (which an endpoint's own body/path validation could
short-circuit before its auth dependency ever runs). This is
regression coverage, not a one-off manual check: a newly added
`/api/v1/admin/*` route -- or a future revival of the legacy runtime
kernel's `/api/tasks`/`/api/agents` endpoints -- that forgets
`require_staff_role(...)` fails this test before it ever reaches
production.

`main.app.routes` does not hold flat `APIRoute` objects for included
sub-routers in this FastAPI build -- `app.include_router(...)` wraps
each mounted router in an internal `_IncludedRouter`, so admin.py's own
12 sub-routers are nested two levels deep (app -> admin router ->
each admin sub-router). `_flatten_routes` recurses through that
(and any future nesting) to find the real `APIRoute` objects.
"""

import main

_LEGACY_KERNEL_PATHS = {"/api/tasks", "/api/tasks/{task_id}", "/api/agents/{agent_id}"}


def _flatten_routes(routes):
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            yield from _flatten_routes(route.original_router.routes)
        elif hasattr(route, "path") and hasattr(route, "dependant"):
            yield route
        elif hasattr(route, "routes"):
            yield from _flatten_routes(route.routes)


def _iter_dependant_chain(dependant):
    """Yield the route's own Dependant plus every nested sub-dependency
    (e.g. require_staff_role's closure wraps get_current_user)."""
    yield dependant
    for sub in dependant.dependencies:
        yield from _iter_dependant_chain(sub)


def _requires_staff_role(route) -> bool:
    for dependant in _iter_dependant_chain(route.dependant):
        call = dependant.call
        if call is not None and getattr(call, "__qualname__", "").startswith("require_staff_role"):
            return True
    return False


def _admin_and_legacy_kernel_routes():
    return [
        route
        for route in _flatten_routes(main.app.routes)
        if route.path.startswith("/api/v1/admin/") or route.path in _LEGACY_KERNEL_PATHS
    ]


def test_route_walk_actually_finds_the_real_admin_surface():
    """Guards the test below against passing vacuously if the route
    walk itself ever breaks (e.g. a FastAPI internals change moves
    `_IncludedRouter` again) -- 35 admin + 3 legacy routes at the time
    this test was written; a large drop means the walk is broken, not
    that routes were removed."""
    routes = _admin_and_legacy_kernel_routes()
    assert len(routes) >= 30, (
        f"Expected at least 30 admin/legacy-kernel routes, found {len(routes)} -- "
        "the route walk may no longer match this FastAPI build's internals."
    )


def test_every_admin_and_legacy_kernel_route_requires_staff_role():
    unguarded = [
        f"{sorted(route.methods)} {route.path}"
        for route in _admin_and_legacy_kernel_routes()
        if not _requires_staff_role(route)
    ]
    assert unguarded == [], f"Routes reachable without require_staff_role(...): {unguarded}"
