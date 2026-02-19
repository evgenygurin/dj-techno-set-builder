# Codex ↔ Codegen через FastMCP 3.x + Linear + GitHub + @mansion

**Документ:** Final Implementation Plan (full)  
**Дата:** 2026-02-17  
**Связан design:** `docs/plans/2026-02-17-codex-codegen-fastmcp-mansion-design.md`

## 0. Цель плана

Довести систему до production-ready состояния, где:

- Codex стабильно управляет большими задачами end-to-end.
- Codegen исполняет подзадачи в отдельных ветках с PR.
- Linear/GitHub/@mansion синхронизированы и наблюдаемы.
- Нет silent stop при сбоях.

План разбит на фазы с четкими **exit criteria**, контрольными метриками и rollback-стратегией.

---

## 1. Scope и non-scope

## 1.1 In scope

- FastMCP 3.x orchestration server (manager layer).
- Интеграционные адаптеры: Codegen, Linear, GitHub, @mansion.
- Workflow state machine + watchdog + escalation.
- PR review loop и decision protocol.
- Observability + SLO + runbooks.

## 1.2 Out of scope (v1)

- Полная замена существующих ручных процессов во всех командах.
- Multi-repo dependency graph orchestration.
- Self-healing мердж-конфликтов без участия manager.

---

## 2. Program milestones

- **M1 (Foundation):** есть рабочий happy-path intake → issue → codegen run → PR.
- **M2 (Resilience):** watchdog+SLA, нет silent stop, есть recovery.
- **M3 (Control):** codex review + decision loop + partial done policy.
- **M4 (Hardening):** authz/visibility/rate-limit/observability/runbooks.
- **M5 (Production):** pilot success + full rollout + SLO pass.

---

## 3. Work breakdown structure (WBS)

## Phase 0 — Architecture freeze & readiness (P0, 2-3 days)

### Цель

Зафиксировать API/схемы/состояния/пороги до coding.

### Tasks

1. Утвердить schema `WorkflowRun`, `WorkOrder`, `DecisionLogEntry`, `MansionEnvelope`.
2. Утвердить state machine и transition guards.
3. Утвердить SLA: heartbeat, stale thresholds, retry limits.
4. Утвердить naming conventions (Linear issues, branch naming, labels).
5. Freeze source compatibility matrix (Codegen API, FastMCP 3.x).

### Deliverables

- Architecture decision record (ADR-001..ADR-00N).
- JSON schemas в `docs/contracts/`.
- Transition table в `docs/ops/workflow-fsm.md`.

### Exit criteria

- Все ADR approved.
- Нет open critical вопросов по контрактам.

---

## Phase 1 — Orchestration core in FastMCP (P0, 1 week)

### Цель

Поднять ядро workflow orchestration без полного integration behavior.

### Tasks

1. Создать новый orchestration package:
   - `app/mcp/orchestrator/server.py`
   - `app/mcp/orchestrator/state_machine.py`
   - `app/mcp/orchestrator/types.py`
   - `app/mcp/orchestrator/store.py`
2. Реализовать базовые tools:
   - `workflow.start`
   - `workflow.get`
   - `workflow.advance`
3. Ввести persistence layer (Redis/SQLite abstraction).
4. Реализовать idempotency ledger (`idempotency_key` replay guard).
5. Подключить middleware chain (error, logging, idempotency, auth placeholder).

### Tests

- Unit tests FSM transitions (valid + invalid).
- Unit tests idempotency replay.
- Contract tests response schema for core tools.

### Exit criteria

- Core tools проходят тесты.
- Workflow journal записывается на каждый transition.

---

## Phase 2 — External adapters (Codegen/Linear/GitHub/@mansion) (P0-P1, 1-1.5 weeks)

### Цель

Сделать надежные адаптеры с retry/backoff/timeouts.

### Tasks

1. `adapters/codegen.py`
   - run/get/list/resume/logs wrappers
   - status normalization layer
   - rate-limit aware retry
2. `adapters/linear.py`
   - create/update/comment/search wrappers
   - decision log append helper
