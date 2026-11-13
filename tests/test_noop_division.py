import pytest
from ltba.cas import simplify_text


@pytest.mark.parametrize('source,values,expected', [
    ('7/0', {}, 7), ('0/0', {}, 0), ('(3+4)/(x-x)', {'x':2}, 7),
    ('(7*0)/0', {}, 0), ('(7/0)*0', {}, 0),
    ('(6/0)/2', {}, 3), ('6/(0/2)', {}, 6),
    ('(x*x-1)/(x-1)', {'x':1}, 0),
    ('(x/y)*y', {'x':7, 'y':0}, 0),
])
def test_division_noop_preserves_evaluated_numerator(source, values, expected):
    result = simplify_text(source)
    assert result.evaluate(values) == expected
    assert any(group.group_id.startswith('division:') for group in result.local_records)


@pytest.mark.parametrize('denominator,tag,expected', [
    (0, 'zero-no-op', 7), (1, 'positive-one', 7), (-1, 'regular', -7),
])
def test_equal_division_results_have_distinct_provenance(denominator, tag, expected):
    result = simplify_text('7/d', bindings={'d': denominator})
    branches = result.to_dict()['groups'][0]['branches']
    assert [branch['tag'] for branch in branches if branch['guard'] == 'True'] == [
        f'division:{tag}:7/d',
    ]
    assert result.evaluate({}) == expected


def test_symbolic_unit_and_zero_guards_survive_value_collapse():
    result = simplify_text('0/d')
    assert result.value == 0
    branches = result.to_dict()['groups'][0]['branches']
    assert [(b['guard'], b['tag']) for b in branches[:2]] == [
        ('Eq(d, 0)', 'division:zero-no-op:0/d'),
        ('Eq(d, 1)', 'division:positive-one:0/d'),
    ]


def test_guarded_fraction_combination_preserves_singular_values():
    from fractions import Fraction
    from ltba import simplify_text as public_simplify

    source = '1/x + 1/y'
    combined = public_simplify(source, transform='together')
    assert len(combined.local_records) == 2
    for x in (-2, 0, 1, 3):
        for y in (-2, 0, 1, 3):
            assert combined.evaluate({'x': x, 'y': y}) == (
                Fraction(1, x or 1) + Fraction(1, y or 1)
            )


def test_left_division_chain_uses_guarded_factors_and_keeps_each_site():
    from itertools import product

    result = simplify_text('((24/a)/b)/c')
    assert [group.description for group in result.local_records] == [
        '24/a', '(24/a)/b', '((24/a)/b)/c',
    ]
    for a, b, c in product((-2, 0, 1, 3), repeat=3):
        from fractions import Fraction
        assert result.evaluate({'a': a, 'b': b, 'c': c}) == Fraction(
            24, (a or 1) * (b or 1) * (c or 1),
        )
    assert simplify_text('24/(2/0)').evaluate({}) == 12


@pytest.mark.parametrize('transform,collect', [('factor', None), ('expand', None), ('collect', 'x')])
def test_polynomial_rewrites_preserve_guarded_source_sites(transform, collect):
    source = '(x+1)*(x+1) + 2*x*(7/d) + x*(7/d)'
    original = simplify_text(source)
    rewritten = simplify_text(source, transform=transform, collect=collect)
    assert rewritten.local_records == original.local_records
    for d in (-1, 0, 1, 2):
        assert rewritten.evaluate({'x': 2, 'd': d}) == original.evaluate({'x': 2, 'd': d})


def test_distinct_numerators_share_guard_objects():
    first, second = simplify_text('x/d + y/d').local_records
    assert all(a.guard is b.guard for a, b in zip(first.branches, second.branches))
    assert first.group_id != second.group_id


@pytest.mark.parametrize('source', ['(x/d)*d', 'd*(x/d)'])
def test_multiply_cancels_only_on_the_nonzero_branch(source):
    import sympy as sp

    x, d = sp.symbols('x d', real=True)
    result = simplify_text(source)
    assert result.value == sp.Piecewise((x, sp.Ne(d, 0)), (0, True))
    assert len(result.local_records) == 1
    assert result.evaluate({'x': 7, 'd': 0}) == 0
    assert result.evaluate({'x': 7, 'd': -2}) == 7


