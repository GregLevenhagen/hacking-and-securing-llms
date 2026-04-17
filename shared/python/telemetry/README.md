# OpenTelemetry Instrumentation Pipeline

Vendor-neutral tracing for the Hacking and Securing LLMs demo suite using **only standard OpenTelemetry APIs** and the OTLP exporter.

## How It Works

1. **`init_telemetry()`** — Called once at startup. Reads standard OTel env vars and configures a `TracerProvider` with `BatchSpanProcessor`.
2. **Auto-instrumentation** — `opentelemetry-instrumentation-openai-v2` automatically traces all OpenAI SDK calls (including Ollama and Azure OpenAI), adding `gen_ai.*` semantic convention attributes.
3. **`@trace_demo()`** — Decorator adds demo-specific span attributes (`demo.name`, `demo.id`, `demo.category`).
4. **`flush_telemetry()`** — Must be called before process exit in short-lived scripts to export buffered spans.

## Dependencies (Zero Vendor Lock-In)

Only standard OpenTelemetry packages are used:
- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp-proto-http`
- `opentelemetry-instrumentation-openai-v2`
- `opentelemetry-semantic-conventions`

No vendor-specific SDKs (no `langfuse`, `datadog`, `arize` packages).

## Configuration via Standard OTel Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `false` | Set to `true` to enable telemetry |
| `OTEL_SERVICE_NAME` | `securing-llms` | Service name in traces |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(none)* | OTLP endpoint URL |
| `OTEL_EXPORTER_OTLP_HEADERS` | *(none)* | Comma-separated `key=value` pairs |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | `http/protobuf` or `http/json` |

When `OTEL_ENABLED=true` but no endpoint is set, traces are printed to the console via `ConsoleSpanExporter`.

## Example Backend Configurations

### LangFuse Cloud
```env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64(public_key:secret_key)>
```

### LangFuse Self-Hosted
```env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:3000/api/public/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64(public_key:secret_key)>
```

### Jaeger (local)
```env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

### Grafana Tempo
```env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

### Arize Phoenix
```env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006
OTEL_EXPORTER_OTLP_HEADERS=api_key=<your-key>
```

### Generic OTel Collector
```env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

## Auto-Captured gen_ai.* Attributes

The OpenAI auto-instrumentation captures:
- `gen_ai.system` — Provider name (e.g., "openai")
- `gen_ai.request.model` — Model name
- `gen_ai.request.temperature` — Sampling temperature
- `gen_ai.request.max_tokens` — Max tokens
- `gen_ai.response.model` — Actual model used
- `gen_ai.usage.prompt_tokens` — Input tokens
- `gen_ai.usage.completion_tokens` — Output tokens

## Verifying Traces Are Flowing

1. Set `OTEL_ENABLED=true` and configure your backend
2. Run any demo (e.g., `make demo-01`)
3. Check your backend dashboard for traces with `service.name=securing-llms`
4. Each demo span will have `demo.name` and `demo.id` attributes

For quick local verification without a backend:
```bash
OTEL_ENABLED=true python -m demo_01_direct_prompt_injection.python.app_terminal
```
Spans will print to the console.
