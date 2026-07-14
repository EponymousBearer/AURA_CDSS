# Model comparison (M2) — RF vs LightGBM vs CatBoost

Same frozen seed-42 split + features; isotonic-calibrated; train subsample=300,000, test=177,406.

| Model | Pooled AUC | Within-cell AUC | Brier (cal) | Top-3 | Size (MB) | Latency (ms) | Train (s) |
|---|---|---|---|---|---|---|---|
| RandomForest | 0.85 | 0.6432 | 0.099 | 0.9978 | 12.55 | 67.13 | 64.2 |
| LightGBM | 0.8781 | 0.6656 | 0.0895 | 0.9983 | 0.88 | 2.19 | 11.1 |
| CatBoost | 0.8758 | 0.6793 | 0.0904 | 0.998 | 0.34 | 1.66 | 46.6 |

> Within-cell AUC (0.5 = no lift over the antibiogram) is the honest patient-specific metric from M1. Discrimination metrics use raw scores; calibration is monotonic so it does not change ranking.