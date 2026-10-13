# Self-hosted CI runtime (#562)

All workflow jobs continue to use the repository's `self-hosted` runners. Each
runner must run Linux, have access to a working Docker daemon, and reach the
official image/action registries. Multiple runner processes may share one host.

Backend and Passkey jobs use the official Python 3.13 Bookworm slim image rather
than a host-OS-specific `setup-python` download. The Ubuntu 26.04 package failed
on the current host with `CPU ISA level is lower than required`. Each job gets
its own PostgreSQL service on its Docker network, reached as `postgres:5432`.
No database service publishes host port 5432; parallel schema/test jobs therefore
cannot collide on that port or use another job's database.

Browser shards use the official `mcr.microsoft.com/playwright:v1.64.0-noble`
image, matching `frontend/package-lock.json`. The explicit version check fails
when the lockfile changes without updating the image. Existing Node 22 setup,
dependency installation, production build, browser installation, four shards,
visual artifacts and aggregate E2E gate remain enabled. Container-local port
4173 isolates each preview, including concurrent PRs. Browser runtime does not
depend on the host's Ubuntu version or alter host browser packages.

The container job installs the pinned Compose v2.32.4 with Docker's official
setup action and still verifies Docker/Compose before building. Only this job is
serialized across workflow runs: the production topology deliberately uses a
pinned proxy subnet and the existing smoke test publishes localhost port 18080.
An explicit per-run/attempt Compose project name confines cleanup to that run.
No production deployment containers or volumes should share that project name.

Full backend tests, all-app migration drift, checks/migrations, all browser and
container checks and the separate Passkey migration gate are required before
delivery. Failures before checkout/runtime setup are infrastructure failures,
not evidence that application tests passed. Diagnose logs before retrying; no
test gate is removed to obtain a green run. The coordination dashboard retains
its metadata-only self-hosted job and privileged input sanitization.

Rollback: revert the runtime follow-up commit. This restores the preceding
self-hosted workflow definitions, including their observed host dependencies;
there is no application/schema/data migration.

Primary runtime contracts checked on 2026-10-13:
- https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers
- https://playwright.dev/docs/docker
- https://github.com/docker/setup-compose-action