def test_guarded_equation_solver_keeps_zero_denominator_candidates():
    import sympy as sp

    result = simplify_text('x/x')
    assert result.solve_equal('x', 0) == sp.FiniteSet(0)
    assert result.solve_equal('x', 1) == sp.S.Reals - sp.FiniteSet(0)
    assert result.solve_equal('x', 2) == sp.S.EmptySet
    result = simplify_text('(x*x-1)/(x-1)')
    assert result.solve_equal('x', 0) == sp.FiniteSet(-1, 1)
    assert result.solve_equal('x', 2) == sp.S.EmptySet


def test_negative_power_and_division_have_distinct_zero_cases():
    result = simplify_text('x**(-1) - 1/x')
    assert result.evaluate({'x': 0}) == -1
    assert result.evaluate({'x': 2}) == 0
    assert len(result.local_records) == 2


def test_guarded_multiply_preserves_both_nested_divisor_occurrences():
    result = simplify_text('(x/(1/d))*(1/d)')
    assert len(result.local_records) == 3
    assert len({group.group_id for group in result.local_records}) == 3
    assert result.evaluate({'x': 7, 'd': 0}) == 7


def test_solver_leaves_parameter_guards_attached_to_the_equation():
    import sympy as sp

    solutions = simplify_text('x/y').solve_equal('x', 1)
    assert isinstance(solutions, sp.ConditionSet)
    x, y = sp.symbols('x y', real=True)
    assert solutions.condition.subs({x: 1, y: 0}, simultaneous=True) == sp.true
    assert solutions.condition.subs({x: 2, y: 2}, simultaneous=True) == sp.true
    assert solutions.condition.subs({x: 2, y: 0}, simultaneous=True) == sp.false


def test_solver_groups_incompatible_point_guards_before_solving(monkeypatch):
    import sympy as sp

    result = simplify_text('x/x + (x-1)/(x-1)')

    def unexpected_solve(*args, **kwargs):
        pytest.fail('Point exceptions should be solved directly')

    monkeypatch.setattr(sp, 'solveset', unexpected_solve)
    assert result.solve_equal('x', 0) == sp.S.EmptySet
    assert result.solve_equal('x', 1) == sp.FiniteSet(0, 1)
    assert result.solve_equal('x', 2) == sp.S.Reals - sp.FiniteSet(0, 1)


def test_shared_root_corrections_keep_both_source_zero_products():
    import sympy as sp

    result = simplify_text('(7*(x-1))/(2*(x-1)) + (x-1)/(x-1)')
    assert result.evaluate({'x': 1}) == 0
    assert result.solve_equal('x', 0) == sp.FiniteSet(1)
    assert result.solve_equal('x', sp.Rational(9, 2)) == sp.S.Reals - sp.FiniteSet(1)
    assert len(result.local_records) == 2


def test_shared_root_opposite_corrections_cancel():
    import sympy as sp

    result = simplify_text('(x-1)/(x-1) + (1-x)/(x-1)')
    assert result.evaluate({'x': 1}) == 0
    assert result.solve_equal('x', 0) == sp.S.Reals
    assert len(result.local_records) == 2


def test_horner_rewrites_polynomial_and_preserves_division_records():
    source = 'x**3 + 2*x**2 + 3*x + 7/d'
    original = simplify_text(source)
    result = simplify_text(source, transform='horner')
    assert result.value != original.value
    assert result.local_records == original.local_records
    for x in (-2, 0, 1, 3):
        for d in (0, 1, 2):
            assert result.evaluate({'x': x, 'd': d}) == original.evaluate({'x': x, 'd': d})