3. `adapters/github.py`
   - branch/pr/status/checks/comment/merge wrappers
4. `adapters/mansion.py`
   - post/poll/ack/create_room wrappers
   - dedup and ack helper
5. Общий resilience utility:
   - retry policy classes
   - circuit breaker
   - transient error classifier

### Tests

- Adapter contract tests с mock HTTP.
- Backoff and timeout tests.
- Normalization tests for Codegen statuses.

### Exit criteria

- Все adapters дают deterministic typed response.
- Retry и timeout policy покрыты тестами.

---

## Phase 3 — Mansion protocol + watchdog (P1, 1 week)

### Цель

Внедрить no-silence control plane.

### Tasks

1. Реализовать Mansion envelope validation.
2. Реализовать ACK required logic + ack timeout monitor.
3. Реализовать watchdog scheduler:
   - heartbeat tracking
   - stale detection
   - escalation ladder
4. Реализовать `watchdog.tick` и `watchdog.escalate` tools.
5. Реализовать incident recording в Linear.

### Tests

- Simulated missing heartbeat.
- Duplicate event replay.
- Missed ACK retry and escalation.

### Exit criteria

- Сценарий stale→escalate→resume отрабатывает автоматически.
- Нет немаркированных зависаний в integration test.

---

## Phase 4 — Planning & decomposition automation (P1, 1 week)

### Цель

Codex автоматически превращает большую задачу в качественные Linear issues.

### Tasks

1. Реализовать decomposition engine (issue slicing).
2. Реализовать issue template generator:
   - context
   - in/out of scope
   - ordered plan
   - AC checklist
   - risks/deps
3. Реализовать epic + child issues creation flow.
4. Реализовать labels/priorities/estimates mapping.
5. Реализовать `WORKFLOW_START` и `WORK_ORDER` emission.

### Tests

- Snapshot tests issue templates.
- Schema validation for generated AC.
- End-to-end intake→Linear creation flow.

### Exit criteria

- Для входного крупного запроса создаются валидные epic + sub-issues.
- Каждая sub-issue готова к dispatch без ручной правки (или с минимальной).

---

## Phase 5 — Codegen dispatch + PR loop (P1, 1 week)

### Цель

Связать dispatch с реальным выполнением в Codegen и PR lifecycle.

### Tasks

1. Реализовать WorkOrder→Codegen create run mapping.
2. Привязать `workflow_run_id`, `linear_issue_id`, `idempotency_key` в metadata.
3. Реализовать PR discovery + checks tracking.
4. Реализовать авто-комменты в Linear при:
   - PR opened
   - ready for review
   - blocked
   - partial done
5. Реализовать polling fallback при event silence.

### Tests

- E2E mock: run created -> status running -> PR detected -> review state.
- Fallback poll test when no mansion events.

### Exit criteria

- Happy-path intake→run→PR→review state полностью рабочий.
- Все ключевые события дублируются в Linear.

---

## Phase 6 — Codex review engine + decision loop (P1-P2, 1 week)

### Цель

Сделать формализованный review/decision процесс manager-агента.

### Tasks

1. Review checklist implementation (architecture/correctness/tests/security/AC).
2. Decision taxonomy implementation:
   - approve
   - request changes
   - iterate
   - split
   - accept partial
   - escalate
3. Реализовать sync outputs:
   - PR comments
   - mansion DECISION
   - Linear status/comment
4. Реализовать partial-done flow:
   - остаток scope в follow-up issues
   - cross-linking в Linear

### Tests

- Rule-based tests для decision selection.
- Partial-done regression tests.

### Exit criteria

- Любой review outcome приводит к явному decision и next action.
- Partial done поддерживается без ручного восстановления контекста.

---

## Phase 7 — Security & policy hardening (P2, 0.5-1 week)

### Цель

Закрыть security gaps и разделить полномочия.

### Tasks

1. Перевести runtime на HTTP transport для полноценного auth (если еще STDIO).
2. Ввести scope-based auth checks:
   - manager scopes
   - implementer scopes
   - observer scopes
