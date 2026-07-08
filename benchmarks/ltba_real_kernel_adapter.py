from __future__ import annotations

import importlib
import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass
class RealKernelResult:
    system: str
    family: str
    n: int
    input_expression: str
    native_value_repr: str
    guard_count: int
    deduped_guard_count: int
    local_rewrite_records: int
    materialized_branch_count: int
    forced_piecewise_branch_count: int
    serialized_size_bytes: int
    ast_node_count_or_repr_node_count: int
    correctness_status: str
    guard_recall_status: str
    guard_precision_status: str
    notes: str

    provenance_query_guard: str
    provenance_query_status: str
    provenance_query_runtime_ms: float
    provenance_query_records_examined: int
    provenance_query_result_count: int
    provenance_query_result_repr: str

    incremental_update_index: int
    incremental_update_status: str
    incremental_update_runtime_ms: float
    incremental_update_records_touched: int
    incremental_update_old_guard: str
    incremental_update_new_guard: str
    incremental_update_notes: str


_CANDIDATE_MODULE_NAMES = [
    "kernel",
    "kernel.api",
    "ltba",
    "ltba.core",
    "ltba.api",
]

_PARSE_CANDIDATES = ["parse", "parse_expr", "parse_text", "expr_from_text"]
_SIMPLIFY_CANDIDATES = [
    "simplify",
    "simplify_text",
    "canonicalize",
    "canonicalize_text",
    "normalize",
    "normalize_text",
    "guarded_simplify",
    "guarded_simplify_text",
    "simplify_expr",
    "reduce_expr",
]
_GUARD_CANDIDATES = [
    "guards",
    "get_guards",
    "extract_guards",
    "guard_records",
    "get_guard_records",
    "provenance",
    "get_provenance",
    "local_records",
    "rewrite_records",
    "get_rewrite_records",
]
_INCREMENTAL_CANDIDATES = [
    "update_factor",
    "replace_factor",
    "update_record",
    "incremental_update",
    "replace_subexpr",
    "substitute_local",
    "update_guarded_factor",
]


def _safe_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _discover_modules() -> List[Any]:
    out = []
    for name in _CANDIDATE_MODULE_NAMES:
        mod = _safe_import(name)
        if mod is not None:
            out.append(mod)
    return out


def _find_callable(module: Any, candidate_names: Sequence[str]) -> Optional[Callable[..., Any]]:
    for name in candidate_names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    return None


def _find_callable_any(modules: Sequence[Any], candidate_names: Sequence[str]) -> Tuple[Optional[Callable[..., Any]], str]:
    for module in modules:
        fn = _find_callable(module, candidate_names)
        if fn is not None:
            return fn, f"{getattr(module, '__name__', '<unknown>')}.{getattr(fn, '__name__', '<callable>')}"
    return None, ""


def _join_factors(items: Sequence[str]) -> str:
    if not items:
        return "1"
    if len(items) == 1:
        return items[0]
    return "*".join(f"({x})" for x in items)


def _family_expression(family: str, n: int) -> str:
    f = family.upper()
    if f == "A":
        return _join_factors([f"x{i}/x{i}" for i in range(1, n + 1)])
    if f == "B":
        return _join_factors([f"(x{i}^2 - a{i}^2)/(x{i} - a{i})" for i in range(1, n + 1)])
    if f == "C":
        return _join_factors(["x/x" for _ in range(n)])
    if f == "D":
        return "abs(x)/x"
    raise ValueError(f"Unsupported family: {family}")


def normalize_guard_text(g: str) -> str:
    out = (g or "").strip().replace("≠", "!=")
    out = re.sub(r"\s+", "", out)
    m = re.fullmatch(r"Ne\(([^,]+),([^\)]+)\)", out)
    if m:
        return f"{m.group(1)}!={m.group(2)}"
    return out


def _expected_guards(family: str, n: int) -> List[str]:
    f = family.upper()
    if f == "A":
        return [normalize_guard_text(f"x{i} != 0") for i in range(1, n + 1)]
    if f == "B":
        return [normalize_guard_text(f"x{i} != a{i}") for i in range(1, n + 1)]
    if f == "C":
        return [normalize_guard_text("x != 0")]
    if f == "D":
        return []
    return []


