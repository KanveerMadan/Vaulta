# Merchant model

Learns subcategories (`backend/app/data/taxonomy.json`) for bank narrations by **knowledge distillation**: an LLM
teacher labels merchant names, a small model learns from those labels, and every metric is *agreement with teacher
labels*, not accuracy. Results: `docs/ml/evaluation.md`; the shipped model: `docs/ml/model-card.md`.

```
make setup     # Python 3.12 venv with requirements.txt
make train     # data → teacher labels (cached) → train + evaluate → export (only if it meets the ship criteria)
make test      # split-leakage and stripping checks
make retrain   # with consented user corrections (see below)
```

| Step | Script | Output |
|---|---|---|
| Real narrations (optional) | `prepare_real.py` | `data/private/real.jsonl` from `local-statements/` (both git-ignored) |
| Synthetic narrations + splits | `generate.py` | `data/merchant_list.jsonl`, `data/narrations.jsonl` (regenerated, not committed), `artifacts/data_summary.json` |
| Teacher labels | `teacher.py` | `data/teacher_cache.jsonl` (committed), `data/labels.jsonl`, `artifacts/teacher_log.json` |
| Train, evaluate, decide | `train.py` | `artifacts/metrics.json`, `artifacts/merchant_model.json`, `artifacts/worst_errors.json`, `docs/ml/*.png` |
| Ship | `export.py` | `backend/app/data/merchant_model.json.gz`, `frontend/public/models/merchant-model.json.gz`, `backend/app/data/merchant_index.json`, `fixtures/merchant_model_parity.json` |
| Retrain | `retrain.py` | `artifacts/retrain_report.json` (+ a new model only if it isn't worse) |

- **Data.**
  - `data/merchants.txt` is the merchant catalogue: brands under a subcategory hint, plus the legal names banks print.
  - `data/local_shops.txt` and `data/name_stems.txt` generate local shops.
  - The hint only steers generation, and its agreement with the teacher is reported. Labels always come from the teacher.
  - Narrations go through the server's PII stripper (`backend/app/services/pii.py`) before anything sees them.
- **Splits are by merchant.**
  - Main test set: unseen catalogue merchants.
  - Unseen-local-shops test set: shops built on name stems that never occur in training.
  - Real-narrations test set: only when `local-statements/` has files.
  - `tests/test_splits.py` checks for leakage.
- **The teacher.** It only ever receives stripped merchant names, never transactions.
  - Two models label each name, and a third labels it when they disagree. Ties are "ambiguous" and excluded.
  - Answers are cached, so a re-run with the cache makes no calls and needs no key.
  - It stops if a call is needed and `GROQ_API_KEY` is missing.
- **Model B** downloads a public embedding model (~430 MB) to `~/.cache/vaulta-ml/` (`MODEL_B_DIR`). `python train.py --skip-b` skips it.
- **Retraining with corrections.**
  1. `backend/scripts/export_training_corrections.py` writes the corrections of users who opted in
     (Settings → Categories) to `data/private/corrections.jsonl`. It takes only the stripped narration and the chosen
     subcategory, and prints counts only.
  2. `make retrain` adds them to training.
  3. The new model is judged on the same frozen test sets, plus a held-out fifth of the corrections (the only
     human-chosen labels).
  4. It's kept only if it isn't worse.
