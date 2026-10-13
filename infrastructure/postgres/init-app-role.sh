#!/bin/sh
# Creates the application role and database. The role is deliberately NOT a superuser:
# Postgres superusers bypass row-level security, which would disable tenant isolation.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE aarogya_app LOGIN PASSWORD '${AAROGYA_APP_DB_PASSWORD}' NOSUPERUSER NOCREATEROLE NOBYPASSRLS;
CREATE DATABASE aarogya OWNER aarogya_app;
SQL
