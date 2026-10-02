# Pinned TFX schema input

`schema.pbtxt` is an unmodified copy of the TensorFlow TFX penguin example's
user-provided schema at commit
`cd99075bfad794a3ea9df49ee77f9c06578f895d` and path
`tfx/examples/penguin/schema/user_provided/schema.pbtxt`.

The upstream project is licensed under Apache License 2.0; a copy is included as
`LICENSE-Apache-2.0.txt`. `SOURCE.json` records the source URL, commit, path, and
local SHA-256. The artifact's projection tool consumes only feature-level
presence constraints with `min_fraction: 1.0` and `min_count: 1`. It does not
implement general protobuf, TFDV, or TFX semantics.
