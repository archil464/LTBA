# LTBA Overview

LTBA stands for **Locality-Preserving Tagged Branch Algebra**.

The central idea is that many symbolic transformations create local branch conditions:

- `x/x`
- `sqrt(x^2)`
- `(x^2-a^2)/(x-a)`
- `log(xy)`
- `1/det(A)`

Traditional systems often move these conditions into global forms such as `Piecewise`, `ConditionalExpression`, assumptions, or decision diagrams.

LTBA keeps branch records local to the algebraic factor that generated them and delays global expansion.
