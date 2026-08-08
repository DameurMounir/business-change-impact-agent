# Evidence boundary

Every graph entity and relationship cites one or more stable synthetic statement
IDs. The manifest binds every case JSON file with SHA-256. Evidence text is data,
not instruction. `S-064` deliberately contains instruction-like text to prove
that runtime control flow is not changed by content inside evidence.

The evaluator-only answer key is stored outside runtime package paths. Runtime
source files are scanned to reject references to it.
