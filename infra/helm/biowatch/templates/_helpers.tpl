{{- define "biowatch.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "biowatch.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "biowatch.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "biowatch.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}

{{- define "biowatch.componentLabels" -}}
{{ include "biowatch.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "biowatch.selectorLabels" -}}
app.kubernetes.io/name: {{ include "biowatch.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "biowatch.configName" -}}
{{ include "biowatch.fullname" . }}-config
{{- end -}}

{{- define "biowatch.secretName" -}}
{{- if .Values.secret.create -}}
{{ include "biowatch.fullname" . }}-secret
{{- else -}}
{{ .Values.secret.existingSecret }}
{{- end -}}
{{- end -}}

{{- define "biowatch.serviceAccountName" -}}
{{- printf "%s-%s" (include "biowatch.fullname" .root) .component -}}
{{- end -}}

{{- define "biowatch.appEnv" -}}
- name: BIOWATCH_APP_NAME
  value: BioWatch
- name: BIOWATCH_ENVIRONMENT
  value: {{ .Values.app.environment | quote }}
- name: BIOWATCH_REDIS_URL
  value: {{ printf "redis://%s-redis:6379/0" (include "biowatch.fullname" .) | quote }}
- name: BIOWATCH_ELASTICSEARCH_URL
  value: {{ printf "http://%s-elasticsearch:9200" (include "biowatch.fullname" .) | quote }}
- name: BIOWATCH_ELASTICSEARCH_INDEX
  value: {{ .Values.app.elasticsearchIndex | quote }}
- name: BIOWATCH_ELASTICSEARCH_TIMEOUT_SECONDS
  value: {{ .Values.app.elasticsearchTimeoutSeconds | quote }}
- name: BIOWATCH_EUROPE_PMC_TIMEOUT_SECONDS
  value: {{ .Values.app.europePmcTimeoutSeconds | quote }}
- name: BIOWATCH_EUROPE_PMC_MAX_ATTEMPTS
  value: {{ .Values.app.europePmcMaxAttempts | quote }}
- name: BIOWATCH_EUROPE_PMC_RETRY_BACKOFF_SECONDS
  value: {{ .Values.app.europePmcRetryBackoffSeconds | quote }}
- name: BIOWATCH_LLM_PROVIDER
  value: {{ .Values.app.llmProvider | quote }}
- name: BIOWATCH_LLM_MODEL
  value: {{ .Values.app.llmModel | quote }}
- name: BIOWATCH_LLM_TIMEOUT_SECONDS
  value: {{ .Values.app.llmTimeoutSeconds | quote }}
- name: BIOWATCH_SUMMARY_PROMPT_VERSION
  value: {{ .Values.app.summaryPromptVersion | quote }}
- name: BIOWATCH_SUMMARY_WAIT_TIMEOUT_SECONDS
  value: {{ .Values.app.summaryWaitTimeoutSeconds | quote }}
- name: BIOWATCH_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "biowatch.secretName" . }}
      key: BIOWATCH_DATABASE_URL
{{- end -}}

{{- define "biowatch.llmApiKeyEnv" -}}
- name: BIOWATCH_LLM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "biowatch.secretName" . }}
      key: BIOWATCH_LLM_API_KEY
      optional: true
{{- end -}}

{{- define "biowatch.telegramTokenEnv" -}}
- name: BIOWATCH_TELEGRAM_BOT_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "biowatch.secretName" . }}
      key: BIOWATCH_TELEGRAM_BOT_TOKEN
      optional: true
{{- end -}}

{{- define "biowatch.waitForPostgres" -}}
python - <<'PY'
import socket
import time

deadline = time.time() + 120
while time.time() < deadline:
    try:
        with socket.create_connection(("{{ include "biowatch.fullname" . }}-postgres", 5432), timeout=3):
            raise SystemExit(0)
    except OSError:
        time.sleep(2)
raise SystemExit("postgres is not reachable")
PY
{{- end -}}
