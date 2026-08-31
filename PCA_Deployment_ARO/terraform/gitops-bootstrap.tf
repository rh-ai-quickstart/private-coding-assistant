# ════════════════════════════════════════════════
# Phase 2: Bootstrap OpenShift GitOps (ArgoCD)
# ════════════════════════════════════════════════
# Installs the OpenShift GitOps operator and creates the
# root App-of-Apps that manages all subsequent resources.

resource "terraform_data" "semantic_router_guard" {
  input = {
    enabled = var.semantic_router_enabled
  }
  lifecycle {
    precondition {
      condition     = var.semantic_router_enabled != true || length(var.huggingface_token) > 0
      error_message = "semantic_router_enabled=true requires huggingface_token (MiniLM and local Qwen)."
    }
    precondition {
      condition = var.semantic_router_enabled != true || alltrue([
        for m in jsondecode(var.semantic_router_models_json) :
        try(lookup(nonsensitive(jsondecode(var.semantic_router_api_keys_json)), m.name, ""), "") != ""
      ])
      error_message = "each extra in semantic_router_models_json needs a matching name in semantic_router_api_keys_json when semantic_router_enabled=true."
    }
  }
}

resource "null_resource" "install_gitops_operator" {
  provisioner "local-exec" {
    command = <<-EOT
      set -e

      echo "Installing OpenShift GitOps operator..."
      cat <<'YAML' | oc apply -f -
      apiVersion: v1
      kind: Namespace
      metadata:
        name: openshift-gitops-operator
      ---
      apiVersion: operators.coreos.com/v1
      kind: OperatorGroup
      metadata:
        name: openshift-gitops-operator
        namespace: openshift-gitops-operator
      spec: {}
      ---
      apiVersion: operators.coreos.com/v1alpha1
      kind: Subscription
      metadata:
        name: openshift-gitops-operator
        namespace: openshift-gitops-operator
      spec:
        channel: gitops-1.15
        installPlanApproval: Automatic
        name: openshift-gitops-operator
        source: redhat-operators
        sourceNamespace: openshift-marketplace
      YAML

      echo "Waiting for GitOps operator to become available..."
      for i in $(seq 1 60); do
        if oc get deployment openshift-gitops-server -n openshift-gitops &>/dev/null; then
          echo "GitOps operator is installed."
          break
        fi
        echo "Waiting... ($i/60)"
        sleep 10
      done

      oc wait --for=condition=Available deployment/openshift-gitops-server \
        -n openshift-gitops --timeout=300s

      echo "Switching ArgoCD to annotation+label resource tracking..."
      # argocd-cm is templated by the GitOps operator from the ArgoCD CR, so it
      # must be set here, not by patching the ConfigMap directly (the operator
      # reconciles argocd-cm back to the CR's value on every pass).
      oc patch argocd openshift-gitops -n openshift-gitops --type merge \
        -p '{"spec":{"resourceTrackingMethod":"annotation+label"}}'

      echo "Granting ArgoCD cluster-admin permissions..."
      cat <<'YAML' | oc apply -f -
      apiVersion: rbac.authorization.k8s.io/v1
      kind: ClusterRoleBinding
      metadata:
        name: openshift-gitops-cluster-admin
      roleRef:
        apiGroup: rbac.authorization.k8s.io
        kind: ClusterRole
        name: cluster-admin
      subjects:
        - kind: ServiceAccount
          name: openshift-gitops-argocd-application-controller
          namespace: openshift-gitops
      YAML
    EOT
  }

  depends_on = [
    null_resource.gpu_machineset,
  ]
}

# ════════════════════════════════════════════════
# Root App-of-Apps
# ════════════════════════════════════════════════
resource "null_resource" "argocd_app_of_apps" {
  count = var.gitops_repo_url != "" ? 1 : 0

  provisioner "local-exec" {
    command = <<-EOT
      set -e

      echo "Creating ArgoCD App-of-Apps..."
      cat <<YAML | oc apply -f -
      apiVersion: argoproj.io/v1alpha1
      kind: Application
      metadata:
        name: pca-root
        namespace: openshift-gitops
        finalizers:
          - resources-finalizer.argocd.argoproj.io
      spec:
        project: default
        source:
          repoURL: ${var.gitops_repo_url}
          targetRevision: ${var.gitops_repo_revision}
          path: ${var.gitops_repo_path}
          helm:
            parameters:
              - name: gitops.repoURL
                value: ${var.gitops_repo_url}
              - name: gitops.targetRevision
                value: ${var.gitops_repo_revision}
              - name: gitops.basePath
                value: charts
              - name: gitops.cloud
                value: aro
              - name: hfToken.raw
                value: ${var.huggingface_token}
              - name: aiServing.modelVariant
                value: ${var.model_variant}
              - name: devSpaces.modelVariant
                value: ${var.model_variant}
              - name: aiServing.semanticRouterModelsJson
                value: ${jsonencode(var.semantic_router_models_json)}
                forceString: true
              - name: aiServing.semanticRouterApiKeysJson
                value: ${jsonencode(var.semantic_router_api_keys_json)}
                forceString: true
%{ if var.semantic_router_enabled != null ~}
              - name: aiServing.semanticRouterEnabled
                value: "${var.semantic_router_enabled}"
%{ endif ~}
        destination:
          server: https://kubernetes.default.svc
          namespace: openshift-gitops
        syncPolicy:
          automated:
            prune: true
            selfHeal: true
          syncOptions:
            - CreateNamespace=true
            - ServerSideApply=true
            - RespectIgnoreDifferences=true
      YAML

      echo "ArgoCD App-of-Apps created successfully."
    EOT
  }

  depends_on = [null_resource.install_gitops_operator]
}