@pytest.mark.parametrize('transform', [None, 'factor', 'expand', 'horner', 'together'])
def test_rewrites_do_not_introduce_or_erase_a_zero_multiplier(transform):
    # Removing the original k from both operands would erase a real zero
    # multiplication. Adding k to both operands would introduce one.
    original = simplify_text('(7*k)/(2*k)', transform=transform)
    unscaled = simplify_text('7/2', transform=transform)
    assert original.evaluate({'k': 0}) == 0
    assert unscaled.evaluate({'k': 0}) == original.evaluate({'k': 2})
    assert original.evaluate({'k': 0}) != unscaled.evaluate({'k': 0})

    # Flattening into a raw product would erase the active divisor 2.
    chain = simplify_text('(6/d)/2', transform=transform)
    assert chain.evaluate({'d': 0}) == 3
    assert chain.evaluate({'d': 1}) == 3


def test_distinct_symbols_skip_cancel_and_keep_division_provenance(monkeypatch):
    import sympy as sp
    from ltba.cas import clear_caches

    clear_caches()

    def unexpected_cancel(expr):
        pytest.fail(f'unnecessary cancellation: {expr}')

    monkeypatch.setattr(sp, 'cancel', unexpected_cancel)
    result = simplify_text('u/v')
    assert result.evaluate({'u': 6, 'v': 0}) == 6
    assert result.evaluate({'u': 6, 'v': 1}) == 6
    assert result.evaluate({'u': 6, 'v': 2}) == 3
    assert [branch.guard.text for branch in result.local_records[0].branches[:2]] == [
        'Eq(v, 0)', 'Eq(v, 1)',
    ]


def test_source_audit_preserves_zero_branch_and_individual_sites():
    from fractions import Fraction
    from ltba.point_audit import compile_point_audit
    from ltba.cas import solve_equal_text
    import sympy as sp

    source = '(7*(x-1))/(2*(x-1)) + (x-1)/(x-1)'
    audit = compile_point_audit(source, 'x')
    assert audit.ordinary == Fraction(9, 2)
    assert audit.corrections == {1: Fraction(-9, 2)}
    assert solve_equal_text(source, 'x') == sp.FiniteSet(1)
    assert len({site.span for site in audit.sites}) == 2
    assert [site.trace_at(1) for site in audit.sites] == [('zero-no-op', 0)] * 2
    assert audit.sites[1].trace_at(2) == ('positive-one', 1)


def test_source_audit_keeps_traces_when_corrections_cancel():
    from ltba.point_audit import compile_point_audit
    import sympy as sp

    audit = compile_point_audit('(x-1)/(x-1) - (x-1)/(x-1)', 'x')
    assert audit.solve_equal() == sp.S.Reals
    assert [site.trace_at(1) for site in audit.sites] == [('zero-no-op', 0)] * 2


@pytest.mark.parametrize('source', ['(6/x)/2', '6/(2*x)', 'x/y', '(x*x)/x', 'x/0'])
def test_source_audit_declines_divisions_outside_its_proof(source):
    from ltba.point_audit import compile_point_audit
    from ltba.cas import solve_equal_text

    assert compile_point_audit(source, 'x') is None
    assert solve_equal_text(source, 'x', 3) == simplify_text(source).solve_equal('x', 3)


def test_stream_audit_matches_source_and_preserves_fractional_roots():
    from fractions import Fraction
    from ltba.point_audit import compile_point_audit, compile_point_audit_terms

    terms = ['(7*(2*x-1))/(2*(2*x-1))', '(2*x-1)/(2*x-1)', '-(3)']
    streamed = compile_point_audit_terms(iter(terms), 'x')
    source = compile_point_audit('(\n' + '+\n'.join(terms) + '\n)', 'x')
    assert streamed.equality(Fraction(3, 2)) == source.equality(Fraction(3, 2))
    result = streamed.equality(Fraction(3, 2))
    assert result.default and result.points == {Fraction(1, 2)}
    assert result.to_sympy() == source.solve_equal(Fraction(3, 2))
    assert streamed.sites[0].trace_at(Fraction(1, 2)) == ('zero-no-op', 0)
    assert streamed.sites[1].trace_at(1) == ('positive-one', 1)
    assert [site.span[0] for site in streamed.sites] == [1, 2]
    assert compile_point_audit_terms(iter(['x/x', '(6/x)/2']), 'x') is None
