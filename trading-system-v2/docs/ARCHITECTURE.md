# Architecture

## Layers

- **Layer 1 — Domain**: Pure business logic. No I/O, no frameworks.
- **Layer 2 — Orchestration**: Wires domain to ports. Agents, supervisors, runtime.
- **Layer 3 — Infrastructure**: Adapters: WebSocket gateway, in-memory bus, FastAPI API.

## Dependency Rule

Layer N may only import from Layer N or lower. Infrastructure never imports from Orchestration or Domain by default; Orchestration imports Domain; Domain imports nothing external.

## Key Components

- `PipelineRuntime`: Starts/stops feed, supervisor, agents.
- `InMemoryEventBus`: Pub/sub bus shared across the system.
- `PriceSupervisor`: Reads from feed, normalizes, publishes to bus.
- `SampleAgent`: Subscribes to bus, tracks latest price.
