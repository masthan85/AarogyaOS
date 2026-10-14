# ADR-0011 Migrations are a release step; one worker per container
Status: accepted. Running `alembic upgrade` in the container's start command races when several replicas start, and
hides failures inside a crash loop; migrations are now a one-shot step and `/ready` blocks traffic until the schema
matches the image. Separately, live transcript partials and the audio gateway's connection guard are process memory,
so the image runs one worker and a recording must stay on one container until a Redis-backed hub exists. Cost:
horizontal scale is by containers with sticky routing, not by workers.