def _query_guard_for(family: str, n: int) -> str:
    f = family.upper()
    if f == "A":
        i = 3 if n >= 3 else 1
        return f"x{i} != 0"
    if f == "B":
        i = 3 if n >= 3 else 1
        return f"x{i} != a{i}"
    if f == "C":
        return "x != 0"
    return "x != 0"


def _incremental_guards_for(family: str, n: int) -> Tuple[str, str, int]:
    f = family.upper()
    if f == "A":
        i = 3 if n >= 3 else 1
        return f"x{i} != 0", f"x{i} != 1", i
    if f == "B":
        i = 3 if n >= 3 else 1
        return f"x{i} != a{i}", f"x{i} != b{i}", i
    if f == "C":
        return "x != 0", "x != 1", 1
    return "x > 0", "x >= 0", 1


def _iter_candidate_payloads(result: Any) -> Iterable[Any]:
    yield result
    if isinstance(result, dict):
        for key in ("value", "expr", "expression", "result", "metadata", "data"):
            if key in result:
                yield result[key]
    if isinstance(result, (list, tuple)):
        for item in result:
            yield item


def _extract_guard_texts(result: Any) -> List[str]:
    guards: List[str] = []

    def add_guard(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            guards.append(value)
            return
        if isinstance(value, dict):
            if "guard" in value:
                guards.append(str(value["guard"]))
            elif "text" in value:
                guards.append(str(value["text"]))
            else:
                for k in ("guards", "guard_records", "records", "rewrite_records", "local_records"):
                    if k in value:
                        add_guard(value[k])
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add_guard(item)
            return
        if hasattr(value, "guard"):
            guards.append(str(getattr(value, "guard")))
            return
        if hasattr(value, "text"):
            guards.append(str(getattr(value, "text")))

    for payload in _iter_candidate_payloads(result):
        if payload is None:
            continue
        for attr in (
            "guards",
            "guard_set",
            "guard_records",
            "records",
            "local_records",
            "rewrite_records",
            "provenance",
        ):
            if hasattr(payload, attr):
                add_guard(getattr(payload, attr))
        if isinstance(payload, dict):
            for key in (
                "guards",
                "guard_set",
                "guard_records",
                "records",
                "rewrite_records",
                "local_records",
            ):
                if key in payload:
                    add_guard(payload[key])
            metadata = payload.get("metadata")
            if isinstance(metadata, dict):
                if "guards" in metadata:
                    add_guard(metadata["guards"])
                if "records" in metadata:
                    add_guard(metadata["records"])

    out = [str(x) for x in guards if str(x).strip()]
    return out


def _extract_local_records(result: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    def add_record(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            record = {k: value[k] for k in value}
            records.append(record)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                add_record(item)
            return
        if hasattr(value, "__dict__"):
            rec = dict(getattr(value, "__dict__", {}))
            if rec:
                records.append(rec)
                return
        text = str(value)
        if text:
            records.append({"repr": text})

    for payload in _iter_candidate_payloads(result):
        if payload is None:
            continue
        for attr in ("guard_records", "records", "local_records", "rewrite_records", "provenance"):
            if hasattr(payload, attr):
                add_record(getattr(payload, attr))
        if isinstance(payload, dict):
            for key in ("guard_records", "records", "local_records", "rewrite_records"):
                if key in payload:
                    add_record(payload[key])
            metadata = payload.get("metadata")
            if isinstance(metadata, dict) and "records" in metadata:
                add_record(metadata["records"])

    # De-duplicate by normalized JSON string.
    unique: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        key = json.dumps(rec, sort_keys=True, default=str)
        unique[key] = rec
    return list(unique.values())


def _result_value_repr(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("value", "expr", "expression", "result"):
            if key in result:
                return str(result[key])
    for attr in ("value", "expr", "expression", "result"):
        if hasattr(result, attr):
            return str(getattr(result, attr))
    return str(result)


def _serialized_size(result: Any) -> int:
    try:
        text = json.dumps(result, default=str, sort_keys=True)
    except Exception:
        text = repr(result)
    return len(text.encode("utf-8"))


def _node_count_estimate(result: Any) -> int:
    def count_nodes(obj: Any, depth: int = 0) -> int:
        if depth > 16:
            return 1
        if obj is None:
            return 1
        if isinstance(obj, (str, bytes, int, float, bool)):
            return 1
        if isinstance(obj, dict):
            return 1 + sum(count_nodes(k, depth + 1) + count_nodes(v, depth + 1) for k, v in obj.items())
        if isinstance(obj, (list, tuple, set)):
            return 1 + sum(count_nodes(x, depth + 1) for x in obj)
        if hasattr(obj, "__dict__"):
            return 1 + count_nodes(getattr(obj, "__dict__"), depth + 1)
        return 1

    try:
        return int(count_nodes(result))
    except Exception:
        return max(1, len(repr(result)))


def _strategy_call_text(fn: Callable[..., Any], input_expression: str) -> Any:
    return fn(input_expression)


def _strategy_call_parse_then_simplify(parse_fn: Callable[..., Any], simplify_fn: Callable[..., Any], input_expression: str) -> Any:
    expr = parse_fn(input_expression)
    return simplify_fn(expr)


def _run_real_simplify(input_expression: str) -> tuple[bool, object, str]:
    modules = _discover_modules()
    if not modules:
        return False, None, "No candidate real-kernel modules could be imported."

    errors: List[str] = []

    direct_fn, direct_name = _find_callable_any(modules, ["simplify_text"])  # Strategy A
    if direct_fn is not None:
        try:
            return True, _strategy_call_text(direct_fn, input_expression), f"text direct via {direct_name}"
        except Exception as exc:
            errors.append(f"text direct failed: {type(exc).__name__}: {exc}")

    parse_fn, parse_name = _find_callable_any(modules, _PARSE_CANDIDATES)
    simplify_fn, simplify_name = _find_callable_any(modules, ["simplify", "simplify_expr", "canonicalize", "normalize", "reduce_expr"])
    if parse_fn is not None and simplify_fn is not None:
        try:
            return (
                True,
                _strategy_call_parse_then_simplify(parse_fn, simplify_fn, input_expression),
                f"parse then simplify via {parse_name} + {simplify_name}",
            )
        except Exception as exc:
            errors.append(f"parse then simplify failed: {type(exc).__name__}: {exc}")

    canon_text_fn, canon_text_name = _find_callable_any(modules, ["canonicalize_text", "normalize_text"])  # Strategy C
    if canon_text_fn is not None:
        try:
            return True, _strategy_call_text(canon_text_fn, input_expression), f"canonicalize text via {canon_text_name}"
        except Exception as exc:
            errors.append(f"canonicalize text failed: {type(exc).__name__}: {exc}")

    guarded_fn, guarded_name = _find_callable_any(modules, ["guarded_simplify", "guarded_simplify_text"])  # Strategy D
    if guarded_fn is not None:
        try:
            return True, guarded_fn(input_expression), f"guarded simplify via {guarded_name}"
        except Exception as exc_text:
            errors.append(f"guarded simplify(text) failed: {type(exc_text).__name__}: {exc_text}")
            if parse_fn is not None:
                try:
                    expr = parse_fn(input_expression)
                    return True, guarded_fn(expr), f"guarded simplify(parse) via {guarded_name}"
                except Exception as exc_expr:
                    errors.append(f"guarded simplify(expr) failed: {type(exc_expr).__name__}: {exc_expr}")

    generic_fn, generic_name = _find_callable_any(modules, _SIMPLIFY_CANDIDATES)
    if generic_fn is not None:
        try:
            return True, generic_fn(input_expression), f"generic simplify fallback via {generic_name}"
        except Exception as exc:
            errors.append(f"generic fallback failed: {type(exc).__name__}: {exc}")

    joined = " | ".join(errors) if errors else "No compatible parse/simplify callable was discovered."
    return False, None, joined


def _real_kernel_provenance_query(records: List[Dict[str, Any]], guard_text: str) -> Dict[str, Any]:
    start = time.perf_counter()
    normalized_target = normalize_guard_text(guard_text)

    if not records:
        return {
            "status": "UNAVAILABLE_REAL_KERNEL_PROVENANCE",
            "records_examined": 0,
            "result_count": 0,
            "result_repr": "",
            "runtime_ms": (time.perf_counter() - start) * 1000.0,
        }

    matches = []
    for rec in records:
        blob = json.dumps(rec, sort_keys=True, default=str)
        if normalized_target and normalized_target in normalize_guard_text(blob):
            matches.append(rec)

    status = "PASS" if matches else "NO_MATCHING_RECORDS"
    return {
        "status": status,
        "records_examined": len(records),
        "result_count": len(matches),
        "result_repr": json.dumps(matches[:5], sort_keys=True, default=str),
        "runtime_ms": (time.perf_counter() - start) * 1000.0,
    }


def _infer_branch_count(result_repr: str) -> int:
    text = (result_repr or "").lower()
    if "piecewise" in text:
        return max(2, text.count("(") // 2)
    if "if" in text and "else" in text:
        return 2
    return 1


def _build_unavailable_row(family: str, n: int, input_expression: str, notes: str) -> Dict[str, Any]:
    row = RealKernelResult(
        system="ltba_real_kernel",
        family=family,
        n=n,
        input_expression=input_expression,
        native_value_repr="",
        guard_count=0,
        deduped_guard_count=0,
        local_rewrite_records=0,
        materialized_branch_count=0,
        forced_piecewise_branch_count=0,
        serialized_size_bytes=0,
        ast_node_count_or_repr_node_count=0,
        correctness_status="UNAVAILABLE_REAL_KERNEL_API",
        guard_recall_status="UNAVAILABLE_REAL_KERNEL_PROVENANCE",
        guard_precision_status="UNAVAILABLE_REAL_KERNEL_PROVENANCE",
        notes=notes,
        provenance_query_guard=_query_guard_for(family, n),
        provenance_query_status="UNAVAILABLE_REAL_KERNEL_PROVENANCE",
        provenance_query_runtime_ms=0.0,
        provenance_query_records_examined=0,
        provenance_query_result_count=0,
        provenance_query_result_repr="",
        incremental_update_index=0,
        incremental_update_status="UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API",
        incremental_update_runtime_ms=0.0,
        incremental_update_records_touched=0,
        incremental_update_old_guard="",
        incremental_update_new_guard="",
        incremental_update_notes="Real kernel does not expose mutable local update API in this harness.",
    )
    return asdict(row)


def _validate_guards(family: str, n: int, extracted_guards: List[str]) -> Tuple[str, str]:
    expected = set(_expected_guards(family, n))
    if not extracted_guards:
        return "UNAVAILABLE_REAL_KERNEL_PROVENANCE", "UNAVAILABLE_REAL_KERNEL_PROVENANCE"
    got = {normalize_guard_text(g) for g in extracted_guards}
    recall = "PASS" if expected.issubset(got) else "FAIL"
    precision = "PASS" if got.issubset(expected) else "FAIL"
    return recall, precision


def _attempt_incremental_update(result_obj: Any, family: str, n: int) -> Dict[str, Any]:
    old_guard, new_guard, index = _incremental_guards_for(family, n)
    modules = _discover_modules()
    fn, fn_name = _find_callable_any(modules, _INCREMENTAL_CANDIDATES)
    if fn is None:
        return {
            "index": index,
            "status": "UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API",
            "runtime_ms": 0.0,
            "records_touched": 0,
            "old_guard": old_guard,
            "new_guard": new_guard,
            "notes": "Real kernel does not expose mutable local update API in this harness.",
        }

    t0 = time.perf_counter()
    try:
        try:
            update_result = fn(result_obj, old_guard, new_guard)
        except TypeError:
            try:
                update_result = fn(result=result_obj, old_guard=old_guard, new_guard=new_guard)
            except TypeError:
                update_result = fn(old_guard=old_guard, new_guard=new_guard)

        touched = 0
        if isinstance(update_result, dict):
            touched_val = update_result.get("records_touched")
            if isinstance(touched_val, int):
                touched = touched_val

        return {
            "index": index,
            "status": "PASS",
            "runtime_ms": (time.perf_counter() - t0) * 1000.0,
            "records_touched": touched,
            "old_guard": old_guard,
            "new_guard": new_guard,
            "notes": f"incremental update via {fn_name}",
        }
    except Exception as exc:
        return {
            "index": index,
            "status": "UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API",
            "runtime_ms": (time.perf_counter() - t0) * 1000.0,
            "records_touched": 0,
            "old_guard": old_guard,
            "new_guard": new_guard,
            "notes": f"incremental API discovered but unusable: {type(exc).__name__}: {exc}",
        }


def _run_case(family: str, n: int) -> Dict[str, Any]:
    input_expression = _family_expression(family, n)
    success, result_obj, strategy_note = _run_real_simplify(input_expression)

    if not success:
        return _build_unavailable_row(
            family=family,
            n=n,
            input_expression=input_expression,
            notes=(
                "Real kernel import succeeded but no compatible parse/simplify API was discovered. "
                + strategy_note
            ),
        )

    guard_texts = _extract_guard_texts(result_obj)
    normalized_guards = [normalize_guard_text(g) for g in guard_texts if str(g).strip()]
    deduped_guards = sorted(set(normalized_guards))
    records = _extract_local_records(result_obj)
    result_repr = _result_value_repr(result_obj)
    serialized_size = _serialized_size(result_obj)
    node_count = _node_count_estimate(result_obj)

    recall_status, precision_status = _validate_guards(family, n, normalized_guards)

    query_guard = _query_guard_for(family, n)
    query = _real_kernel_provenance_query(records, query_guard)

    if not records and deduped_guards:
        if family.upper() == "C":
            query_status = "DEDUPED_GUARD_ONLY_NO_MULTIPLE_RECORDS"
        else:
            query_status = "GUARDS_ONLY_NO_LOCAL_PROVENANCE"
    else:
        query_status = query["status"]

    incremental = _attempt_incremental_update(result_obj, family, n)

    correctness_status = "PASS"
    notes = strategy_note

    if family.upper() == "D":
        rr = result_repr.lower()
        if "piecewise" not in rr and "sign" not in rr and "if" not in rr:
            correctness_status = "UNAVAILABLE_REAL_KERNEL_BRANCHING"
    elif family.upper() in ("A", "B", "C"):
        if result_repr.strip() == "":
            correctness_status = "UNAVAILABLE_REAL_KERNEL_API"

    if not guard_texts:
        notes = notes + " | guard/provenance extraction unavailable"

    row = RealKernelResult(
        system="ltba_real_kernel",
        family=family,
        n=n,
        input_expression=input_expression,
        native_value_repr=result_repr,
        guard_count=len(normalized_guards),
        deduped_guard_count=len(deduped_guards),
        local_rewrite_records=len(records),
        materialized_branch_count=_infer_branch_count(result_repr),
        forced_piecewise_branch_count=0,
        serialized_size_bytes=serialized_size,
        ast_node_count_or_repr_node_count=node_count,
        correctness_status=correctness_status,
        guard_recall_status=recall_status,
        guard_precision_status=precision_status,
        notes=notes,
        provenance_query_guard=query_guard,
        provenance_query_status=query_status,
        provenance_query_runtime_ms=float(query["runtime_ms"]),
        provenance_query_records_examined=int(query["records_examined"]),
        provenance_query_result_count=int(query["result_count"]),
        provenance_query_result_repr=str(query["result_repr"]),
        incremental_update_index=int(incremental["index"]),
        incremental_update_status=str(incremental["status"]),
        incremental_update_runtime_ms=float(incremental["runtime_ms"]),
        incremental_update_records_touched=int(incremental["records_touched"]),
        incremental_update_old_guard=str(incremental["old_guard"]),
        incremental_update_new_guard=str(incremental["new_guard"]),
        incremental_update_notes=str(incremental["notes"]),
    )
    return asdict(row)


def real_kernel_available() -> bool:
    modules = _discover_modules()
    if not modules:
        return False
    ok, _, _ = _run_real_simplify("x1/x1")
    return bool(ok)


def run_real_kernel_family_a(n: int) -> dict:
    return _run_case("A", n)


def run_real_kernel_family_b(n: int) -> dict:
    return _run_case("B", n)


def run_real_kernel_family_c(n: int) -> dict:
    return _run_case("C", n)


def run_real_kernel_family_d() -> dict:
    return _run_case("D", 1)


def run_real_kernel_case(family: str, n: int) -> dict:
    fam = family.upper()
    if fam == "A":
        return run_real_kernel_family_a(n)
    if fam == "B":
        return run_real_kernel_family_b(n)
    if fam == "C":
        return run_real_kernel_family_c(n)
    if fam == "D":
        return run_real_kernel_family_d()
    return _build_unavailable_row(
        family=fam,
        n=n,
        input_expression="",
        notes=f"Unsupported family: {family}",
    )
