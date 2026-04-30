# Pipeline Controls and Entry Points

## Execution Control

The pipeline fails closed by default. `RUN_PIPELINE` defaults to `false` if it is missing.

Set `RUN_PIPELINE=true` only for an approved manual run or approved cron schedule.

## OpenAI Cost Controls

- OpenAI calls exist only in `jobs/classifier.py`.
- OpenAI SDK retries are disabled with `max_retries=0`.
- Classification uses the lower of `CLASSIFICATION_BATCH_SIZE` and `OPENAI_MAX_RECORDS_PER_RUN`.
- All run-size caps must be `<= 200`.
- Before classification starts, `jobs/run_classification.py` estimates cost from `OPENAI_ESTIMATED_COST_PER_RECORD_USD`.
- The run is blocked if estimated cost exceeds `OPENAI_RUN_BUDGET_USD`.
- The run is blocked if estimated weekly spend would exceed `OPENAI_WEEKLY_BUDGET_USD`.
- Estimated weekly spend is tracked in `public.job_state` by ISO week.

## Backlog Controls

Historical/backlog classification is off by default.

By default, only unclassified posts inside `PROCESSING_WINDOW_DAYS` are eligible. To process older unclassified data, set `ALLOW_HISTORICAL_REPROCESSING=true` for that approved run only.

## Deduplication

- Raw posts are deduped by `posts(source, external_id)`.
- Classifications are deduped by `post_classifications(post_id)`.
- The classifier selects only posts without an existing classification row.

## Entrypoints

These commands can execute pipeline work and are guarded by `RUN_PIPELINE`:

- `python main.py`
- `python -m jobs.run_collection`
- `python -m jobs.run_classification`
- `python -m jobs.run_retention`
- `python -m jobs.weekly_report`
- `python -m scripts.test_collection`
- `python -m scripts.test_classification`
- `python -m scripts.test_retention`
- `python -m scripts.test_weekly_report`

The Render deployment entrypoint is `python main.py` in `render.yaml`, scheduled once every 24 hours by default.

There are no `while True` loops, daemon workers, web endpoints, queue consumers, or background schedulers in this repo.
