# LTBA Piecewise Comparison Summary

## Real LTBA Kernel Integration

- real kernel imports succeeded: False
- API strategy observed: unavailable
- guard extraction worked: False
- local rewrite provenance extraction worked: False
- incremental update API available: False
- LTBA-native A/B/C rows store local rewrite records only; they do not materialize global branches.
- Forced Piecewise comparison for LTBA-native A/B/C remains 2^n branches.
- Family C keeps 1 deduped guard across n local rewrite records.
- Family D requires genuine branching and is not counted as LTBA local cancellation success.

| family | n | real_kernel_status | real_kernel_guard_count | real_kernel_deduped_guard_count | real_kernel_local_records | real_kernel_provenance_status | real_kernel_incremental_update_status | notes |
|---|---:|---|---:|---:|---:|---|---|---|
| A | 5 | UNAVAILABLE_REAL_KERNEL_API | 0 | 0 | 0 | UNAVAILABLE_REAL_KERNEL_PROVENANCE | UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API | Real kernel import succeeded but no compatible parse/simplify API was discovered. No compatible parse/simplify callable was discovered. |
| B | 5 | UNAVAILABLE_REAL_KERNEL_API | 0 | 0 | 0 | UNAVAILABLE_REAL_KERNEL_PROVENANCE | UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API | Real kernel import succeeded but no compatible parse/simplify API was discovered. No compatible parse/simplify callable was discovered. |
| C | 5 | UNAVAILABLE_REAL_KERNEL_API | 0 | 0 | 0 | UNAVAILABLE_REAL_KERNEL_PROVENANCE | UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API | Real kernel import succeeded but no compatible parse/simplify API was discovered. No compatible parse/simplify callable was discovered. |

The real LTBA kernel adapter emitted placeholder rows but could not discover a compatible public API. Mock LTBA results still test the representation model, but real-kernel validation requires exposing parse/simplify/guard-record APIs.
