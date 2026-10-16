# OpenCode feasibility & security verification harness

Disposable verification harness for the Architecture Assistant OpenCode
integration. It is **not** part of the application: nothing here is imported by
`api/` or `web/`, it connects to no application endpoint, and it never touches
the developer's live OpenCode service, database, or credentials.

Purpose: prove or disprove the OpenCode assumptions the approved plan depends on
before any gateway, persistence, or UI work starts.

## Layout

```
runtime/
  profile/opencode.json                      restricted OpenCode profile (shipped candidate)
  profile/.opencode/plugins/verify/index.ts  test-only plugin: harmless tools + scope hook
  mock_provider.py                           scripted OpenAI-compatible model provider
  harness.py                                 isolated server/mock lifecycle + API helpers
tests/
  conftest.py                                fixtures (isolated servers, mock provider)
  test_opencode_feasibility.py               21 focused verification tests
compose/
  Dockerfile, compose.verify.yml, verify.sh  private-network (no host port) proof
artifacts/
  pytest.txt, compose-proof.txt, versions.txt  captured evidence
VERIFICATION_REPORT.md                       findings, answers, classification
```

## How isolation is achieved

* The OpenCode server runs with `XDG_CONFIG_HOME`, `XDG_DATA_HOME`,
  `XDG_CACHE_HOME` and `XDG_STATE_HOME` all pointed inside a scratch directory,
  so it has its own database, its own config, and no access to the developer's
  OpenCode state.
* The only OpenCode configuration is the shipped restricted profile plus the
  verification plugin, copied into a scratch sandbox directory that contains
  nothing else (no repository, no references, no instructions files).
* The model provider is a local scripted mock
  (`runtime/mock_provider.py`) reached over `http://127.0.0.1:4700/v1`. No real
  provider, credential, network egress, or cost is involved, and every
  tool-call experiment is deterministic.
* The plugin's tools are harmless (`get_test_context`, `echo_bounded_value`,
  `get_test_context_second`). No approve/apply/undo, database, architecture
  helper, shell, or filesystem tool is exposed or called.

## Running

```sh
# focused verification tests (~40 s, 21 tests)
/home/sedu/architect/api/.venv/bin/python -m pytest \
  verification/opencode-assistant-feasibility/tests -v

# private-network / no-host-port proof (~1-2 min incl. image build)
bash verification/opencode-assistant-feasibility/compose/verify.sh
```

The tests are intentionally outside `api/tests`, so the application suite
(`api/pyproject.toml` `testpaths = ["tests"]`) is unaffected.

## Notes

* Ports used: mock provider `4700`, verification servers `4701`-`4713`.
* Scratch state lives under `/tmp/opencode/archverify*` and can be deleted at any
  time; `ARCHVERIFY_SCRATCH` overrides the location.
* The harness writes its journals (`.verify-hook-log.jsonl`,
  `.verify-tool-log.jsonl`, `.verify-scopes.json`) inside the scratch sandbox
  only.
