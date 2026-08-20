# AI-assisted Development

CrisisAgent was built with AI assistance, but the engineering control loop stayed human-led.

## How AI Was Used

AI helped accelerate:

- boilerplate code
- tests
- documentation
- repetitive refactors
- error-location suggestions
- report drafting

AI did not replace project ownership.

## Human-led Decisions

The human side defined and reviewed:

- project topic
- business workflow
- agent decomposition
- technical direction
- phased roadmap
- acceptance criteria
- git diff review
- test result interpretation
- interview packaging

## Guardrails Against AI Over-editing

Each phase used explicit constraints such as:

- do not modify Agent business logic
- do not modify Prompt semantics
- do not modify API core paths
- do not modify RAG algorithm
- run pytest after changes
- keep commits small
- do not auto-commit
- review `git diff` before commit

This matters because AI can write plausible code that changes behavior accidentally.

## How To Answer: "Was This Project Written By AI?"

Interview answer:

> I used AI as a coding assistant, but I controlled the project direction, acceptance criteria, test verification and git review. The important part was not just generating code; it was defining the system boundaries, preventing unrelated changes, checking tests and keeping failure reports. I can explain each module and why it exists.

## How To Answer: "What Percentage Was AI-generated?"

Interview answer:

> I would not describe it as a simple percentage. AI accelerated boilerplate, tests and docs, while I decided architecture, phased scope, what not to change, what metrics mattered and whether the result was acceptable. In a real team, I would still treat AI output as code that needs review, tests and ownership.

## How To Answer: "What Did You Personally Do?"

Interview answer:

> I designed the crisis-response workflow, split the agents, defined RAG/Gate/Reranker evaluation phases, kept failure audits, checked git diffs and made sure the system stayed demoable. AI helped with implementation speed, but I had to decide which changes were safe and which would overclaim the project.

## How To Answer: "How Do You Ensure AI-generated Code Quality?"

Interview answer:

> I use tight task scopes, explicit forbidden changes, offline tests, small commits, diff review and regression reports. For example, many phases explicitly said not to modify Agent logic, Prompt, RAG algorithm or API paths. If tests pass but the behavior is misleading, I still do not accept it.
