# Project Boundaries

## What CrisisAgent Is

CrisisAgent is an evidence-guided enterprise crisis-response Copilot workbench MVP. It helps teams collect controlled signals, manage a crisis event, produce reviewable response drafts, inspect evidence and trace, conduct Human Review, and export reports.

## Watchlist Monitoring

P18 adds bounded, manually configured monitoring queries for allowlisted providers. It does not enable whole-web crawling or automatic response publication.

P19 adds a manually run live smoke and a guarded scheduler. It does not claim cloud deployment, production uptime, or continuous whole-web coverage.

P20 adds reviewed case-summary memory and deterministic context packing. It does not store complete news articles, user-chat memory, or claim a production vector memory system.

## What It Is Not

- Not a whole-web or real-time monitoring SaaS.
- Not connected to real enterprise production systems or customers.
- Not an automated public-statement publishing system.
- Not a claim of production-scale concurrency, uptime, throughput, or SLA.
- Not a complete PostgreSQL migration or multi-tenant enterprise authorization implementation.
- Not a replacement for legal, PR, quality, or compliance personnel.

## Current Validation Scope

The default demo and CI paths are offline and deterministic: mock agents, JSON storage, hash embeddings, no live-fetch, and no real LLM. Optional modes for PostgreSQL, Redis/RQ, BGE, real LLMs, and live allowlisted sources require separate environment setup and should be described as optional/manual validation paths.

## Safe Communication

Use "MVP", "engineering prototype", "controlled connector", and "human-in-the-loop" when describing the project. Do not claim real-time whole-web coverage, automatic publication, production deployment, or enterprise adoption.
