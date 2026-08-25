{{/*
  Bash body for a Job that POSTs/PUTs a kubernetes.io/tls Secret.
  Keep in sync with pca-ai-serving.upsertTlsSecretScript.
  Caller: dict namespace secretName cn san (SAN already includes DNS: prefixes).
*/}}
{{- define "pca-platform-config.upsertTlsSecretScript" -}}
set -e
SECRET_NAME="{{ .secretName }}"
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /tmp/tls.key -out /tmp/tls.crt \
  -subj "/CN={{ .cn }}" \
  -addext "subjectAltName={{ .san }}"

cat <<EOF > /tmp/secret.json
{
  "apiVersion": "v1",
  "kind": "Secret",
  "metadata": {
    "name": "${SECRET_NAME}",
    "namespace": "{{ .namespace }}"
  },
  "type": "kubernetes.io/tls",
  "data": {
    "tls.crt": "$(base64 -w0 /tmp/tls.crt)",
    "tls.key": "$(base64 -w0 /tmp/tls.key)"
  }
}
EOF

TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
CACERT=/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
APISERVER=https://kubernetes.default.svc

curl -sf -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --cacert ${CACERT} \
  "${APISERVER}/api/v1/namespaces/{{ .namespace }}/secrets" \
  -d @/tmp/secret.json || \
curl -sf -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --cacert ${CACERT} \
  "${APISERVER}/api/v1/namespaces/{{ .namespace }}/secrets/${SECRET_NAME}" \
  -d @/tmp/secret.json

echo "TLS secret ${SECRET_NAME} created/updated successfully"
{{- end -}}
