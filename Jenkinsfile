#!/usr/bin/env groovy

// PR / branch validation for preset-io/sqlalchemy-drill.
//
// Scope is deliberately limited to checks that need no external services:
// the repo's pytest suite (test_sadrill.py, test_dbapi_compliance.py) boots an
// apache/drill testcontainer, which is not available to this agent pod, so it
// stays in GitHub Actions. Here we validate that the package installs and that
// every declared sqlalchemy.dialects entry point resolves to a real Dialect
// class -- the failure mode that breaks Superset at driver-discovery time.
//
// This pipeline intentionally publishes nothing: no sdist, no wheel, no
// registry upload, no git tag, no credentials.

properties([
    [$class: 'BuildDiscarderProperty',
     strategy: [$class: 'LogRotator', numToKeepStr: '20']],
])

podTemplate(
    imagePullSecrets: ['preset-pull'],
    nodeUsageMode: 'NORMAL',
    containers: [
        containerTemplate(
            alwaysPullImage: true,
            name: 'py-ci',
            image: 'preset/python:3.11.14-2026-05-22-ci',
            ttyEnabled: true,
            command: 'cat',
            resourceRequestCpu: '500m',
            resourceLimitCpu: '2000m',
            resourceRequestMemory: '1000Mi',
            resourceLimitMemory: '2000Mi',
        ),
    ]
) {
    node(POD_LABEL) {
        container('py-ci') {
            stage('Checkout') {
                checkout scm
            }

            stage('Install System Dependencies') {
                // pyodbc (and therefore the drill.odbc dialect) needs the
                // unixODBC runtime to be importable.
                sh(
                    script: 'apt-get update && apt-get install -y --no-install-recommends unixodbc',
                    label: 'unixODBC runtime',
                )
            }

            stage('Install') {
                sh(script: 'python -m pip install --upgrade pip', label: 'Upgrade pip')
                sh(
                    script: 'pip install -e . -r requirements/common.txt',
                    label: 'Install sqlalchemy_drill and driver dependencies',
                )
            }

            stage('Checks') {
                parallel(
                    compile: {
                        sh(
                            script: 'python -m compileall -q sqlalchemy_drill',
                            label: 'Byte-compile sources',
                        )
                    },
                    dialects: {
                        sh(
                            script: '''#!/usr/bin/env bash
set -eo pipefail
python - <<'PY'
from sqlalchemy.dialects import registry
from sqlalchemy.engine.default import DefaultDialect

EXPECTED = ["drill", "drill.sadrill", "drill.jdbc", "drill.odbc"]
failures = []
for name in EXPECTED:
    try:
        dialect = registry.load(name)
    except Exception as exc:
        failures.append(f"{name}: {type(exc).__name__}: {exc}")
        continue
    if not (isinstance(dialect, type) and issubclass(dialect, DefaultDialect)):
        failures.append(f"{name}: resolved to {dialect!r}, not a Dialect class")
        continue
    print(f"OK   {name} -> {dialect.__module__}.{dialect.__name__}")

if failures:
    for line in failures:
        print(f"FAIL {line}")
    raise SystemExit("sqlalchemy.dialects entry points are broken")
print("All sqlalchemy.dialects entry points resolve to Dialect classes")
PY
''',
                            label: 'sqlalchemy.dialects entry points',
                        )
                    },
                )
            }
        }
    }
}
