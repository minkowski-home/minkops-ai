# Solutions

A solution composes reusable workflows, implemented connectors, and client
configuration for one customer or use case. The shared applications provide the
product surfaces; solutions do not copy them.

Keep client-specific workflow composition, mappings, policies, prompts, and
available AI Employee catalog entries under `solutions/<id>/`. Put shared
workflow implementations under the root `workflows/` only when more than one
solution needs them. Keep small one-off instructions beside their workflow.

Connector declarations in a solution are configuration only. Enable a
connector for real execution only after its implementation exists under
`connectors/`.

`mock-client` is a local UI fixture. `pr-infra` is the first client solution;
its current manifest selects the shared console and declares connector intent.
