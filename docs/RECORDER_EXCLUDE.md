# Recorder configuration

Skywatch's array-bearing sensors (the ones that surface a `sightings`,
`recent_overhead`, `movements`, etc. attribute) carry ~5-15 KB payloads
on a busy day. By default the HA recorder serializes every state change
to its history DB — keeping these in history bloats the DB and triggers
"attribute size exceeds threshold" warnings in the log.

Add this to `configuration.yaml`:

```yaml
recorder:
  exclude:
    entities:
      - sensor.skywatch_log_recent
      - sensor.skywatch_log_search
      - sensor.skywatch_log_overhead
      - sensor.skywatch_military_sightings
      - sensor.skywatch_movements_today
      - sensor.skywatch_log_hour_histogram
```

All excluded sensors are marked `EntityCategory.DIAGNOSTIC` so they
don't appear in the user-facing tile picker — recorder-excluding them
loses no everyday-visible state.

The scalar sensors (`sensor.skywatch_log_today`, `_this_week`,
`_log_stats`, the watch sensors) are not excluded — they're small
enough that recorder-history bloat isn't a concern, and they're
genuinely useful in history graphs.
