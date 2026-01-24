-- TODO: this should create bronze, silver, and gold schemas for our data warehouse.

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- Bronze: Raw data from external sources