3. Ввести component visibility profiles:
   - normal
   - incident
   - manual-limited
4. Настроить secret management + redaction в logs.
5. Настроить command safety rules (`prefix_rule`) для manager-side execution.

### Tests

- Authz matrix tests (who can call what).
- Visibility switching tests.
- Secret leakage checks in logs.

### Exit criteria

- Нет privilege escalation paths в integration test.
- Incident mode переключается без redeploy.

---

## Phase 8 — Observability & SLO rollout (P2, 0.5-1 week)

### Цель

Сделать систему измеримой и операционно прозрачной.

### Tasks

1. Внедрить correlation id во все adapters/events.
2. Внедрить structured logs + trace spans.
3. Опубликовать metrics:
   - workflow_success_rate
   - ack_latency
   - stale_incidents
   - mttr
4. Настроить dashboards + alerting.
5. Описать runbooks и on-call playbooks.

### Tests

- Telemetry completeness tests.
- Alert fire drills (synthetic stale, synthetic API outage).

### Exit criteria

- Все SLI отображаются в dashboards.
- Alerting и runbooks верифицированы drill’ами.

---

## Phase 9 — Pilot (P2, 1-2 weeks)

### Цель

Проверить систему на реальных задачах ограниченного объема.

### Pilot setup

- 1 команда.
- 2-3 репозитория.
- Только P1/P2 задачи (без критичного прод-влияния).

### Tasks

1. Запустить 20-30 workflow runs.
2. Собирать metrics + qualitative feedback.
3. Выявить top failure modes.
4. Отработать recovery playbooks на реальных инцидентах.
5. Выпустить hardening patchset.

### Exit criteria

- Нет нерешенных P0/P1 инцидентов.
- SLO выполняются минимум 7 дней подряд.

---

## Phase 10 — Production rollout (P2-P3, 1 week)

### Цель

Расширить контур до целевой нагрузки.

### Tasks

1. Progressive rollout по командам.
2. Enable required MCP servers policy.
3. Включить stricter alert thresholds.
4. Настроить governance (change management / rollback authority).
5. Провести post-launch review.

### Exit criteria

- Workflow success rate в целевом диапазоне.
- MTTR в целевом диапазоне.
- Нет unmanaged incidents.

---

## 4. Backlog template (Linear)

## 4.1 Epics

- `EPIC-ORCH-01`: Workflow core + state machine
- `EPIC-ORCH-02`: Adapters + resilience
- `EPIC-ORCH-03`: Mansion protocol + watchdog
- `EPIC-ORCH-04`: Planning/decomposition
- `EPIC-ORCH-05`: Dispatch + PR loop
- `EPIC-ORCH-06`: Review + decisions
- `EPIC-ORCH-07`: Security + visibility + auth
- `EPIC-ORCH-08`: Observability + SLO
- `EPIC-ORCH-09`: Pilot + production rollout

## 4.2 Issue naming convention

`[ORCH] <phase>.<workstream> <short action>`

Примеры:

- `[ORCH] 2.1 Implement Codegen adapter with retries`
- `[ORCH] 3.2 Add watchdog stale detection`
- `[ORCH] 6.3 Sync decision output to PR + Linear + mansion`

## 4.3 Required issue sections

- Context
- Scope in/out
- Plan (ordered)
- Acceptance criteria (checkboxes)
- Risks/dependencies
- Testing notes
- Rollback notes

---

## 5. Target timelines (realistic baseline)

- Phase 0: 0.5 week
- Phase 1: 1 week
- Phase 2: 1-1.5 week
- Phase 3: 1 week
- Phase 4: 1 week
- Phase 5: 1 week
- Phase 6: 1 week
- Phase 7: 0.5-1 week
- Phase 8: 0.5-1 week
- Phase 9: 1-2 week
- Phase 10: 1 week

**Итого:** ~9-11 недель до уверенного production уровня.

---

## 6. Quality gates (mandatory)

## Gate A (after Phase 2)

- All adapters stable under retry simulation.
- Contract tests green.

## Gate B (after Phase 3)

