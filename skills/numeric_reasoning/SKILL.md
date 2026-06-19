---
name: numeric-reasoning
description: How to compute accurate final answers after grounded values are found — choosing a formula, normalizing units, and running arithmetic programmatically; use whenever a question requires calculation.
---

# Numeric Reasoning and Calculation Rules

Derive a **formula first**, then compute. Once values are grounded and the formula is chosen, run the arithmetic **programmatically** (e.g. a one-line `python3 -c "..."`) rather than by mental math or longhand. Most numeric errors come from wrong values or wrong formulas — but mental arithmetic is an avoidable extra source of error, so do not rely on it.

## Common formulas
- Difference: `A - B`
- Absolute difference: `abs(A - B)`
- Sum: `sum(values)`
- Average: `sum(values) / n`
- Ratio: `A / B`
- Percent: `(A / B) * 100`
- Percent change (old→new): `((new - old) / old) * 100`
- Absolute percent change: `abs((new - old) / old) * 100`
- Share of total: `(part / total) * 100`
- Euclidean norm of two changes: `sqrt(change_1**2 + change_2**2)`

## Monthly aggregation
- "all individual calendar months in YEAR" → collect all **12** monthly values.
- Do **not** use a reported annual total unless the question explicitly asks for the reported annual total.
- Verify 12 months are present before summing.
- If a month is missing, search adjacent issues or table variants before concluding it is unavailable.

## Unit normalization
- Convert all values to the same unit before arithmetic.
- Do not add millions to thousands without conversion.
- Percent values and dollar values must not be combined directly.

## Sign and denominator checks
- For percent change, clearly identify the old/base value and the new/comparison value.
- If absolute percent change is requested, apply `abs()` after computing the change.
- Decide whether output should be percent form (`12.34`) or decimal form (`0.1234`).

## Rounding
- Preserve full precision during intermediate calculations.
- Round only at the final step.
- Follow the requested precision exactly.
- "Nearest hundredths" in percent form means output like `12.34`, not `0.1234`, unless explicitly requested otherwise.

## Final answer
- When the prompt requests a numeric-only answer, output **only** the number.
- No units, no explanation, no citations in the final output unless the task explicitly requires them.

## Verification checklist
1. Formula matches the question?
2. All required grounded values found?
3. Units normalized?
4. Signs handled correctly?
5. Denominator correct?
6. Rounding correct?
7. Final format correct?
8. Was the final arithmetic actually run programmatically, not by hand?
