-- Public sign-up goes (docs/workspace-access.md), with its email
-- verification, join requests and the workspace a work email's domain
-- suggested. A person joins through an invitation's link, which reaches their
-- inbox and so verifies the address.
DROP TABLE join_requests;
DROP TABLE email_verifications;
DROP TABLE tenant_domains;