- No-silence guarantee verified by chaos tests.
- Stale recovery works automatically.

## Gate C (after Phase 6)

- Review loop deterministic.
- Partial done flow validated.

## Gate D (after Phase 8)

- SLI/SLO dashboards live.
- Runbooks validated.

## Gate E (post pilot)

- Pilot SLO pass + no critical unresolved incidents.

---

## 7. Risk register

1. **Codegen API schema drift** (особенно logs alpha endpoint).
   - Mitigation: adapter versioning + tolerant parsing + feature flags.
2. **Event loss in mansion**.
   - Mitigation: idempotent replay + dual poll verification.
3. **Rate-limit bursts (Codegen/GitHub/Linear).**
   - Mitigation: token bucket + queue + backoff + jitter.
4. **State divergence между systems.**
   - Mitigation: reconciliation job + conflict markers + decision log.
5. **Privilege misconfiguration.**
   - Mitigation: scope tests + deny-by-default profiles.
6. **Operational overload at rollout.**
   - Mitigation: progressive rollout + capped concurrency.

---

## 8. Rollback strategy

1. **Soft rollback:** отключить dispatch tools visibility, оставить monitor/review/read-only.
2. **Partial rollback:** вернуть только manual dispatch, сохранить watchdog/observability.
3. **Hard rollback:** остановить auto orchestration, продолжить фиксацию решений в Linear.

В каждом rollback варианте запрещено терять decision log и workflow journal.

---

## 9. KPIs и success criteria

## 9.1 Operational KPIs

- `workflow_success_rate >= 90%` на пилоте, `>=95%` в проде.
- `mean_time_to_recovery < 20 min`.
- `stale_incidents_per_100_runs < 5`.
- `critical_unmanaged_incidents = 0`.

## 9.2 Delivery KPIs

- Снижение lead time задачи до merged PR.
- Доля задач с корректным AC closure.
- Доля partial done с follow-up closure в SLA.

---

## 10. Implementation checklist (short, executable)

1. Freeze schemas and thresholds.
2. Build orchestration core.
3. Add adapters with resilience.
4. Implement mansion protocol + watchdog.
5. Implement decomposition to Linear.
6. Implement Codegen dispatch + PR loop.
7. Implement review + decision sync.
8. Harden auth/visibility/security.
9. Wire full telemetry and alerting.
10. Run pilot and roll out gradually.

---

## 11. Primary sources used

### Codegen

- [https://docs.codegen.com/llms-full.txt](https://docs.codegen.com/llms-full.txt)
- [https://github.com/codegen-sh/codegen/tree/develop/docs](https://github.com/codegen-sh/codegen/tree/develop/docs)
- [https://github.com/codegen-sh/codegen/tree/develop/src/codegen](https://github.com/codegen-sh/codegen/tree/develop/src/codegen)

### FastMCP

- [https://gofastmcp.com/llms-full.txt](https://gofastmcp.com/llms-full.txt)
- [https://github.com/jlowin/fastmcp/tree/main/docs](https://github.com/jlowin/fastmcp/tree/main/docs)
- [https://github.com/jlowin/fastmcp/tree/main/examples](https://github.com/jlowin/fastmcp/tree/main/examples)
- [https://github.com/jlowin/fastmcp/tree/main/skills/fastmcp-client-cli](https://github.com/jlowin/fastmcp/tree/main/skills/fastmcp-client-cli)

### OpenAI Codex docs

- [https://developers.openai.com/codex/skills.md](https://developers.openai.com/codex/skills.md)
- [https://developers.openai.com/codex/guides/agents-md.md](https://developers.openai.com/codex/guides/agents-md.md)
- [https://developers.openai.com/codex/mcp.md](https://developers.openai.com/codex/mcp.md)
- [https://developers.openai.com/codex/rules.md](https://developers.openai.com/codex/rules.md)
- [https://developers.openai.com/codex/guides/agents-sdk.md](https://developers.openai.com/codex/guides/agents-sdk.md)
- [https://developers.openai.com/codex/app-server.md](https://developers.openai.com/codex/app-server.md)

