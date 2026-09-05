-- Creates the dedicated integration-test database alongside the main one.
-- Executed automatically by the postgres image on first initialisation.
SELECT 'CREATE DATABASE mydb_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mydb_test')\gexec
