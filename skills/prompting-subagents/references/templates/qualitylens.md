# Template: qualitylens dispatch

For one bounded measurement request from a persona reviewer or review-circus. qualitylens works through the `signals_code_churn`, `signals_change_coupling` and `signals_code_hotspots` tools and transcribes their output; its contract lives in the qualitylens agent file. The dispatch carries no command and no path to a script.

**Ten-second checklist:** the target is the changed files or one directory, not the repository root · the history window is explicit (`since`, `max-commits`, or `baseline-ref`) and fits the repository's age · broader context (hotspots) is asked for only when it changes a finding.

```text
<objective>Measure <target> with the `signals_*` tools and report the values.</objective>
<context>
Target: <paths>
History window: <since=DATE | max-commits=N | all-history | baseline-ref=REF>
<Include hotspots: yes, only when broader context is needed.>
</context>
```

Slots: target · history window · hotspots flag.
