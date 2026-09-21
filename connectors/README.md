# Connectors

External-system implementations live here. A connector owns protocol-specific
authentication, clients, and data mapping; it does not contain customer rules
or workflow orchestration. Customer selection belongs in `solutions/<id>/`.

Create a directory only when there is a concrete integration to implement.
